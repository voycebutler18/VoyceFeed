# app.py
# Updated to securely pass the OpenAI API key from the server environment to the webpage.

from flask import Flask, render_template
import os

app = Flask(__name__, template_folder='templates')

@app.route('/')
def index():
    """Serves the main AI Analyzer page and injects the OpenAI API key."""
    
    # Read the API key from Render's environment variables
    # It's crucial that you have set OPENAI_API_KEY in your Render dashboard.
    openai_api_key = os.environ.get('OPENAI_API_KEY', '') # Defaults to an empty string if not found
    
    # Pass the key as a variable to the index.html template
    return render_template('index.html', openai_api_key=openai_api_key)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
