from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text, JSON
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
    job_id = Column(String, unique=True, nullable=False)
    title = Column(String, nullable=False)
    company = Column(String, nullable=False)
    location = Column(String)
    salary_min = Column(Integer)
    salary_max = Column(Integer)
    description = Column(Text)
    url = Column(String, nullable=False)
    source = Column(String)
    posted_date = Column(DateTime)
    discovered_date = Column(DateTime, default=datetime.utcnow)
    
    is_remote = Column(Boolean, default=False)
    location_type = Column(String)
    
    skills_match_score = Column(Float)
    salary_score = Column(Float)
    company_score = Column(Float)
    location_score = Column(Float)
    overall_score = Column(Float)
    
    status = Column(String, default='new')
    applied = Column(Boolean, default=False)
    applied_date = Column(DateTime)
    
    requires_human_review = Column(Boolean, default=False)
    auto_apply_eligible = Column(Boolean, default=False)
    
    metadata = Column(JSON)

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
    return engine

def get_session():
    engine = get_engine()
    Session = sessionmaker(bind=engine)
    return Session()
