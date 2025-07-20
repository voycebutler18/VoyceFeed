# app.py
# This is a simple Flask server whose only job is to serve the index.html file.

from flask import Flask, render_template
import os

app = Flask(__name__, template_folder='templates')

@app.route('/')
def index():
    """Serves the main AI Analyzer page."""
    return render_template('index.html')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
