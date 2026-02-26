                                                                                                        1``# LinkedIn Job Extractor Bot

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

   Copy `candidate.yaml.example` to `candidate.yaml` and edit with your LinkedIn credentials:
   ```bash
   cp candidate.yaml.example candidate.yaml
   ```
   Then edit `candidate.yaml`:
   ```yaml
   candidates:
     - candidate_id: "candidate_001"
       name: "Your Name"
       linkedin_username: "your_email@example.com"
       linkedin_password: "your_password"
       # ...
   ```

## Usage

### Run Immediately
```bash
python run_now.py
```

### Schedule Daily Runs
The bot can be scheduled to run daily at a specific time (configured in `.env`):
```bash
python scheduler.py
```

### Windows Task Scheduler (Recommended)
For a 100% automatic setup:
1. Open **Task Scheduler**.
2. Create a basic task pointing to `trigger_bot.bat`.
3. Set the trigger to daily at your preferred time.

## Maintenance & Security

### Automatic Cleanup
To keep the local database small and relevant, the bot **automatically deletes extraction history older than 3 days** every time a run starts.

### Scrubbing Sensitive Data
If you need to share your local database or clear your credentials, use the provided scrub script:
```bash
# Clears passwords in DB and removes the local API token
python scripts/scrub_sensitive.py
```

### Security Notes
⚠️ **Important**: 
- **Never commit `.env` or `candidate.yaml`** (they are ignored by Git).
- Use `candidate.yaml.example` as a template for new environments.
- Keep your `API_TOKEN` and passwords secure.

## Project Structure

```
project-bot-easy-apply-python-webdriver/
├── bot/                    # Core bot logic
├── data/                  # Local storage (profiles, exports)
├── scripts/               # Maintenance and security scripts
├── daily_extractor.py     # Main extraction script
├── scheduler.py           # Daily scheduler script
├── run_now.py             # Immediate trigger script
├── .env.example           # Environment template
└── candidate.yaml.example # Candidate configuration template
```

## Configuration

### Environment Variables (`.env`)

| Variable | Description | Required |
|----------|-------------|----------|
| `SECRET_KEY` | API secret key | Yes |
| `WBL_API_URL` | Backend API URL | Yes |
| `API_TOKEN` | API authentication token | Yes |
| `SCHEDULER_TIME` | Daily run time (HH:MM) | No (default: "09:00") |
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


## License

Apache License 2.0 - See [LICENSE](LICENSE) file for details.

## Support

For issues or questions, please check the troubleshooting section or open an issue on GitHub.
