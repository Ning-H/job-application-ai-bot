import asyncio
import sys
from src.models import init_db
from src.scheduler import JobScheduler
from src.crawler import JobCrawler
from src.job_manager import JobManager

async def run_once():
    print("Initializing database...")
    init_db()
    
    crawler = JobCrawler()
    await crawler.run_full_crawl()

async def run_scheduled():
    print("Initializing database...")
    init_db()
    
    scheduler = JobScheduler()
    await scheduler.run_once_then_schedule()

def interactive_mode():
    print("Initializing database...")
    init_db()
    
    manager = JobManager()
    
    while True:
        print("\n" + "="*60)
        print("JOB SEARCH MANAGER - Interactive Mode")
        print("="*60)
        print("1. View high-priority jobs (requires human review)")
        print("2. View auto-apply eligible jobs")
        print("3. View all new jobs")
        print("4. Prepare application package for a job")
        print("5. Mark job as reviewed")
        print("6. Mark job as applied")
        print("7. View job details")
        print("8. Exit")
        print("="*60)
        
        choice = input("\nEnter your choice (1-8): ").strip()
        
        if choice == '1':
            jobs = manager.get_high_priority_jobs()
            if not jobs:
                print("\nNo high-priority jobs found.")
                continue
            
            print(f"\nFound {len(jobs)} high-priority jobs:\n")
            for i, job in enumerate(jobs, 1):
                print(f"{i}. {job.title} at {job.company}")
                print(f"   Score: {job.overall_score:.2f} | Location: {job.location}")
                print(f"   Job ID: {job.job_id}\n")
        
        elif choice == '2':
            jobs = manager.get_auto_apply_jobs()
            if not jobs:
                print("\nNo auto-apply eligible jobs found.")
                continue
            
            print(f"\nFound {len(jobs)} auto-apply eligible jobs:\n")
            for i, job in enumerate(jobs, 1):
                print(f"{i}. {job.title} at {job.company}")
                print(f"   Score: {job.overall_score:.2f} | Location: {job.location}")
                print(f"   Job ID: {job.job_id}\n")
        
        elif choice == '3':
            jobs = manager.get_new_jobs()
            if not jobs:
                print("\nNo new jobs found.")
                continue
            
            print(f"\nFound {len(jobs)} new jobs:\n")
            for i, job in enumerate(jobs, 1):
                print(f"{i}. {job.title} at {job.company}")
                print(f"   Score: {job.overall_score:.2f} | Location: {job.location}")
                print(f"   Job ID: {job.job_id}\n")
        
        elif choice == '4':
            job_id = input("\nEnter job ID: ").strip()
            manager.prepare_application_package(job_id)
        
        elif choice == '5':
            job_id = input("\nEnter job ID: ").strip()
            decision = input("Decision (reviewed/interested/not_interested): ").strip()
            manager.mark_as_reviewed(job_id, decision)
        
        elif choice == '6':
            job_id = input("\nEnter job ID: ").strip()
            manager.mark_as_applied(job_id)
        
        elif choice == '7':
            job_id = input("\nEnter job ID: ").strip()
            job = manager.get_job_by_id(job_id)
            if job:
                manager.display_job_details(job)
            else:
                print(f"\nJob {job_id} not found.")
        
        elif choice == '8':
            print("\nExiting...")
            break
        
        else:
            print("\nInvalid choice. Please try again.")

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python main.py once          - Run crawl once and exit")
        print("  python main.py schedule      - Run scheduled crawls")
        print("  python main.py interactive   - Interactive job management mode")
        sys.exit(1)
    
    mode = sys.argv[1].lower()
    
    if mode == 'once':
        asyncio.run(run_once())
    elif mode == 'schedule':
        asyncio.run(run_scheduled())
    elif mode == 'interactive':
        interactive_mode()
    else:
        print(f"Unknown mode: {mode}")
        print("Valid modes: once, schedule, interactive")
        sys.exit(1)

if __name__ == '__main__':
    main()
