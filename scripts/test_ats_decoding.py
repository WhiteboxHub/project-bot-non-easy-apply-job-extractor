import os
import sys

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.utils.url_utils import decode_linkedin_redir

# Test Cases
test_urls = [
    "https://www.linkedin.com/redir/redirect/?url=https%3A%2F%2Fjobs%2Elever%2Eco%2Fimo-online%2F7076909a-2ce8-4c69-957f-ca36a3abf683%2Fapply%3Fsource%3DLinkedIn&urlhash=0Y94&isSdui=true",
    "https://www.linkedin.com/redir/redirect/?url=https%3A%2F%2Fboards%2Egreenhouse%2Eio%2Fgoogle%2Fjobs%2F12345&urlhash=abc",
    "https://www.google.com" # Should return as is
]

print("--- LinkedIn Redirect Decoder Test ---")
for url in test_urls:
    decoded = decode_linkedin_redir(url)
    print(f"Original: {url[:50]}...")
    print(f"Decoded:  {decoded}")
    print("-" * 20)
