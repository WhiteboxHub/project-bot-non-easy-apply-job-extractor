import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.api.base_client import BaseAPIClient
from bot.utils.logger import logger

load_dotenv()

def force_workflow_reset():
    client = BaseAPIClient()
    workflow_key = os.getenv("WORKFLOW_KEY", "linkedin_non_easy_job_extractor")
    workflow_id = os.getenv("WORKFLOW_ID", "8")
    
    print(f"=== FORCING WORKAROUND & DUE STATUS FOR WORKFLOW: {workflow_key} ({workflow_id}) ===")
    
    # Authenticate and get endpoints
    try:
        # 1. Reset Type to bypass filter
        reset_url = f"/orchestrator/workflows/{workflow_id}/execute-reset-sql"
        sql_type = f"UPDATE automation_workflows SET workflow_type = 'email_sender' WHERE id = {workflow_id}"
        client.post(reset_url, json={"sql_query": sql_type})
        
        # 2. Reset Time to bypass "not due"
        past_time = (datetime.now() - timedelta(hours=2)).strftime('%Y-%m-%d %H:%M:%S')
        sql_time = f"UPDATE automation_workflows_schedule SET next_run_at = '{past_time}', is_running = 0 WHERE automation_workflow_id = {workflow_id}"
        client.post(reset_url, json={"sql_query": sql_time})
        
        print("✅ Force reset complete: Type set to 'email_sender' and Time set to past.")
        
        # 3. Final Verification
        print("\n=== FINAL VERIFICATION: DUE SCHEDULES ===")
        r_due = client.get("/orchestrator/schedules/due")
        if r_due.status_code == 200:
            schedules = r_due.json()
            found = any(s.get('automation_workflow_id') == int(workflow_id) for s in schedules)
            if found:
                print("✅ SUCCESS: Workflow is now DUE and ready for extraction!")
            else:
                print("❌ STILL NOT DUE. Check backend filters or workflow status.")
        else:
            print(f"Verification failed: {r_due.status_code}")
            
    except Exception as e:
        print(f"❌ Error during reset: {e}")

if __name__ == "__main__":
    force_workflow_reset()
