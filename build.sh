#!/usr/bin/env bash
# A robust build script to fix C-extension compilation errors on Render.

# Exit immediately if a command exits with a non-zero status.
set -o errexit

# 1. Upgrade pip and build tools
# This is the crucial step to solve the 'greenlet' error.
echo "Upgrading pip, setuptools, and wheel..."
pip install --upgrade pip setuptools wheel

# 2. Install Python dependencies from requirements.txt
echo "Installing Python dependencies..."
pip install -r requirements.txt

# 3. Install Playwright's browsers
echo "Installing Playwright browsers..."
python -m playwright install --with-deps

echo "Build complete."
