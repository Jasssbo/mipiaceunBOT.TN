# Dockerfile for mipiaceunBOT.TN

# Use the official Python image.
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Create a non-root user and switch to it for security
RUN useradd -m botuser && chown -R botuser:botuser /app
USER botuser

# Command to run the bot
CMD ["python", "source/main.py"]
