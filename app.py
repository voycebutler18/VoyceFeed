# app.py
# The core backend server for the AI Social Media Assistant.
# This script runs on Render and handles all incoming webhooks and API requests.

import os
import json
import requests
from flask import Flask, request, jsonify
from datetime import datetime, timedelta

# --- INITIALIZATION ---
app = Flask(__name__)

# --- CONFIGURATION ---
# It is critical to use environment variables for your secrets.
# On Render, set these in the "Environment" section of your web service.
# For local testing, you can run `export VERIFY_TOKEN='your_token'` in your terminal.
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN', 'set-your-verify-token')
PAGE_ACCESS_TOKEN = os.environ.get('PAGE_ACCESS_TOKEN', 'set-your-page-access-token')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', 'set-your-openai-api-key')

# --- IN-MEMORY DATA STORE (for live dashboard stats) ---
# In a production app, you would replace this with a real database like PostgreSQL.
# This simple dictionary will store live stats while the server is running.
live_stats = {
    "dms_today": 0,
    "comments_today": 0,
    "last_seven_days": {
        "dms": [0] * 7,
        "comments": [0] * 7
    },
    "recent_events": []
}

# --- META API HELPERS ---

def send_message(recipient_id, message_text):
    """Sends a message to a user via the Meta Graph API."""
    print(f"Attempting to send message to {recipient_id}: '{message_text}'")
    
    params = {
        "access_token": PAGE_ACCESS_TOKEN
    }
    headers = {
        "Content-Type": "application/json"
    }
    data = json.dumps({
        "recipient": {"id": recipient_id},
        "messaging_type": "RESPONSE",
        "message": {"text": message_text}
    })
    
    # The API endpoint for sending messages
    r = requests.post("https://graph.facebook.com/v18.0/me/messages", params=params, headers=headers, data=data)
    
    if r.status_code != 200:
        print(f"Error sending message: {r.status_code} {r.text}")
    else:
        print(f"Message sent successfully to {recipient_id}.")

# --- AI LOGIC HELPER ---

def get_ai_response(message_text):
    """
    Gets a response from an AI model (like OpenAI's GPT).
    This is where you'll implement the core AI logic.
    """
    print(f"Getting AI response for: '{message_text}'")
    
    # TODO: Implement the actual call to the OpenAI API.
    # You will need the `openai` library: pip install openai
    #
    # Example (using OpenAI's library):
    # from openai import OpenAI
    # client = OpenAI(api_key=OPENAI_API_KEY)
    # response = client.chat.completions.create(
    #   model="gpt-4o",
    #   messages=[
    #     {"role": "system", "content": "You are a helpful social media assistant."},
    #     {"role": "user", "content": message_text}
    #   ]
    # )
    # return response.choices[0].message.content

    # For now, we'll return a simple echo response for testing.
    return f"AI response placeholder: You said '{message_text}'"


# --- WEBHOOK ENDPOINT ---
# This is the single endpoint that Meta will communicate with.

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    """Handles both webhook verification (GET) and incoming messages (POST)."""
    if request.method == 'POST':
        # --- Handle Incoming Messages ---
        data = request.get_json()
        print("Received webhook data:")
        print(json.dumps(data, indent=2)) # Pretty-print the JSON for readability

        if data.get("object") == "page":
            for entry in data.get("entry", []):
                for messaging_event in entry.get("messaging", []):
                    if messaging_event.get("message"):
                        sender_id = messaging_event["sender"]["id"]
                        message_text = messaging_event["message"]["text"]
                        
                        print(f"Message from sender {sender_id}: {message_text}")

                        # --- Update Live Stats ---
                        live_stats["dms_today"] += 1
                        live_stats["recent_events"].insert(0, {
                            "type": "dm",
                            "user": f"User-{sender_id[-4:]}",
                            "message": message_text,
                            "timestamp": datetime.now().isoformat()
                        })
                        # Keep only the last 10 events
                        live_stats["recent_events"] = live_stats["recent_events"][:10]

                        # --- Process and Reply ---
                        ai_reply = get_ai_response(message_text)
                        send_message(sender_id, ai_reply)

        return "EVENT_RECEIVED", 200
    
    elif request.method == 'GET':
        # --- Handle Webhook Verification ---
        if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.challenge"):
            if not request.args.get("hub.verify_token") == VERIFY_TOKEN:
                return "Verification token mismatch", 403
            return request.args["hub.challenge"], 200
        return "OK", 200

# --- DASHBOARD API ENDPOINT ---
# This endpoint feeds the live data to your HTML dashboard.

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Provides the latest statistics to the frontend dashboard."""
    # Note: In a real app, you'd be querying your PostgreSQL database here.
    # This uses the in-memory `live_stats` dictionary.
    
    # Simple confidence metric placeholder
    ai_confidence = f"{95.0 + (live_stats['dms_today'] % 5)}%"

    return jsonify({
        "dmsReplied": live_stats["dms_today"],
        "commentsHandled": live_stats["comments_today"],
        "engagementRate": "---", # This requires Meta Insights API
        "aiConfidence": ai_confidence,
        "chartData": {
            "dms": live_stats["last_seven_days"]["dms"],
            "comments": live_stats["last_seven_days"]["comments"]
        },
        "newEvents": live_stats["recent_events"]
    })


# --- MAIN EXECUTION ---
if __name__ == '__main__':
    # The 'host' must be '0.0.0.0' to be externally accessible, e.g., on Render.
    # The 'port' is automatically set by Render, but we default to 8080 for local testing.
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True)
