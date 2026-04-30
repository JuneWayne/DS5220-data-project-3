from typing import List, Optional, Dict, Any, Tuple
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import time
import requests

# A script to parse raw job postings into structured data, extract skills and job functions from descriptions

# Geocoding cache to avoid redundant API calls
_geocode_cache: Dict[str, Tuple[Optional[float], Optional[float]]] = {}
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search" 

degree_patterns = [
    ("PhD",      r"\b(ph\.?d\.?|doctorate|doctoral)\b"),
    ("Master",   r"\b(master'?s|m\.?s\.?|msc|graduate degree)\b"),
    ("Bachelor", r"\b(bachelor'?s|b\.?s\.?|b\.?a\.?|undergraduate degree)\b"),
    ("Associate", r"\b(associate'?s)\b"),
]

def extract_degree_requirements(text):
    txt = text.lower()
    for label, pattern in degree_patterns:
        if re.search(pattern, txt, flags=re.IGNORECASE):
            return label
    
    return None

skill_patterns: Dict[str, str] = {
    # Programming languages
    "Python":            r"\bpython\b",
    "R":                 r"\br[\s\W]",   
    "SQL":               r"\bsql\b",
    "NoSQL":             r"\bnosql\b",
    "Java":              r"\bjava\b",
    "C++":               r"\bc\+\+\b",
    "C":                 r"\bc language\b|\bc programming\b",
    "C#":                r"\bc#\b|\bc sharp\b",
    "JavaScript":        r"\bjavascript\b|\bjs\b",
    "TypeScript":        r"\btypescript\b",
    "Go":                r"\bgolang\b|\bgo language\b",
    "Rust":              r"\brust\b",
    "Scala":             r"\bscala\b",
    "Ruby":              r"\bruby\b",
    "PHP":               r"\bphp\b",
    "Swift":             r"\bswift\b",
    "Kotlin":            r"\bkotlin\b",
    "Shell":             r"\bshell scripting\b|\bshell script\b",
    "Bash":              r"\bbash\b",
    "PowerShell":        r"\bpowershell\b",
    "MATLAB":            r"\bmatlab\b",

    # Web basics
    "HTML":              r"\bhtml\b",
    "CSS":               r"\bcss\b",
    "SASS":              r"\bsass\b|\bscss\b",

    # Data science / statistics
    "Pandas":            r"\bpandas\b",
    "NumPy":             r"\bnumpy\b",
    "SciPy":             r"\bscipy\b",
    "Scikit-learn":      r"\bscikit-learn\b|\bsklearn\b",
    "TensorFlow":        r"\btensorflow\b",
    "PyTorch":           r"\bpytorch\b",
    "Keras":             r"\bkeras\b",
    "Jupyter":           r"\bjupyter\b",
    "XGBoost":           r"\bxgboost\b",
    "LightGBM":          r"\blightgbm\b",
    "CatBoost":          r"\bcatboost\b",
    "Statsmodels":       r"\bstatsmodels\b",
    "Bayesian Methods":  r"\bbayesian\b",
    "A/B Testing":       r"\ba/b testing\b|\ba\/b testing\b",
    "Hypothesis Testing":r"\bhypothesis testing\b",
    "Time Series":       r"\btime series\b",
    "Forecasting":       r"\bforecasting\b",
    "NLP":               r"\bnatural language processing\b|\bnlp\b",
    "Computer Vision":   r"\bcomputer vision\b",
    "Reinforcement Learning": r"\breinforcement learning\b",

    # Data engineering / big data
    "Apache Spark":      r"\bspark\b",
    "Hadoop":            r"\bhadoop\b",
    "Kafka":             r"\bkafka\b",
    "Airflow":           r"\bairflow\b",
    "dbt":               r"\bdbt\b",
    "Snowflake":         r"\bsnowflake\b",
    "Redshift":          r"\bredshift\b",
    "BigQuery":          r"\bbigquery\b",
    "Databricks":        r"\bdatabricks\b",
    "ETL":               r"\betl\b|\bextract[- ]?transform[- ]?load\b",
    "ELT":               r"\belt\b|\bextract[- ]?load[- ]?transform\b",
    "Data Warehouse":    r"\bdata warehouse\b",
    "Data Lake":         r"\bdata lake\b",
    "Lakehouse":         r"\blakehouse\b",
    "Kafka Streams":     r"\bkafka streams\b",
    "Flink":             r"\bflink\b",
    "Beam":              r"\bapache beam\b|\bbeam pipeline\b",
    "DuckDB":            r"\bduckdb\b",
    "MotherDuck":        r"\bmotherduck\b",

    # Cloud / DevOps
    "AWS":               r"\baws\b|\bamazon web services\b",
    "Azure":             r"\bazure\b",
    "GCP":               r"\bgoogle cloud\b|\bgcp\b",
    "AWS Lambda":        r"\blambda\b",
    "AWS S3":            r"\bs3\b|\bsimple storage service\b",
    "ECS":               r"\becs\b|\belastic container service\b",
    "EKS":               r"\beks\b|\belastic kubernetes service\b",
    "CloudFormation":    r"\bcloudformation\b",
    "Azure Functions":   r"\bazure functions\b",
    "Kubernetes":        r"\bkubernetes\b|\bk8s\b",
    "Docker":            r"\bdocker\b",
    "Terraform":         r"\bterraform\b",
    "Git":               r"\bgit\b",
    "GitHub":            r"\bgithub\b",
    "GitLab":            r"\bgitlab\b",
    "Bitbucket":         r"\bbitbucket\b",
    "CI/CD":             r"\bci/cd\b|\bcontinuous integration\b|\bcontinuous deployment\b",
    "Jenkins":           r"\bjenkins\b",
    "Argo":              r"\bargo\b|\bargo cd\b",
    "Linux":             r"\blinux\b",

    # AI / LLM / MLOps frameworks
    "OpenAI":            r"\bopenai\b",
    "LangChain":         r"\blangchain\b",
    "Hugging Face":      r"\bhugging face\b|\bhuggingface\b",
    "TensorFlow Serving":r"\btensorflow serving\b",
    "MLflow":            r"\bmlflow\b",
    "Kubeflow":          r"\bkubeflow\b",
    "Ray":               r"\bray\b",
    "FastAPI":           r"\bfastapi\b",
    "LangFlow":          r"\blangflow\b",
    "LlamaIndex":        r"\bllamaindex\b|\bgpt index\b",
    "AutoGen":           r"\bautogen\b",
    "BentoML":           r"\bbentoml\b",
    "SageMaker":         r"\bsagemaker\b",
    "Vertex AI":         r"\bvertex ai\b",
    "Azure ML":          r"\bazure ml\b|\bazure machine learning\b",
    "Pinecone":          r"\bpinecone\b",
    "Weights & Biases":  r"\bweights ?& ?biases\b|\bwandb\b",

    # Databases
    "MySQL":             r"\bmysql\b",
    "PostgreSQL":        r"\bpostgresql\b|\bpostgres\b",
    "SQL Server":        r"\bsql server\b",
    "MongoDB":           r"\bmongodb\b|\bmongo db\b",
    "SQLite":            r"\bsqlite\b",
    "Oracle":            r"\boracle\b",
    "Cassandra":         r"\bcassandra\b",
    "Redis":             r"\bredis\b",
    "Elasticsearch":     r"\belasticsearch\b",
    "Firebase":          r"\bfirebase\b",
    "DynamoDB":          r"\bdynamodb\b",
    "Neo4j":             r"\bneo4j\b",
    "Snowflake DB":      r"\bsnowflake\b",

    # Web / SWE frameworks
    "React":             r"\breact\b",
    "Angular":           r"\bangular\b",
    "Vue":               r"\bvue\.js\b|\bvuejs\b|\bvue\b",
    "Node.js":           r"\bnode\.js\b|\bnodejs\b",
    "Express":           r"\bexpress\.js\b|\bexpressjs\b|\bexpress\b",
    "Django":            r"\bdjango\b",
    "Flask":             r"\bflask\b",
    "FastAPI (Web)":     r"\bfastapi\b",
    "Spring":            r"\bspring\b",
    "Spring Boot":       r"\bspring boot\b",
    ".NET":              r"\.net\b",
    "ASP.NET":           r"\basp\.net\b",
    "REST APIs":         r"\brest api\b|\brestful api\b",
    "GraphQL":           r"\bgraphql\b",

    # Analytics / BI
    "Excel":             r"\bexcel\b",
    "Excel VBA":         r"\bvba\b|\bexcel vba\b",
    "Tableau":           r"\btableau\b",
    "Power BI":          r"\bpower\s*bi\b",
    "Looker":            r"\blooker\b",
    "Qlik":              r"\bqlik\b",
    "SAS":               r"\bsas\b",
    "SPSS":              r"\bspss\b",
    "Stata":             r"\bstata\b",
    "Google Analytics":  r"\bgoogle analytics\b",
    "PowerPoint":        r"\bpowerpoint\b",
    "Alteryx":           r"\balteryx\b",
    "Mode":              r"\bmode analytics\b|\bmode\b",
    "Domo":              r"\bdomo\b",
    "MicroStrategy":     r"\bmicrostrategy\b",
    "Sigma":             r"\bsigma computing\b|\bsigma analytics\b",
    "CRM":               r"\bcrm\b",
    

    # Security / cyber
    "Cybersecurity":     r"\bcyber ?security\b",
    "Penetration Testing": r"\bpenetration testing\b|\bpen testing\b",
    "Threat Detection":  r"\bthreat detection\b",
    "SIEM":              r"\bsiem\b",
    "Splunk":            r"\bsplunk\b",
    "Wireshark":         r"\bwireshark\b",
    "NIST":              r"\bnist\b",
    "ISO 27001":         r"\biso\s*27001\b",
    "SOC 2":             r"\bsoc\s*2\b",
    "OWASP":             r"\bowasp\b",
    "Vulnerability Management": r"\bvulnerability management\b",

    # PM / collaboration / CRM tools
    "Jira":              r"\bjira\b",
    "Confluence":        r"\bconfluence\b",
    "Notion":            r"\bnotion\b",
    "Trello":            r"\btrello\b",
    "Asana":             r"\basana\b",
    "Figma":             r"\bfigma\b",
    "Miro":              r"\bmiro\b",
    "Salesforce":        r"\bsalesforce\b",
    "HubSpot":           r"\bhubspot\b",

    # Soft skills 
    "Communication":     r"\bstrong communication\b|\bexcellent communication\b|\bcommunication skills\b",
    "Teamwork":          r"\bteam player\b|\bteamwork\b|\bcollaborative\b",
    "Leadership":        r"\bleadership\b|\bleading teams\b",
    "Problem Solving":   r"\bproblem[- ]solving\b|\bsolve complex problems\b",
    "Time Management":   r"\btime management\b",
    "Presentation":      r"\bpresentation skills\b|\bpresent findings\b",
    "Stakeholder Management": r"\bstakeholder management\b|\bstakeholder engagement\b",
    "Project Management":     r"\bproject management\b",
}

