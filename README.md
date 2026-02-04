# LinkedIn Job Extractor Bot

A Python-based bot that automatically extracts LinkedIn job postings and sends them to your backend API. Built with Selenium and anti-detection features to avoid bot detection.

## Features

- 🤖 **Automated Job Extraction** - Searches LinkedIn and extracts job details
- 🔒 **Anti-Detection** - Uses undetected-chromedriver and selenium-stealth
- 🌐 **API Integration** - Sends extracted jobs to your backend API
- 📊 **Metrics Tracking** - Detailed reports of extraction runs
- ⏰ **Scheduling** - Run manually or schedule daily extractions
- 💾 **Duplicate Prevention** - Tracks extracted jobs to avoid re-processing

## Prerequisites

- Python 3.10 or higher
- Google Chrome browser
- Backend API for storing job data

## Installation

1. **Clone the repository**
```bash
git clone <your-repo-url>
cd project-bot-easy-apply-python-webdriver
```

2. **Create virtual environment**
```bash
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # macOS/Linux
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Configure environment variables**

Copy `.env.example` to `.env` and add your credentials:
```bash
SECRET_KEY=your_secret_key_here
WBL_API_URL=https://api.whitebox-learning.com/api
API_TOKEN=your_api_token_here
```

5. **Configure candidates**

Edit `candidate.yaml` with your LinkedIn credentials and job search criteria:
```yaml
candidates:
  - candidate_id: "candidate_001"
    name: "Your Name"
    linkedin_username: "your_email@example.com"
    linkedin_password: "your_password"
    keywords:
      - "AI/ML"
      - "Software Engineer"
    locations:
      - "94566"  # Zip codes
      - "10001"
    run_extract_linkedin_jobs: true
```

## Usage

### Run Immediately
```bash
python run_now.py
```

### Schedule Daily Runs (8:20 AM)
```bash
python scheduler.py
```

### Windows Task Scheduler
1. Open Task Scheduler
2. Create new task
3. Set action to run `trigger_bot.bat`
4. Set trigger to daily at 8:20 AM

## Project Structure

```
project-bot-easy-apply-python-webdriver/
├── bot/                    # Core bot modules
│   ├── api/               # API client
│   ├── core/              # Browser and session management
│   ├── discovery/         # Job extraction logic
│   ├── persistence/       # Data storage
│   └── utils/             # Utilities and helpers
├── data/                  # Data storage
│   ├── exports/           # CSV exports
│   └── profiles/          # Browser profiles
├── daily_extractor.py     # Main extraction script
├── scheduler.py           # Scheduling script
├── run_now.py             # Manual run script
├── candidate.yaml         # Candidate configuration
├── .env                   # Environment variables (not in Git)
├── .env.example           # Environment template
└── requirements.txt       # Python dependencies
```

## Configuration

### Environment Variables (`.env`)

| Variable | Description | Required |
|----------|-------------|----------|
| `SECRET_KEY` | API secret key | Yes |
| `WBL_API_URL` | Backend API URL | Yes |
| `API_TOKEN` | API authentication token | Yes |
| `DISTANCE_MILES` | Job search radius | No (default: 50) |
| `DRY_RUN` | Test mode without saving | No (default: false) |

### Candidate Settings (`candidate.yaml`)

- `candidate_id`: Unique identifier
- `name`: Candidate name
- `linkedin_username`: LinkedIn email
- `linkedin_password`: LinkedIn password
- `keywords`: Job search keywords (list)
- `locations`: Zip codes to search (list)
- `run_extract_linkedin_jobs`: Enable/disable extraction (true/false)

## How It Works

1. **Loads candidates** from `candidate.yaml`
2. **Validates environment** and credentials
3. **Launches Chrome** with anti-detection features
4. **Logs into LinkedIn** using persistent browser profiles
5. **Searches for jobs** based on keywords and locations
6. **Extracts job details** (title, company, location, URL)
7. **Sends to API** for storage
8. **Saves to CSV** for backup
9. **Tracks duplicates** to avoid re-extraction
10. **Generates metrics report** with statistics

## Output

- **CSV Export**: `data/exports/extractor_job_links.csv`
- **API**: Jobs sent to your backend endpoint
- **Logs**: Console output with detailed progress
- **Metrics**: End-of-run summary with statistics

## Troubleshooting

### Bot is detected by LinkedIn
- Ensure `selenium-stealth` is installed
- Increase delays between actions
- Use residential proxy (not included)

### No jobs found
- Verify zip codes are valid
- Check keywords are not too specific
- Ensure `DISTANCE_MILES` is reasonable (25-50)

### API authentication failed
- Verify `API_TOKEN` in `.env` is correct
- Check `WBL_API_URL` is accessible
- Ensure token hasn't expired

### Chrome fails to start
- Close all Chrome instances
- Delete browser profile: `rm -rf data/profiles/candidate_001`
- Update Chrome to latest version

## Security Notes

⚠️ **Important**: 
- Never commit `.env` with real credentials (it's in `.gitignore`)
- `candidate.yaml` contains dummy credentials in Git - replace with your real credentials locally
- Keep your API tokens secure
- Use strong passwords

## License

Apache License 2.0 - See [LICENSE](LICENSE) file for details.

## Support

For issues or questions, please check the troubleshooting section or open an issue on GitHub.
