import json
import asyncio
import os
from typing import List, Dict, Any
from src.scrapers.base_scraper import get_openai_client

RESUME_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "resume.txt")

SYSTEM_PROMPT = """You are an expert recruiter and career coach evaluating job-candidate fit.
Given a candidate's resume and a list of jobs, score each job's fit accurately and critically.
Return ONLY valid JSON — no explanation, no markdown."""

USER_PROMPT_TEMPLATE = """## Candidate Resume
{resume}

## Candidate Preferences
- Target roles: Principal/Staff/Senior Data Engineer, Data Engineering Tech Lead, Data Engineering Manager/Senior Manager, Analytics Engineer, AI Engineer, AI Enablement Engineer, ML Engineer
- 8+ years data engineering experience, 3+ years people management/tech lead
- Location priority: Remote (ideal) > DMV area DC/MD/VA (great) > San Francisco Bay Area / California (ok)
- Minimum salary: Remote $200k+, DMV $230k+, Bay Area $300k+

## Scoring Instructions
Score each job 0.0–1.0 on these dimensions:
- **skills_match_score**: How closely the job's required tech stack, domain, and responsibilities match the candidate's actual experience. Penalize heavily for mismatches (e.g. pure software/backend/frontend roles, pure research/science, student/entry-level). Reward for DE stack: Spark, Airflow, Snowflake, Databricks, AWS/GCP/Azure, SQL, Python, dbt, Kafka, data pipelines, lakehouse.
- **seniority_match_score**: Does the title level match 8+ yrs DE experience + 3+ yrs management? Senior/Staff/Principal/Manager/Lead = 1.0. Mid-level = 0.5. Junior/entry = 0.0.
- **location_score**: Remote = 1.0. DMV (DC/MD/VA/Alexandria/Arlington) = 0.9. California/Bay Area = 0.7. Other US = 0.4.
- **salary_score**: If salary range listed and meets minimum for location = 1.0. Listed but below minimum = 0.2. Not listed = 0.5.
- **company_score**: Company quality, growth stage, tech reputation (FAANG/top AI = 1.0, strong mid-size tech = 0.7, unknown/startup = 0.4).
- **overall_score**: Weighted fit (skills 40%, seniority 25%, location 15%, salary 10%, company 10%). Be honest — a score above 0.7 means this is a genuinely strong match the candidate should prioritize.
- **salary_min / salary_max**: Use the `salary` field in the job data if provided. If not provided, look in the description for $, USD, pay range, base salary. Return as integer dollars (e.g. 200000). If a range, set min and max separately. If only one number, set both to that. If not found anywhere, return null for both.
- **summary**: Write 4-5 sentences covering: (1) what the role does day-to-day, (2) what team/product/system it owns, (3) the core technical stack and challenges, (4) what seniority/leadership is expected, (5) anything notable about scope or impact. Be specific and concrete. No filler phrases.
- **filter_out**: true if this job should be HARD-EXCLUDED regardless of score. Set true if ANY of: (1) salary is explicitly listed AND below candidate minimums (Remote <$200k, DMV <$230k, Bay Area <$300k); (2) location is clearly non-US; (3) role is clearly entry-level/intern/junior. Otherwise false.

## Jobs to Score
{jobs_json}

## Response Format
{{
  "scores": [
    {{
      "job_id": "...",
      "overall_score": 0.82,
      "skills_match_score": 0.85,
      "seniority_match_score": 0.90,
      "location_score": 1.0,
      "salary_score": 0.5,
      "company_score": 0.85,
      "salary_min": 200000,
      "salary_max": 280000,
      "filter_out": false,
      "summary": "2-3 sentence role summary here."
    }}
  ]
}}"""