def extract_skills(text):
    txt = text.lower()
    found_skills = []
    for skill, pattern in skill_patterns.items():
        if re.search(pattern, txt, flags=re.IGNORECASE):
            found_skills.append(skill)
    return found_skills

def extract_work_mode(text, location):
    desc = text.lower()
    loc = location.lower()
    if "remote" in desc or "remote" in loc:
        if "hybrid" in desc:
            return "Hybrid"
        return "Remote"
    
    if "hybrid" in desc:
        return "Hybrid"
    
    if "remote" in loc:
        return "Remote"
    
    return "On-site"

def parse_num_applicants(string):
    txt = string.replace(",", "")
    match = re.search(r"(\d+)", txt)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None

def extract_visa_sponsorship(text):
    """
    Determine if a job sponsors visas for international students.
    Returns: "Yes", "No", or "Unclear"
    """
    txt = text.lower()
    
    # Strong positive indicators
    positive_patterns = [
        r"sponsorship is available",
        r"will sponsor",
        r"can sponsor",
        r"sponsors? (h-?1b|opt|cpt)",
        r"(h-?1b|opt|cpt) sponsor",
        r"international (students?|candidates?) (welcome|encouraged)",
        r"open to international",
        r"eligible for visa",
        r"f-?1.*opt.*sponsor",
    ]
    
    # Strong negative indicators
    negative_patterns = [
        r"no visa sponsor",
        r"cannot sponsor",
        r"unable to provide sponsorship",
        r"unable to",
        r"will not sponsor",
        r"does not sponsor",
        r"visa sponsorship is not",
        r"unable to sponsor",
        r"not eligible for.*sponsor",
        r"us citizen.*required",
        r"must be (a )?us citizen",
        r"citizenship required",
        r"security clearance required",
        r"active (secret|top.?secret) clearance",
        r"must possess.*clearance",
        r"us persons? only",
        r"visa sponsorship is not available"
    ]
    
    # Check for positive signals
    for pattern in positive_patterns:
        if re.search(pattern, txt, flags=re.IGNORECASE):
            return "Yes"
    
    # Check for negative signals
    for pattern in negative_patterns:
        if re.search(pattern, txt, flags=re.IGNORECASE):
            return "No"
    
    # Default to unclear if no explicit mention
    return "Unclear"
