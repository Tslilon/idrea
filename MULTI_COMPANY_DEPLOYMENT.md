# Multi-Company Deployment Guide for iDrea

This guide explains how to deploy the iDrea WhatsApp receipt processing service for multiple companies using a single codebase with environment-based configuration.

## 🎯 **Deployment Strategy: Environment-Based Multi-Tenancy**

**✅ RECOMMENDED APPROACH**: One repository, multiple environment configurations

### Why This Approach?

| **Approach** | **Pros** | **Cons** | **Best For** |
|-------------|----------|----------|--------------|
| **🏆 Environment-Based** | ✅ Single codebase<br>✅ Easy maintenance<br>✅ Security isolation<br>✅ Scalable | ⚠️ Requires discipline | **Multiple clients** |
| Separate Repositories | ✅ Complete isolation | ❌ Code duplication<br>❌ Maintenance overhead | Large enterprises |
| Multi-tenant App | ✅ Resource efficient | ❌ Complex architecture<br>❌ Security risks | SaaS platforms |

## 📁 **Project Structure**

```
idrea/
├── app/                          # 🔄 Shared application code  
├── requirements.txt              # 🔄 Shared dependencies
├── Dockerfile                    # 🔄 Shared container config
├── deploy-company.sh             # 🆕 Multi-company deployment
├── manage-deployments.sh         # 🆕 Management utilities
├── environments/                 # 🆕 Company-specific configs
│   ├── your-company/            # Your current setup
│   │   ├── .env
│   │   ├── data/
│   │   └── token.json
│   ├── client-a/                # New client A
│   │   ├── .env
│   │   └── data/
│   ├── client-b/                # New client B
│   │   ├── .env
│   │   └── data/
│   └── company-template/        # Template for new companies
│       └── .env.template
└── README.md
```

## 🚀 **Quick Start: Deploy for New Company**

### 1. Create Company Environment
```bash
# Create new company configuration
cp -r environments/company-template environments/client-a
cd environments/client-a
cp .env.template .env

# Edit .env and replace all PLACEHOLDER values
nano .env
```

### 2. Set Up Company Credentials
```bash
# Add Google service account file
cp /path/to/client-a-service-account.json data/service-account.json

# Add OAuth credentials  
cp /path/to/client-a-credentials.json data/credentials.json

# Run OAuth flow for Google APIs
# (Run this step manually with the client)
```

### 3. Deploy to Server
```bash
# Option A: New EC2 instance (recommended)
./deploy-company.sh --company client-a --host ec2-new-instance.amazonaws.com

# Option B: Same instance, different port
./deploy-company.sh --company client-a --host ec2-15-236-56-227.eu-west-3.compute.amazonaws.com --port 8001
```

### 4. Configure WhatsApp Webhook
```bash
# Update Meta Developer Console with:
# Webhook URL: https://client-a.yourdomain.com/webhook
# Verify Token: [from client-a/.env]
```

## 🛠️ **Management Commands**

```bash
# List all configured companies
./manage-deployments.sh list

# Check server status
./manage-deployments.sh status ec2-instance.amazonaws.com

# View logs for specific company
./manage-deployments.sh logs client-a ec2-instance.amazonaws.com

# Check health
./manage-deployments.sh health ec2-instance.amazonaws.com 8001

# Stop deployment
./manage-deployments.sh stop client-a ec2-instance.amazonaws.com
```

## 📊 **Deployment Options**

### Option 1: Separate EC2 Instances (Recommended)
```
Company A → EC2 Instance A:8000 → a.yourdomain.com
Company B → EC2 Instance B:8000 → b.yourdomain.com  
Your Co   → EC2 Instance C:8000 → yourdomain.com
```

**Pros**: Complete isolation, easier scaling, independent billing
**Cons**: Higher AWS costs (~$8.50/month per t2.micro)

### Option 2: Same Instance, Different Ports
```
Company A → EC2 Instance:8000 → yourdomain.com:8000
Company B → EC2 Instance:8001 → yourdomain.com:8001
Your Co   → EC2 Instance:8002 → yourdomain.com:8002
```

