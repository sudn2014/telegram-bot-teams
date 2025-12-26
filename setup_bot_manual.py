import json
import os
from typing import Dict, Any
import telebot
from telebot import types
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import csv
from datetime import datetime
import re

# Config file
CONFIG_FILE = 'config.json'

def load_config() -> Dict[str, Any]:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_config(config: Dict[str, Any]):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)

def setup_telegram(config: Dict[str, Any]):
    print("\n=== Telegram Setup ===")
    if not config.get('bot_token'):
        token = input("Paste your Bot Token from @BotFather: ").strip()
        if not token:
            raise ValueError("Token required!")
        config['bot_token'] = token
        save_config(config)
        print("Token saved.")
    if not config.get('group_chat_id'):
        chat_id = input("Paste your Supergroup Chat ID (e.g., -1001234567890): ").strip()
        if not chat_id.startswith('-'):
            raise ValueError("Must be negative for groups!")
        config['group_chat_id'] = chat_id
        save_config(config)
        print("Group ID saved.")
    # Email setup (Gmail example; use your SMTP)
    if not config.get('email_to'):
        config['email_to'] = input("Your email for notifications (e.g., you@gmail.com): ").strip()
    if not config.get('email_from'):
        config['email_from'] = input("Sender email (e.g., bot@gmail.com): ").strip()
    if not config.get('email_password'):
        config['email_password'] = input("Sender app password (Gmail: Generate at myaccount.google.com/apppasswords): ").strip()
    save_config(config)

def send_email(config: Dict[str, Any], user_data: Dict[str, str]):
    try:
        msg = MIMEMultipart()
        msg['From'] = config['email_from']
        msg['To'] = user_data['email']  # NEW: Send to USER's email (what they entered)
        msg['Subject'] = f"Welcome to Teams Community - Confirmation from Bot"
        body = f"""
        Hi {user_data['name']}! 

        Thanks for joining our Telegram group and providing your details. We've received everything:
        - Name: {user_data['name']}
        - Email: {user_data['email']}
        - Phone: {user_data['phone']}

        We'll add you to our Microsoft Teams community shortly (usually within 24 hours). 
        If you have questions, reply to this email or DM the bot.

        Best, 
        Your Teams Admin
        """
        msg.attach(MIMEText(body, 'plain'))
        
        # Optional: CC to admin for records
        # msg['Cc'] = config['email_to']  # Uncomment if you want a copy
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(config['email_from'], config['email_password'])
        text = msg.as_string()
        server.sendmail(config['email_from'], [user_data['email']], text)  # NEW: To list for user (add Cc if needed)
        server.quit()
        print(f"Email sent to user {user_data['email']} for {user_data['name']}")
    except Exception as e:
        print(f"Email failed: {e} - Saving to CSV instead")

def save_to_csv(user_data: Dict[str, str]):
    file_exists = os.path.isfile('pending_teams.csv')
    with open('pending_teams.csv', 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['Name', 'Email', 'Phone', 'Timestamp'])
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            'Name': user_data['name'],
            'Email': user_data['email'],
            'Phone': user_data['phone'],
            'Timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
    print("Saved to pending_teams.csv")
    # Auto-push to repo (only if GIT_TOKEN set, e.g., in hosting env)
    if os.environ.get('GIT_TOKEN'):
        import subprocess
        repo_url = 'https://x-access-token:' + os.environ['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'] + '@github.com/sudn2014/telegram-bot-teams.git'
        subprocess.run(['git', 'remote', 'set-url', 'origin', repo_url], check=True)
        subprocess.run(['git', 'add', 'pending_teams.csv'], check=True)
        subprocess.run(['git', 'commit', '-m', f'Add user: {user_data["name"]}'], capture_output=True)
        if subprocess.run(['git', 'push', 'origin', 'main'], capture_output=True).returncode == 0:
            print("Pushed to repo")
        else:
            print("Push failed - check token")
    
def generate_dummy_csv():
    save_to_csv({
        'name': 'Test User',
        'email': 'test@example.com',
        'phone': '1234567890'
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
            bot.reply_to(message, f"Welcome, {username}! To join Teams, first message me privately with '/start', then reply with your full name, email, and phone (one at a time).")
            # try:
            #     bot.send_message(user_id, "Hi! What's your full name?")
            #     user_states[user_id] = {'state': 'name', 'data': {}}
            # except Exception as e:
            #     print(f"PM failed: {e}")

    @bot.message_handler(commands=['start'])
    def start_handler(message):
        user_id = message.from_user.id
        print(f"# NEW: /start from {user_id}")  # NEW
        if user_id not in user_states:
            bot.reply_to(message, "Welcome! Reply with your full name to request Teams access.")
            user_states[user_id] = {'state': 'name', 'data': {}}
            print(f"# NEW: Set state to 'name' for {user_id}")  # NEW

    @bot.message_handler(func=lambda m: True, chat_types=['private'])
    def private_handler(message):
        user_id = message.from_user.id
        print(f"# NEW: Received private message from {user_id}: '{message.text}'")  # NEW: Logs every DM
        
        if user_id not in user_states:
            print(f"# NEW: User {user_id} not in states - starting new session")  # NEW
            bot.send_message(user_id, "Join the group first, then reply with your full name.")
            user_states[user_id] = {'state': 'name', 'data': {}}
            return
        
        state = user_states[user_id]['state']
        data = user_states[user_id]['data']
        print(f"# NEW: Current state for {user_id}: '{state}'")  # NEW: Shows state
        
        if state == 'name':
            data['name'] = message.text
            print(f"# NEW: Set name to '{data['name']}' for {user_id}")  # NEW
            bot.send_message(user_id, "Thanks! Now your email:")
            user_states[user_id]['state'] = 'email'
        elif state == 'email':
            email_input = message.text.strip()
            if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', message.text.strip()):
                bot.send_message(user_id, "That doesn't look like a valid email (e.g., user@example.com). Please try again:")
                return  # Stay in 'email' state
            data['email'] = message.text.strip()
            print(f"# NEW: Set email to '{data['email']}' for {user_id}")  # NEW
            bot.send_message(user_id, "Last: your phone number:")
            user_states[user_id]['state'] = 'phone'
        elif state == 'phone':
            data['phone'] = message.text
            print(f"# NEW: Set phone to '{data['phone']}' for {user_id}")  # NEW
            # Notify instead of add
            send_email(config, data)
            save_to_csv(data)
            try:
                bot.send_message(user_id, f"Thanks! We've noted your details ({data['name']}, {data['email']}, {data['phone']}). You'll be added to Teams soon—check your email for confirmation.")
                print(f"# CONFIRM: Final message sent to {user_id}")
            except Exception as e:
                print(f"# ERROR: Final message failed for {user_id}: {e}")
            del user_states[user_id]

    print("Bot running... Press Ctrl+C to stop.")
    bot.delete_webhook()
    bot.polling(none_stop=True)


if __name__ == "__main__":
    try:
        config = load_config()
        setup_telegram(config)

        if os.environ.get("CI") == "true":
            generate_dummy_csv()
        else:
            run_bot(config)

    except KeyboardInterrupt:
        print("\nStopped.")
    except Exception as e:
        print(f"Error: {e}")
        print("Run again or check prerequisites.")









