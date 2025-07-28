# iDrea - WhatsApp Receipt Processing System

iDrea is a WhatsApp-based automated system for processing, categorizing, and storing receipt information. The bot allows users to send images or PDFs of receipts, automatically extracts the relevant details using AI, and stores the information in a structured format.

# App Functionality

## Receipt Processing System

The iDrea WhatsApp bot is designed to help users efficiently manage and process receipt details through a conversational interface.

### Core Features

1. **Multi-format Receipt Capture**
   - **Image Processing**: Extract details from receipt photos using OCR and AI
   - **PDF Processing**: Convert PDF documents to images and extract receipt information
   - **Manual Entry**: Enter receipt details directly through a structured conversation

2. **Intelligent Data Extraction**
   - Automatically extracts key receipt information:
     - Item description (What)
     - Amount
     - VAT/IVA
     - Store name
     - Payment method
     - Charge to department
     - Additional comments

3. **User-friendly Interaction**
   - Personalized responses addressing users by their first name
   - Step-by-step guidance through the receipt submission process
   - Ability to review and correct extracted information
   - Simple confirmation commands ("yes"/"confirm" or "no"/"cancel")

4. **Google Drive Integration**
   - Automatically saves receipt images and PDFs to Google Drive
   - Creates organized files with receipt numbers as filenames
   - Provides secure links for future reference

5. **Spreadsheet Record Keeping**
   - Stores all receipt data in a Google Sheet for easy tracking
   - Assigns unique receipt numbers for reference
   - Maintains timestamps for audit purposes

### User Flow

1. User sends a receipt image or PDF to the WhatsApp bot
2. Bot uploads the file to Google Drive for storage
3. AI extracts receipt details from the image/document
4. Bot presents the extracted information to the user for verification
5. User can confirm or modify the extracted information 
6. Upon confirmation, receipt details are stored in a Google Sheet
7. User receives a confirmation message with their receipt number

### Admin Features

- Admin notifications about user interactions and receipt submissions
- Drive links included in admin notifications for easy access
- Complete visibility of all receipt transactions

### Technical Capabilities

- **Receipt Extraction**: Uses OpenAI's Vision API to intelligently extract text from images
- **PDF Handling**: Uses pdf2image library to convert PDF documents to processable images
- **Secure Storage**: Implements Google Drive API for reliable file storage
- **Data Management**: Uses shelve database to temporarily store receipt details during processing
- **Error Handling**: Graceful error recovery with user-friendly messages

The system is designed to create a smooth, error-resistant receipt processing experience through WhatsApp, making expense tracking and management simple and accessible.

# Development & Deployment

## Technical Documentation

For detailed information about the Flask application structure and implementation details, please refer to the [app/README.md](app/README.md) file.

## SSL Certificate Management

The production server uses Let's Encrypt SSL certificates that need periodic renewal. Let's Encrypt certificates are valid for 90 days.

### Automated Renewal (Recommended)

**The deployment script (`cleanup_and_deploy.sh`) automatically sets up SSL certificate renewal!** When you deploy using the script, it:

1. Installs the cron daemon if not already present
2. Configures a monthly cron job that runs `certbot renew --quiet` at midnight on the 1st of each month
3. Shows the current certificate status after deployment

This means SSL certificate renewal is now **fully automated** - you don't need to manually manage it anymore!

### Manual Renewal (If Needed)

If you need to manually check or renew certificates:

```bash
# Check certificate status
sudo certbot certificates

# Manually renew certificates if needed
sudo certbot renew
```

If certificates are not due for renewal yet, you'll see a message like:
```
The following certificates are not due for renewal yet:
  /etc/letsencrypt/live/idrea.diligent-devs.com/fullchain.pem expires on 2025-10-26 (skipped)
No renewals were attempted.
```

## Running the app

### Production Deployment

#### Automated Deployment with cleanup_and_deploy.sh

