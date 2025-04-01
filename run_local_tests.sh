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
pip install playwright
python -m playwright install chromium

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

# Run performance tests
echo -e "\nRunning performance tests..."
python -m pytest src/performance_tests.py -v --html=reports/performance_report.html

# Clean up
echo -e "\nCleaning up..."
kill $(cat app.pid)
rm app.pid

echo -e "\nDone! Test report available at reports/performance_report.html"