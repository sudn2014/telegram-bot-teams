import json
import os
import sys  # NEW: For isatty() check
from typing import Dict, Any
import telebot
from telebot import types
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import csv
from datetime import datetime
import re
import random

print("All imports successful")  # Debug: First print
sys.stdout.flush()  # Force output

# Config file (local only; prod uses env vars)
CONFIG_FILE = 'config.json'

def load_config() -> Dict[str, Any]:
    config = {}
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            config.update(json.load(f))
    # Always prefer/require env vars for secrets
    config['bot_token'] = os.environ.get('BOT_TOKEN') or config.get('bot_token')
    config['group_chat_id'] = os.environ.get('GROUP_CHAT_ID') or config.get('group_chat_id')
    config['email_to'] = os.environ.get('EMAIL_TO') or config.get('email_to')  # Unused but kept
    config['email_from'] = os.environ.get('EMAIL_FROM') or config.get('email_from')
    config['email_password'] = os.environ.get('EMAIL_PASSWORD') or config.get('email_password')
    return config

def save_config(config: Dict[str, Any]):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)

def setup_telegram(config: Dict[str, Any]):
    print("Entering setup_telegram")  # Debug
    sys.stdout.flush()
    print("\n=== Telegram Setup ===")
    sys.stdout.flush()  # Force output
    interactive = sys.stdin.isatty() # NEW: Detect local terminal vs. hosting
    print(f"Print 2: Interactive mode? {interactive}")  # Debug
    sys.stdout.flush()
   
    required = ['bot_token', 'group_chat_id']
    for key in required:
        if not config.get(key):
            if interactive:
                if key == 'bot_token':
                    token = input("Paste your Bot Token from @BotFather: ").strip()
                    if not token:
                        raise ValueError("Token required!")
                    config['bot_token'] = token
                elif key == 'group_chat_id':
                    chat_id = input("Paste your Supergroup Chat ID (e.g., -1001234567890): ").strip()
                    if not chat_id.startswith('-'):
                        raise ValueError("Must be negative for groups!")
                    config['group_chat_id'] = chat_id
                save_config(config)
                print(f"{key} saved.")
            else:
                raise ValueError(f"Missing required config '{key}'. Set {key.upper()} env var in hosting!")
        print(f"Checked {key}: {'OK' if config.get(key) else 'MISSING'}")  # Debug: Add this line here
        sys.stdout.flush()
    print("Print 5: Required keys done")  # Debug
    sys.stdout.flush()
    # Email setup (prompt only if interactive)
    email_keys = ['email_to', 'email_from', 'email_password']
    for key in email_keys:
        if not config.get(key) and interactive:
            if key == 'email_to':
                config[key] = input("Your email for notifications (e.g., you@gmail.com): ").strip()
            elif key == 'email_from':
                config[key] = input("Sender email (e.g., bot@gmail.com): ").strip()
            elif key == 'email_password':
                config[key] = input("Sender app password (Gmail: Generate at myaccount.google.com/apppasswords): ").strip()
            save_config(config)
    if not interactive and not all(config.get(k) for k in email_keys):
        print("Warning: Email config incomplete—emails may fail. Set EMAIL_* env vars.")
    print(f"CI env: '{os.environ.get('CI')}'") # Should be None
    if os.environ.get("CI") == "true":
        print("Dummy mode")
        generate_dummy_csv()
    else:
        print("Full mode - starting polling")
        run_bot(config)

def send_email(config: Dict[str, Any], user_data: Dict[str, str]):
    try:
        msg = MIMEMultipart()
        msg['From'] = config['email_from']
        msg['To'] = user_data['email']  # Send to user's email
        msg['Subject'] = f"Welcome to Teams Community - Confirmation from Bot"
        body = f"""
Hi {user_data['name']}! 

Thanks for joining our Telegram group and providing your details. We've received everything:
- Name: {user_data['name']}
- Email: {user_data['email']}
- Phone: {user_data['phone']}

Join our Teams community here: https://teams.live.com/l/community/FEAz7PhpWTe1hYm1gQ
If you have questions, reply to this email or DM the bot.

Best,
Your Teams Admin
"""
        msg.attach(MIMEText(body, 'plain'))
        # Optional: CC to admin (uncomment if needed)
        # if config.get('email_to'):
        #     msg['Cc'] = config['email_to']
        #     server.sendmail(..., [user_data['email'], config['email_to']], ...)

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(config['email_from'], config['email_password'])
        text = msg.as_string()
        server.sendmail(config['email_from'], [user_data['email']], text)
        server.quit()
        print(f"Email sent to {user_data['email']} for {user_data['name']}")
    except Exception as e:
        print(f"Email failed: {e} - Data saved to CSV anyway")

def save_to_csv(user_data: Dict[str, str]):
    """Save user data to CSV with fast GitHub API push."""
    from datetime import datetime
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    row = {
        'Name': user_data['name'].strip(),
        'Email': user_data['email'].strip(),
        'Phone': user_data['phone'].strip(),
        'Timestamp': timestamp
    }
    file_exists = os.path.isfile('pending_teams.csv')
    with open('pending_teams.csv', 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['Name', 'Email', 'Phone', 'Timestamp'])
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)
    print("Saved to pending_teams.csv")
    
    # Fast API push using GIT_TOKEN
    git_token = os.environ.get('GIT_TOKEN')
    if git_token:
        import requests
        import base64
        try:
            # Read CSV content
            with open('pending_teams.csv', 'rb') as f:
                content = f.read()
            content_b64 = base64.b64encode(content).decode('utf-8')
            
            # Headers for API
            headers = {'Authorization': f'token {git_token}', 'Content-Type': 'application/json'}
            
            # Get current file SHA for update
            get_response = requests.get('https://api.github.com/repos/sudn2014/telegram-bot-teams/contents/pending_teams.csv', headers=headers)
            sha = get_response.json().get('sha') if get_response.status_code == 200 else None
            
            # Update file
            data = {
                'message': f'Add user: {row["Name"]} ({timestamp})',
                'content': content_b64,
                'sha': sha  # Required for updates
            }
            put_response = requests.put('https://api.github.com/repos/sudn2014/telegram-bot-teams/contents/pending_teams.csv', headers=headers, json=data)
            if put_response.status_code in [200, 201]:
                print("Pushed to GitHub via API (<5s update)")
            else:
                print(f"API push failed ({put_response.status_code}): {put_response.text}")
        except Exception as e:
            print(f"API push error: {e} - Local save only")
    else:
        print("GIT_TOKEN not set—skipping push (check secret)")