The recommended way to deploy the application to production is using the included `cleanup_and_deploy.sh` script, which automates the entire deployment process.

To deploy using the script:

```bash
# Basic usage
./cleanup_and_deploy.sh --host <server-hostname> --key <path-to-ssh-key>

# Example
./cleanup_and_deploy.sh --host ec2-##-###-##-###.eu-west-3.compute.amazonaws.com --key ssh_key.pem
```

The script handles:
- Stopping and removing existing containers
- Backing up configuration files
- Pulling the latest code from GitHub
- Building the Docker image on the server
- Setting up proper volume mounts for configuration files
- Starting the container with the correct settings
- Setting up logs
- **SSL Certificate Auto-Renewal**: Automatically configures a monthly cron job to renew Let's Encrypt certificates

For advanced options, run `./cleanup_and_deploy.sh --help` for a full list of parameters.

#### Manual Deployment (Alternative)

If you need to manually deploy the application:

1. Build the app docker container: `docker build -f Dockerfile . -t <tag or commit SHA> --platform=linux/amd64`
2. Save the docker container: `docker save -o idrea-bot.tar <docker image>`
3. Copy the docker container: `scp idrea-bot.tar <ssh hostname>:~`
4. Load the docker container to the local registry: `docker load --input idrea-bot.tar`
5. Run the container on the production server:
   ```bash 
   docker run -d -p 8000:8000 --rm \
       -v ~/deployment/idrea/.env:/app/.env \
       -v ~/deployment/idrea/data:/app/data \
       -v ~/deployment/idrea/token.json:/app/token.json \
       --name nadlan-bot <docker image>
   ```

The production server is configured with a reverse proxy that routes traffic from `https://idrea.diligent-devs.com/webhook` to the Docker container running on port 8000.

### Local Development with Tunneling

For local development, you need a tunneling service like localtunnel to make your local server accessible to WhatsApp's webhooks:

```bash
# Install localtunnel globally
npm install -g localtunnel

# Create a tunnel to your local server
lt --port 8080 --subdomain curly-laws-smile-just-for-me
```

Your local webhook URL will be: `https://curly-laws-smile-just-for-me.loca.lt/webhook`

# Development Tools

## Health Endpoint

A health check endpoint has been implemented to monitor the application's status:

- **Endpoint**: `/health`
- **Method**: GET
- **Response**: JSON object containing:
  ```json
  {
    "status": "healthy",
    "version": "1.0.1",
    "environment": "production"
  }
  ```
- **Use Cases**:
  - Monitoring application health
  - Load balancer health checks
  - Automated deployment verification

Example usage:
```bash
curl -i http://localhost:8000/health
```

## Docker Container Management

### Local Development

To build and run the application locally:

tldr:
```bash
docker-compose build server && docker-compose up -d server
docker-compose logs --follow server
lt --port 8080 --subdomain curly-laws-smile-just-for-me
```

or:
```bash
# Build the Docker image
docker build -t nadlanbot-local .

# Run the container
docker run -d -p 8000:8000 -v $(pwd)/.env:/app/.env -v $(pwd)/data:/app/data --name nadlanbot-local nadlanbot-local

# View container logs
docker logs -f nadlanbot-local
```

### Managing Containers

```bash
# List all running containers
docker ps -a | grep 8000

# Stop and remove containers
docker stop nadlanbot && docker rm nadlanbot
docker stop nadlanbot-local && docker rm nadlanbot-local

# Check for port conflicts
lsof -i :8000
```

### Server Directory Structure

The EC2 server uses the following directory structure for the application:

```
/home/ec2-user/
├── deployment/                # Main deployment directory
│   ├── idrea/                 # Application code and configuration
│   │   ├── .env               # Environment variables
│   │   ├── data/              # Data directory containing:
│   │   │   ├── credentials.json               # Google API credentials
│   │   │   ├── nadlanbot-410712-ad9fec93b0df.json  # Service account key
│   │   │   └── temp_receipts/                # Temporary storage for receipts
│   │   └── token.json         # OAuth token for Google API
├── backups/                   # Backup directory created by deployment script
└── logs/                      # Directory for container logs
```