class LLMScorer:
    def __init__(self):
        try:
            with open(RESUME_PATH) as f:
                self.resume = f.read()
        except FileNotFoundError:
            self.resume = "Resume not found."
        self.client = get_openai_client()

    def _load_feedback_examples(self) -> str:
        """Load past user-rated jobs to use as few-shot calibration examples."""
        try:
            from src.models import get_session, Job
            s = get_session()
            rated = s.query(Job).filter(
                Job.user_preference_score != None
            ).order_by(Job.feedback_date.desc()).limit(15).all()
            if not rated:
                return ""
            lines = ["\n## Your Past Feedback (use these to calibrate scores)\n"]
            for j in rated:
                lines.append(
                    f"- \"{j.title}\" @ {j.company} ({j.location or 'unknown location'})\n"
                    f"  Your ratings → Skills:{j.user_skills_rating}/5  Company:{j.user_company_rating}/5  "
                    f"Location:{j.user_location_rating}/5  Salary:{j.user_salary_rating}/5  "
                    f"Personal preference:{j.user_preference_score}/5\n"
                    f"  Your notes: {j.user_notes or 'none'}\n"
                    f"  Description snippet: {(j.description or '')[:300]}\n"
                )
            return "\n".join(lines)
        except Exception:
            return ""

    async def score_jobs(self, jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Score all jobs via LLM in batches of 25. Returns jobs with scores merged in."""
        if not jobs:
            return jobs

        print(f"  LLM scoring {len(jobs)} jobs in batches of 25...")
        batches = [jobs[i:i+25] for i in range(0, len(jobs), 25)]

        # Run up to 3 batches concurrently
        all_score_maps = {}
        for chunk_start in range(0, len(batches), 3):
            chunk = batches[chunk_start:chunk_start+3]
            results = await asyncio.gather(*[self._score_batch(b) for b in chunk])
            for score_map in results:
                all_score_maps.update(score_map)
            if chunk_start + 3 < len(batches):
                await asyncio.sleep(2)  # brief pause between chunks

        # Merge scores back into job dicts, drop LLM-flagged hard exclusions
        from src.config_loader import config
        kept = []
        filtered_out = 0
        for job in jobs:
            s = all_score_maps.get(job["job_id"], {})
            # Hard filter: LLM says exclude (below-min salary, non-US, entry-level)
            if s.get("filter_out") is True:
                filtered_out += 1
                continue
            job["skills_match_score"] = s.get("skills_match_score", 0.3)
            job["salary_score"]       = s.get("salary_score", 0.5)
            job["company_score"]      = s.get("company_score", 0.5)
            job["location_score"]     = s.get("location_score", 0.5)
            job["overall_score"]      = s.get("overall_score", 0.3)
            job["requires_human_review"]  = job["overall_score"] >= config.human_review_threshold
            job["auto_apply_eligible"]    = config.auto_apply_threshold <= job["overall_score"] < config.human_review_threshold
            # Salary from LLM (overrides regex extraction if found)
            if s.get("salary_min"):
                job["salary_min"] = int(s["salary_min"])
            if s.get("salary_max"):
                job["salary_max"] = int(s["salary_max"])
            # Summary from LLM
            if s.get("summary"):
                job["summary"] = s["summary"]
            kept.append(job)

        if filtered_out:
            print(f"  LLM hard-filtered {filtered_out} jobs (salary/location/level mismatch)")
        kept.sort(key=lambda x: x.get("overall_score", 0), reverse=True)
        return kept

    async def _score_batch(self, jobs: List[Dict[str, Any]]) -> Dict[str, Dict]:
        """Score one batch, return {job_id: score_dict}."""
        job_list = [
            {
                "job_id":      j["job_id"],
                "title":       j.get("title", ""),
                "company":     j.get("company", ""),
                "location":    j.get("location", ""),
                "salary":      f"${j['salary_min']:,}–${j['salary_max']:,}" if j.get("salary_min") is not None else "not listed",
                "description": (j.get("description") or "")[:1500],
            }
            for j in jobs
        ]

        feedback_section = self._load_feedback_examples()
        prompt = USER_PROMPT_TEMPLATE.format(
            resume=self.resume,
            jobs_json=json.dumps(job_list, indent=2),
        ) + feedback_section

        for attempt in range(4):
            try:
                resp = await self.client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user",   "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0,
                )
                data = json.loads(resp.choices[0].message.content)
                return {s["job_id"]: s for s in data.get("scores", [])}
            except Exception as e:
                wait = 10 * (attempt + 1)
                print(f"  LLM score error (attempt {attempt+1}/4): {e} — retrying in {wait}s")
                await asyncio.sleep(wait)

        # Fallback: neutral scores for all jobs in batch
        return {j["job_id"]: {} for j in jobs}
