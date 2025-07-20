# app.py
# Updated with the /fb-login endpoint to handle direct login from the dashboard.

import os
import subprocess
import json
from flask import Flask, render_template, jsonify, request
from playwright.sync_api import sync_playwright

app = Flask(__name__, template_folder='templates')
STATUS_LOG_FILE = 'status.log'
SESSION_FILE = 'session.json' # The file where the login session will be stored

# --- Web Interface Routes ---

@app.route('/')
def index():
    """Serves the main professional dashboard page."""
    return render_template('index.html')

@app.route('/fb-login', methods=['POST'])
def fb_login():
    """Handles the Facebook login form submission from the dashboard."""
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"error": "Email and password are required."}), 400

    print("Attempting to log into Facebook via Playwright...")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context()
            page = context.new_page()
            
            print("Navigating to Facebook login page...")
            page.goto("https://www.facebook.com/login")

            print("Filling in credentials...")
            page.fill('input[name="email"]', email)
            page.fill('input[name="pass"]', password)
            
            print("Clicking login button...")
            page.click('button[name="login"]')
            
            # Wait for navigation after login attempt
            try:
                page.wait_for_url(lambda url: "facebook.com" in url and "login" not in url, timeout=10000)
            except Exception as e:
                 print(f"Login navigation failed or took too long: {e}")
                 # Check for common failure indicators even after timeout
                 if "login/device-based/regular/login" in page.url or "checkpoint" in page.url:
                    print("Login failed: Checkpoint or invalid credentials.")
                    browser.close()
                    return jsonify({"error": "Login failed. Check credentials or 2FA."}), 401
                 # If we are not on a login page, assume success despite timeout
                 print("Warning: Navigation timed out, but not on a login page. Assuming success.")

            print("Login appears successful. Saving session state...")
            # Save the entire storage state (cookies, local storage, etc.)
            storage_state = context.storage_state()
            with open(SESSION_FILE, "w") as f:
                json.dump(storage_state, f)
            
            print(f"Session state saved to {SESSION_FILE}")
            browser.close()
            
        return jsonify({"message": "Login successful. Session saved."})
    except Exception as e:
        print(f"An unexpected error occurred during login: {e}")
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500


@app.route('/start-bot', methods=['POST'])
def start_bot():
    """Launches the bot.py script, which will use the saved session.json."""
    print("Received request to start the bot...")
    
    if not os.path.exists(SESSION_FILE):
        return jsonify({"error": "Not logged in. Please log in first to create a session."}), 401

    try:
        if os.path.exists(STATUS_LOG_FILE):
            os.remove(STATUS_LOG_FILE)
            
        subprocess.Popen(['python', 'bot.py'])
        print("bot.py script has been launched successfully.")
        return jsonify({"message": "Successfully launched the AI Assistant."}), 200
    except Exception as e:
        print(f"Error launching bot.py: {e}")
        return jsonify({"error": f"An unexpected error occurred: {e}"}), 500

@app.route('/get-status', methods=['GET'])
def get_status():
    """Reads the latest status from the log file and returns it."""
    if not os.path.exists(STATUS_LOG_FILE):
        return jsonify({"status": "waiting", "log": []})

    with open(STATUS_LOG_FILE, 'r', encoding='utf-8') as f:
        logs = f.readlines()
    
    return jsonify({"status": "running", "log": [line.strip() for line in logs]})

# --- Main Execution ---

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True)
