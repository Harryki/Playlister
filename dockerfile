# Use a lightweight Python image for ARM (Raspberry Pi)
FROM python:3.11-slim

# Set workdir
WORKDIR /app

# Install system dependencies required by Playwright and Chromium
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    unzip \
    ca-certificates \
    libnss3 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libgbm1 \
    libxss1 \
    libasound2 \
    libx11-xcb1 \
    xdg-utils \
    fonts-liberation \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install playwright && playwright install chromium

# Copy rest of the app
COPY . .

# Expose port
EXPOSE 5000

# Start the Flask app
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:5000", "app:app"]
