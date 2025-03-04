#!/bin/bash
# Script to fetch the remote application files

# Configuration
EC2_HOST="ec2-15-236-56-227.eu-west-3.compute.amazonaws.com"
EC2_USER="ec2-user"
SSH_KEY="ssh_key.pem"
REMOTE_DIR="/home/ec2-user/NadlanBot"

# Ensure SSH key has correct permissions
chmod 600 ${SSH_KEY}

echo "Fetching remote files from ${EC2_HOST}..."

# Create necessary directories
mkdir -p data/temp_receipts

# Fetch the application files
ssh -i ${SSH_KEY} ${EC2_USER}@${EC2_HOST} "cd ${REMOTE_DIR} && tar -czf - \
  --exclude='.env' \
  --exclude='*.pem' \
  --exclude='*.tar' \
  --exclude='nohup.out' \
  --exclude='*.log' \
  --exclude='.venv' \
  --exclude='venv' \
  --exclude='__pycache__' \
  --exclude='threads_db*' \
  ." | tar -xzf - -C .

if [ $? -ne 0 ]; then
    echo "Error: Failed to fetch remote files."
    exit 1
fi

# Create a requirements.txt file if it doesn't exist
if [ ! -f requirements.txt ]; then
    ssh -i ${SSH_KEY} ${EC2_USER}@${EC2_HOST} "cd ${REMOTE_DIR} && pip freeze > /tmp/requirements.txt && cat /tmp/requirements.txt" > requirements.txt
fi

echo "Remote files fetched successfully!"
echo "Next steps:"
echo "1. Set up a virtual environment: python -m venv venv"
echo "2. Activate it: source venv/bin/activate"
echo "3. Install dependencies: pip install -r requirements.txt"
echo "4. Run the application with Docker or directly with Flask" 