def generate_dummy_csv():
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    save_to_csv({
        'name': f'Test User {random.randint(1000, 9999)}',
        'email': f'test{random.randint(1000, 9999)}@example.com',
        'phone': f'123-456-{random.randint(1000, 9999)}'
    })

def run_bot(config: Dict[str, Any]):
    print("\n=== Starting Bot ===")
    bot = telebot.TeleBot(config['bot_token'])
    group_chat_id = config['group_chat_id']
    user_states = {}

    @bot.message_handler(content_types=['new_chat_members'])
    def new_member_handler(message):
        if message.chat.id != int(group_chat_id):
            return
        for member in message.new_chat_members:
            if member.id == bot.get_me().id:
                continue
            user_id = member.id
            username = member.username or member.first_name or 'User'
            bot.reply_to(message, f"Welcome, {username}! To join Teams, message me privately with '/start', then reply with your full name, email, and phone (one at a time).")

    @bot.message_handler(commands=['start'])
    def start_handler(message):
        user_id = message.from_user.id
        print(f"# /start from {user_id}")
        if user_id not in user_states:
            bot.reply_to(message, "Welcome! Reply with your full name please.")
            user_states[user_id] = {'state': 'name', 'data': {}}
            print(f"# Set state to 'name' for {user_id}")

    @bot.message_handler(func=lambda m: True, chat_types=['private'])
    def private_handler(message):
        user_id = message.from_user.id
        print(f"# Private msg from {user_id}: '{message.text}'")
        
        if user_id not in user_states:
            bot.send_message(user_id, "Join the group first, then reply with your full name.")
            user_states[user_id] = {'state': 'name', 'data': {}}
            return
        
        state = user_states[user_id]['state']
        data = user_states[user_id]['data']
        print(f"# State for {user_id}: '{state}'")
        
        input_text = message.text.strip()
        print(f"Handler entered for state '{state}' with input '{input_text}'")  # Debug
        sys.stdout.flush()

        if not input_text:  # NEW: Skip empty messages
            return
        
        if state == 'name':
            if not input_text:  # NEW: Basic validation
                bot.send_message(user_id, "Name can't be empty. Please try again.")
                return
            data['name'] = input_text
            print(f"# Name: '{data['name']}' for {user_id}")
            bot.send_message(user_id, "Thanks! Now your email:")
            user_states[user_id]['state'] = 'email'
        elif state == 'email':
            if not re.match(r'^[\w.-]+@[\w.-]+\.\w+$', input_text):  # FIXED: Removed \ before . in classes
                bot.send_message(user_id, "That doesn't look like a valid email (e.g., user@example.com). Please try again:")
                return  # Stay in 'email' state
            data['email'] = input_text
            print(f"# Email: '{data['email']}' for {user_id}")
            bot.send_message(user_id, "Last: your phone number:")
            user_states[user_id]['state'] = 'phone'
        elif state == 'phone':
            if not input_text:  # NEW: Basic validation
                bot.send_message(user_id, "Phone can't be empty. Please try again.")
                return
            data['phone'] = input_text
            print(f"# Phone: '{data['phone']}' for {user_id}")
            print("Phone state complete—calling send_email and save_to_csv")  # Debug: Add this line
            sys.stdout.flush()  # Force output
            send_email(config, data)
            save_to_csv(data)
            print("send_email and save_to_csv done")  # Debug: Add this line
            sys.stdout.flush()  # Force output
            try:
                bot.send_message(user_id, f"Thanks! We've noted your details ({data['name']}, {data['email']}, {data['phone']}). check your email for confirmation.")
                print(f"# Final msg sent to {user_id}")
            except Exception as e:
                print(f"# Final msg failed for {user_id}: {e}")
            del user_states[user_id]
    
    print("Bot running... Press Ctrl+C to stop.")
    bot.delete_webhook()
    bot.polling(none_stop=True)

if __name__ == "__main__":
    print("Entering main block")  # Debug
    sys.stdout.flush()
    try:
        config = load_config()
        print("load_config complete")  # Debug
        sys.stdout.flush()
        setup_telegram(config)
        print("Setup complete—checking RUN_DUMMY...")  # Debug #1
        print(f"RUN_DUMMY env: '{os.environ.get('RUN_DUMMY')}'")  # Debug
        if os.environ.get("RUN_DUMMY") == "true":
            print("Dummy mode")
            generate_dummy_csv()
        else:
            print("Full mode - starting polling")
            run_bot(config)
    except KeyboardInterrupt:
        print("\nStopped.")
    except Exception as e:
        print(f"Error: {e}")
        import traceback #1
        traceback.print_exc()  # Full stack trace #1
        print("Check env vars (BOT_TOKEN, etc.) or run locally for setup.")

        #1 : added to debug to resolve the csv update issue 

