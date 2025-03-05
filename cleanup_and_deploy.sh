#!/bin/bash

# ------------------------------------------------------------
# Server Cleanup and Redeployment Script
# ------------------------------------------------------------
# This script deploys the application to the EC2 server using the following structure:
# 
# Directory Structure on Server:
# /home/ec2-user/
# ├── deployment/                # Main deployment directory
# │   ├── idrea/                 # Application code and configuration
# │   │   ├── .env               # Environment variables
# │   │   ├── data/              # Data directory containing credentials & receipts
# │   │   └── token.json         # OAuth token for Google API
# └── backups/                   # Backup directory for important files
#
# IMPORTANT: All deployments use the /home/ec2-user/deployment/idrea/ directory.
# Do NOT use the legacy ~/NadlanBot directory for new deployments.
# ------------------------------------------------------------

# Configuration
SSH_HOST=""                # Your AWS SSH hostname or IP
SSH_KEY="ssh_key.pem"      # Path to SSH private key
SSH_USER="ec2-user"        # SSH username (typically ec2-user for Amazon Linux)
GITHUB_REPO="https://github.com/Tslilon/idrea.git"  # GitHub repository URL (public)
BRANCH="main"              # Branch to deploy
PORT="8000"                # Port to expose the application
ENABLE_LOGGING=true        # Whether to enable persistent logging

# Display help message
function show_help() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -h, --host HOST      Set SSH hostname (required)"
    echo "  -k, --key KEY        Set SSH key file path (default: ssh_key.pem)"
    echo "  -u, --user USER      Set SSH username (default: ec2-user)"
    echo "  -b, --branch BRANCH  Set Git branch (default: main)"
    echo "  -p, --port PORT      Set port to expose (default: 8000)"
    echo "  -l, --logging        Enable persistent logging (default: true)"
    echo "  --help               Show this help message"
    echo ""
    echo "Example:"
    echo "  $0 --host ec2-15-236-56-227.eu-west-3.compute.amazonaws.com"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--host)
            SSH_HOST="$2"
            shift 2
            ;;
        -k|--key)
            SSH_KEY="$2"
            shift 2
            ;;
        -u|--user)
            SSH_USER="$2"
            shift 2
            ;;
        -b|--branch)
            BRANCH="$2"
            shift 2
            ;;
        -p|--port)
            PORT="$2"
            shift 2
            ;;
        -l|--logging)
            ENABLE_LOGGING="$2"
            shift 2
            ;;
        --help)
            show_help
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Check required parameters
if [ -z "$SSH_HOST" ]; then
    echo "Error: SSH host is required."
    show_help
    exit 1
fi

# Show configuration and confirm
echo "Cleanup and Deployment Settings:"
echo "  - SSH Host: $SSH_HOST"
echo "  - SSH Key: $SSH_KEY"
echo "  - SSH User: $SSH_USER"
echo "  - GitHub Branch: $BRANCH"
echo "  - Port: $PORT"
echo "  - Persistent Logging: $ENABLE_LOGGING"
echo ""
read -p "Continue with these settings? (y/n): " CONFIRM
if [ "$CONFIRM" != "y" ]; then
    echo "Deployment cancelled."
    exit 0
fi

# Ensure SSH key has correct permissions
chmod 600 "$SSH_KEY"

