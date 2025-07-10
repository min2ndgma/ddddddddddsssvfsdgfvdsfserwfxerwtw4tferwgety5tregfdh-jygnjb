# -*- coding: utf-8 -*-
"""
This script logs into ivasms.com using Selenium in a headless Chrome browser
on Replit, fetches SMS messages from the last 24 hours, filters for new OTPs,
and sends them to Telegram in a clean, styled format.

This is the final, production-ready version for 24/7 hosting on Replit.

Author: s m yamin hasan
Reviewed and Integrated by: Gemini
Date: July 10, 2025
"""

# Standard library imports
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta

# Third-party imports
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# Local application/library specific imports
from keep_alive import keep_alive

# --- CONFIGURATION ---
EMAIL = "s77shahidul@gmail.com"
PASSWORD = "s77shahidul"
TELEGRAM_BOT_TOKEN = "7924086431:AAGQVgbVbG1O_dkqo3t4uGIkuwETc_GQouo"
TELEGRAM_CHAT_ID = "-1002156267437"

# --- SCRIPT SETTINGS ---
SETTINGS = {
    "LOGIN_URL": "https://www.ivasms.com/login",
    "SMS_URL": "https://www.ivasms.com/portal/sms/received",
    "OUTPUT_FILE": "code.txt",
    "SLEEP_SECONDS": 10,  # Updated to 10 seconds
}

# --- LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# ==============================================================================
# === OTP UTILITIES ============================================================
# ==============================================================================

def format_single_otp(otp_data):
    """Formats a single OTP into a more gorgeous HTML message for Telegram."""
    otp = otp_data.get('otp', 'N/A')
    phone = otp_data.get('phone', 'N/A')
    service = otp_data.get('service', 'Unknown')
    full_message = otp_data.get('full_message', 'N/A')
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    sanitized_message = full_message.replace('<', '&lt;').replace('>', '&gt;').replace('&', '&amp;')

    message = f"""
- - - - - - - - - - - - - - - - - - - -
✨ <b>New OTP from {service}</b> ✨
- - - - - - - - - - - - - - - - - - - -

📲 <b>To Number:</b>
<code>{phone}</code>

🔑 <b>Your Code:</b>
<code>{otp}</code>

📄 <b>Full Message:</b>
<pre>{sanitized_message}</pre>

- - - - - - - - - - - - - - - - - - - -
<i>Received at: {timestamp}</i>
"""
    return message

def extract_otp_from_text(text):
    """Extract OTP code from SMS text using various common patterns."""
    if not text: return None
    patterns = [r'<#>\s*(\d{4,8})\s+is your', r'G-(\d{6})', r'\b(\d{4,8})\b', r'code is\s*(\d+)', r'code:\s*(\d+)', r'verification code[:\s]*(\d+)', r'OTP is\s*(\d+)', r'pin[:\s]*(\d+)']
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match: return match.group(1)
    return None

def clean_service_name(service):
    """Cleans and standardizes the service name (CLI)."""
    if not service: return "Unknown"
    service = service.strip().title()
    service_mappings = {'fb': 'Facebook', 'ig': 'Instagram'}
    return service_mappings.get(service.lower(), service)

def load_processed_otps(filepath: str) -> set:
    """Loads already processed OTPs from the output file to prevent duplicates."""
    processed_keys = set()
    if not os.path.exists(filepath):
        return processed_keys
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    otp_data = json.loads(line)
                    key = f"{otp_data.get('otp','')}_{otp_data.get('phone','')}_{otp_data.get('service','')}"
                    processed_keys.add(key)
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logging.error(f"Could not load processed OTPs from {filepath}: {e}")
    return processed_keys

# ==============================================================================
# === CORE SCRAPING LOGIC ======================================================
# ==============================================================================

def send_telegram_message(text: str):
    """Sends a message to the configured Telegram chat."""
    if not text: return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, data=data, timeout=10).raise_for_status()
        logging.info("Successfully sent message to Telegram.")
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to send Telegram message: {e}")

def setup_driver():
    """Initializes the Selenium WebDriver for Replit's headless environment."""
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    logging.info("Starting headless Chrome browser for Replit...")
    driver = webdriver.Chrome(options=options)
    driver.implicitly_wait(5)
    return driver

def login(driver: webdriver.Chrome) -> bool:
    """Logs into the website using Selenium."""
    try:
        logging.info(f"Navigating to login page and logging in as {EMAIL}...")
        driver.get(SETTINGS["LOGIN_URL"])
        WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.NAME, "email"))).send_keys(EMAIL)
        driver.find_element(By.NAME, "password").send_keys(PASSWORD)
        time.sleep(1)
        driver.find_element(By.TAG_NAME, "button").click()
        WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.CLASS_NAME, "page-header")))
        logging.info("Login successful.")
        return True
    except Exception as e:
        logging.error(f"Login failed! An error occurred: {e}")
        return False