**IMPORTANT NOTES**:
1. **Always use the deployment script**: The `cleanup_and_deploy.sh` script handles all necessary backups and setup.
2. **Container name**: The Docker container should be named `nadlan-bot` (with a hyphen).
3. **Volume mounts**: The deployment script ensures these three essential volume mounts:
   - `.env` file
   - `data` directory
   - `token.json` file

### Troubleshooting Deployment

1. **Container won't start**: Check logs with `docker logs nadlan-bot`
2. **Missing data directory**: The `data` directory must exist and contain:
   - `credentials.json`
   - `nadlanbot-410712-ad9fec93b0df.json` (service account key)
   - `temp_receipts` subdirectory
3. **Permission issues**: Ensure files have proper permissions:
   ```bash
   ssh <server> "chmod 644 /home/ec2-user/deployment/idrea/.env"
   ssh <server> "chmod 644 /home/ec2-user/deployment/idrea/token.json"
   ssh <server> "chmod -R 755 /home/ec2-user/deployment/idrea/data"
   ```

### Viewing Server Logs

To monitor the application logs on the server:

```bash
# View all logs
ssh -i ssh_key.pem ec2-user@<server-hostname> "docker logs nadlan-bot"

# View most recent logs (last 50 lines)
ssh -i ssh_key.pem ec2-user@<server-hostname> "docker logs nadlan-bot --tail 50"

# Follow logs in real-time (press Ctrl+C to exit)
ssh -i ssh_key.pem ec2-user@<server-hostname> "docker logs nadlan-bot --follow"

# Filter logs for errors
ssh -i ssh_key.pem ec2-user@<server-hostname> "docker logs nadlan-bot | grep -i error"
```

## Testing Endpoints

### Test Health Endpoint

```bash
curl -i http://localhost:8000/health
```

### Test Webhook Endpoint

```bash
curl -i "http://localhost:8000/webhook?hub.mode=subscribe&hub.verify_token=<your-verify-token>&hub.challenge=test_challenge"
```

## Local Development Guide

## Running the Application with Docker

The application is containerized using Docker, which makes it easy to run consistently across different environments. Follow these steps to run the application locally:

### Prerequisites