# Step 1: Clean up the server
echo "Step 1: Cleaning up the server..."
ssh -i "$SSH_KEY" "$SSH_USER@$SSH_HOST" << 'EOF'
    # Stop all running containers
    echo "Stopping all Docker containers..."
    CONTAINERS=$(docker ps -q)
    if [ ! -z "$CONTAINERS" ]; then
        echo $CONTAINERS
        docker stop $CONTAINERS
    fi
    
    # Remove all containers
    echo "Removing all Docker containers..."
    CONTAINERS=$(docker ps -a -q)
    if [ ! -z "$CONTAINERS" ]; then
        echo $CONTAINERS
        docker rm $CONTAINERS
    fi
    
    # Clean up unused Docker resources
    echo "Cleaning up unused Docker resources..."
    docker system prune -f
    
    # Backup important files
    echo "Backing up important files..."
    mkdir -p ~/backups/data
    
    # The following section backs up files from the deployment directory
    # IMPORTANT: All files are stored in /home/ec2-user/deployment/idrea/
    # This is the correct path for all deployments
    if [ -f ~/deployment/idrea/.env ]; then
        cp ~/deployment/idrea/.env ~/backups/.env
    fi
    
    if [ -f ~/deployment/idrea/token.json ]; then
        cp ~/deployment/idrea/token.json ~/backups/token.json
    fi
    
    if [ -d ~/deployment/idrea/data ]; then
        cp -r ~/deployment/idrea/data/* ~/backups/data/
    fi
    
    # Remove redundant large files - add sudo for permission issues
    echo "Removing redundant large files..."
    sudo rm -f ~/nadlan-bot.tar || true
    sudo rm -f ~/deployment/idrea/nadlan-bot.tar || true
    sudo rm -f ~/deployment/idrea/ec2-13-37-217-122.eu-west-3.compute.amazonaws.com || true
    
    # Clean up docker image tarballs - add sudo for permission issues
    sudo rm -f ~/*.tar || true
    
    # Create logs directory for persistent logging
    mkdir -p ~/logs
    
    echo "Cleanup completed successfully."
EOF

# Step 2: Make sure critical directories exist on remote server
echo "Step 2: Setting up required directories..."
ssh -i "$SSH_KEY" "$SSH_USER@$SSH_HOST" << 'EOF'
    mkdir -p ~/deployment/idrea/data/temp_receipts
    mkdir -p ~/logs
EOF

# Step 3: Update important configuration files
echo "Step 3: Updating environment file..."
scp -i "$SSH_KEY" .env "$SSH_USER@$SSH_HOST":~/deployment/idrea/.env

# Upload credentials files if they exist locally
echo "Step 4: Uploading credential files..."
if [ -f "token.json" ]; then
    scp -i "$SSH_KEY" token.json "$SSH_USER@$SSH_HOST":~/deployment/idrea/token.json
fi

if [ -f "data/credentials.json" ]; then
    scp -i "$SSH_KEY" data/credentials.json "$SSH_USER@$SSH_HOST":~/deployment/idrea/data/credentials.json
fi

if [ -f "data/nadlanbot-410712-ad9fec93b0df.json" ]; then
    scp -i "$SSH_KEY" data/nadlanbot-410712-ad9fec93b0df.json "$SSH_USER@$SSH_HOST":~/deployment/idrea/data/nadlanbot-410712-ad9fec93b0df.json
fi

# Step 5: Deploy on the server using GitHub repository
echo "Step 5: Deploying to AWS using GitHub repository..."
ssh -i "$SSH_KEY" "$SSH_USER@$SSH_HOST" << EOF
    # Navigate to deployment directory
    cd ~/deployment
    
    # Restore important files from backup
    if [ -f ~/backups/.env ]; then
        cp ~/backups/.env .env || true
    fi
    
    if [ -f ~/backups/token.json ]; then
        cp ~/backups/token.json token.json || true
    fi
    
    if [ -d ~/backups/data ]; then
        mkdir -p data
        cp -r ~/backups/data/* data/ || true
    fi

    # Clean previous deployment if exists
    if [ -d "idrea" ]; then
        echo "Updating existing repository..."
        cd idrea
        git fetch --all
        git reset --hard origin/$BRANCH
    else
        echo "Cloning repository..."
        git clone --branch $BRANCH $GITHUB_REPO idrea
        
        # Check if clone was successful
        if [ ! -d "idrea" ]; then
            echo "Failed to clone repository. Aborting deployment."
            exit 1
        fi
        
        cd idrea
    fi

    # Verify we have necessary files
    if [ ! -f "Dockerfile" ]; then
        echo "Dockerfile not found in repository. Aborting deployment."
        exit 1
    fi
    
    # Copy environment files to the repository
    echo "Setting up environment files..."
    cp ~/deployment/idrea/.env .env || true

    # Ensure data directories are available 
    mkdir -p data/temp_receipts
    
    # If there are credentials or token files, copy them to the repo
    if [ -f ~/deployment/idrea/token.json ]; then
        cp ~/deployment/idrea/token.json . || true
    fi
    
    if [ -d ~/deployment/idrea/data ]; then
        cp -r ~/deployment/idrea/data/* data/ || true
    fi

    # Stop and remove any existing container
    echo "Stopping existing container..."
    docker stop nadlan-bot || true
    docker rm nadlan-bot || true
    docker stop nadlanbot || true
    docker rm nadlanbot || true
    
    # Clean up unused Docker resources
    docker system prune -f
    
    # Build Docker image on the server
    echo "Building Docker image on the server..."
    docker build -t nadlan-bot:latest .
    
    # Check if port is already in use and find an alternative if needed
    if netstat -tuln | grep -q ":$PORT "; then
        echo "Warning: Port $PORT is already in use."
        echo "Using alternative port: 8001"
        PORT=8001
        
        # Check if alternative port is also in use
        if netstat -tuln | grep -q ":$PORT "; then
            echo "Warning: Port $PORT is also in use."
            echo "Using alternative port: 8002"
            PORT=8002
        fi
    fi
    
    # Run the new container with volume mounts for important files
    echo "Starting container on port $PORT..."
    
    # If logging is enabled, set up log redirection
    if [ "$ENABLE_LOGGING" = "true" ]; then
        # Create a log file with timestamp
        LOG_FILE=~/logs/nadlan-bot-\$(date +%Y-%m-%d_%H-%M-%S).log
        mkdir -p ~/logs
        touch \$LOG_FILE
        chmod 666 \$LOG_FILE
        
        docker run -d \
          --name nadlan-bot \
          --restart unless-stopped \
          -p $PORT:8000 \
          -v ~/deployment/idrea/.env:/app/.env \
          -v ~/deployment/idrea/data:/app/data \
          -v ~/deployment/idrea/token.json:/app/token.json \
          nadlan-bot:latest > \$LOG_FILE 2>&1
        
        echo "Logs will be saved to: \$LOG_FILE"
        echo "You can view logs with: docker logs nadlan-bot"
    else
        # Run without persistent logging
        docker run -d \
          --name nadlan-bot \
          --restart unless-stopped \
          -p $PORT:8000 \
          -v ~/deployment/idrea/.env:/app/.env \
          -v ~/deployment/idrea/data:/app/data \
          -v ~/deployment/idrea/token.json:/app/token.json \
          nadlan-bot:latest
    fi
    
    # Verify container is running
    docker ps | grep nadlan-bot
    
    # Clean up unnecessary files
    echo "Cleaning up unnecessary files from ~/deployment/idrea..."
    rm -f nadlan-bot.tar || true
    
    # Output success message
    echo "Container is available at: http://$SSH_HOST:$PORT"
EOF

echo "Cleanup and redeployment complete!"
echo "Your application is available at: http://$SSH_HOST:$PORT"
echo "To view logs on the server run: ssh -i $SSH_KEY $SSH_USER@$SSH_HOST 'docker logs nadlan-bot'"
# echo "To start a local tunnel for webhook testing, run:"
# echo "lt --port 8080 --subdomain curly-laws-smile-just-for-me" 