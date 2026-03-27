# Automated Job Search System

An intelligent job search automation system that crawls company career pages and job boards, filters and ranks opportunities based on your preferences, and helps you apply efficiently.

## Features

- **Automated Web Scraping** using OpenClaw (Claw) for:
  - Company career pages (Google, Meta, Amazon, etc.)
  - Job boards (LinkedIn, Indeed, Glassdoor)
  
- **Smart Filtering** based on:
  - Job titles (Principal Data Engineer, Data Engineer Tech Lead, etc.)
  - Salary requirements (location-specific)
  - Location preferences (Remote > DMV > Bay Area > Other)

- **Intelligent Ranking** using:
  - Skills match score (35%)
  - Salary fit (25%)
  - Company reputation (20%)
  - Location preference (20%)

- **AI-Powered Resume Customization**:
  - Automatically tailors your resume for each job
  - Generates custom cover letters
  - Uses OpenAI GPT-4 or Anthropic Claude

- **Scheduled Crawling**:
  - Runs multiple times per day (configurable)
  - Prevents duplicate job entries
  - Tracks crawl history

- **Notification System**:
  - Email alerts for high-priority jobs
  - Console notifications
  - Saves high-priority jobs to files

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Install Playwright (required by Claw)

```bash
playwright install
```

### 3. Configure Environment Variables

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env`:
```
OPENAI_API_KEY=your_openai_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# Optional: Email notifications
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SENDER_EMAIL=your_email@gmail.com
SENDER_PASSWORD=your_app_password
RECIPIENT_EMAIL=your_email@gmail.com

# Database
DATABASE_URL=sqlite:///jobs.db

# User preferences
USER_LOCATION=801 N Fairfax St, Alexandria, VA
USER_MIN_SALARY_REMOTE=200000
USER_MIN_SALARY_SF=300000
USER_MIN_SALARY_DMV=230000

# Crawl frequency (hours)
CRAWL_FREQUENCY_HOURS=6
```

### 4. Add Your Resume

Create a file named `resume.txt` in the project root with your resume content. This will be used as the base for AI customization.

### 5. Customize Configuration

Edit `config.yaml` to:
- Add/remove target companies
- Modify job titles you're searching for
- Update your skills list
- Adjust ranking weights
- Set salary thresholds

## Usage

### Run Once (Single Crawl)

```bash
python main.py once
```

This will:
1. Crawl all configured companies and job boards
2. Filter jobs based on your criteria
3. Rank jobs by fit
4. Save to database
5. Display top jobs

### Run Scheduled (Continuous)

```bash
python main.py schedule
```

This will:
1. Run an initial crawl
2. Schedule crawls every N hours (configured in `.env`)
3. Send notifications for high-priority jobs
4. Continue running until stopped (Ctrl+C)

### Interactive Mode

```bash
python main.py interactive
```

Interactive menu to:
- View high-priority jobs
- View auto-apply eligible jobs
- Prepare application packages (customized resume + cover letter)
- Mark jobs as reviewed/applied
- View detailed job information

## Project Structure

```
windsurf-project/
├── main.py                          # Main entry point
├── requirements.txt                 # Python dependencies
├── config.yaml                      # Configuration file
├── .env                            # Environment variables
├── resume.txt                      # Your base resume
├── jobs.db                         # SQLite database (created automatically)
├── src/
│   ├── models.py                   # Database models
│   ├── config_loader.py            # Configuration loader
│   ├── crawler.py                  # Main crawling orchestrator
│   ├── filters.py                  # Job filtering logic
│   ├── ranker.py                   # Job ranking system
│   ├── resume_customizer.py        # AI resume customization
│   ├── scheduler.py                # Scheduled crawling
│   ├── notifier.py                 # Notification system
│   ├── job_manager.py              # Job management utilities
│   └── scrapers/
│       ├── base_scraper.py         # Base scraper class
│       ├── company_scraper.py      # Company career page scrapers
│       └── job_board_scraper.py    # Job board scrapers
└── applications/                   # Generated application packages
```

## Configuration Details

### Target Job Titles

Default titles in `config.yaml`:
- Principal Data Engineer
- Data Engineer Tech Lead
- Data Engineer Senior Manager
- Senior Data Engineer
- Staff Data Engineer
- AI Engineer
- ML Engineer

### Salary Requirements

- **Remote**: $200k+ minimum
- **Bay Area**: $300k+ minimum
- **DMV Area**: $230k+ minimum
- **Other**: $250k+ minimum

### Location Preferences (Priority Order)

1. Remote (highest priority)
2. Within 30 minutes of Alexandria, VA
3. Bay Area
4. Other locations

### Ranking Thresholds

- **Human Review Required**: Score ≥ 0.75
- **Auto-Apply Eligible**: 0.60 ≤ Score < 0.75
- **Low Priority**: Score < 0.60

## Database Schema

The system uses SQLite with three main tables:

- **jobs**: Stores all discovered jobs with scores and metadata
- **companies**: Tracks company information and crawl status
- **crawl_logs**: Logs all crawl activities

## Workflow

### 1. Discovery Phase
- Crawl company career pages
- Crawl job boards
- Extract job details (title, company, location, salary, description)

### 2. Filtering Phase
- Match job titles against target titles
- Verify salary meets location-specific requirements
- Remove duplicates

### 3. Ranking Phase
- Calculate skills match score
- Evaluate salary fit
- Score company reputation
- Assess location preference
- Compute weighted overall score

### 4. Action Phase
- **High Priority (≥0.75)**: Notify for human review
- **Medium Priority (0.60-0.75)**: Eligible for auto-apply
- **Low Priority (<0.60)**: Store for reference

### 5. Application Phase
- Generate customized resume
- Create tailored cover letter
- Prepare application package

## Tips

1. **First Run**: Start with `python main.py once` to test configuration
2. **Resume Quality**: Provide a detailed base resume for better AI customization
3. **API Keys**: OpenAI or Anthropic API key required for resume customization
4. **Email Notifications**: Configure SMTP for email alerts (optional but recommended)
5. **Crawl Frequency**: Start with 6-hour intervals, adjust based on your needs
6. **Company List**: Focus on companies you're genuinely interested in to reduce noise

## Troubleshooting

### Claw/Playwright Issues
```bash
playwright install
```

### Database Locked
Stop all running instances and delete `jobs.db` to reset

### No Jobs Found
- Check your filter criteria in `config.yaml`
- Verify target companies have accessible career pages
- Review salary thresholds

### Email Notifications Not Working
- Use app-specific password for Gmail
- Enable "Less secure app access" or use OAuth2
- Check SMTP settings in `.env`

## Future Enhancements

- Auto-apply functionality with form filling
- LinkedIn Easy Apply integration
- Job application tracking dashboard
- Analytics on application success rates
- Browser extension for one-click applications
- Integration with ATS systems

## License

MIT License - Feel free to customize for your job search needs!

## Disclaimer

This tool is for personal use. Always review jobs before applying and ensure you comply with job board terms of service. Be respectful of rate limits and crawling policies.
