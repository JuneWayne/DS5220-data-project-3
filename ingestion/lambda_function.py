import json
import logging
import datetime
import time
import random
import re
import boto3
import requests
from bs4 import BeautifulSoup, Comment
import pandas as pd
from collections import Counter
from decimal import Decimal

# importing custom parser from another script
from job_parser import parse_job_postings

# AWS logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Rotate user agents to reduce detection
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
]

def get_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

def request_with_retry(url, max_retries=3, base_delay=5):
    for attempt in range(max_retries):
        try:
            headers = get_headers()
            response = requests.get(url, headers=headers, timeout=30)
            if response.status_code == 200:
                return response
            elif response.status_code == 429:
                delay = base_delay * (2 ** attempt) + random.uniform(1, 5)
                logger.warning(f"Rate limited (429), waiting {delay:.1f}s before retry...")
                time.sleep(delay)
            else:
                logger.warning(f"Got status {response.status_code} for {url}")
                return None
        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError) as e:
            delay = base_delay * (2 ** attempt) + random.uniform(1, 3)
            logger.warning(f"Request failed ({type(e).__name__}), retry {attempt+1}/{max_retries} after {delay:.1f}s")
            time.sleep(delay)
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return None
    logger.error(f"Failed after {max_retries} retries: {url}")
    return None

def get_num_applicants(detail_soup):
    tag = detail_soup.find(class_="num-applicants__caption")
    if tag:
        return tag.get_text(strip=True)
    return None

def extract_application_link(job_soup, job_id):
    code = job_soup.find("code", id="applyUrl")
    if code:
        comment = code.find(string=lambda s: isinstance(s, Comment))
        if comment:
            url = comment.strip().strip('"')
            if url:
                return url
    apply_anchor = job_soup.select_one("a.apply-button[href]")
    if apply_anchor and apply_anchor.get("href"):
        return apply_anchor["href"]
    apply_anchor = job_soup.find("a", attrs={"data-tracking-control-name": re.compile("apply-link")})
    if apply_anchor and apply_anchor.get("href"):
        return apply_anchor["href"]
    easy_button = job_soup.select_one("button.apply-button")
    if easy_button:
        return f"https://www.linkedin.com/jobs/view/{job_id}"
    return None

def scrape_linkedin(keywords, location, geo_id, f_tpr="r86400", max_results=50):
    base_url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    job_list = []
    seen_ids = set() # Handles deduplication for this hourly run
    start = 0

    while True:
        params = {"keywords": keywords, "location": location, "geoId": geo_id, "f_TPR": f_tpr, "start": start}
        url = f"{base_url}?keywords={params['keywords']}&location={params['location']}&geoId={params['geoId']}&f_TPR={params['f_TPR']}&start={params['start']}"
        response = request_with_retry(url, max_retries=3, base_delay=5)
        
        if response is None:
            logger.warning(f"Failed to fetch page at start={start}, skipping...")
            start += 25
            time.sleep(5)
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        page_jobs = soup.find_all("li")
        logger.info(f"start={start}, jobs_on_page={len(page_jobs)}")

        if not page_jobs:
            break

        id_list = []
        for job in page_jobs:
            base_card_div = job.find("div", {"class": "base-card"})
            if base_card_div and base_card_div.get("data-entity-urn"):
                job_id = base_card_div.get("data-entity-urn").split(":")[-1]
                if job_id not in seen_ids:
                    seen_ids.add(job_id)
                    id_list.append(job_id)

        time.sleep(random.uniform(3, 6))

        for job_id in id_list:
            detail_url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
            detail_response = request_with_retry(detail_url, max_retries=3, base_delay=3)

            if detail_response is None:
                continue

            detail_soup = BeautifulSoup(detail_response.text, "html.parser")
            job_post = {"job_id": job_id}

            def safe_text(selector, attrs=None):
                if attrs is None: attrs = {}
                tag = detail_soup.find(selector, attrs)
                return tag.get_text(strip=True) if tag else None

            job_post["job_title"] = safe_text("h2", {"class": "top-card-layout__title"})
            job_post["company_name"] = safe_text("a", {"class": "topcard__org-name-link"})
            job_post["location"] = safe_text("span", {"class": "topcard__flavor topcard__flavor--bullet"})
            job_post["time_posted"] = safe_text("span", {"class": "posted-time-ago__text"})
            job_post["num_applicants"] = get_num_applicants(detail_soup)

            desc_div = detail_soup.find("div", {"class": "decorated-job-posting__details"})
            job_post["job_description"] = desc_div.get_text(strip=True) if desc_div else None
            job_post["application_link"] = extract_application_link(detail_soup, job_id)

            job_list.append(job_post)
            time.sleep(random.uniform(1, 2))

            if len(job_list) >= max_results:
                logger.info("Hit max_results cap.")
                break

        if len(job_list) >= max_results:
            break
        start += 25

    df = pd.DataFrame(job_list)
    if not df.empty and "job_title" in df.columns:
        df = df.dropna(subset=["job_title"])
    return df

# aws lambda function entry point
def lambda_handler(event, context):
    logger.info("Lambda triggered, Starting job market ingestion.")
    
    try:
        # scrape a maximum of 200 jobs to avoid lambda timeout
        df_jobs = scrape_linkedin(
            keywords="Data intern",
            location="United States",
            geo_id="103644278",
            f_tpr="r86400", 
            max_results=200 
        )

        if df_jobs.empty:
            logger.warning("No jobs found this cycle.")
            return {"statusCode": 200, "body": json.dumps("No jobs found.")}

        # extract structured info from raw job description using custom parser
        enriched_jobs = df_jobs.apply(parse_job_postings, axis=1, result_type="expand")
        df_final = pd.DataFrame(enriched_jobs)
        
        industry_breakdown = {}
        
        # fallback in case parser misses the industry column
        if 'industry' not in df_final.columns:
            df_final['industry'] = 'General Data'
            
        # group jobs by industry to calculate stats
        for industry, group in df_final.groupby('industry'):
            total = len(group)
            
            # extract and split all skills into a flat list
            all_skills_list = []
            for skills_str in group['skills'].dropna():
                all_skills_list.extend([s.strip() for s in str(skills_str).split(',') if s.strip()])
            
            # count frequencies of each skill
            skill_counts = Counter(all_skills_list)
            
            # grab the top 5 most requested skills and calculate percentages
            top_skills = skill_counts.most_common(5)
            skill_pcts = {skill: Decimal(str(round((count / total) * 100, 2))) for skill, count in top_skills}
            # count degree requirements
            degrees = {}
            if 'degree_requirement' in group.columns:
                degrees = group['degree_requirement'].value_counts().to_dict()
                
            # store calculated stats for this industry
            industry_breakdown[industry] = {
                "total_jobs": int(total),
                "top_skills": skill_pcts,
                "degrees": degrees
            }

        # prepare the single summary row containing all grouped data
        current_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
        item = {
            'metric_id': 'data_intern_market',
            'timestamp': current_time,
            'total_sample_size': len(df_final),
            'industry_stats': industry_breakdown
        }
        
        # save payload to dynamodb
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table('DP3_JobTrends') 
        table.put_item(Item=item)
        
        logger.info(f"Successfully saved aggregated data to DynamoDB: {item}")
        
        return {
            "statusCode": 200,
            "body": json.dumps("Ingestion successful.")
        }

    except Exception as e:
        logger.error(f"Pipeline failed: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps(f"Error: {str(e)}")
        }