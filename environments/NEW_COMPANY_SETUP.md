# Setting Up iDrea for a New Company

This guide walks you through deploying the iDrea WhatsApp receipt processing service for a new company.

## 🎯 Quick Setup Checklist

- [ ] Create company environment directory
- [ ] Set up WhatsApp Business API 
- [ ] Configure Google Drive & Sheets
- [ ] Get OpenAI API key
- [ ] Deploy to AWS EC2
- [ ] Test the service

## 📁 Step 1: Create Company Environment

```bash
# Replace 'company-name' with actual company name (lowercase, no spaces)
cp -r environments/company-template environments/company-name
cd environments/company-name
cp .env.template .env
```

## 🔧 Step 2: WhatsApp Business API Setup

1. **Create Meta App**: Go to [Meta for Developers](https://developers.facebook.com/apps/)
2. **Add WhatsApp Business**: Add WhatsApp Business product to your app
3. **Get Credentials**: Copy these values to your `.env` file:
   - `ACCESS_TOKEN`: From API Setup → Temporary token (later upgrade to System User token)
   - `APP_SECRET`: From App Dashboard → App Settings → Basic
   - `PHONE_NUMBER_ID`: From API Setup → Phone number ID
   - `VERIFY_TOKEN`: Create your own secure token (e.g., `company-name-webhook-2024`)

4. **Configure Webhook**:
   - URL: `https://your-domain.com/webhook`  
   - Verify Token: Your `VERIFY_TOKEN`
   - Subscribe to: `messages`

## 📊 Step 3: Google Services Setup

### Google Drive & Sheets
1. **Create Google Project**: [Google Cloud Console](https://console.cloud.google.com/)
2. **Enable APIs**: Drive API, Sheets API
3. **Create Service Account**: 
   - Download JSON → save as `data/service-account.json`
   - Share Drive folder with service account email
4. **Create Folder & Sheet**:
   - Create Google Drive folder for receipts
   - Create Google Sheet for receipt data  
   - Copy IDs from URLs to `.env`

### OAuth Credentials (for admin access)
1. **Create OAuth 2.0 Client**: In Google Cloud Console
2. **Download JSON** → save as `data/credentials.json`
3. **Run initial auth**: `python -c "from app.utils.google_auth import authenticate; authenticate()"`

## 🤖 Step 4: OpenAI API

1. **Get API Key**: [OpenAI Platform](https://platform.openai.com/api-keys)
2. **Add to `.env`**: `OPENAI_API_KEY="sk-proj-..."`
3. **Set Budget Limits**: Recommended $20/month for small company

## 🚀 Step 5: Deploy to AWS

### Option A: New EC2 Instance
```bash
# Create new EC2 t2.micro instance
# Install Docker, configure security groups for port 8000

# Deploy
./deploy-company.sh --company company-name --host ec2-new-instance.amazonaws.com
```

### Option B: Same Instance, Different Port  
```bash
# Deploy to different port on existing instance
./deploy-company.sh --company company-name --host ec2-15-236-56-227.eu-west-3.compute.amazonaws.com --port 8001
```

## ✅ Step 6: Test & Verify

1. **Health Check**: `curl https://your-domain.com/health`
2. **Webhook Test**: Send test WhatsApp message
3. **Receipt Test**: Send receipt image via WhatsApp
4. **Check Google**: Verify file appears in Drive & data in Sheet

## 🔐 Security Best Practices

- [ ] Use System User tokens (not temporary) for production
- [ ] Set up proper Google IAM permissions
- [ ] Configure environment-specific domain names
- [ ] Monitor API usage limits
- [ ] Regular token rotation schedule

## 📞 Support

- **Technical Issues**: Contact your development team
- **WhatsApp Setup**: [Meta Business Help](https://business.facebook.com/help/)
- **Google API Issues**: [Google Cloud Support](https://cloud.google.com/support)

---

**Estimated Setup Time**: 2-3 hours for first company, 30 minutes for subsequent companies. 