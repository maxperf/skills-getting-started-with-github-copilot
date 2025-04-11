#!/bin/bash
# Helper script to run performance tests locally

set -e  # Exit on error

# Check for dependencies
echo "Checking dependencies..."
if ! command -v python &> /dev/null; then
    echo "Python not found. Please install Python 3.10+"
    exit 1
fi

if ! command -v neofetch &> /dev/null; then
    echo "Installing neofetch for system metrics..."
    sudo apt-get update && sudo apt-get install -y neofetch
fi

# Install Python dependencies if needed
echo "Installing Python dependencies..."
pip install -r requirements.txt
pip install pytest-html

# Install Playwright if needed and browser
echo "Setting up Playwright..."
pip3 install --upgrade pip
pip3 install playwright

echo "Installing Playwright system dependencies..."
# The install-deps command will handle sudo permissions itself if needed
python3 -m playwright install-deps

# Install browser
echo "Installing Playwright browsers..."
python3 -m playwright install chromium

# Create reports directory
mkdir -p reports

# Start the application in background
echo "Starting the application..."
python src/app.py > app.log 2>&1 &
APP_PID=$!
echo $APP_PID > app.pid
echo "Application started with PID: $APP_PID"

# Wait for app to start
echo "Waiting for application to start..."
sleep 5

# Check if app is responding
if ! curl -s http://localhost:8000/activities > /dev/null; then
    echo "Error: Application is not responding. Check app.log for details."
    kill $APP_PID
    exit 1
fi

echo "Application is running."

# Run performance tests and capture output
echo -e "\nRunning performance tests..."
python3 -m pytest src/performance_tests.py -v --html=reports/performance_report.html

# The performance_tests.py now generates the metrics.json and summary HTML directly

# Clean up
echo -e "\nCleaning up..."
kill $APP_PID 2>/dev/null || true
rm -f app.pid
echo -e "\nDone! Test reports available at:"
echo "- HTML Report: reports/performance_report.html"
echo "- Performance Summary: reports/performance_summary.html" 
echo "- Performance Metrics: reports/performance_metrics.json"