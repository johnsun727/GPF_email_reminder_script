import imaplib
import email
import google.generativeai as genai
import datetime
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import re
import os

# Gmail IMAP Settings
IMAP_SERVER = "imap.gmail.com"
EMAIL_ACCOUNT = "NEED TO ADD THE NEW GMAIL"
EMAIL_PASSWORD = "NEED TO CREATE NEW GOOGLE APP PASSWORD"

# Gemini API Key
GEMINI_API_KEY = "NEW API KEY"
genai.configure(api_key=GEMINI_API_KEY)

# Predefined Prompt for Gemini
GEMINI_PROMPT = "1. Analyze and identify all brands and sub-brands that are experiencing price increase or updates or changes, ignore promotions and promos, in their pricing and when that will take place. 2. Look at the price change dates and convert them to standardized format ex. yyyy-mm-dd 3. Return key value pairs in JSON {brand: date}, ensure the response is always in valid JSON format with double quotes."

# Predefined Sender Email
SENDER_EMAIL = "NEED TO ADD LAURA'S EMAIL"

# Files for tracking email processing and reminders
LAST_EMAIL_ID_FILE = "last_email_id.txt"
REMINDER_FILE = os.path.join("reminders", "reminder_dates.json") #EDIT TO SEND TO CORRECT PATH, EX. REMINDER_FILE = "C:/Users/YourUser/gpf_script/reminder_dates.json"

def fetch_email_from_sender():
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL_ACCOUNT, EMAIL_PASSWORD)
        mail.select("inbox")

        result, data = mail.search(None, f'FROM "{SENDER_EMAIL}"')
        email_ids = data[0].split()

        if not email_ids:
            send_email("woodbine@gpfyorkregion.com", "PRICE UPDATE REMINDER: No New Emails Found", f"No new emails were found from {SENDER_EMAIL} at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.")
            return None, None

        latest_email_id = email_ids[-1].decode("utf-8")

        if os.path.exists(LAST_EMAIL_ID_FILE):
            with open(LAST_EMAIL_ID_FILE, "r") as f:
                last_email_id = f.read().strip()
            
            if latest_email_id == last_email_id:
                send_email("woodbine@gpfyorkregion.com", "PRICE UPDATE REMINDER: No New Emails Found", 
                           f"The latest email from {SENDER_EMAIL} has already been processed. No new emails were found at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.")
                return None, None

        with open(LAST_EMAIL_ID_FILE, "w") as f:
            f.write(latest_email_id)

        result, data = mail.fetch(latest_email_id, "(RFC822)")
        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)

        subject = msg["subject"]
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                    break
        else:
            body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")

        return body, subject

    except Exception as e:
        send_email("woodbine@gpfyorkregion.com", "PRICE UPDATE REMINDER: Script Error Alert", f"An error occurred: {str(e)}")
        return None, None

def send_to_gemini(email_content):
    try:
        model = genai.GenerativeModel("gemini-pro")
        response = model.generate_content(f"{GEMINI_PROMPT}\n\n{email_content}")
        return response.text.strip()
    except Exception as e:
        send_email("woodbine@gpfyorkregion.com", "PRICE UPDATE REMINDER: Gemini API Error", f"Error occurred: {str(e)}")
        return None

def clean_json_response(response):
    return re.sub(r'```[a-zA-Z]*\n?|```', '', response, flags=re.MULTILINE).strip()

def save_reminders(reminders):
    os.makedirs("reminders", exist_ok=True)
    with open(REMINDER_FILE, "w") as f:
        json.dump(reminders, f)

def load_reminders():
    if os.path.exists(REMINDER_FILE):
        with open(REMINDER_FILE, "r") as f:
            return json.load(f)
    return {}

def send_email(to_email, subject, body):
    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_ACCOUNT
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_ACCOUNT, EMAIL_PASSWORD)
            server.sendmail(EMAIL_ACCOUNT, to_email, msg.as_string())
    except Exception as e:
        send_email("woodbine@gpfyorkregion.com", "PRICE UPDATE REMINDER: Email Sending Error", f"An error occurred: {str(e)}")

if __name__ == "__main__":
    today = datetime.date.today()
    reminders = load_reminders()
    
    email_content, original_subject = fetch_email_from_sender()
    if email_content:
        gemini_response = send_to_gemini(email_content)
        if gemini_response:
            try:
                clean_response = clean_json_response(gemini_response)
                response_data = json.loads(clean_response)
                
                for brand, date in response_data.items():
                    event_date = datetime.date.fromisoformat(date)
                    reminder_date = event_date - datetime.timedelta(days=7)
                    reminders[brand] = str(reminder_date)
                save_reminders(reminders)
            except (ValueError, KeyError, json.JSONDecodeError) as e:
                send_email("woodbine@gpfyorkregion.com", "PRICE UPDATE REMINDER: Data Processing Error", f"An error occurred while processing data: {str(e)}")
    
    for brand, reminder_date in list(reminders.items()):
        if today == datetime.date.fromisoformat(reminder_date):
            email_subject = f"PRICE UPDATE REMINDER: Upcoming Price Change for {brand}"
            email_body = f"Reminder: The price for {brand} is changing soon on {event_date}. Please act accordingly (big order for higher margin time?)."
            send_email("woodbine@gpfyorkregion.com", email_subject, email_body)
            del reminders[brand]
    
    save_reminders(reminders)
