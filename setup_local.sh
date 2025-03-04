#!/bin/bash
# Script to set up local development environment

set -e

echo "Setting up local development environment for iDrea..."

# Create Python virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Create necessary directories
echo "Creating necessary directories..."
mkdir -p data/temp_receipts

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "Warning: .env file not found. Make sure to create one with the necessary environment variables."
fi

echo "Local development environment setup complete!"
echo ""
echo "Next steps:"
echo "1. Ensure your .env file is properly configured"
echo "2. Run the application with 'python run.py'"
echo "3. Or use Docker with 'docker-compose up'"
echo ""
echo "To expose the application for webhook testing:"
echo "ngrok http 8000" 