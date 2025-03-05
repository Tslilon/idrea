#!/bin/bash

# ------------------------------------------------------------
# AWS Deployment Script (Docker-only approach)
# ------------------------------------------------------------

# Configuration
SSH_HOST=""                # Your AWS SSH hostname or IP
SSH_KEY="ssh_key.pem"      # Path to SSH private key
SSH_USER="ec2-user"        # SSH username (typically ec2-user for Amazon Linux)
DOCKER_IMAGE="nadlan-bot"  # Docker image name
TAR_FILE="nadlan-bot.tar"  # Local tar file name

# Display help message
function show_help() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -h, --host HOST      Set SSH hostname (required)"
    echo "  -k, --key KEY        Set SSH key file path (default: ssh_key.pem)"
    echo "  -u, --user USER      Set SSH username (default: ec2-user)"
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

# Step 3: Build Docker image locally with all code
echo "Building Docker image with PDF processing capabilities included..."
TIMESTAMP=$(date +%s)
IMAGE_NAME="$DOCKER_IMAGE-$TIMESTAMP"
docker build -f Dockerfile . -t "$IMAGE_NAME" --platform=linux/amd64

# Get the latest image ID
IMAGE_ID=$(docker images --format "{{.ID}}" | head -n 1)
echo "Built image: $IMAGE_ID with tag $IMAGE_NAME"

# Step 4: Save and transfer Docker image
echo "Saving Docker image to $TAR_FILE..."
docker save -o "$TAR_FILE" "$IMAGE_NAME"

echo "Transferring Docker image to AWS (this may take a while)..."
scp -i "$SSH_KEY" "$TAR_FILE" "$SSH_USER@$SSH_HOST":~

# Step 5: Deploy on the server
echo "Deploying to AWS..."
ssh -i "$SSH_KEY" "$SSH_USER@$SSH_HOST" << EOF
    # Stop and remove any existing container
    docker stop nadlan-bot || true
    docker rm nadlan-bot || true
    
    # Clean up unused Docker resources
    docker system prune -f
    
    # Load the new image
    echo "Loading Docker image (this may take a while)..."
    docker load --input ~/nadlan-bot.tar
    
    # Get the loaded image information
    echo "Verifying loaded image..."
    LOADED_IMAGE=\$(docker images --format "{{.Repository}}:{{.Tag}}" | head -n 1)
    echo "Image loaded as: \$LOADED_IMAGE"
    
    # Run the new container with volume mounts for important files
    echo "Starting container..."
    docker run -d \
      --name nadlan-bot \
      --restart unless-stopped \
      -p 8000:8000 \
      -v ~/NadlanBot/.env:/app/.env \
      -v ~/NadlanBot/data:/app/data \
      -v ~/NadlanBot/token.json:/app/token.json \
      \$LOADED_IMAGE
    
    # Check if container is running
    docker ps | grep nadlan-bot
EOF

echo "Deployment complete!"
echo "To start localtunnel, run and use it in meta for developers/webhook:"
echo "lt --port 8080 --subdomain curly-laws-smile-just-for-me" 