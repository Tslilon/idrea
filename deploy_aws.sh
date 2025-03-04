#!/bin/bash

# ------------------------------------------------------------
# AWS Deployment Script with PDF Processing Option
# ------------------------------------------------------------

# Configuration
SSH_HOST=""                # Your AWS SSH hostname or IP
SSH_KEY="ssh_key.pem"      # Path to SSH private key
DOCKER_IMAGE="nadlan-bot"  # Docker image name
TAR_FILE="nadlan-bot.tar"  # Local tar file name
WITH_PDF=true              # Set to true to include PDF processing

# Display help message
function show_help() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -h, --host HOST      Set SSH hostname (required)"
    echo "  -k, --key KEY        Set SSH key file path (default: ssh_key.pem)"
    echo "  -p, --pdf            Include PDF processing support"
    echo "  --help               Show this help message"
    echo ""
    echo "Example:"
    echo "  $0 --host ec2-13-37-217-122.eu-west-3.compute.amazonaws.com --pdf"
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
        -p|--pdf)
            WITH_PDF=true
            shift
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
echo "  - PDF Processing: $([ "$WITH_PDF" = true ] && echo "Enabled" || echo "Disabled")"
echo ""
read -p "Continue with these settings? (y/n): " confirm
if [[ $confirm != [yY] ]]; then
    echo "Deployment cancelled."
    exit 0
fi

echo "Building Docker image..."
if [ "$WITH_PDF" = true ]; then
    # Use the full Dockerfile with PDF processing
    echo "Including PDF processing capabilities"
    docker build -f Dockerfile . -t "$DOCKER_IMAGE-$(date +%s)" --platform=linux/amd64
else
    # Use the minimal Dockerfile without PDF processing
    echo "Using minimal configuration without PDF processing"
    docker build -f Dockerfile-minimal . -t "$DOCKER_IMAGE-$(date +%s)" --platform=linux/amd64
fi

# Get the latest image ID
IMAGE_ID=$(docker images --format "{{.ID}}" | head -n 1)
echo "Built image: $IMAGE_ID"

echo "Saving Docker image to $TAR_FILE..."
docker save -o "$TAR_FILE" "$IMAGE_ID"

echo "Copying Docker image to AWS..."
scp -i "$SSH_KEY" "$TAR_FILE" "$SSH_HOST":~

echo "Deploying to AWS..."
ssh -i "$SSH_KEY" "$SSH_HOST" << EOF
    # Stop and remove any existing container
    docker stop nadlan-bot || true
    docker rm nadlan-bot || true
    
    # Load the new image
    docker load --input nadlan-bot.tar
    
    # Run the new container
    docker run -d -p 8000:8000 --rm -v ~/NadlanBot/.env:/app/.env --name nadlan-bot $IMAGE_ID
    
    # Check if container is running
    docker ps | grep nadlan-bot
EOF

echo "Deployment complete!"
echo "To start localtunnel, run and use it in meta for developers/webhook:"
echo "lt --port 8080 --subdomain curly-laws-smile-just-for-me" 