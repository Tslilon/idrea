#!/bin/bash

# ------------------------------------------------------------
# Server Cleanup and Redeployment Script
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

# Check if hostname is provided
if [ -z "$SSH_HOST" ]; then
    echo "Error: SSH hostname is required"
    show_help
    exit 1
fi

# Confirm deployment settings
echo "Cleanup and Deployment Settings:"
echo "  - SSH Host: $SSH_HOST"
echo "  - SSH Key: $SSH_KEY"
echo "  - SSH User: $SSH_USER"
echo "  - GitHub Branch: $BRANCH"
echo "  - Port: $PORT"
echo "  - Persistent Logging: $ENABLE_LOGGING"
echo ""
read -p "Continue with these settings? (y/n): " confirm
if [[ $confirm != [yY] ]]; then
    echo "Operation cancelled."
    exit 0
fi

# Ensure SSH key has correct permissions
chmod 600 "$SSH_KEY"

# Step 1: SSH into the server and clean up all Docker containers and redundant files
echo "Step 1: Cleaning up the server..."
ssh -i "$SSH_KEY" "$SSH_USER@$SSH_HOST" << 'EOF'
    # Stop all Docker containers
    echo "Stopping all Docker containers..."
    docker stop $(docker ps -aq) || true
    
    # Remove all Docker containers
    echo "Removing all Docker containers..."
    docker rm $(docker ps -aq) || true
    
    # Clean up unused Docker resources
    echo "Cleaning up unused Docker resources..."
    docker system prune -af --volumes
    
    # Clean up old deployment files but preserve important ones
    echo "Backing up important files..."
    mkdir -p ~/backups
    
    # Save important files before cleanup
    if [ -f ~/NadlanBot/.env ]; then
        cp ~/NadlanBot/.env ~/backups/.env || true
    fi
    
    if [ -f ~/NadlanBot/token.json ]; then
        cp ~/NadlanBot/token.json ~/backups/token.json || true
    fi
    
    if [ -d ~/NadlanBot/data ]; then
        mkdir -p ~/backups/data
        cp -r ~/NadlanBot/data/* ~/backups/data/ || true
    fi
    
    # Remove redundant large files - add sudo for permission issues
    echo "Removing redundant large files..."
    sudo rm -f ~/nadlan-bot.tar || true
    sudo rm -f ~/NadlanBot/nadlan-bot.tar || true
    sudo rm -f ~/NadlanBot/ec2-13-37-217-122.eu-west-3.compute.amazonaws.com || true
    
    # Clean up docker image tarballs - add sudo for permission issues
    sudo rm -f ~/*.tar || true
    
    # Create logs directory for persistent logging
    mkdir -p ~/logs
    
    echo "Cleanup completed successfully."
EOF

# Step 2: Make sure critical directories exist on remote server
echo "Step 2: Setting up required directories..."
ssh -i "$SSH_KEY" "$SSH_USER@$SSH_HOST" << 'EOF'
    mkdir -p ~/NadlanBot/data/temp_receipts
    mkdir -p ~/deployment
    mkdir -p ~/logs
EOF

# Step 3: Update important configuration files
echo "Step 3: Updating environment file..."
scp -i "$SSH_KEY" .env "$SSH_USER@$SSH_HOST":~/NadlanBot/.env

# Upload credentials files if they exist locally
echo "Step 4: Uploading credential files..."
if [ -f "token.json" ]; then
    scp -i "$SSH_KEY" token.json "$SSH_USER@$SSH_HOST":~/NadlanBot/token.json
fi

if [ -f "data/credentials.json" ]; then
    scp -i "$SSH_KEY" data/credentials.json "$SSH_USER@$SSH_HOST":~/NadlanBot/data/credentials.json
fi

if [ -f "data/nadlanbot-410712-0929523261c7.json" ]; then
    scp -i "$SSH_KEY" data/nadlanbot-410712-0929523261c7.json "$SSH_USER@$SSH_HOST":~/NadlanBot/data/nadlanbot-410712-0929523261c7.json
fi

if [ -f "data/nadlanbot-410712-58847aeaca48.json" ]; then
    scp -i "$SSH_KEY" data/nadlanbot-410712-58847aeaca48.json "$SSH_USER@$SSH_HOST":~/NadlanBot/data/nadlanbot-410712-58847aeaca48.json
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
    cp ~/NadlanBot/.env .env || true

    # Ensure data directories are available 
    mkdir -p data/temp_receipts
    
    # If there are credentials or token files, copy them to the repo
    if [ -f ~/NadlanBot/token.json ]; then
        cp ~/NadlanBot/token.json . || true
    fi
    
    if [ -d ~/NadlanBot/data ]; then
        cp -r ~/NadlanBot/data/* data/ || true
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
        touch \$LOG_FILE
        chmod 666 \$LOG_FILE
        
        docker run -d \
          --name nadlan-bot \
          --restart unless-stopped \
          -p $PORT:8000 \
          -v ~/NadlanBot/.env:/app/.env \
          -v ~/NadlanBot/data:/app/data \
          -v ~/NadlanBot/token.json:/app/token.json \
          -v \$LOG_FILE:/app/app.log \
          --log-driver json-file \
          --log-opt max-size=50m \
          --log-opt max-file=3 \
          nadlan-bot:latest
          
        echo "Logs will be saved to: \$LOG_FILE"
        echo "You can view logs with: docker logs nadlan-bot"
    else
        docker run -d \
          --name nadlan-bot \
          --restart unless-stopped \
          -p $PORT:8000 \
          -v ~/NadlanBot/.env:/app/.env \
          -v ~/NadlanBot/data:/app/data \
          -v ~/NadlanBot/token.json:/app/token.json \
          nadlan-bot:latest
    fi
    
    # Check if container is running
    docker ps | grep nadlan-bot
    
    # Clean up any unnecessary files except important ones
    echo "Cleaning up unnecessary files from ~/NadlanBot..."
    
    # Keep track of important files we need to preserve
    mkdir -p ~/temp_preserve
    
    if [ -f ~/NadlanBot/.env ]; then
        cp ~/NadlanBot/.env ~/temp_preserve/ || true
    fi
    
    if [ -f ~/NadlanBot/token.json ]; then
        cp ~/NadlanBot/token.json ~/temp_preserve/ || true
    fi
    
    if [ -d ~/NadlanBot/data ]; then
        mkdir -p ~/temp_preserve/data
        cp -r ~/NadlanBot/data/* ~/temp_preserve/data/ || true
    fi
    
    # Remove the entire NadlanBot directory and recreate with only important files
    # Added sudo to fix permission issues
    sudo rm -rf ~/NadlanBot || true
    mkdir -p ~/NadlanBot/data/temp_receipts
    
    # Restore important files
    if [ -f ~/temp_preserve/.env ]; then
        cp ~/temp_preserve/.env ~/NadlanBot/ || true
    fi
    
    if [ -f ~/temp_preserve/token.json ]; then
        cp ~/temp_preserve/token.json ~/NadlanBot/ || true
    fi
    
    if [ -d ~/temp_preserve/data ]; then
        cp -r ~/temp_preserve/data/* ~/NadlanBot/data/ || true
    fi
    
    # Clean up temp directory with sudo for permission issues
    sudo rm -rf ~/temp_preserve || true
    
    echo "Container is available at: http://$SSH_HOST:$PORT"
EOF

echo "Cleanup and redeployment complete!"
echo "Your application is available at: http://$SSH_HOST:$PORT"
echo "To view logs on the server run: ssh -i $SSH_KEY $SSH_USER@$SSH_HOST 'docker logs nadlan-bot'"
# echo "To start a local tunnel for webhook testing, run:"
# echo "lt --port 8080 --subdomain curly-laws-smile-just-for-me" 