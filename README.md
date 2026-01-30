# LinkedIn Job Extractor & Marketing Bot (Daily Automatic)

A fully automated, scheduled job extraction system designed to collect LinkedIn job links daily. It syncs with a MySQL database to manage multiple candidates and uses professional-grade anti-detection features.

## 🌟 Key Features

*   **100% Automatic Scheduling**: Pre-configured to run every morning at **08:20 AM**.
*   **Modular "Trigger-Job" Architecture**: Separates the business logic from the execution trigger for maximum reliability.
*   **Smart Selection**: Automatically pulls zip codes and credentials from your MySQL database or YAML file.
*   **Anti-Detection**: Powered by `undetected-chromedriver` and `selenium-stealth` with persistent browser profiles.
*   **Multi-Storage**: Saves results simultaneously to **CSV**, **MySQL**, and **SQLite**.
*   **Dynamic Flagging**: Only processes candidates with the `run_extract_linkedin_jobs` flag set to `true` in the database.

---

## 🛠️ Setup Instructions

### 1. Prerequisites
- Python 3.10+
- Google Chrome
- MySQL Server

### 2. Installation
```bash
pip install -r requirements.txt
pip install schedule
```

### 3. Database Configuration (.env)
Ensure your `.env` file contains your MySQL credentials and API keys. The bot uses these to fetch candidate marketing data and sync results.

---

## ▶️ Execution Methods

Based on the [Trigger-Job Separation](file:///C:/Users/KUMAR-MINI-PC-7/.gemini/antigravity/brain/6435329c-c43b-4a45-81d8-c18b0fa7b448/walkthrough.md) pattern, you have three ways to run the bot:

### 1. ⚡ Manual Run (Immediate)
Use this to test the bot or run an extraction right now:
```bash
python run_now.py
```

### 2. 🕙 Automatic Internal Scheduler
Run this and leave the terminal open. It will wait and trigger the bot every day at **08:20 AM**:
```bash
python scheduler.py
```

### 3. 🛡️ Windows Task Scheduler (Recommended)
For the most reliable "hands-off" experience, connect the provided **`trigger_bot.bat`** to your Windows Task Scheduler.
- **Action**: Start a Program
- **Program**: Select `trigger_bot.bat`
- **Trigger**: Daily at 08:20 AM

---

## 📂 Project Architecture

- **`daily_extractor.py`**: The core "Job" layer. Contains extraction and sync logic.
- **`scheduler.py`**: The internal "Trigger" for hands-off daily runs.
- **`run_now.py`**: Shortcut for manual trigger.
- **`trigger_bot.bat`**: Integration point for OS-level scheduling.
- **`candidate_marketing.yaml`**: Local configuration file for candidate keywords and overrides.

---

## 📊 Data & Output

- **CSV Export**: `data/exports/extractor_job_links.csv` (All jobs merged here).
- **MySQL Sync**: Automatically saves to the `position` table in your database.
- **Job Tracking**: Uses a local SQLite `job_catalog.db` to ensure no duplicates are ever extracted.
- **Profiles**: Browser sessions are stored per candidate in `data/profiles/` to persist logins.

---

## 🔧 Maintenance

- **Adding Candidates**: Simply set the `run_extract_linkedin_jobs` flag to `true` in your `candidate_marketing` table in MySQL.
- **Updating Keywords**: Update the `keywords` or `locations` column in the database or the `candidate_marketing.yaml` file.
- **Browser Issue**: If Chrome fails to start, ensure no other `chrome.exe` processes are running in the Task Manager.
