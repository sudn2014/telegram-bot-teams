import csv
import requests
import base64
import json
from datetime import datetime, timedelta
from msal import ConfidentialClientApplication
import os

# Env vars
git_token = os.environ['GIT_TOKEN']
client_id = os.environ['AZURE_CLIENT_ID']
client_secret = os.environ['AZURE_CLIENT_SECRET']
tenant_id = os.environ['AZURE_TENANT_ID']
community_id = os.environ['TEAMS_COMMUNITY_ID']

# Fetch CSV from GitHub
headers = {'Authorization': f'token {git_token}'}
response = requests.get('https://api.github.com/repos/sudn2014/telegram-bot-teams/contents/pending_teams.csv', headers=headers)
if response.status_code != 200:
    print(f"Failed to fetch CSV: {response.status_code}")
    exit(1)

content_b64 = response.json()['content']
content = base64.b64decode(content_b64).decode('utf-8')
rows = list(csv.DictReader(content.splitlines()))

# Extract today's unique emails (Timestamp >= today 00:00, no duplicates)
today = datetime.now().date()
new_emails = []
for row in rows:
    if 'Timestamp' not in row:
        continue
    row_date = datetime.strptime(row['Timestamp'], '%Y-%m-%d %H:%M:%S').date()
    email = row['Email'].strip().lower()
    if row_date == today and email and email not in [e['email'] for e in new_emails]:
        new_emails.append({'email': email, 'name': row['Name']})

print(f"Found {len(new_emails)} new unique emails for today: {new_emails}")

if not new_emails:
    print("No new emails—skipping")
    exit(0)

# Auth for Microsoft Graph
scopes = ["https://graph.microsoft.com/.default"]
app = ConfidentialClientApplication(
    client_id, authority=f"https://login.microsoftonline.com/{tenant_id}",
    client_credential=client_secret
)
result = app.acquire_token_silent(scopes, account=None)
if not result:
    result = app.acquire_token_for_client(scopes)
if 'access_token' not in result:
    print(f"Auth failed: {result}")
    exit(1)
token = result['access_token']

# Add to Teams community (invite as members)
headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
added_count = 0
for user in new_emails:
    body = {
        'members': [{
            'email': user['email'],
            'displayName': user['name'],
            'roles': ['member']
        }]
    }
    response = requests.post(f"https://graph.microsoft.com/v1.0/groups/{community_id}/members/$ref", headers=headers, json=body)
    if response.status_code in [200, 201, 204]:
        print(f"Added {user['name']} ({user['email']}) to Teams community")
        added_count += 1
    else:
        print(f"Failed to add {user['email']}: {response.status_code} - {response.text}")

print(f"Daily processing complete: {added_count}/{len(new_emails)} added")