def extract_visa_sponsorship(text, title: str = ""):
    """
    Heuristic visa sponsorship classifier.

    Returns: "Yes", "No", or "Unclear".
    Uses both title and description to catch more cues.
    """
    combined = f"{title} {text}".lower()

    positive_patterns = [
        r"\bvisa sponsorship\b",
        r"\bsponsorship (is )?available\b",
        r"\bwill sponsor\b",
        r"\bcan sponsor\b",
        r"\bsponsor(s|ship)? (h-?1b|h1b|opt|cpt|stem opt)\b",
        r"\b(h-?1b|h1b|opt|cpt|stem opt) sponsorship\b",
        r"\binternational (students?|candidates?) (welcome|encouraged)\b",
        r"\bopen to international\b",
        r"\bvisa eligible\b",
    ]

    negative_patterns = [
        r"\bno visa sponsorship\b",
        r"\b(no|not|unable to) sponsor\b",
        r"\bwill not sponsor\b",
        r"\bdoes not sponsor\b",
        r"\bwithout (visa )?sponsorship\b",
        r"\bnot (eligible|able) for sponsorship\b",
        r"\bmust have work authorization\b",
        r"\bno c2c\b",
        r"\b(us citizen|citizenship) required\b",
        r"\bgreen card (holders?|required)\b",
        r"\bus persons? only\b",
        r"\bsecurity clearance required\b",
        r"\b(active )?(secret|top ?secret) clearance\b",
        r"\bitar\b",
        r"\bvisa sponsorship is not available\b",
        r"\bdo not provide visa sponsorship\b",
    ]

    for pattern in positive_patterns:
        if re.search(pattern, combined, flags=re.IGNORECASE):
            return "Yes"

    for pattern in negative_patterns:
        if re.search(pattern, combined, flags=re.IGNORECASE):
            return "No"

    return "Unclear"

