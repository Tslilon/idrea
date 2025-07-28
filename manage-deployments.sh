#!/bin/bash

# ------------------------------------------------------------
# Multi-Company Deployment Management Script
# ------------------------------------------------------------
# This script helps manage multiple iDrea deployments across
# different companies and servers.
# ------------------------------------------------------------

SSH_KEY="ssh_key.pem"
SSH_USER="ec2-user"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

function show_help() {
    echo "iDrea Multi-Company Deployment Manager"
    echo ""
    echo "Usage: $0 [COMMAND] [OPTIONS]"
    echo ""
    echo "Commands:"
    echo "  list                  List all configured companies"
    echo "  status HOST           Show running containers on specified host"
    echo "  logs COMPANY HOST     View logs for specific company deployment"
    echo "  stop COMPANY HOST     Stop specific company deployment"
    echo "  restart COMPANY HOST  Restart specific company deployment"
    echo "  health HOST [PORT]    Check health of deployment(s)"
    echo ""
    echo "Examples:"
    echo "  $0 list"
    echo "  $0 status ec2-15-236-56-227.eu-west-3.compute.amazonaws.com"
    echo "  $0 logs your-company ec2-instance.amazonaws.com"
    echo "  $0 health ec2-instance.amazonaws.com 8001"
}

function list_companies() {
    echo -e "${GREEN}📁 Configured Companies:${NC}"
    echo ""
    if [ -d "environments" ]; then
        for company_dir in environments/*/; do
            if [ -d "$company_dir" ]; then
                company=$(basename "$company_dir")
                if [ "$company" != "company-template" ]; then
                    echo -n "  📋 $company"
                    if [ -f "$company_dir/.env" ]; then
                        echo -e " ${GREEN}✓${NC}"
                    else
                        echo -e " ${RED}✗ (missing .env)${NC}"
                    fi
                fi
            fi
        done
    else
        echo -e "${RED}No environments directory found${NC}"
    fi
    echo ""
}

function show_status() {
    local host=$1
    if [ -z "$host" ]; then
        echo -e "${RED}Error: Host required${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}🖥️  Server Status: $host${NC}"
    echo ""
    
    ssh -i "$SSH_KEY" "$SSH_USER@$host" << 'EOF'
        echo "📊 Running iDrea Containers:"
        echo ""
        docker ps --filter "name=idrea-" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
        echo ""
        
        echo "💾 Memory Usage:"
        free -h | grep Mem
        echo ""
        
        echo "💿 Disk Usage:"
        df -h / | tail -1
        echo ""
        
        echo "📁 Deployment Directories:"
        if [ -d ~/deployment ]; then
            ls -la ~/deployment/ | grep -E '^d' | awk '{print "  " $9}'
        else
            echo "  No deployment directories found"
        fi
EOF
}

function show_logs() {
    local company=$1
    local host=$2
    
    if [ -z "$company" ] || [ -z "$host" ]; then
        echo -e "${RED}Error: Company and host required${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}📋 Logs for $company on $host:${NC}"
    echo ""
    
    # Try to find the container for this company
    ssh -i "$SSH_KEY" "$SSH_USER@$host" << EOF
        # Find container name
        CONTAINER=\$(docker ps --filter "name=idrea-$company" --format "{{.Names}}" | head -1)
        
        if [ -n "\$CONTAINER" ]; then
            echo "📦 Container: \$CONTAINER"
            echo "🕐 Last 50 log entries:"
            echo ""
            docker logs --tail 50 "\$CONTAINER"
        else
            echo "❌ No running container found for company: $company"
            echo ""
            echo "Available containers:"
            docker ps --filter "name=idrea-" --format "{{.Names}}"
        fi
EOF
}

function stop_deployment() {
    local company=$1
    local host=$2
    
    if [ -z "$company" ] || [ -z "$host" ]; then
        echo -e "${RED}Error: Company and host required${NC}"
        exit 1
    fi
    
    echo -e "${YELLOW}⏹️  Stopping deployment for $company on $host...${NC}"
    
    ssh -i "$SSH_KEY" "$SSH_USER@$host" << EOF
        CONTAINERS=\$(docker ps --filter "name=idrea-$company" --format "{{.Names}}")
        
        if [ -n "\$CONTAINERS" ]; then
            echo "Stopping containers: \$CONTAINERS"
            docker stop \$CONTAINERS
            docker rm \$CONTAINERS
            echo "✅ Stopped successfully"
        else
            echo "❌ No running containers found for company: $company"
        fi
EOF
}

function restart_deployment() {
    local company=$1
    local host=$2
    
    if [ -z "$company" ] || [ -z "$host" ]; then
        echo -e "${RED}Error: Company and host required${NC}"
        exit 1
    fi
    
    echo -e "${BLUE}🔄 Restarting deployment for $company on $host...${NC}"
    
    # Stop first
    stop_deployment "$company" "$host"
    
    echo ""
    echo "To restart, use the deploy command:"
    echo "  ./deploy-company.sh --company $company --host $host"
}

function check_health() {
    local host=$1
    local port=${2:-8000}
    
    if [ -z "$host" ]; then
        echo -e "${RED}Error: Host required${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}🏥 Health Check: $host:$port${NC}"
    echo ""
    
    if curl -s -f "http://$host:$port/health" > /dev/null; then
        response=$(curl -s "http://$host:$port/health")
        echo -e "${GREEN}✅ Healthy${NC}"
        echo "Response: $response"
    else
        echo -e "${RED}❌ Unhealthy or unreachable${NC}"
    fi
}

# Main command handling
case $1 in
    list)
        list_companies
        ;;
    status)
        show_status "$2"
        ;;
    logs)
        show_logs "$2" "$3"
        ;;
    stop)
        stop_deployment "$2" "$3"
        ;;
    restart)
        restart_deployment "$2" "$3"
        ;;
    health)
        check_health "$2" "$3"
        ;;
    *)
        show_help
        ;;
esac 