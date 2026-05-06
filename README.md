# DS5220 Data Project 3: Data Science Internship Job Market Trends Tracker

This repository contains the code for an automated data pipeline and REST API designed to track, analyze, and visualize the job market for early career data science jobs (both internships & entry-level fulltime opportunities)

## Overview

The system continuously ingests job postings and uses a custom Python parser to extract structured information from unstructured text. It categorizes each job into specific industries, extracts required technical and soft skills, and determines details such as degree requirements and visa sponsorship availability.

## Architecture

The project is built on AWS serverless infrastructure. The data ingestion and parsing scripts run on AWS Lambda and store the cleaned, categorized data in Amazon DynamoDB. The backend API is built using the AWS Chalice framework, which seamlessly deploys and manages the routing for the application.

## API Endpoints

The Chalice API exposes three primary endpoints for data analysis.

The current endpoint provides a snapshot of the active job market. It calculates the total number of jobs analyzed, provides a breakdown of job volume by industry, and ranks the global demand percentage for specific skills.

The trend endpoint analyzes historical data to calculate shifts in the market over the last week. It compares the most recent job data against past records to show exactly how many postings were added and which specific skills are experiencing a surge in demand.

The plot endpoint generates a visual representation of the market data. It utilizes Matplotlib and Numpy to draw a dynamic heatmap of skill demand across different industries. The generated image is saved to an Amazon S3 bucket, and the endpoint returns a secure link to view the graphic.

## Integration

The API is designed to be easily consumed by external applications. It is currently integrated with a Discord bot, allowing users to type commands in a chat interface to instantly retrieve market analytics, trend reports, and graphical heatmaps.