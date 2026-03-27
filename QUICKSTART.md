# Quick Start Guide

Get your automated job search system running in 5 minutes!

## Step 1: Install Dependencies (2 minutes)

```bash
# Install Python packages
pip install -r requirements.txt

# Install Playwright browsers (required by Claw)
playwright install
```

## Step 2: Configure (2 minutes)

### Create .env file
```bash
cp .env.example .env
```

### Edit .env - Add your API key (choose one):
```
# Option 1: Use OpenAI
OPENAI_API_KEY=sk-your-key-here

# Option 2: Use Anthropic
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

### Add your resume
Create `resume.txt` with your resume content (plain text format)

## Step 3: Customize Your Search (1 minute)

Edit `config.yaml` to match your preferences:

```yaml
user_profile:
  target_titles:
    - "Principal Data Engineer"
    - "Data Engineer Tech Lead"
    # Add more titles...
  
  location_preferences:
    home_address: "801 N Fairfax St, Alexandria, VA"  # Update this
```

## Step 4: Run! (30 seconds)

### Test with a single crawl:
```bash
python main.py once
```

### Start scheduled crawling:
```bash
python main.py schedule
```

### Use interactive mode:
```bash
python main.py interactive
```

## What Happens Next?

1. **Crawling**: System searches company career pages and job boards
2. **Filtering**: Removes jobs that don't match your criteria
3. **Ranking**: Scores jobs based on fit (0-1 scale)
4. **Notification**: Alerts you to high-priority jobs (score ≥ 0.75)
5. **Database**: Saves all jobs to `jobs.db` for tracking

## Expected Output

```
Starting full job crawl...
==================================================

Crawling Google...
Found 15 jobs at Google

Crawling Meta...
Found 12 jobs at Meta

...

Total jobs collected: 127
Jobs after filtering: 43
Jobs after ranking: 43

New jobs saved: 43 out of 43

==================================================
Crawl completed!

Top 5 jobs:

1. Principal Data Engineer at Databricks
   Score: 0.87
   Location: Remote
   URL: https://...
   ⭐ REQUIRES HUMAN REVIEW

2. Senior Data Engineer at Google
   Score: 0.82
   Location: San Francisco, CA
   URL: https://...
   ⭐ REQUIRES HUMAN REVIEW
```

## Interactive Mode Commands

Once in interactive mode, you can:

1. **View high-priority jobs** - Jobs requiring your review (score ≥ 0.75)
2. **View auto-apply jobs** - Medium-priority jobs (score 0.60-0.75)
3. **Prepare application** - Generate customized resume + cover letter
4. **Mark as reviewed** - Track which jobs you've looked at
5. **Mark as applied** - Track applications

## Tips for First Run

✅ **Start small**: Test with `python main.py once` first  
✅ **Check filters**: Review jobs in database to ensure filtering works  
✅ **Adjust config**: Tweak `config.yaml` based on results  
✅ **Set up email**: Add SMTP settings for notifications (optional)  
✅ **Review resume**: Ensure `resume.txt` is comprehensive  

## Common Issues

### "No jobs found"
- Check salary thresholds in `config.yaml`
- Verify target titles match actual job postings
- Some companies may have anti-scraping measures

### "Playwright not installed"
```bash
playwright install
```

### "API key error"
- Verify your OpenAI or Anthropic API key in `.env`
- Check you have credits/quota available

## Next Steps

1. Run scheduled crawls: `python main.py schedule`
2. Set crawl frequency in `.env` (default: every 6 hours)
3. Configure email notifications for alerts
4. Use interactive mode to manage applications
5. Customize ranking weights in `config.yaml`

## Need Help?

Check the full `README.md` for detailed documentation.

Happy job hunting! 🚀
