# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install Python dependencies
# The --no-cache-dir flag is a good practice for keeping image sizes small
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers AND all their required system dependencies.
# The --with-deps flag is crucial and will work correctly inside Docker.
RUN python -m playwright install --with-deps

# Copy the rest of your application code into the container
COPY . .

# Tell Docker that the container will listen on this port at runtime.
# Render will automatically use this port.
EXPOSE 10000

# The command to run your application using Gunicorn, a professional web server.
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "app:app"]
