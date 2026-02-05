# daily_teams_inviter.py
import csv
import requests
import json
import base64
import os
from datetime import datetime, timedelta, timezone
from msal import ConfidentialClientApplication

# Environment variables from GitHub Secrets
client_id = os.environ["AZURE_CLIENT_ID"]
client_secret = os.environ["AZURE_CLIENT_SECRET"]
tenant_id = os.environ["AZURE_TENANT_ID"]
community_id = os.environ["TEAMS_COMMUNITY_ID"]

# Step 1: Fetch CSV from GitHub (using GIT_TOKEN for auth)
git_token = os.environ.get("GIT_TOKEN")
if not git_token:
    print("GIT_TOKEN not set — cannot fetch CSV")
    exit(1)

headers = {"Authorization": f"token {git_token}"}
response = requests.get(
    "https://api.github.com/repos/sudn2014/telegram-bot-teams/contents/pending_teams.csv",
    headers=headers
)
if response.status_code != 200:
    print(f"Failed to fetch CSV: {response.status_code} - {response.text}")
    exit(1)

content_b64 = response.json()["content"]
csv_content = base64.b64decode(content_b64).decode("utf-8")

# Step 2: Parse CSV and extract emails from the last 24 hours (unique)
rows = list(csv.DictReader(csv_content.splitlines()))  # ← FIXED: Uncommented this line
now = datetime.now(timezone.utc)
last_24h = now - timedelta(hours=24)
emails_last_24h = set()  # ← Your new variable

for row in rows:  # ← Uses 'rows' correctly
    if "Timestamp" not in row or "Email" not in row:
        continue
    try:
        # Parse timestamp (assume UTC)
        row_time = datetime.strptime(row["Timestamp"], "%Y-%m-%d %H:%M:%S")
        row_time = row_time.replace(tzinfo=timezone.utc)  # make aware
        if row_time >= last_24h:
            email = row["Email"].strip().lower()
            if email:
                emails_last_24h.add(email)
    except ValueError:
        continue  # invalid timestamp

print(f"Found {len(emails_last_24h)} unique emails in the last 24 hours")

if not emails_last_24h:
    print("No new emails in the last 24 hours — exiting")
    exit(0)

# Step 3: Authenticate to Microsoft Graph
scopes = ["https://graph.microsoft.com/.default"]
authority = f"https://login.microsoftonline.com/{tenant_id}"

app = ConfidentialClientApplication(
    client_id=client_id,
    client_credential=client_secret,
    authority=authority
)

token_result = app.acquire_token_for_client(scopes=scopes)

if "access_token" not in token_result:
    print("Authentication failed:")
    print(token_result.get("error"))
    print(token_result.get("error_description"))
    exit(1)

access_token = token_result["access_token"]

# Step 4: Invite each email to the Teams community
headers = {
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json"
}

added = 0
for email in emails_last_24h:  # ← FIXED: Changed to emails_last_24h
    payload = {
        "members": [
            {
                "@odata.type": "#microsoft.graph.aadUserConversationMember",
                "email": email,
                "roles": ["member"]
            }
        ]
    }

    url = f"https://graph.microsoft.com/v1.0/teams/{community_id}/members"
    response = requests.post(url, headers=headers, json=payload)

    if response.status_code in (200, 201, 204):
        print(f"Successfully invited {email}")
        added += 1
    else:
        print(f"Failed to invite {email}: {response.status_code} - {response.text}")

print(f"Daily invite complete: {added}/{len(emails_last_24h)} users added")
