#!/usr/bin/env bash
# This script runs on the Render build server.

# Exit on error
set -o errexit

# 1. Install Python dependencies
echo "Installing Python dependencies..."
pip install -r requirements.txt

# 2. Install Playwright browsers
echo "Installing Playwright browsers..."
playwright install

echo "Build complete."
