from chalice import Chalice
import boto3
from boto3.dynamodb.conditions import Key
import datetime

app = Chalice(app_name='job-market-api')

# Connect to the database outside the routes
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('DP3_JobTrends')

@app.route('/')
def index():
    return {
        "about": "Tracks the hourly demand and skill requirements for Data Intern roles on LinkedIn.",
        "resources": ["current", "trend", "plot"]
    }

@app.route('/current')
def current():
    try:
        # Query the database for the newest item
        # ScanIndexForward=False sorts the timestamps in descending order (newest first)
        response = table.query(
            KeyConditionExpression=Key('metric_id').eq('data_intern_market'),
            ScanIndexForward=False, 
            Limit=1
        )
        
        items = response.get('Items', [])
        if not items:
            return {"response": "No data collected yet."}
            
        latest = items[0]
        timestamp = latest['timestamp'][:16].replace('T', ' ') # Clean up the ISO string for display
        
        # Build a clean string response for the Discord bot
        reply = (f"Latest data ({timestamp} UTC): "
                 f"Sampled {int(latest['total_sample_size'])} jobs. "
                 f"Remote: {int(latest.get('remote_count', 0))} | "
                 f"Python mentions: {int(latest.get('python_count', 0))} | "
                 f"SQL mentions: {int(latest.get('sql_count', 0))}")
                 
        return {"response": reply}
        
    except Exception as e:
        return {"response": f"Database error: {str(e)}"}

@app.route('/trend')
def trend():
    try:
        # Calculate the timestamp for 24 hours ago
        yesterday = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)).isoformat()
        
        # Query all items from the last 24 hours
        response = table.query(
            KeyConditionExpression=Key('metric_id').eq('data_intern_market') & Key('timestamp').gt(yesterday)
        )
        
        items = response.get('Items', [])
        if not items:
            return {"response": "Not enough data in the last 24 hours to calculate a trend."}
            
        # Calculate a derived metric: Average Remote Percentage
        total_jobs = sum(int(item.get('total_sample_size', 0)) for item in items)
        total_remote = sum(int(item.get('remote_count', 0)) for item in items)
        
        if total_jobs == 0:
            return {"response": "error: No valid jobs in the last 24 hours."}
            
        avg_remote = (total_remote / total_jobs) * 100
        
        reply = f"24-Hour Trend: Based on {len(items)} hourly scrapes, an average of {avg_remote:.1f}% of data intern roles offer remote work."
        return {"response": reply}
        
    except Exception as e:
        return {"response": f"Database error: {str(e)}"}

@app.route('/plot')
def plot():
    try:
        # Fetch all data from DynamoDB 
        # fetching the last 7 days to have enough points for a trend plot
        last_week = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)).isoformat()
        response = table.query(
            KeyConditionExpression=Key('metric_id').eq('data_intern_market') & Key('timestamp').gt(last_week)
        )
        
        items = response.get('Items', [])
        if len(items) < 2:
            return {"response": "Not enough data points to draw a plot yet. Let it run for a few more hours!"}

        # Tell Matplotlib to run in headless mode
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import io
        import uuid

        # Extract the data for the X and Y axes
        # X-axis: Format timestamp to show just "MM-DD HH:MM"
        timestamps = [item['timestamp'][5:16].replace('T', ' ') for item in items] 
        # Y-axis: We will plot the number of Remote roles available
        remote_counts = [int(item.get('remote_count', 0)) for item in items]

        plt.figure(figsize=(8, 4))
        plt.plot(timestamps, remote_counts, marker='o', linestyle='-', color='indigo', linewidth=2)
        plt.title('Remote Data Intern Jobs Over Time')
        plt.xlabel('Time (UTC)')
        plt.ylabel('Remote Postings')
        plt.xticks(rotation=45)
        plt.tight_layout() # Ensures labels don't get cut off

        # Save the image to memory instead of on disk
        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png')
        img_buffer.seek(0)
        plt.close()

        # Upload to public S3 Bucket
        s3 = boto3.client('s3')
        bucket_name = 'dp3-plots-wkt7ne'
        
        # Give the image a random unique name so it doesn't overwrite old plots
        file_name = f'trend_plot_{uuid.uuid4().hex[:8]}.png' 
        
        s3.put_object(
            Bucket=bucket_name,
            Key=file_name,
            Body=img_buffer,
            ContentType='image/png'
        )

        # Return the public URL for Discord to render
        s3_url = f"https://{bucket_name}.s3.amazonaws.com/{file_name}"
        return {"response": s3_url}

    except Exception as e:
        return {"response": f"Plotting error: {str(e)}"}