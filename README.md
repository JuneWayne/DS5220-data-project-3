# DS5220 Data Project 3 I Data Science Internship Job Market Trends Tracker

I developed this project to track the early career job market for data scientists by utilizing a custom made job board scraper engine. I designed the system to scrape job postings every hour so I can analyze current trends in the internship landscape. 

## Overview

I built this system to ingest job postings and use a custom Python parser that extracts structured information from unstructured text. My scripts categorize each job into specific industries and extract required technical and soft skills. Furthermore, I determine details such as degree requirements and whether visa sponsorship is available for each role.

## Architecture

The project relies on AWS serverless infrastructure for all operations. My data ingestion and parsing scripts run on AWS Lambda and I store the cleaned and categorized data in Amazon DynamoDB. Because libraries like Matplotlib and Pandas are often too large for Lambda, I created a custom slim layer to ensure the package fits within the AWS 250MB limit. The backend API is built using the AWS Chalice framework and I use this to manage the routing and deployment for the entire application.

## API Endpoints

I have established three primary endpoints for data analysis and they are as follows.

The current endpoint provides a snapshot of the active job market. It calculates the total number of jobs I have analyzed and provides a breakdown of job volume by industry while ranking the global demand for specific skills.

The trend endpoint analyzes historical data to calculate shifts in the market over the last week. I designed this to compare the most recent job data against past records so users can see exactly how many postings were added and which specific skills are experiencing a surge in demand.

The plot endpoint generates a visual representation of the market data by using Matplotlib and Numpy to draw a dynamic heatmap of skill demand. I configured the system to save this image to an Amazon S3 bucket. To comply with the project rubric, this endpoint returns a JSON response where the response key contains the secure URL to view the graphic. I have also set the S3 bucket policies to ensure the object is publicly readable for anyone with the link.

## Integration

I designed the API to be easily consumed by external applications and it is currently integrated with a Discord bot. This allows users to type commands in a chat interface to instantly retrieve market analytics and graphical heatmaps.

## How to use the Discord bot

If you want to interact with the data on Discord, you can use the following commands.

To see the current job market snapshot, type /project wkt7ne current. 

If you want to see the weekly trend report and demand surges, type /project wkt7ne trend. 

To view the graphical heatmap, type /project wkt7ne plot and the bot will display the image link from S3 so the plot renders directly in the chat.