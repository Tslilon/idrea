#!/bin/bash

# ------------------------------------------------------------
# Multi-Company Deployment Script for iDrea
# ------------------------------------------------------------
# This script deploys company-specific configurations of the 
# iDrea WhatsApp receipt processing service.
#
# Usage Examples:
#   ./deploy-company.sh --company your-company --host ec2-instance.amazonaws.com
#   ./deploy-company.sh --company client-a --host ec2-instance.amazonaws.com --port 8001
#   ./deploy-company.sh --company client-b --host another-instance.amazonaws.com
# ------------------------------------------------------------

# Configuration defaults
COMPANY_NAME=""
SSH_HOST=""
SSH_KEY="ssh_key.pem"
SSH_USER="ec2-user"
GITHUB_REPO="https://github.com/Tslilon/idrea.git"
BRANCH="main"
PORT="8000"
ENABLE_LOGGING=true

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Display help
function show_help() {
    echo "Multi-Company iDrea Deployment Script"
    echo ""
    echo "Usage: $0 --company COMPANY_NAME --host SSH_HOST [OPTIONS]"
    echo ""
    echo "Required:"
    echo "  -c, --company NAME    Company environment name (must exist in environments/)"
    echo "  -h, --host HOST       EC2 SSH hostname or IP address"
    echo ""
    echo "Options:"
    echo "  -k, --key FILE        SSH private key file (default: ssh_key.pem)"
    echo "  -u, --user USER       SSH username (default: ec2-user)"
    echo "  -p, --port PORT       Application port (default: 8000)"
    echo "  -b, --branch BRANCH   Git branch to deploy (default: main)"
    echo "  --help                Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 --company your-company --host ec2-15-236-56-227.eu-west-3.compute.amazonaws.com"
    echo "  $0 --company client-a --host ec2-instance.amazonaws.com --port 8001"
    echo ""
    echo "Available companies:"
    if [ -d "environments" ]; then
        ls environments/ | grep -v "company-template" | sed 's/^/  - /'
    else
        echo "  No environments directory found. Run from project root."
    fi
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -c|--company)
            COMPANY_NAME="$2"
            shift 2
            ;;
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
        -p|--port)
            PORT="$2"
            shift 2
            ;;
        -b|--branch)
            BRANCH="$2"
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

# Validate required parameters
if [ -z "$COMPANY_NAME" ] || [ -z "$SSH_HOST" ]; then
    echo -e "${RED}Error: Both --company and --host are required.${NC}"
    show_help
    exit 1
fi

# Validate company environment exists
COMPANY_ENV_DIR="environments/$COMPANY_NAME"
if [ ! -d "$COMPANY_ENV_DIR" ]; then
    echo -e "${RED}Error: Company environment '$COMPANY_NAME' not found.${NC}"
    echo "Expected directory: $COMPANY_ENV_DIR"
    echo ""
    echo "To create a new company environment:"
    echo "  cp -r environments/company-template environments/$COMPANY_NAME"
    exit 1
fi

# Validate required files exist
REQUIRED_FILES=("$COMPANY_ENV_DIR/.env")
for file in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$file" ]; then
        echo -e "${RED}Error: Required file not found: $file${NC}"
        echo "Copy .env.template to .env and configure it first."
        exit 1
    fi
done

# Check for placeholder values in .env
if grep -q "PLACEHOLDER" "$COMPANY_ENV_DIR/.env"; then
    echo -e "${YELLOW}Warning: Found PLACEHOLDER values in $COMPANY_ENV_DIR/.env${NC}"
    echo "Please replace all PLACEHOLDER values with actual credentials."
    echo ""
    grep "PLACEHOLDER" "$COMPANY_ENV_DIR/.env" | head -3
    echo ""
    read -p "Continue anyway? (y/N): " CONTINUE
    if [ "$CONTINUE" != "y" ]; then
        echo "Deployment cancelled."
        exit 0
    fi
fi

# Generate container name based on company and port
CONTAINER_NAME="idrea-${COMPANY_NAME}-${PORT}"

# Show deployment configuration
echo -e "${GREEN}🚀 Multi-Company Deployment Configuration:${NC}"
echo "  - Company: $COMPANY_NAME"
echo "  - SSH Host: $SSH_HOST"
echo "  - SSH Key: $SSH_KEY"
echo "  - Port: $PORT"
echo "  - Container: $CONTAINER_NAME"
echo "  - Branch: $BRANCH"
echo "  - Environment: $COMPANY_ENV_DIR"
echo ""
read -p "Continue with deployment? (y/N): " CONFIRM
if [ "$CONFIRM" != "y" ]; then
    echo "Deployment cancelled."
    exit 0