1. Install [Docker](https://www.docker.com/get-started) and [Docker Compose](https://docs.docker.com/compose/install/) on your machine
2. Clone the repository to your local machine
3. Create a `.env` file in the root directory with the required environment variables (see below for reference)

### Environment Variables

The following environment variables should be defined in your `.env` file:

```
OPENAI_API_KEY=your_openai_api_key
GOOGLE_SERVICE_ACCOUNT_FILE=path_to_service_account_file
GOOGLE_CREDENTIALS_JSON=your_google_credentials_json
GOOGLE_SHEET_ID=your_google_sheet_id
GOOGLE_FOLDER_ID=your_google_folder_id
ACCESS_TOKEN=your_access_token
APP_SECRET=your_app_secret
RECIPIENT_WAID=your_recipient_waid
VERSION=your_version
PHONE_NUMBER_ID=your_phone_number_id
VERIFY_TOKEN=your_verify_token
```

### Starting the Docker Container

1. Build and start the Docker container:

```bash
# Build and start the server in detached mode
docker-compose build server && docker-compose up -d server
```

2. Check if the container is running:

```bash
docker-compose ps
```

3. View the logs:

```bash
# View all logs
docker-compose logs server

# View the last 50 lines
docker-compose logs --tail=50 server

# Follow the logs in real-time
docker-compose logs --follow server
```

4. Stop the container:

```bash
docker-compose down
```

### Rebuilding After Code Changes

When you make changes to the code, you need to rebuild the Docker container:

```bash
docker-compose build server && docker-compose up -d server
```

## Exposing Your Local Server with Localtunnel

To test webhooks, you need to expose your local server to the internet using Localtunnel.

### Installing Localtunnel

```bash
# Install localtunnel globally using npm
npm install -g localtunnel
```

### Using Localtunnel

1. Start your Docker container as described above
2. In a separate terminal, run localtunnel to expose your local server with a fixed subdomain:

```bash
# With the specific subdomain used in Meta Developer Portal
lt --port 8080 --subdomain curly-laws-smile-just-for-me
```

3. Your localtunnel URL will be: `https://curly-laws-smile-just-for-me.loca.lt`

4. To check if the tunnel is working, visit the health endpoint:

```bash
curl https://curly-laws-smile-just-for-me.loca.lt/health
```

5. To stop localtunnel, press `Ctrl+C` in the terminal where it's running

## Configuring WhatsApp Webhook for Development vs Production

### Development Webhook
For local development, the webhook URL is:
- **Webhook URL**: `https://curly-laws-smile-just-for-me.loca.lt/webhook`

### Production Webhook
For production, the webhook URL is:
- **Production Webhook URL**: `https://idrea.diligent-devs.com/webhook`

### Setting Up the Webhook in Meta Developer Portal

1. Navigate to the Meta Developer Portal and go to your WhatsApp business app
2. Configure your webhook with:
   - **Callback URL**: The development or production URL depending on your needs
   - **Verify Token**: The value you set in your `.env` file for `VERIFY_TOKEN`
   - **Subscribe to**: The `messages` field

3. Test the webhook verification by visiting:
   ```
   https://curly-laws-smile-just-for-me.loca.lt/webhook?hub.mode=subscribe&hub.verify_token=YOUR_VERIFY_TOKEN&hub.challenge=CHALLENGE_ACCEPTED
   ```

4. If configured correctly, you should see `CHALLENGE_ACCEPTED` as the response

## Troubleshooting

### Docker Issues

- **Container won't start**: Check the logs with `docker-compose logs` for error messages
- **Port conflicts**: Make sure port 8080 is not being used by another application
- **Environment variables**: Ensure all required environment variables are set in your `.env` file

### Localtunnel Issues

- **Connection refused**: Make sure your Docker container is running and listening on port 8080
- **Tunnel unavailable**: Restart localtunnel, as the session may have expired
- **503 error**: The tunnel may be overloaded or experiencing issues; try restarting localtunnel

### Webhook Issues

- **Verification fails**: Double-check that the verify token in your `.env` file matches the one in the Meta Developer Portal
- **Not receiving messages**: Check the Docker logs to see if the webhook is receiving requests
- **403 errors**: The signature verification may be failing; temporarily comment out the `@signature_required` decorator in `app/views.py` for testing

## Development Best Practices

- Always test webhook functionality with localtunnel before deploying
- Use the enhanced logging in the webhook handler to debug issues
- Check the Docker logs frequently to monitor the application's behavior
- After making changes to the code, rebuild the Docker container and restart localtunnel

## Webhook Configuration for Local Development

When developing locally, you need to ensure that WhatsApp messages can reach your local development server.

### Update the webhook URL in Meta Developer Dashboard

1. Start your local development server:
   ```
   docker-compose up --build -d
   ```

2. Create a tunnel to expose your local server:
   ```
   lt --port 8080 --print-url
   ```

3. Update the webhook URL in the Meta Developer Dashboard:
   - Go to [Meta Developer Dashboard](https://developers.facebook.com/)
   - Navigate to your WhatsApp app > Configuration
   - Update the Callback URL to your localtunnel URL + `/webhook` (e.g., `https://great-mangos-doubt.loca.lt/webhook`)
   - Verify Token: Use the value from your `.env` file (default: `1234`)
   - Click "Verify and Save"

