import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime
from src.crawler import JobCrawler
from src.config_loader import config
from src.notifier import JobNotifier

class JobScheduler:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.crawler = JobCrawler()
        self.notifier = JobNotifier()
        self.crawl_frequency_hours = config.get_crawl_frequency_hours()
    
    async def scheduled_crawl_task(self):
        print(f"\n{'='*60}")
        print(f"Scheduled crawl started at {datetime.now()}")
        print(f"{'='*60}\n")
        
        try:
            ranked_jobs = await self.crawler.run_full_crawl()
            
            high_priority_jobs = [job for job in ranked_jobs if job.get('requires_human_review')]
            auto_apply_jobs = [job for job in ranked_jobs if job.get('auto_apply_eligible')]
            
            if high_priority_jobs:
                print(f"\n🔔 Found {len(high_priority_jobs)} high-priority jobs requiring human review!")
                await self.notifier.notify_high_priority_jobs(high_priority_jobs)
            
            if auto_apply_jobs:
                print(f"\n✓ Found {len(auto_apply_jobs)} jobs eligible for auto-apply")
            
        except Exception as e:
            print(f"Error during scheduled crawl: {e}")
        
        print(f"\n{'='*60}")
        print(f"Scheduled crawl completed at {datetime.now()}")
        print(f"Next crawl in {self.crawl_frequency_hours} hours")
        print(f"{'='*60}\n")
    
    def start(self):
        self.scheduler.add_job(
            self.scheduled_crawl_task,
            trigger=IntervalTrigger(hours=self.crawl_frequency_hours),
            id='job_crawl',
            name='Periodic Job Crawl',
            replace_existing=True
        )
        
        self.scheduler.start()
        print(f"Scheduler started! Crawling every {self.crawl_frequency_hours} hours.")
        print("Press Ctrl+C to stop.\n")
    
    async def run_once_then_schedule(self):
        print("Running initial crawl...")
        await self.scheduled_crawl_task()
        
        self.start()
        
        try:
            while True:
                await asyncio.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            print("\nShutting down scheduler...")
            self.scheduler.shutdown()
