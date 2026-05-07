from chalice import Chalice
import boto3
from boto3.dynamodb.conditions import Key
import datetime

app = Chalice(app_name='job-market-api')

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('DP3_JobTrends')

@app.route('/')
def index():
    return {
        "about": "An API that tracks the demand for specific technical and soft skills in the Early Careers Data Science job market.",
        "resources": ["current", "trend", "plot", "education", "compare", "skill"]
    }

@app.route('/current')
def current():
    try:
        response = table.query(
            KeyConditionExpression=Key('metric_id').eq('data_intern_market'),
            ScanIndexForward=False, 
            Limit=1
        )
        
        items = response.get('Items', [])
        if not items:
            return {"response": "No data available."}

        latest = items[0]
        stats = latest.get('industry_stats', {})
        
        industry_breakdown = {}
        global_skills = {}
        total_market_jobs = 0

        for ind, data in stats.items():
            jobs = int(data.get('total_jobs', 0))
            total_market_jobs += jobs
            industry_breakdown[ind] = jobs
            
            for skill, pct in data.get('top_skills', {}).items():
                global_skills[skill] = global_skills.get(skill, 0) + (float(pct) * jobs / 100)

        global_skill_pct = {}
        if total_market_jobs > 0:
            for skill, count in global_skills.items():
                global_skill_pct[skill] = round((count / total_market_jobs) * 100, 2)

        sorted_skills = dict(sorted(global_skill_pct.items(), key=lambda item: item[1], reverse=True))
        date_str = latest.get('timestamp', 'Unknown')[:10]
        msg = f"**Current Market Snapshot** *(Last updated: {date_str})*\n\n"
        msg += f"**Total Postings Analyzed:** {total_market_jobs}\n\n"
        
        msg += "**Industry Breakdown**\n"
        sorted_inds = sorted(industry_breakdown.items(), key=lambda x: x[1], reverse=True)
        for ind, jobs in sorted_inds:
            ind_skills = stats.get(ind, {}).get('top_skills', {})
            if ind_skills:
                top_skill = max(ind_skills, key=lambda k: float(ind_skills[k]))
                skill_val = float(ind_skills[top_skill])
                msg += f"• **{ind}:** {jobs} jobs *(Top skill: {top_skill} at {skill_val:.1f}%)*\n"
            else:
                msg += f"• **{ind}:** {jobs} jobs\n"

        msg += "\n**Global Skill Demand (Top 5)**\n"
        count = 0
        for skill, pct in sorted_skills.items():
            if count < 5:
                msg += f"{count+1}. **{skill}:** {pct}%\n"
                count += 1

        return {"response": msg.strip()}

    except Exception as e:
        return {"response": f"Error: {str(e)}"}


@app.route('/trend')
def trend():
    try:
        response = table.query(
            KeyConditionExpression=Key('metric_id').eq('data_intern_market'),
            ScanIndexForward=False, 
            Limit=168 
        )
        
        items = response.get('Items', [])
        if not items:
            return {"response": "No data available."}

        current = items[0]
        current_stats = current.get('industry_stats', {})

        jobs_last_run = int(current.get('total_sample_size', 0))
        jobs_24h = sum(int(item.get('total_sample_size', 0)) for item in items[:24])
        jobs_7d = sum(int(item.get('total_sample_size', 0)) for item in items)

        past_index = min(24, len(items) - 1)
        past = items[past_index]
        past_stats = past.get('industry_stats', {})

        def get_flat_skills(stats_dict):
            skills = {}
            total = 0
            for ind, data in stats_dict.items():
                jobs = int(data.get('total_jobs', 0))
                total += jobs
                for s, p in data.get('top_skills', {}).items():
                    skills[s] = skills.get(s, 0) + (float(p) * jobs / 100)
            if total > 0:
                return {s: round((c / total) * 100, 2) for s, c in skills.items()}
            return {}

        current_skills = get_flat_skills(current_stats)
        past_skills = get_flat_skills(past_stats)

        skill_trends = {}
        all_skill_keys = set(list(current_skills.keys()) + list(past_skills.keys()))

        for s in all_skill_keys:
            c_val = current_skills.get(s, 0)
            p_val = past_skills.get(s, 0)
            diff = round(c_val - p_val, 2)
            skill_trends[s] = {
                "current_pct": c_val,
                "change_pct": diff
            }

        sorted_trends = dict(sorted(skill_trends.items(), key=lambda item: item[1]['change_pct'], reverse=True))

        # Build the Human-Readable Markdown String
        msg = f"**Market Trend Analysis (Last {len(items)} Hours)**\n\n"
        
        msg += "**Job Volume Tracking**\n"
        msg += f"• **Latest Scan:** {jobs_last_run} postings\n"
        msg += f"• **Last 24 Hours:** {jobs_24h} postings\n"
        msg += f"• **Last 7 Days:** {jobs_7d} postings\n\n"
        
        msg += "**Top Skill Surges (24-Hour Change)**\n"
        count = 0
        for skill, data in sorted_trends.items():
            if data['change_pct'] > 0 and count < 7:
                msg += f"• **{skill}:** {data['current_pct']}% *(+{data['change_pct']}%)*\n"
                count += 1
                
        if count == 0:
            msg += "*Not enough historical variance yet to calculate surges.*"

        return {"response": msg.strip()}

    except Exception as e:
        return {"response": f"Error: {str(e)}"}
@app.route('/plot')
def plot():
    return {
        "response": "https://dp3-plots-wkt7ne.s3.amazonaws.com/latest.png"
    }

@app.route('/skill/{skill_name}')
def specific_skill(skill_name):
    try:
        response = table.query(
            KeyConditionExpression=Key('metric_id').eq('data_intern_market'),
            ScanIndexForward=False, Limit=1
        )
        items = response.get('Items', [])
        if not items: return {"response": "No data available."}

        stats = items[0].get('industry_stats', {})
        total_market_jobs = int(items[0].get('total_sample_size', 0))
        
        skill_total_mentions = 0
        industry_breakdown = {}

        # Search for the skill across all industries
        for ind, data in stats.items():
            jobs_in_ind = int(data.get('total_jobs', 0))
            for s_name, pct in data.get('top_skills', {}).items():
                if skill_name.lower().strip() in s_name.lower():
                    mentions = (float(pct) / 100) * jobs_in_ind
                    skill_total_mentions += mentions
                    industry_breakdown[ind] = float(pct)

        if skill_total_mentions == 0:
            return {"response": f"I couldn't find any significant demand for '{skill_name}' in the current data science job market database"}

        global_pct = round((skill_total_mentions / total_market_jobs) * 100, 2)
        sorted_inds = sorted(industry_breakdown.items(), key=lambda x: x[1], reverse=True)

        msg = f"**Skill Deep Dive: {skill_name.title()}**\n"
        msg += f"• **Global Market Demand:** {global_pct}%\n\n"
        msg += "**Highest Demand Sectors:**\n"
        
        for ind, pct in sorted_inds[:3]: # Show top 3 sectors
            msg += f"• {ind}: {pct}%\n"

        return {"response": msg.strip()}
    except Exception as e:
        return {"response": f"Error: {str(e)}"}
@app.route('/skill')
def skill_fallback():
    return {"response": "please specify a skill to search for. Example: `/project wkt7ne skill/python`"}

@app.route('/compare')
def compare_fallback():
    return {"response": "please specify two industries to compare. Example: `/project wkt7ne compare/startup/finance`"}