def extract_all_otps_from_page(driver: webdriver.Chrome) -> list[dict]:
    """Parses the current page source to extract all visible OTPs."""
    all_otps = []
    logging.info("Starting page parsing with BeautifulSoup...")
    soup = BeautifulSoup(driver.page_source, "html.parser")

    range_items = soup.select("div.item")
    logging.info(f"Parser found {len(range_items)} range items.")
    if not range_items:
        logging.warning("No 'div.item' elements found. Page might not have loaded correctly.")

    for item_index, item in enumerate(range_items):
        range_name_div = item.select_one("div.card.card-body.mb-1.pointer > div.row > div.col-sm-4")
        if not range_name_div:
            logging.warning(f"Could not find range name in item {item_index + 1}.")
            continue
        range_name = range_name_div.text.strip()

        number_cards = item.select("div.card.card-body.border-bottom.bg-100")
        for num_card in number_cards:
            number_div = num_card.select_one("div.row > div.col-sm-4")
            if not number_div:
                logging.warning("Could not find number_div in a number card.")
                continue
            number = number_div.text.strip()

            sms_cards = num_card.select("div.card.card-body.border-bottom.bg-soft-dark")
            for sms_card in sms_cards:
                cli_div = sms_card.select_one("div.row > div.col-sm-4")
                msg_div = sms_card.select_one("div.row > div[class*='col-9']")
                if not (cli_div and msg_div and msg_div.find("p")):
                    continue

                message_text = msg_div.find("p").get_text(strip=True)
                otp = extract_otp_from_text(message_text)
                if not otp:
                    continue

                if cli_div.find("span"): cli_div.find("span").decompose()
                service = clean_service_name(cli_div.get_text(strip=True))

                logging.info(f"Successfully extracted OTP: Service='{service}', Number='{number}', OTP='{otp}'")
                all_otps.append({
                    "otp": otp, "phone": number, "service": service,
                    "range": range_name, "full_message": message_text
                })

    logging.info(f"Parsing complete. Total OTPs found on page: {len(all_otps)}")
    return all_otps

def main():
    """Main function to run the SMS fetching bot."""
    logging.info("Bot started.")
    keep_alive() # Start the keep-alive web server
    driver = None
    try:
        driver = setup_driver()
        if not login(driver):
            raise Exception("Login failed. Please check the logs for details.")

        try:
            logging.info("Checking for and handling site tour popover...")
            wait = WebDriverWait(driver, 5)
            next_button_1 = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.driver-popover-next-btn")))
            driver.execute_script("arguments[0].click();", next_button_1)
            time.sleep(1)
            next_button_2 = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.driver-popover-next-btn")))
            driver.execute_script("arguments[0].click();", next_button_2)
            time.sleep(1)
            logging.info("Site tour popover handled.")
        except TimeoutException:
            logging.info("Site tour popover did not appear, continuing script.")
        except Exception as e:
            logging.warning(f"A non-critical issue occurred while handling the site tour: {e}")

        while True:
            logging.info("Navigating to the SMS page...")
            driver.get(SETTINGS["SMS_URL"])
            time.sleep(2)

            wait = WebDriverWait(driver, 10)
            start_date_input = wait.until(EC.visibility_of_element_located((By.ID, "start_date")))
            end_date_input = driver.find_element(By.ID, "end_date")
            get_sms_button = driver.find_element(By.CSS_SELECTOR, "button.btn-primary")

            # Calculate dynamic date range (yesterday to today)
            today = datetime.now()
            yesterday = today - timedelta(days=1)

            start_date = yesterday.strftime("%m-%d-%Y")
            end_date = today.strftime("%m-%d-%Y")

            driver.execute_script(f"arguments[0].value = '{start_date}';", start_date_input)
            driver.execute_script(f"arguments[0].value = '{end_date}';", end_date_input)

            logging.info("Scrolling to bottom of page...")
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)

            logging.info(f"Set date range from {start_date} to {end_date} and clicking 'Get SMS'.")
            get_sms_button.click()
            time.sleep(5)

            logging.info("Expanding all ranges to reveal numbers...")
            expandable_ranges = driver.find_elements(By.CSS_SELECTOR, ".card.card-body.mb-1.pointer")
            for i, r in enumerate(expandable_ranges):
                try:
                    driver.execute_script("arguments[0].click();", r)
                    time.sleep(1.5)
                except Exception as e:
                    logging.warning(f"Could not click range {i+1}: {e}")

            time.sleep(2)

            logging.info("Expanding all numbers to reveal SMS messages...")
            expandable_numbers = driver.find_elements(By.CSS_SELECTOR, "div[onclick*='getDetialsNumber']")
            for i, n in enumerate(expandable_numbers):
                try:
                    driver.execute_script("arguments[0].click();", n)
                    time.sleep(0.75)
                except Exception as e:
                    logging.warning(f"Could not click number {i+1}: {e}")

            logging.info("Waiting 10 seconds for all SMS content to load...")
            time.sleep(10)

            logging.info("Parsing page for all OTPs...")
            all_otps_this_cycle = extract_all_otps_from_page(driver)

            processed_keys = load_processed_otps(SETTINGS["OUTPUT_FILE"])
            new_otps = []
            for otp_data in all_otps_this_cycle:
                key = f"{otp_data.get('otp','')}_{otp_data.get('phone','')}_{otp_data.get('service','')}"
                if key not in processed_keys:
                    new_otps.append(otp_data)

            if new_otps:
                logging.info(f"Found {len(new_otps)} new OTPs to send.")
                for otp_data in new_otps:
                    telegram_message = format_single_otp(otp_data)
                    send_telegram_message(telegram_message)

                try:
                    with open(SETTINGS["OUTPUT_FILE"], "a", encoding="utf-8") as f:
                        for otp_data in new_otps:
                            f.write(json.dumps(otp_data) + "\n")
                    logging.info(f"Appended {len(new_otps)} new OTP details to {SETTINGS['OUTPUT_FILE']}")
                except IOError as e:
                    logging.error(f"Could not write to file: {e}")
            else:
                logging.info("No new OTPs found in this cycle.")

            logging.info(f"Sleeping for {SETTINGS['SLEEP_SECONDS']} seconds...")
            time.sleep(SETTINGS["SLEEP_SECONDS"])

    except KeyboardInterrupt:
        logging.info("Bot stopped by user.")
    except Exception as e:
        logging.critical(f"An unexpected critical error occurred: {e}", exc_info=True)
    finally:
        if driver:
            logging.info("Closing Chrome browser.")
            driver.quit()
        logging.info("Bot shutting down.")

if __name__ == "__main__":
    main()
