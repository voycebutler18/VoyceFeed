# app.py
# A simple Flask server to serve the control panel and launch the automation bot.

import os
import subprocess
from flask import Flask, render_template, jsonify, request

app = Flask(__name__, template_folder='.')

# --- Web Interface Routes ---

@app.route('/')
def index():
    """Serves the main control panel page."""
    # This will look for a file named 'index.html' in the same directory.
    return render_template('index.html')

@app.route('/start-bot', methods=['POST'])
def start_bot():
    """
    Launches the bot.py script as a separate process.
    This is non-blocking, so the web server can continue to run.
    """
    print("Received request to start the bot...")
    try:
        # We use Popen to run the script in the background.
        # This allows the server to respond immediately while the bot runs.
        # It's crucial for long-running automation tasks.
        subprocess.Popen(['python', 'bot.py'])
        print("bot.py script has been launched successfully.")
        return jsonify({"message": "Successfully launched the AI Assistant. Check the server console for logs."}), 200
    except FileNotFoundError:
        print("Error: 'bot.py' not found. Make sure it's in the same directory.")
        return jsonify({"error": "Failed to launch bot: 'bot.py' not found."}), 500
    except Exception as e:
        print(f"Error launching bot.py: {e}")
        return jsonify({"error": f"An unexpected error occurred: {e}"}), 500

# --- Main Execution ---

if __name__ == '__main__':
    # The host '0.0.0.0' makes the server accessible on your local network
    # and is required for deployment on services like Render.
    # The port is fetched from environment variables, defaulting to 8080.
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True)
