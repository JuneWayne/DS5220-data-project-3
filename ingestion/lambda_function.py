import io
import json
import logging
import datetime
import time
import random
import re
import boto3
import requests
import matplotlib.pyplot as plt
import numpy as np
from bs4 import BeautifulSoup, Comment
import pandas as pd
from collections import Counter
from decimal import Decimal

# importing custom parser from another script
from job_parser import parse_job_postings

# setup aws logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# rotate user agents to avoid getting blocked by linkedin
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
]

# generate randomized headers for web requests
def get_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

# helper function to make http requests with exponential backoff for rate limits
def request_with_retry(url, max_retries=3, base_delay=5):
    for attempt in range(max_retries):
        try:
            headers = get_headers()
            response = requests.get(url, headers=headers, timeout=30)
            # return successfully if the request goes through
            if response.status_code == 200:
                return response
            # pause and wait if we hit a rate limit wall
            elif response.status_code == 429:
                delay = base_delay * (2 ** attempt) + random.uniform(1, 5)
                logger.warning(f"Rate limited (429), waiting {delay:.1f}s before retry...")
                time.sleep(delay)
            # log other weird status codes but don't retry
            else:
                logger.warning(f"Got status {response.status_code} for {url}")
                return None
        # handle connection drops gracefully
        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError) as e:
            delay = base_delay * (2 ** attempt) + random.uniform(1, 3)
            logger.warning(f"Request failed ({type(e).__name__}), retry {attempt+1}/{max_retries} after {delay:.1f}s")
            time.sleep(delay)
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return None
            
    logger.error(f"Failed after {max_retries} retries: {url}")
    return None

# extract the number of applicants from the job detail page
def get_num_applicants(detail_soup):
    tag = detail_soup.find(class_="num-applicants__caption")
    if tag:
        return tag.get_text(strip=True)
    return None

# dig through various html structures to find the actual apply link
def extract_application_link(job_soup, job_id):
    # check inside hidden code comment blocks first
    code = job_soup.find("code", id="applyUrl")
    if code:
        comment = code.find(string=lambda s: isinstance(s, Comment))
        if comment:
            url = comment.strip().strip('"')
            if url:
                return url
                
    # fallback to standard anchor tags
    apply_anchor = job_soup.select_one("a.apply-button[href]")
    if apply_anchor and apply_anchor.get("href"):
        return apply_anchor["href"]
        
    apply_anchor = job_soup.find("a", attrs={"data-tracking-control-name": re.compile("apply-link")})
    if apply_anchor and apply_anchor.get("href"):
        return apply_anchor["href"]
        
    # fallback to easy apply button logic
    easy_button = job_soup.select_one("button.apply-button")
    if easy_button:
        return f"https://www.linkedin.com/jobs/view/{job_id}"
        
    return None

# main scraping loop to fetch job postings from linkedin search results
def scrape_linkedin(keywords, location, geo_id, f_tpr="r86400", max_results=50):
    base_url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    job_list = []
    seen_ids = set()
    start = 0

    # keep fetching pages until we hit the max results or run out of jobs
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

        # break out of the loop if the page is empty
        if not page_jobs:
            break

        # parse the search results page to find individual job ids
        id_list = []
        for job in page_jobs:
            base_card_div = job.find("div", {"class": "base-card"})
            if base_card_div and base_card_div.get("data-entity-urn"):
                job_id = base_card_div.get("data-entity-urn").split(":")[-1]
                if job_id not in seen_ids:
                    seen_ids.add(job_id)
                    id_list.append(job_id)

        # random pause to mimic human browsing behavior
        time.sleep(random.uniform(3, 6))

        # loop through each unique job id and fetch its full description
        for job_id in id_list:
            detail_url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
            detail_response = request_with_retry(detail_url, max_retries=3, base_delay=3)

            if detail_response is None:
                continue

            detail_soup = BeautifulSoup(detail_response.text, "html.parser")
            job_post = {"job_id": job_id}

            # helper to safely extract text without crashing on missing elements
            def safe_text(selector, attrs=None):
                if attrs is None: attrs = {}
                tag = detail_soup.find(selector, attrs)
                return tag.get_text(strip=True) if tag else None

            # populate the job dictionary with extracted data
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

            # stop scraping if reach the requested limit
            if len(job_list) >= max_results:
                logger.info("Hit max_results cap.")
                break

        if len(job_list) >= max_results:
            break
            
        # increment the pagination counter
        start += 25

    # convert the final list of dictionaries into a pandas dataframe
    df = pd.DataFrame(job_list)
    if not df.empty and "job_title" in df.columns:
        df = df.dropna(subset=["job_title"])
    return df