**Pros**: Lower cost, resource sharing
**Cons**: Shared failure point, port management complexity

### Option 3: Hybrid Approach
```
Your Company     → Dedicated EC2:8000
Small Clients    → Shared EC2:8001,8002,8003
Enterprise Client → Dedicated EC2:8000
```

**Pros**: Balanced cost and isolation
**Cons**: More complex management

## 🔐 **Security & Isolation**

### What's Isolated Per Company:
- ✅ **WhatsApp API credentials** (ACCESS_TOKEN, etc.)
- ✅ **Google Drive/Sheets** (separate folders & sheets)
- ✅ **Receipt data** (completely separate storage)
- ✅ **Container processes** (separate Docker containers)
- ✅ **Log files** (company-specific log directories)

### What's Shared:
- 🔄 **Application code** (same Docker image)
- 🔄 **OpenAI API key** (can be shared or separate)
- 🔄 **Server infrastructure** (if using same EC2)

## 💰 **Cost Analysis**

### Per Company Costs:
| **Resource** | **Separate Instance** | **Shared Instance** |
|-------------|----------------------|-------------------|
| EC2 t2.micro | $8.50/month | $0 (shared) |
| WhatsApp API | $0 (1000 msgs free) | $0 |
| OpenAI API | ~$10-20/month | ~$10-20/month |
| Google APIs | $0 (generous free tier) | $0 |
| **Total** | **~$18-28/month** | **~$10-20/month** |

### Setup Time:
- **First company**: 2-3 hours (learning curve)
- **Additional companies**: 30-45 minutes each

## 🔧 **Advanced Configuration**

### Custom Domain Setup
```bash
# 1. Set up reverse proxy (nginx)
# 2. Configure SSL (Let's Encrypt)
# 3. Point subdomain to specific port

# Example nginx config:
server {
    server_name client-a.yourdomain.com;
    location / {
        proxy_pass http://localhost:8001;
    }
}
```

### Monitoring & Alerts
```bash
# Set up health check monitoring
*/5 * * * * curl -f http://client-a.yourdomain.com/health || echo "Client A down!"

# Log rotation for each company
# (Handled automatically by Docker log rotation)
```

### Backup Strategy
```bash
# Backup company-specific data
tar -czf backup-client-a-$(date +%Y%m%d).tar.gz environments/client-a/
```

## 🚨 **Troubleshooting**

### Common Issues:

**1. Container won't start**
```bash
# Check logs
./manage-deployments.sh logs company-name host

# Check environment file
grep PLACEHOLDER environments/company-name/.env
```

**2. WhatsApp webhook fails**
```bash
# Verify webhook URL in Meta Console
curl -X GET "https://your-domain.com/webhook?hub.mode=subscribe&hub.verify_token=YOUR_TOKEN&hub.challenge=test"

# Should return "test"
```

**3. Google API errors**
```bash
# Verify service account permissions
# Check if files are correctly mounted in container
docker exec idrea-company-8001 ls -la /app/data/
```

## 📈 **Scaling Recommendations**

### When to Use Each Option:

**Single Instance** (1-3 companies):
- Small clients with low message volume
- Cost optimization priority
- Acceptable shared risk

**Multiple Instances** (3+ companies):
- Enterprise clients requiring SLAs  
- High-volume message processing
- Geographic distribution needs

**Kubernetes/ECS** (10+ companies):
- Large-scale deployment
- Auto-scaling requirements
- Professional DevOps management

---

## 🎉 **Success! You Now Have**

✅ **Scalable multi-company deployment**
✅ **Complete data isolation per company** 
✅ **Single codebase for easy maintenance**
✅ **Automated deployment scripts**
✅ **Management utilities for monitoring**
✅ **Comprehensive documentation**

**Next Steps**: Follow the [New Company Setup Guide](environments/NEW_COMPANY_SETUP.md) to deploy your first client! 