def extract_job_function(text, title):
    parts = []
    parts.append(title.lower())
    parts.append(text.lower())
    combined = " ".join(parts)

    if not combined.strip():
        return "Other"
    
    # ML engineer / applied ML
    if ("machine learning engineer" in combined or
        "ml engineer" in combined or
        "ml ops engineer" in combined or
        "applied scientist" in combined or
        "applied machine learning" in combined):
        return "Machine Learning Engineer"

    # Research scientist
    if ("research scientist" in combined or
        "research engineer" in combined or
        "researcher" in combined and "research" in combined):
        return "Research Scientist"

    # Data engineer / platform / pipelines
    if ("data engineer" in combined or
        "data engineering" in combined or
        "etl developer" in combined or
        "etl engineer" in combined or
        "data pipeline" in combined or
        "data platform" in combined):
        return "Data Engineer"

    # MLOps / platform
    if ("mlops" in combined or
        "model deployment" in combined or
        "model serving" in combined or
        "model monitoring" in combined or
        "ml platform" in combined):
        return "MLOps / Platform"

    # Data scientist
    if ("data scientist" in combined or
        "data science" in combined or
        "ml scientist" in combined or
        "machine learning" in combined and "scientist" in combined):
        return "Data Scientist"

    # Data analyst / BI / analytics
    if ("data analyst" in combined or
        "business intelligence" in combined or
        "bi analyst" in combined or
        "analytics engineer" in combined or
        "marketing analyst" in combined or
        "product analyst" in combined or
        "insights analyst" in combined or
        "reporting analyst" in combined or
        "business analytics" in combined or
        "analytics" in combined):
        return "Data Analyst / BI"

    # Security / cyber
    if ("security engineer" in combined or
        "security analyst" in combined or
        "cyber security" in combined or
        "cybersecurity" in combined or
        "infosec" in combined or
        "information security" in combined):
        return "Security / Cyber"

    # Software engineering / backend / frontend / fullstack
    if ("software engineer" in combined or
        "software developer" in combined or
        "sde" in combined or
        "backend engineer" in combined or
        "back-end engineer" in combined or
        "frontend engineer" in combined or
        "front-end engineer" in combined or
        "fullstack" in combined or
        "full stack" in combined or
        "mobile engineer" in combined or
        "android engineer" in combined or
        "ios engineer" in combined):
        return "Software Engineer"

    # Product manager
    if ("product manager" in combined or
        "product management" in combined or
        "pm role" in combined):
        return "Product Manager"

    # Business / strategy / operations / consulting
    if ("business analyst" in combined or
        "strategy analyst" in combined or
        "operations analyst" in combined or
        "ops analyst" in combined or
        "management consultant" in combined or
        "strategy consultant" in combined):
        return "Business / Strategy Analyst"

    # Quant / finance roles
    if ("quantitative analyst" in combined or
        "quant analyst" in combined or
        "quant research" in combined or
        "trading" in combined and "analyst" in combined or
        "risk analyst" in combined):
        return "Quant / Finance"

    return "Other"