# take the parsed stats and generate a matplotlib heatmap image
def generate_and_upload_plot(stats_data):
    try:
        logger.info("Starting heatmap generation")
        
        # gather all unique industries and skills from the data
        industries = list(stats_data.keys())
        all_skills = set()
        for ind_data in stats_data.values():
            for skill in ind_data.get('top_skills', {}).keys():
                all_skills.add(skill)
        
        # sort them alphabetically for a cleaner layout
        skills = sorted(list(all_skills))
        industries = sorted(industries)

        # create an empty 2d array to hold the percentage values
        data_matrix = np.zeros((len(industries), len(skills)))
        
        # fill the matrix, casting dynamodb decimals to floats
        for i, ind in enumerate(industries):
            for j, skill in enumerate(skills):
                pct = stats_data[ind].get('top_skills', {}).get(skill, 0)
                data_matrix[i][j] = float(pct)

        # initialize the matplotlib figure and draw the heatmap
        fig, ax = plt.subplots(figsize=(12, 8))
        cax = ax.imshow(data_matrix, cmap='YlGnBu', aspect='auto')
        
        # configure the axes, labels, and rotation for readability
        ax.set_xticks(np.arange(len(skills)))
        ax.set_yticks(np.arange(len(industries)))
        ax.set_xticklabels(skills, rotation=45, ha='right', fontsize=10)
        ax.set_yticklabels(industries, fontsize=10)
        
        # add the colorbar legend on the side
        cbar = fig.colorbar(cax, ax=ax)
        cbar.set_label('Demand Frequency (%)', rotation=270, labelpad=15)

        # loop through the matrix to print the exact percentage text inside each box
        for i in range(len(industries)):
            for j in range(len(skills)):
                val = data_matrix[i][j]
                if val > 0:
                    text_color = "white" if val > 50 else "black"
                    ax.text(j, i, f"{val:.0f}%", ha="center", va="center", color=text_color, fontsize=8)

        # add title and adjust layout to prevent clipping
        plt.title('Data Science Jobs Skill Demand by Industry', pad=20, fontsize=14, fontweight='bold')
        plt.tight_layout()

        # save the image to an in-memory buffer instead of a physical hard drive
        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png', bbox_inches='tight', dpi=150)
        img_buffer.seek(0)
        
        # clear the plot from memory to prevent lambda from crashing
        plt.close()

        # connect to s3 and upload the new image, overwriting the old one
        s3 = boto3.client('s3')
        bucket_name = 'dp3-plots-wkt7ne' 
        file_name = 'latest.png' 
        
        logger.info(f"Uploading new {file_name} to S3...")
        s3.put_object(
            Bucket=bucket_name,
            Key=file_name,
            Body=img_buffer.getvalue(),
            ContentType='image/png'
        )
        logger.info("Heatmap successfully overwritten in S3!")

    except Exception as e:
        logger.error(f"Failed to generate or upload plot: {str(e)}")
        raise e

# main entry point for the aws lambda function
def lambda_handler(event, context):
    logger.info("Lambda triggered, Starting job market ingestion.")
    
    try:
        # scrape linkedin for data intern roles in the us
        df_jobs = scrape_linkedin(
            keywords="Data intern",
            location="United States",
            geo_id="103644278",
            f_tpr="r86400", 
            max_results=200 
        )

        # stop early if no jobs were found this cycle
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
        
        # save the aggregated payload to dynamodb
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table('DP3_JobTrends') 
        table.put_item(Item=item)
        logger.info(f"Successfully saved aggregated data to DynamoDB: {item}")
        
        # trigger the plotting function to update the s3 dashboard
        generate_and_upload_plot(industry_breakdown)
        
        return {
            "statusCode": 200,
            "body": json.dumps("Ingestion and plotting successful.")
        }

    except Exception as e:
        # log critical failures so they appear in cloudwatch
        logger.error(f"Pipeline failed: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps(f"Error: {str(e)}")
        }