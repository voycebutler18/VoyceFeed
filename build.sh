#!/usr/bin/env bash
# This script runs on the Render build server.
# This version uses a more explicit command to install browsers.

# Exit on any error
set -o errexit

# 1. Install Python dependencies from requirements.txt
echo "Installing Python dependencies..."
pip install -r requirements.txt

# 2. Install Playwright browsers using the Python module
# This is a more robust method than calling 'playwright' directly.
echo "Installing Playwright browsers via python -m playwright..."
python -m playwright install

echo "Build complete. Browsers should now be installed."