def classify_company_industry(company_name: str) -> str:
    """Classify a company into a coarse industry bucket based on its name."""
    name = (company_name or "").lower()
    # canonical keyword lists
    tech_giants = [
        "google", "alphabet", "microsoft", "meta", "facebook", "amazon", "apple",
        "netflix", "nvidia", "adobe", "salesforce", "oracle", "ibm", "tesla", "cisco",
        "intel", "amd", "qualcomm", "broadcom", "texas instruments", "micron",
        "dell", "hp", "hewlett packard", "lenovo", "vmware", "red hat", "sap",
        "intuit", "autodesk", "synopsys", "cadence", "ansys", "siemens", "ge digital",
        "sony", "samsung", "tencent", "alibaba", "baidu", "bytedance", "tiktok",
        "x", "twitter", "spacex", "paypal", "ebay", "booking", "expedia"
    ]
    tech_mid = [
        "snowflake", "databricks", "palantir", "stripe", "block", "square", "twilio", "cloudflare",
        "shopify", "atlassian", "zendesk", "mongodb", "datadog", "okta", "servicenow",
        "airbnb", "uber", "lyft", "doordash", "instacart", "grubhub", "snap", "snapchat",
        "pinterest", "reddit", "discord", "roblox", "unity", "epic games", "riot games",
        "zoom", "slack", "asana", "notion", "figma", "canva", "airtable", "hubspot",
        "splunk", "palo alto", "crowdstrike", "fortinet", "zscaler", "cloudflare",
        "confluent", "elastic", "hashicorp", "gitlab", "github", "bitbucket",
        "docusign", "dropbox", "box", "workday", "coupa", "veeva", "appian",
        "twitch", "spotify", "soundcloud", "duolingo", "coursera", "udemy", "chegg",
        "robinhood", "coinbase", "kraken", "binance", "plaid", "affirm", "klarna",
        "chime", "nubank", "revolut", "n26", "monzo", "betterment", "wealthfront",
        "etsy", "poshmark", "mercari", "offerup", "letgo", "zillow", "redfin",
        "opendoor", "compass", "trulia", "apartments.com", "realtor.com",
        "peloton", "strava", "noom", "calm", "headspace", "whoop", "oura",
        "23andme", "ancestry", "color genomics", "tempus", "flatiron health",
        "grammarly", "monday.com", "clickup", "smartsheet", "amplitude", "mixpanel",
        "segment", "mparticle", "braze", "iterable", "sendgrid", "mailchimp",
        "zapier", "make", "integromat", "fivetran", "airbyte", "census", "hightouch",
        "retool", "bubble", "webflow", "wix", "squarespace", "wordpress vip",
        "vercel", "netlify", "render", "fly.io", "railway", "heroku", "planetscale"
    ]
    tech_startup_hints = ["labs", "ventures", "ai", "analytics", "systems", "technologies", "solutions"]

    investment_banks = [
        "goldman", "morgan stanley", "jp morgan", "j.p. morgan", "bank of america", "bofa", "barclays",
        "credit suisse", "ubs", "deutsche bank", "jefferies", "evercore", "piper sandler", "lazard",
        "centerview", "moelis", "guggenheim", "rbc capital", "nomura", "mizuho", "hsbc", "citigroup",
        "citi", "bnpp", "bnp paribas", "wells fargo securities", "td securities", "scotiabank",
        "bmo capital", "stifel", "william blair", "raymond james", "cowen", "greenhill"
    ]
    finance = [
        "jpmorgan", "chase", "capital one", "american express", "visa", "mastercard", "discover",
        "blackrock", "fidelity", "two sigma", "citadel", "point72", "aig", "state street",
        "pnc", "ally", "regions bank", "us bank", "charles schwab", "vanguard", "t. rowe price",
        "bridgewater", "aqr", "renaissance technologies", "de shaw", "jane street", "jump trading",
        "hrt", "virtu", "tower research", "susquehanna", "optiver", "imc trading",
        "prudential", "metlife", "allstate", "progressive", "travelers", "hartford"
    ]
    consulting = [
        "mckinsey", "boston consulting", "bcg", "bain", "deloitte", "pwc", "kpmg", "ey",
        "ernst & young", "accenture", "booz allen", "oliver wyman", "at kearney", "a.t. kearney",
        "roland berger", "l.e.k.", "lek consulting", "lek", "strategy&", "monitor deloitte", "monitor","cap tech"
    ]
    retail = [
        "walmart", "target", "costco", "home depot", "lowe's", "lowes", "best buy", "kroger",
        "walgreens", "cvs", "tesco", "aldi", "lidl", "ikea", "macy", "kohls", "nordstrom", "wayfair",
        "gap", "old navy", "tj maxx", "marshalls", "ross", "burlington", "bed bath", "williams sonoma",
        "foot locker", "dick's sporting", "rei", "petco", "petsmart", "whole foods", "trader joe"
    ]
    healthcare = [
        "johnson", "pfizer", "merck", "abbvie", "amgen", "novartis", "roche", "eli lilly",
        "bristol myers", "gsk", "sanofi", "astrazeneca", "unitedhealth", "cigna", "anthem", "elevance",
        "moderna", "regeneron", "biogen", "vertex", "gilead", "bayer", "boehringer", "takeda",
        "cardinal health", "mckesson", "amerisource", "quest diagnostics", "labcorp", "davita",
        "humana", "centene", "molina", "wellcare", "magellan", "optum", "aetna", "kaiser"
    ]
    automotive = [
        "ford", "gm", "general motors", "toyota", "honda", "bmw", "mercedes", "volkswagen", "stellantis",
        "rivian", "lucid", "nissan", "hyundai", "kia", "mazda", "subaru", "volvo", "porsche", "ferrari",
        "waymo", "cruise", "argo ai", "aurora", "motional", "zoox", "mobileye", "aptiv", "bosch automotive"
    ]
    energy = [
        "chevron", "exxon", "exxonmobil", "shell", "bp", "total", "conocophillips", "duke energy",
        "nextera", "dominion", "southern company", "exelon", "pge", "pg&e", "american electric",
        "sempra", "consolidated edison", "entergy", "xcel", "wec energy", "enbridge", "kinder morgan"
    ]

    def contains(keywords):
        return any(k in name for k in keywords)

    if contains(tech_giants):
        return "Tech - Giant"
    if contains(tech_mid):
        return "Tech - Mid"
    if contains(investment_banks):
        return "Investment Banking"
    if contains(consulting):
        return "Consulting"
    if contains(finance):
        return "Finance"
    if contains(retail):
        return "Retail"
    if contains(healthcare):
        return "Healthcare / Pharma"
    if contains(automotive):
        return "Automotive / Manufacturing"
    if contains(energy):
        return "Energy / Utilities"
    # Startup-ish heuristics (only if nothing else matched)
    if name and contains(tech_startup_hints):
        return "Tech - Startup"
    return "Other"

