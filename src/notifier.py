from typing import List, Dict, Any
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from datetime import datetime

class JobNotifier:
    def __init__(self):
        self.email_enabled = False
        self.smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.sender_email = os.getenv('SENDER_EMAIL')
        self.sender_password = os.getenv('SENDER_PASSWORD')
        self.recipient_email = os.getenv('RECIPIENT_EMAIL')
        
        if self.sender_email and self.sender_password and self.recipient_email:
            self.email_enabled = True
    
    async def notify_high_priority_jobs(self, jobs: List[Dict[str, Any]]):
        print("\n" + "="*60)
        print("HIGH PRIORITY JOBS REQUIRING HUMAN REVIEW")
        print("="*60)
        
        for i, job in enumerate(jobs, 1):
            print(f"\n{i}. {job['title']}")
            print(f"   Company: {job['company']}")
            print(f"   Location: {job['location']}")
            print(f"   Overall Score: {job['overall_score']:.2f}")
            print(f"   Skills Match: {job['skills_match_score']:.2f}")
            print(f"   Salary Score: {job['salary_score']:.2f}")
            print(f"   Company Score: {job['company_score']:.2f}")
            print(f"   Location Score: {job['location_score']:.2f}")
            if job.get('salary_min') or job.get('salary_max'):
                salary_range = f"${job.get('salary_min', 0):,} - ${job.get('salary_max', 0):,}"
                print(f"   Salary Range: {salary_range}")
            print(f"   URL: {job['url']}")
            print(f"   Discovered: {job.get('discovered_date', datetime.now())}")
        
        print("\n" + "="*60)
        
        if self.email_enabled:
            await self.send_email_notification(jobs)
        else:
            print("\n⚠️  Email notifications not configured. Set SMTP credentials in .env to enable.")
        
        self.save_to_file(jobs)
    
    async def send_email_notification(self, jobs: List[Dict[str, Any]]):
        try:
            subject = f"🔔 {len(jobs)} High-Priority Job{'s' if len(jobs) > 1 else ''} Found!"
            
            body = f"""
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; }}
        .job {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }}
        .job-title {{ font-size: 18px; font-weight: bold; color: #2c3e50; }}
        .company {{ font-size: 16px; color: #34495e; }}
        .score {{ color: #27ae60; font-weight: bold; }}
        .high-score {{ color: #e74c3c; font-weight: bold; }}
        .details {{ margin: 10px 0; }}
        .label {{ font-weight: bold; }}
    </style>
</head>
<body>
    <h2>High-Priority Jobs Requiring Your Review</h2>
    <p>Found {len(jobs)} job(s) that match your criteria with high scores:</p>
"""
            
            for i, job in enumerate(jobs, 1):
                score_class = 'high-score' if job['overall_score'] >= 0.85 else 'score'
                
                body += f"""
    <div class="job">
        <div class="job-title">{i}. {job['title']}</div>
        <div class="company">{job['company']}</div>
        <div class="details">
            <span class="label">Location:</span> {job['location']}<br>
            <span class="label">Overall Score:</span> <span class="{score_class}">{job['overall_score']:.2f}</span><br>
            <span class="label">Skills Match:</span> {job['skills_match_score']:.2f} | 
            <span class="label">Salary:</span> {job['salary_score']:.2f} | 
            <span class="label">Company:</span> {job['company_score']:.2f} | 
            <span class="label">Location:</span> {job['location_score']:.2f}<br>
"""
                
                if job.get('salary_min') or job.get('salary_max'):
                    salary_range = f"${job.get('salary_min', 0):,} - ${job.get('salary_max', 0):,}"
                    body += f"            <span class='label'>Salary Range:</span> {salary_range}<br>\n"
                
                body += f"""
            <span class="label">URL:</span> <a href="{job['url']}">{job['url']}</a>
        </div>
    </div>
"""
            
            body += """
</body>
</html>
"""
            
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.sender_email
            msg['To'] = self.recipient_email
            
            html_part = MIMEText(body, 'html')
            msg.attach(html_part)
            
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.send_message(msg)
            
            print(f"✓ Email notification sent to {self.recipient_email}")
            
        except Exception as e:
            print(f"Error sending email notification: {e}")
    
    def save_to_file(self, jobs: List[Dict[str, Any]]):
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"high_priority_jobs_{timestamp}.txt"
        
        try:
            with open(filename, 'w') as f:
                f.write("HIGH PRIORITY JOBS REQUIRING HUMAN REVIEW\n")
                f.write("=" * 60 + "\n\n")
                
                for i, job in enumerate(jobs, 1):
                    f.write(f"{i}. {job['title']}\n")
                    f.write(f"   Company: {job['company']}\n")
                    f.write(f"   Location: {job['location']}\n")
                    f.write(f"   Overall Score: {job['overall_score']:.2f}\n")
                    f.write(f"   Skills Match: {job['skills_match_score']:.2f}\n")
                    f.write(f"   Salary Score: {job['salary_score']:.2f}\n")
                    f.write(f"   Company Score: {job['company_score']:.2f}\n")
                    f.write(f"   Location Score: {job['location_score']:.2f}\n")
                    
                    if job.get('salary_min') or job.get('salary_max'):
                        salary_range = f"${job.get('salary_min', 0):,} - ${job.get('salary_max', 0):,}"
                        f.write(f"   Salary Range: {salary_range}\n")
                    
                    f.write(f"   URL: {job['url']}\n")
                    f.write(f"   Discovered: {job.get('discovered_date', datetime.now())}\n")
                    f.write("\n" + "-" * 60 + "\n\n")
            
            print(f"✓ High-priority jobs saved to {filename}")
            
        except Exception as e:
            print(f"Error saving jobs to file: {e}")
