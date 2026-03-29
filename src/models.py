from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text, JSON, text, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

Base = declarative_base()

class Job(Base):
    __tablename__ = 'jobs'
    
    id = Column(Integer, primary_key=True)
    job_id = Column(String, unique=True, nullable=False, index=True)
    title = Column(String, nullable=False)
    company = Column(String, nullable=False)
    location = Column(String)
    salary_min = Column(Integer)
    salary_max = Column(Integer)
    description = Column(Text)
    url = Column(String, nullable=False)
    source = Column(String)
    posted_date = Column(DateTime, index=True)
    discovered_date = Column(DateTime, default=datetime.utcnow)
    first_seen_at = Column(DateTime, default=datetime.utcnow, index=True)
    last_seen_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    is_remote = Column(Boolean, default=False)
    location_type = Column(String)
    
    skills_match_score = Column(Float)
    salary_score = Column(Float)
    company_score = Column(Float)
    location_score = Column(Float)
    overall_score = Column(Float, index=True)
    
    status = Column(String, default='new', index=True)
    applied = Column(Boolean, default=False, index=True)
    applied_date = Column(DateTime)
    reviewed_at = Column(DateTime, index=True)
    last_viewed_at = Column(DateTime)
    view_count = Column(Integer, default=0)
    resume_generated_at = Column(DateTime)
    hidden = Column(Boolean, default=False, index=True)
    hidden_reason = Column(Text)
    not_fit = Column(Boolean, default=False, index=True)
    not_fit_reason = Column(Text)
    not_fit_feedback_at = Column(DateTime)
    
    requires_human_review = Column(Boolean, default=False, index=True)
    auto_apply_eligible = Column(Boolean, default=False)
    
    summary = Column(Text)   # AI-generated summary
    extra_data = Column(JSON)

    # User feedback (1–5 ratings, saved after manual review)
    user_skills_rating    = Column(Float)   # how well skills match
    user_company_rating   = Column(Float)   # company appeal
    user_location_rating  = Column(Float)   # location fit
    user_salary_rating    = Column(Float)   # salary satisfaction
    user_preference_score = Column(Float)   # overall personal preference
    user_notes            = Column(Text)    # free-text reasoning
    feedback_date         = Column(DateTime)
    
    # Composite index for common query patterns
    __table_args__ = (
        Index('ix_job_status_score', 'status', 'overall_score'),
        Index('ix_job_active_board', 'hidden', 'not_fit', 'applied', 'overall_score'),
    )

class Company(Base):
    __tablename__ = 'companies'
    
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    careers_url = Column(String)
    priority = Column(String)
    reputation_score = Column(Float, default=0.5)
    last_crawled = Column(DateTime)
    crawl_success = Column(Boolean, default=True)

class CrawlLog(Base):
    __tablename__ = 'crawl_logs'
    
    id = Column(Integer, primary_key=True)
    source = Column(String, nullable=False)
    crawl_date = Column(DateTime, default=datetime.utcnow)
    jobs_found = Column(Integer, default=0)
    new_jobs = Column(Integer, default=0)
    success = Column(Boolean, default=True)
    error_message = Column(Text)

def get_engine():
    database_url = os.getenv('DATABASE_URL', 'sqlite:///jobs.db')
    return create_engine(database_url)

def init_db():
    engine = get_engine()
    Base.metadata.create_all(engine)
    # Add new columns to existing DBs without losing data
    # Using a whitelist of allowed columns to avoid SQL injection
    allowed_columns = {
        "summary": "TEXT",
        "user_skills_rating": "REAL",
        "user_company_rating": "REAL",
        "user_location_rating": "REAL",
        "user_salary_rating": "REAL",
        "user_preference_score": "REAL",
        "user_notes": "TEXT",
        "feedback_date": "DATETIME",
        "first_seen_at": "DATETIME",
        "last_seen_at": "DATETIME",
        "reviewed_at": "DATETIME",
        "last_viewed_at": "DATETIME",
        "view_count": "INTEGER DEFAULT 0",
        "resume_generated_at": "DATETIME",
        "hidden": "BOOLEAN DEFAULT 0",
        "hidden_reason": "TEXT",
        "not_fit": "BOOLEAN DEFAULT 0",
        "not_fit_reason": "TEXT",
        "not_fit_feedback_at": "DATETIME",
    }
    
    with engine.connect() as conn:
        for col_name, col_type in allowed_columns.items():
            try:
                # Safe: col_name and col_type are from a controlled whitelist
                conn.execute(text(f"ALTER TABLE jobs ADD COLUMN {col_name} {col_type}"))
                conn.commit()
            except Exception:
                # Column likely already exists, continue
                pass
        for stmt in [
            "CREATE INDEX IF NOT EXISTS ix_jobs_first_seen_at ON jobs (first_seen_at)",
            "CREATE INDEX IF NOT EXISTS ix_jobs_last_seen_at ON jobs (last_seen_at)",
            "CREATE INDEX IF NOT EXISTS ix_jobs_reviewed_at ON jobs (reviewed_at)",
            "CREATE INDEX IF NOT EXISTS ix_jobs_active_board ON jobs (hidden, not_fit, applied, overall_score)",
            "UPDATE jobs SET first_seen_at = COALESCE(first_seen_at, discovered_date, CURRENT_TIMESTAMP)",
            "UPDATE jobs SET last_seen_at = COALESCE(last_seen_at, discovered_date, CURRENT_TIMESTAMP)",
            "UPDATE jobs SET view_count = COALESCE(view_count, 0)",
            "UPDATE jobs SET hidden = COALESCE(hidden, 0)",
            "UPDATE jobs SET not_fit = COALESCE(not_fit, 0)",
            "UPDATE jobs SET reviewed_at = COALESCE(reviewed_at, feedback_date, applied_date)",
        ]:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass
    return engine

def get_session():
    engine = get_engine()
    Session = sessionmaker(bind=engine)
    return Session()
