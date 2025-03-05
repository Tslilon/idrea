#!/bin/bash

# ------------------------------------------------------------
# AWS Deployment Script (GitHub-based approach)
# ------------------------------------------------------------

# Configuration
SSH_HOST=""                # Your AWS SSH hostname or IP
SSH_KEY="ssh_key.pem"      # Path to SSH private key
SSH_USER="ec2-user"        # SSH username (typically ec2-user for Amazon Linux)
GITHUB_REPO="https://github.com/Tslilon/idrea.git"  # GitHub repository URL (public)
BRANCH="main"              # Branch to deploy
PORT="8000"                # Port to expose the application

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
echo "Deployment settings:"
echo "  - SSH Host: $SSH_HOST"
echo "  - SSH Key: $SSH_KEY"
echo "  - SSH User: $SSH_USER"
echo "  - GitHub Branch: $BRANCH"
echo "  - Port: $PORT"
echo ""
read -p "Continue with these settings? (y/n): " confirm
if [[ $confirm != [yY] ]]; then
    echo "Deployment cancelled."
    exit 0
fi

# Step 1: Ensure critical directories exist on remote server
echo "Ensuring required directories exist on the server..."
ssh -i "$SSH_KEY" "$SSH_USER@$SSH_HOST" << 'EOF'
    mkdir -p ~/NadlanBot/data/temp_receipts
EOF

# Step 2: Update important configuration files
echo "Updating environment file..."
scp -i "$SSH_KEY" .env "$SSH_USER@$SSH_HOST":~/NadlanBot/.env

# Step 3: Deploy on the server using GitHub repository
echo "Deploying to AWS using GitHub repository..."
ssh -i "$SSH_KEY" "$SSH_USER@$SSH_HOST" << EOF
    # Create deployment directory if it doesn't exist
    mkdir -p ~/deployment

    # Navigate to deployment directory
    cd ~/deployment

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
    cp ~/NadlanBot/.env .env

    # Ensure data directories are available 
    mkdir -p data/temp_receipts
    
    # If there are credentials or token files, copy them to the repo
    if [ -f ~/NadlanBot/token.json ]; then
        cp ~/NadlanBot/token.json .
    fi
    
    if [ -d ~/NadlanBot/data ]; then
        cp -r ~/NadlanBot/data/* data/
    fi

    # Stop and remove any existing container
    echo "Stopping existing container..."
    docker stop nadlan-bot || true
    docker rm nadlan-bot || true
    
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
    fi
    
    # Run the new container with volume mounts for important files
    echo "Starting container on port $PORT..."
    docker run -d \
      --name nadlan-bot \
      --restart unless-stopped \
      -p $PORT:8000 \
      -v ~/NadlanBot/.env:/app/.env \
      -v ~/NadlanBot/data:/app/data \
      -v ~/NadlanBot/token.json:/app/token.json \
      nadlan-bot:latest
    
    # Check if container is running
    docker ps | grep nadlan-bot
    
    echo "Container is available at: http://$HOSTNAME:$PORT"
    echo "Use your EC2 instance public DNS: $SSH_HOST on port $PORT"
EOF

echo "Deployment complete!"
echo "Your application is available at: http://$SSH_HOST:$PORT"
echo "To start localtunnel, run and use it in meta for developers/webhook:"
echo "lt --port 8080 --subdomain curly-laws-smile-just-for-me" 