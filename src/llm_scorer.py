import json
import asyncio
import os
from typing import List, Dict, Any
from src.scrapers.base_scraper import get_openai_client
from src.job_board import role_alignment_bonus

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
- Strongest fit themes: data platform, ETL/ELT, Spark, Airflow, warehouses/lakehouse, analytics engineering, ML/AI platform, applied AI engineering, pipeline ownership, technical leadership
- Important ranking rule: the first jobs shown to the candidate should feel like "this is exactly my lane." Generic software roles and niche ML domains should not outrank strong data engineering jobs.

## Scoring Instructions
Score each job 0.0–1.0 on these dimensions:
- **skills_match_score**: How closely the job's required tech stack, domain, and responsibilities match the candidate's actual experience. Penalize heavily for mismatches. Strong positives: Data Engineer, Analytics Engineer, ML/AI platform, applied AI engineering, data infrastructure, warehouse/lakehouse, experimentation/data platform, pipeline ownership. Strong negatives: generic backend/frontend/mobile, pure research scientist, computer vision/perception/autonomy specialties, ads auction/ranking roles that are mostly ML modeling rather than data engineering.
- **seniority_match_score**: Does the title level match 8+ yrs DE experience + 3+ yrs management? Senior/Staff/Principal/Manager/Lead = 1.0. Mid-level = 0.5. Junior/entry = 0.0.
- **location_score**: Remote = 1.0. DMV (DC/MD/VA/Alexandria/Arlington) = 0.9. California/Bay Area = 0.7. Other US = 0.4.
- **salary_score**: If salary range listed and meets minimum for location = 1.0. Listed but below minimum = 0.2. Not listed = 0.5.
- **company_score**: Company quality, growth stage, tech reputation (FAANG/top AI = 1.0, strong mid-size tech = 0.7, unknown/startup = 0.4).
- **overall_score**: Weighted fit (skills 45%, seniority 20%, location 15%, salary 10%, company 10%). Be honest and conservative. A score above 0.8 means this should be one of the first jobs the candidate sees on the front page. A score below 0.6 should not feel like a "perfect next job."
- **salary_min / salary_max**: Use the `salary` field in the job data if provided. If not provided, look in the description for $, USD, pay range, base salary. Return as integer dollars (e.g. 200000). If a range, set min and max separately. If only one number, set both to that. If not found anywhere, return null for both.
- **summary**: Write 4-5 sentences covering: (1) what the role does day-to-day, (2) what team/product/system it owns, (3) the core technical stack and challenges, (4) what seniority/leadership is expected, (5) anything notable about scope or impact. Be specific and concrete. No filler phrases.
- **filter_out**: true if this job should be HARD-EXCLUDED regardless of score. Set true if ANY of: (1) salary is explicitly listed AND below candidate minimums (Remote <$200k, DMV <$230k, Bay Area <$300k); (2) location is clearly non-US; (3) role is clearly entry-level/intern/junior; (4) role is clearly outside the target lane after considering the user's explicit past "not fit" feedback.

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
        self.client = None
        self.client_error = None
        try:
            self.client = get_openai_client()
        except Exception as e:
            self.client_error = str(e)

    def _load_feedback_examples(self) -> str:
        """Load past user-rated jobs to use as few-shot calibration examples."""
        try:
            from src.models import get_session, Job
            s = get_session()
            rated = s.query(Job).filter(
                Job.user_preference_score != None
            ).order_by(Job.feedback_date.desc()).limit(12).all()
            not_fit = s.query(Job).filter(
                (Job.not_fit == True) | (Job.not_fit_reason != None)
            ).order_by(Job.not_fit_feedback_at.desc(), Job.feedback_date.desc()).limit(8).all()

            if not rated and not not_fit:
                return ""

            lines = []
            if rated:
                lines.append("\n## Your Past Feedback (use these to calibrate scores)\n")
                for j in rated:
                    lines.append(
                        f"- \"{j.title}\" @ {j.company} ({j.location or 'unknown location'})\n"
                        f"  Your ratings -> Skills:{j.user_skills_rating}/5  Company:{j.user_company_rating}/5  "
                        f"Location:{j.user_location_rating}/5  Salary:{j.user_salary_rating}/5  "
                        f"Personal preference:{j.user_preference_score}/5\n"
                        f"  Your notes: {j.user_notes or 'none'}\n"
                        f"  Description snippet: {(j.description or '')[:300]}\n"
                    )

            if not_fit:
                lines.append("\n## Jobs The Candidate Explicitly Marked Not Fit\n")
                for j in not_fit:
                    lines.append(
                        f"- \"{j.title}\" @ {j.company} ({j.location or 'unknown location'})\n"
                        f"  Not fit reason: {j.not_fit_reason or j.hidden_reason or j.user_notes or 'candidate rejected this role'}\n"
                        f"  Treat similar title/domain patterns as low-priority or filter_out if they clearly match this same problem.\n"
                    )

            s.close()
            return "\n".join(lines)
        except Exception:
            return ""

    def _load_not_fit_keywords(self) -> set[str]:
        try:
            from src.models import get_session, Job

            session = get_session()
            rejected_jobs = session.query(Job).filter(
                (Job.not_fit == True) | (Job.not_fit_reason != None)
            ).order_by(Job.not_fit_feedback_at.desc(), Job.feedback_date.desc()).limit(20).all()

            if not rejected_jobs:
                session.close()
                return set()

            candidate_terms = [
                "ads", "auction", "perception", "simulation", "autonomy", "vision",
                "frontend", "front-end", "mobile", "research", "scientist",
                "support", "sales", "clearance", "security", "consumer",
            ]
            terms = set()
            for job in rejected_jobs:
                text = " ".join(
                    filter(
                        None,
                        [job.title or "", job.not_fit_reason or "", job.user_notes or ""],
                    )
                ).lower()
                for term in candidate_terms:
                    if term in text:
                        terms.add(term)

            session.close()
            return terms
        except Exception:
            return set()

    async def score_jobs(self, jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Score all jobs via LLM in batches of 25. Returns jobs with scores merged in."""
        if not jobs:
            return jobs

        if self.client is None:
            print(f"  LLM unavailable, using heuristic scorer: {self.client_error}")
            return self._heuristic_score_jobs(jobs)

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

    def _heuristic_score_jobs(self, jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        from src.config_loader import config
        not_fit_keywords = self._load_not_fit_keywords()

        def clamp(value: float) -> float:
            return max(0.0, min(1.0, value))

        scored = []
        for job in jobs:
            title = (job.get("title") or "").lower()
            description = (job.get("description") or "").lower()
            location = (job.get("location") or "").lower()
            title_bonus = role_alignment_bonus(title)
            negative_feedback_hits = sum(
                1 for term in not_fit_keywords if term in title or term in description
            )

            skills_score = clamp(0.58 + (title_bonus * 1.4) - (negative_feedback_hits * 0.12))
            if any(token in title for token in ["data engineer", "analytics engineer", "data platform", "applied ai", "ai engineer"]):
                skills_score = max(skills_score, 0.78)

            seniority_score = 0.95 if any(token in title for token in ["principal", "staff", "lead", "manager", "senior"]) else 0.65
            if any(token in title for token in ["intern", "junior", "associate"]):
                seniority_score = 0.1

            if job.get("is_remote") or "remote" in location:
                location_score = 1.0
            elif any(token in location for token in ["alexandria", "arlington", "washington", "virginia", "maryland", "dc"]):
                location_score = 0.9
            elif any(token in location for token in ["san francisco", "bay area", "palo alto", "mountain view", "san jose", "california"]):
                location_score = 0.7
            else:
                location_score = 0.45

            salary_min = job.get("salary_min")
            salary_max = job.get("salary_max")
            if salary_min is None and salary_max is None:
                salary_score = 0.5
            else:
                listed_salary = salary_max or salary_min or 0
                threshold = 200000 if location_score >= 1.0 else 230000 if location_score >= 0.9 else 300000 if location_score >= 0.7 else 250000
                salary_score = 1.0 if listed_salary >= threshold else 0.2

            company_score = 0.75 if any(token in job.get("company", "").lower() for token in ["google", "meta", "amazon", "openai", "anthropic", "snowflake", "databricks"]) else 0.6
            overall = clamp(
                skills_score * 0.45
                + seniority_score * 0.20
                + location_score * 0.15
                + salary_score * 0.10
                + company_score * 0.10
            )
            overall = clamp(overall - (negative_feedback_hits * 0.08))

            job["skills_match_score"] = skills_score
            job["salary_score"] = salary_score
            job["company_score"] = company_score
            job["location_score"] = location_score
            job["overall_score"] = overall
            job["requires_human_review"] = overall >= config.human_review_threshold
            job["auto_apply_eligible"] = config.auto_apply_threshold <= overall < config.human_review_threshold
            job.setdefault("summary", (job.get("description") or "")[:280] or None)
            scored.append(job)

        scored.sort(key=lambda x: x.get("overall_score", 0), reverse=True)
        return scored

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
