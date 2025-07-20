#!/bin/bash

# Install Python dependencies
pip install -r requirements.txt

# Install Playwright and its dependencies
playwright install

# Download standalone Chromium manually
mkdir -p /opt/render/chrome
curl -Lo /opt/render/chrome/chrome-linux.zip https://storage.googleapis.com/chromium-browser-snapshots/Linux_x64/1181205/chrome-linux.zip
unzip /opt/render/chrome/chrome-linux.zip -d /opt/render/chrome/
mv /opt/render/chrome/chrome-linux /opt/render/chrome/chrome-linux64
chmod +x /opt/render/chrome/chrome-linux64/chrome
