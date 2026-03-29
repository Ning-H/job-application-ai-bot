from typing import List, Dict, Any, Optional
from src.models import Job, get_session
from src.resume_customizer import ResumeCustomizer
from datetime import datetime
import os
from sqlalchemy import or_

from src.job_board import board_rank_score

class JobManager:
    def __init__(self):
        self.session = get_session()
        self.resume_customizer = ResumeCustomizer()
        self.base_resume = self.resume_customizer.load_base_resume()

    def _active_query(self):
        return self.session.query(Job).filter(
            or_(Job.hidden == False, Job.hidden == None),
            or_(Job.not_fit == False, Job.not_fit == None),
        )

    def _rank_jobs(self, jobs: List[Job], limit: int) -> List[Job]:
        ranked = sorted(jobs, key=board_rank_score, reverse=True)
        return ranked[:limit]
    
    def get_new_jobs(self, limit: int = 50) -> List[Job]:
        jobs = self._active_query().filter(
            Job.applied != True,
            or_(Job.reviewed_at == None, Job.status == 'new')
        ).all()
        return self._rank_jobs(jobs, limit)
    
    def get_high_priority_jobs(self, limit: int = 20) -> List[Job]:
        jobs = self._active_query().filter(
            Job.requires_human_review == True,
            Job.applied != True
        ).all()
        return self._rank_jobs(jobs, limit)
    
    def get_auto_apply_jobs(self, limit: int = 30) -> List[Job]:
        jobs = self._active_query().filter(
            Job.auto_apply_eligible == True,
            Job.applied == False
        ).all()
        return self._rank_jobs(jobs, limit)
    
    def get_job_by_id(self, job_id: str) -> Optional[Job]:
        return self.session.query(Job).filter_by(job_id=job_id).first()
    
    def mark_as_reviewed(self, job_id: str, decision: str = 'reviewed'):
        job = self.get_job_by_id(job_id)
        if job:
            job.status = decision or 'reviewed'
            job.reviewed_at = job.reviewed_at or datetime.utcnow()
            job.last_viewed_at = datetime.utcnow()
            job.view_count = (job.view_count or 0) + 1
            self.session.commit()
            print(f"Job {job_id} marked as {job.status}")

    def mark_as_viewed(self, job_id: str, mark_reviewed: bool = True):
        job = self.get_job_by_id(job_id)
        if job:
            now = datetime.utcnow()
            job.last_viewed_at = now
            job.view_count = (job.view_count or 0) + 1
            if mark_reviewed:
                job.reviewed_at = job.reviewed_at or now
                if job.status in (None, '', 'new'):
                    job.status = 'reviewed'
            self.session.commit()
    
    def mark_as_applied(self, job_id: str):
        job = self.get_job_by_id(job_id)
        if job:
            now = datetime.utcnow()
            job.applied = True
            job.applied_date = now
            job.reviewed_at = job.reviewed_at or now
            job.status = 'applied'
            self.session.commit()
            print(f"Job {job_id} marked as applied")

    def mark_as_not_fit(self, job_id: str, reason: str = ""):
        job = self.get_job_by_id(job_id)
        if job:
            now = datetime.utcnow()
            reason = reason.strip()
            job.not_fit = True
            job.hidden = True
            job.status = 'not_fit'
            job.not_fit_reason = reason or None
            job.hidden_reason = reason or job.hidden_reason
            job.not_fit_feedback_at = now
            job.reviewed_at = job.reviewed_at or now
            if job.user_preference_score is None:
                job.user_preference_score = 1
            if reason and not job.user_notes:
                job.user_notes = reason
            self.session.commit()
            print(f"Job {job_id} removed from the board as not fit")
    
    def customize_resume_for_job(self, job_id: str, output_path: str = None) -> str:
        job = self.get_job_by_id(job_id)
        if not job:
            print(f"Job {job_id} not found")
            return None
        
        job_dict = {
            'title': job.title,
            'company': job.company,
            'description': job.description or '',
            'url': job.url
        }
        
        customized_resume = self.resume_customizer.customize_resume_for_job(
            self.base_resume,
            job_dict
        )
        
        if output_path:
            with open(output_path, 'w') as f:
                f.write(customized_resume)
            print(f"Customized resume saved to {output_path}")

        job.resume_generated_at = datetime.utcnow()
        job.reviewed_at = job.reviewed_at or datetime.utcnow()
        if job.status in (None, '', 'new'):
            job.status = 'reviewed'
        self.session.commit()
        
        return customized_resume
    
    def generate_cover_letter_for_job(self, job_id: str, output_path: str = None) -> str:
        job = self.get_job_by_id(job_id)
        if not job:
            print(f"Job {job_id} not found")
            return None
        
        job_dict = {
            'title': job.title,
            'company': job.company,
            'description': job.description or '',
            'url': job.url
        }
        
        cover_letter = self.resume_customizer.generate_cover_letter(
            self.base_resume,
            job_dict
        )
        
        if output_path:
            with open(output_path, 'w') as f:
                f.write(cover_letter)
            print(f"Cover letter saved to {output_path}")

        job.reviewed_at = job.reviewed_at or datetime.utcnow()
        if job.status in (None, '', 'new'):
            job.status = 'reviewed'
        self.session.commit()
        
        return cover_letter
    
    def prepare_application_package(self, job_id: str, output_dir: str = 'applications'):
        os.makedirs(output_dir, exist_ok=True)
        
        job = self.get_job_by_id(job_id)
        if not job:
            print(f"Job {job_id} not found")
            return
        
        safe_company = job.company.replace(' ', '_').replace('/', '_')
        safe_title = job.title.replace(' ', '_').replace('/', '_')[:50]
        
        resume_path = os.path.join(output_dir, f"{safe_company}_{safe_title}_resume.txt")
        cover_letter_path = os.path.join(output_dir, f"{safe_company}_{safe_title}_cover_letter.txt")
        
        print(f"\nPreparing application package for: {job.title} at {job.company}")
        print(f"Score: {job.overall_score:.2f}")
        print(f"URL: {job.url}\n")
        
        self.customize_resume_for_job(job_id, resume_path)
        self.generate_cover_letter_for_job(job_id, cover_letter_path)
        
        print(f"\n✓ Application package ready in {output_dir}/")
        print(f"  - Resume: {resume_path}")
        print(f"  - Cover Letter: {cover_letter_path}")
        
        return {
            'resume_path': resume_path,
            'cover_letter_path': cover_letter_path,
            'job_url': job.url
        }
    
    def display_job_details(self, job: Job):
        print("\n" + "="*60)
        print(f"Title: {job.title}")
        print(f"Company: {job.company}")
        print(f"Location: {job.location}")
        print(f"Remote: {'Yes' if job.is_remote else 'No'}")
        
        if job.salary_min or job.salary_max:
            print(f"Salary Range: ${job.salary_min or 0:,} - ${job.salary_max or 0:,}")
        
        print(f"\nScores:")
        print(f"  Overall: {job.overall_score:.2f}")
        print(f"  Skills Match: {job.skills_match_score:.2f}")
        print(f"  Salary: {job.salary_score:.2f}")
        print(f"  Company: {job.company_score:.2f}")
        print(f"  Location: {job.location_score:.2f}")
        
        print(f"\nStatus: {job.status}")
        print(f"Applied: {'Yes' if job.applied else 'No'}")
        print(f"First Seen: {job.first_seen_at or job.discovered_date}")
        print(f"Last Pulled: {job.last_seen_at or job.discovered_date}")
        print(f"Reviewed: {job.reviewed_at or 'No'}")
        print(f"Not Fit: {'Yes' if job.not_fit else 'No'}")

        print(f"\nURL: {job.url}")
        
        if job.description:
            print(f"\nDescription (first 500 chars):")
            print(job.description[:500] + "..." if len(job.description) > 500 else job.description)
        
        print("="*60 + "\n")