def parse_time_posted(time_posted):
    txt = time_posted.strip().lower()
    match = re.search(r"(\d+)\s+(minute|hour|day|week|month|year)s?\s+ago", txt)
    if not match:
        return None
    value = int(match.group(1))
    unit = match.group(2)
    now_et = datetime.now(ZoneInfo("America/New_York"))  

    if unit == "minute":
        delta = timedelta(minutes=value)
    elif unit == "hour":
        delta = timedelta(hours=value)
    elif unit == "day":
        delta = timedelta(days=value)
    elif unit == "week":
        delta = timedelta(weeks=value)
    elif unit == "month":
        # crude approximation, fine for trend analysis
        delta = timedelta(days=30 * value)
    elif unit == "year":
        delta = timedelta(days=365 * value)
    else:
        return None

    return now_et - delta

def geocode_location(location: str, use_cache: bool = True) -> Tuple[Optional[float], Optional[float]]:
    """
    Geocode a location string to latitude/longitude using Nominatim API.
    
    Args:
        location: Location string to geocode
        use_cache: Whether to use cached results (default True)
    
    Returns:
        Tuple of (latitude, longitude) or (None, None) if not found
    """
    if not location or location.strip() == "":
        return None, None
    
    # Normalize location for cache lookup
    location_key = location.strip().lower()
    
    # Check cache first
    if use_cache and location_key in _geocode_cache:
        return _geocode_cache[location_key]
    
    # Make API request
    params = {
        "q": f"{location}, United States",
        "format": "json",
        "limit": 1,
    }
    
    try:
        resp = requests.get(
            NOMINATIM_URL,
            params=params,
            headers={"User-Agent": "JobMarketStreamBot/1.0 (Educational Project)"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        
        if data and len(data) > 0:
            lat = float(data[0]["lat"])
            lon = float(data[0]["lon"])
            _geocode_cache[location_key] = (lat, lon)
            
            # Rate limiting to respect Nominatim usage policy (1 req/sec)
            time.sleep(1.1)
            
            return lat, lon
    except Exception as e:
        print(f"[geocode] Error geocoding '{location}': {e}")
    
    # Cache negative results too to avoid re-trying
    _geocode_cache[location_key] = (None, None)
    return None, None

def parse_job_postings(df_jobs, geocode: bool = False):
    """
    Parse job posting data and extract structured information.
    
    Args:
        df_jobs: Job data dictionary
        geocode: Whether to geocode the location (default False, set True to enable)
    
    Returns:
        Parsed job dictionary with extracted fields
    """
    job = dict(df_jobs)

    description = job.get("job_description", "") or ""
    title = job.get("job_title", "") or ""
    time_posted = job.get("time_posted", "") or ""
    location = job.get("location", "") or ""
    num_applicants_str = job.get("num_applicants", None)
    job["num_applicants_int"] = parse_num_applicants(num_applicants_str) if num_applicants_str else None
    job["degree_requirement"] = extract_degree_requirements(description)
    skill_list = extract_skills(description)
    job["skills"] = ", ".join(skill_list) if skill_list else ""
    job["work_mode"] = extract_work_mode(description, location)
    job["job_function"] = extract_job_function(description, title)
    job["industry"] = classify_company_industry(job.get("company_name"))
    job["visa_sponsorship"] = extract_visa_sponsorship(description)
    posting_dt = parse_time_posted(time_posted)
    job["time_posted_parsed"] = posting_dt.isoformat() if posting_dt else None
    
    # Geocode location if requested
    if geocode and location:
        lat, lon = geocode_location(location)
        job["latitude"] = lat
        job["longitude"] = lon
    else:
        job["latitude"] = None
        job["longitude"] = None
    
    # Record when this job was actually scraped/processed
    job["scraped_at"] = datetime.now(ZoneInfo("America/New_York")).isoformat()
    
    return job