fi

# Ensure SSH key has correct permissions
chmod 600 "$SSH_KEY"

echo -e "${GREEN}Step 1: Preparing server environment...${NC}"
ssh -i "$SSH_KEY" "$SSH_USER@$SSH_HOST" << EOF
    # Create company-specific directories
    mkdir -p ~/deployment/${COMPANY_NAME}/data/temp_receipts
    mkdir -p ~/logs/${COMPANY_NAME}
    
    # Stop existing container if running
    docker stop $CONTAINER_NAME 2>/dev/null || true
    docker rm $CONTAINER_NAME 2>/dev/null || true
    
    echo "Server preparation completed for $COMPANY_NAME"
EOF

echo -e "${GREEN}Step 2: Uploading company-specific configuration...${NC}"
# Upload environment file
scp -i "$SSH_KEY" "$COMPANY_ENV_DIR/.env" "$SSH_USER@$SSH_HOST":~/deployment/${COMPANY_NAME}/.env

# Upload credentials if they exist
if [ -f "$COMPANY_ENV_DIR/token.json" ]; then
    scp -i "$SSH_KEY" "$COMPANY_ENV_DIR/token.json" "$SSH_USER@$SSH_HOST":~/deployment/${COMPANY_NAME}/token.json
fi

if [ -d "$COMPANY_ENV_DIR/data" ]; then
    scp -i "$SSH_KEY" -r "$COMPANY_ENV_DIR/data" "$SSH_USER@$SSH_HOST":~/deployment/${COMPANY_NAME}/
fi

echo -e "${GREEN}Step 3: Deploying application...${NC}"
ssh -i "$SSH_KEY" "$SSH_USER@$SSH_HOST" << EOF
    # Navigate to deployment directory
    cd ~/deployment
    
    # Clone or update repository
    if [ -d "idrea-shared" ]; then
        echo "Updating existing repository..."
        cd idrea-shared
        git fetch --all
        git reset --hard origin/$BRANCH
    else
        echo "Cloning repository..."
        git clone --branch $BRANCH $GITHUB_REPO idrea-shared
        cd idrea-shared
    fi
    
    # Build Docker image (shared across companies)
    echo "Building Docker image..."
    docker build -t idrea:latest .
    
    # Run company-specific container
    echo "Starting container: $CONTAINER_NAME on port $PORT"
    
    # Set up logging
    LOG_FILE=~/logs/${COMPANY_NAME}/app-\$(date +%Y-%m-%d_%H-%M-%S).log
    mkdir -p ~/logs/${COMPANY_NAME}
    touch \$LOG_FILE
    chmod 666 \$LOG_FILE
    
    # Start container with company-specific mounts
    docker run -d \\
        --name $CONTAINER_NAME \\
        --restart unless-stopped \\
        -p $PORT:8000 \\
        -v ~/deployment/${COMPANY_NAME}/.env:/app/.env \\
        -v ~/deployment/${COMPANY_NAME}/data:/app/data \\
        -v ~/deployment/${COMPANY_NAME}/token.json:/app/token.json \\
        --log-driver json-file \\
        --log-opt max-size=50m \\
        --log-opt max-file=3 \\
        idrea:latest
    
    # Set up log streaming
    nohup docker logs -f $CONTAINER_NAME >> \$LOG_FILE 2>&1 &
    
    # Verify container is running
    sleep 5
    if docker ps | grep -q $CONTAINER_NAME; then
        echo "✅ Container $CONTAINER_NAME is running successfully"
        docker ps | grep $CONTAINER_NAME
    else
        echo "❌ Container failed to start"
        docker logs $CONTAINER_NAME
        exit 1
    fi
    
    echo "Deployment completed for $COMPANY_NAME"
    echo "Logs: \$LOG_FILE"
    echo "Container: $CONTAINER_NAME"
    echo "Port: $PORT"
EOF

echo ""
echo -e "${GREEN}🎉 Deployment Complete!${NC}"
echo ""
echo "Company: $COMPANY_NAME"
echo "URL: http://$SSH_HOST:$PORT"
echo "Health Check: curl http://$SSH_HOST:$PORT/health"
echo "Container: $CONTAINER_NAME"
echo ""
echo "Next steps:"
echo "1. Configure your domain/reverse proxy to point to port $PORT"
echo "2. Update WhatsApp webhook URL to your domain"
echo "3. Test with a receipt image via WhatsApp"
echo ""
echo "View logs: ssh -i $SSH_KEY $SSH_USER@$SSH_HOST 'docker logs $CONTAINER_NAME'" 