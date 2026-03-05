import os
import sys
from dotenv import load_dotenv

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.api.base_client import BaseAPIClient
from bot.utils.logger import logger

load_dotenv()

def verify_api():
    client = BaseAPIClient()
    api_url = os.getenv("WBL_API_URL")
    
    print(f"=== API CONNECTION VERIFICATION ({api_url}) ===")
    
    # 1. Check Connection & Logs
    print("\n[1] Checking logs access...")
    r = client.get("/orchestrator/logs")
    if r.status_code == 200:
        print(f"✅ Logs connection successful. Count: {len(r.json())}")
    else:
        print(f"❌ Logs access failed: {r.status_code}")

    # 2. Check Positions
    print("\n[2] Checking positions access...")
    r = client.get("/positions/")
    if r.status_code == 200:
        print(f"✅ Positions access successful. Count: {len(r.json())}")
    else:
        print(f"❌ Positions access failed: {r.status_code}")

if __name__ == "__main__":
    verify_api()
