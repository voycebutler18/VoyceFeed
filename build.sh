#!/bin/bash

# Install Python packages
pip install -r requirements.txt

# Manually install Chromium and export paths
apt-get update && apt-get install -y wget unzip fonts-liberation libatk-bridge2.0-0 libatk1.0-0 libcups2 libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libgbm1 libasound2 libpangocairo-1.0-0 libgtk-3-0 libnss3 libxss1 libxshmfence1 libx11-xcb1

# Download Chromium
mkdir -p /opt/render/chrome
wget -q https://storage.googleapis.com/chrome-for-testing-public/121.0.6167.184/linux64/chrome-linux64.zip -O chrome.zip
unzip chrome.zip -d /opt/render/chrome/
chmod +x /opt/render/chrome/chrome-linux64/chrome

# Export env var so Playwright uses this manually installed Chromium
echo "PLAYWRIGHT_BROWSERS_PATH=0" > .env
echo "CHROME_EXECUTABLE_PATH=/opt/render/chrome/chrome-linux64/chrome" >> .env
