#!/bin/bash
# Deployment script for iDrea/NadlanBot

# Configuration
EC2_HOST="ec2-15-236-56-227.eu-west-3.compute.amazonaws.com"
EC2_USER="ec2-user"
SSH_KEY="ssh_key.pem"
REMOTE_DIR="/home/ec2-user/NadlanBot"

# Ensure SSH key has correct permissions
chmod 600 ${SSH_KEY}

echo "Deploying to ${EC2_HOST}..."

# Sync files to the EC2 instance using rsync
rsync -avz -e "ssh -i ${SSH_KEY}" ./ ${EC2_USER}@${EC2_HOST}:${REMOTE_DIR}/

echo "Files synced successfully."

# SSH into the EC2 instance and run the commands
ssh -i ${SSH_KEY} -t ${EC2_USER}@${EC2_HOST} << 'EOF'
cd /home/ec2-user/NadlanBot

# More aggressive approach to handle port 8000
echo "Checking for processes using port 8000..."
sudo lsof -i :8000 || echo "No process found using lsof"
PORT_PROCESSES=$(sudo lsof -i :8000 -t || echo "")
if [ ! -z "$PORT_PROCESSES" ]; then
    echo "Killing processes using port 8000: $PORT_PROCESSES"
    for pid in $PORT_PROCESSES; do
        sudo kill -9 $pid || echo "Failed to kill process $pid"
    done
fi

# Force kill any Docker container using port 8000
echo "Stopping all Docker containers..."
docker ps -q | xargs -r docker stop
docker ps -aq | xargs -r docker rm

# Clean up Docker resources
echo "Cleaning up Docker resources..."
docker system prune -f

# Build a new Docker image
echo "Building Docker image..."
docker build -t nadlanbot .

# Try running on a different port first to test if the container works
echo "Testing container on alternative port (8001)..."
docker run -d --name nadlanbot-test -p 8001:8000 nadlanbot
sleep 3
docker logs nadlanbot-test
docker stop nadlanbot-test
docker rm nadlanbot-test

# Now try to run on port 8000
echo "Starting container on port 8000..."
docker run -d \
  --name nadlanbot \
  --restart unless-stopped \
  -p 8000:8000 \
  -v /home/ec2-user/NadlanBot/.env:/app/.env \
  -v /home/ec2-user/NadlanBot/data:/app/data \
  nadlanbot

# Print the container ID for verification
docker ps | grep nadlanbot
EOF

echo "Deployment completed successfully!" 