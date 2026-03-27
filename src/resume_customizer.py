from typing import Dict, Any
import os
from openai import OpenAI
from anthropic import Anthropic

class ResumeCustomizer:
    def __init__(self, use_anthropic: bool = False):
        self.use_anthropic = use_anthropic
        
        if use_anthropic:
            self.client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
        else:
            self.client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    
    def load_base_resume(self, resume_path: str = 'resume.txt') -> str:
        try:
            with open(resume_path, 'r') as f:
                return f.read()
        except FileNotFoundError:
            return ""
    
    def customize_resume_for_job(self, base_resume: str, job: Dict[str, Any]) -> str:
        job_title = job.get('title', '')
        company = job.get('company', '')
        description = job.get('description', '')
        
        prompt = f"""You are an expert resume writer. Customize the following resume to best match the job description below.

Job Title: {job_title}
Company: {company}
Job Description: {description}

Base Resume:
{base_resume}

Instructions:
1. Keep all factual information accurate - do not fabricate experience
2. Reorder and emphasize relevant skills and experiences
3. Adjust the summary/objective to align with the role
4. Highlight relevant technical skills mentioned in the job description
5. Use keywords from the job description naturally
6. Keep the resume concise and ATS-friendly
7. Maintain professional formatting

Return ONLY the customized resume text, no additional commentary."""

        if self.use_anthropic:
            response = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text
        else:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=3000
            )
            return response.choices[0].message.content
    
    def generate_cover_letter(self, base_resume: str, job: Dict[str, Any]) -> str:
        job_title = job.get('title', '')
        company = job.get('company', '')
        description = job.get('description', '')
        
        prompt = f"""Write a compelling cover letter for the following job application.

Job Title: {job_title}
Company: {company}
Job Description: {description}

Candidate Resume:
{base_resume}

Instructions:
1. Keep it concise (3-4 paragraphs)
2. Show genuine interest in the company and role
3. Highlight 2-3 most relevant achievements
4. Explain why you're a great fit
5. Professional but personable tone
6. Include a strong opening and closing

Return ONLY the cover letter text."""

        if self.use_anthropic:
            response = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text
        else:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.8,
                max_tokens=1500
            )
            return response.choices[0].message.content
