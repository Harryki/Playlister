# Use a lightweight Python image for ARM (Raspberry Pi)
FROM python:3.11-slim

# Set workdir
WORKDIR /app

# Install Chromium + Chromedriver + dependencies
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    wget \
    unzip \
    fonts-liberation \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libgbm1 \
    libnss3 \
    libxss1 \
    libasound2 \
    libx11-xcb1 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy rest of the app
COPY . .

# Expose port
EXPOSE 5000

# Start the Flask app
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:5000", "app:app"]
