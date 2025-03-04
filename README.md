# Build AI WhatsApp Bots with Pure Python

This guide will walk you through the process of creating a WhatsApp bot using the Meta (formerly Facebook) Cloud API with pure Python, and Flask particular. We'll also integrate webhook events to receive messages in real-time and use OpenAI to generate AI responses. For more information on the structure of the Flask application, you can refer to [this documentation](https://github.com/daveebbelaar/python-whatsapp-bot/tree/main/app).

## Prerequisites

1. A Meta developer account — If you don't have one, you can [create a Meta developer account here](https://developers.facebook.com/).
2. A business app — If you don't have one, you can [learn to create a business app here](https://developers.facebook.com/docs/development/create-an-app/). If you don't see an option to create a business app, select **Other** > **Next** > **Business**.
3. Familiarity with Python to follow the tutorial.


## Table of Contents

- [Build AI WhatsApp Bots with Pure Python](#build-ai-whatsapp-bots-with-pure-python)
  - [Prerequisites](#prerequisites)
  - [Table of Contents](#table-of-contents)
  - [Get Started](#get-started)
  - [Step 1: Select Phone Numbers](#step-1-select-phone-numbers)
  - [Step 2: Send Messages with the API](#step-2-send-messages-with-the-api)
  - [Step 3: Configure Webhooks to Receive Messages](#step-3-configure-webhooks-to-receive-messages)
      - [Start your app](#start-your-app)
      - [Launch ngrok](#launch-ngrok)
      - [Integrate WhatsApp](#integrate-whatsapp)
      - [Testing the Integration](#testing-the-integration)
  - [Step 4: Understanding Webhook Security](#step-4-understanding-webhook-security)
      - [Verification Requests](#verification-requests)
      - [Validating Verification Requests](#validating-verification-requests)
      - [Validating Payloads](#validating-payloads)
  - [Step 5: Learn about the API and Build Your App](#step-5-learn-about-the-api-and-build-your-app)
  - [Step 6: Integrate AI into the Application](#step-6-integrate-ai-into-the-application)
  - [Step 7: Add a Phone Number](#step-7-add-a-phone-number)
  - [Datalumina](#datalumina)
  - [Tutorials](#tutorials)

## Get Started

1. **Overview & Setup**: Begin your journey [here](https://developers.facebook.com/docs/whatsapp/cloud-api/get-started).
2. **Locate Your Bots**: Your bots can be found [here](https://developers.facebook.com/apps/).
3. **WhatsApp API Documentation**: Familiarize yourself with the [official documentation](https://developers.facebook.com/docs/whatsapp).
4. **Helpful Guide**: Here's a [Python-based guide](https://developers.facebook.com/blog/post/2022/10/24/sending-messages-with-whatsapp-in-your-python-applications/) for sending messages.
5. **API Docs for Sending Messages**: Check out [this documentation](https://developers.facebook.com/docs/whatsapp/cloud-api/guides/send-messages).

## Step 1: Select Phone Numbers

- Make sure WhatsApp is added to your App.
- You begin with a test number that you can use to send messages to up to 5 numbers.
- Go to API Setup and locate the test number from which you will be sending messages.
- Here, you can also add numbers to send messages to. Enter your **own WhatsApp number**.
- You will receive a code on your phone via WhatsApp to verify your number.

## Step 2: Send Messages with the API

1. Obtain a 24-hour access token from the API access section.
2. It will show an example of how to send messages using a `curl` command which can be send from the terminal or with a tool like Postman.
3. Let's convert that into a [Python function with the request library](https://github.com/daveebbelaar/python-whatsapp-bot/blob/main/start/whatsapp_quickstart.py).
4. Create a `.env` files based on `example.env` and update the required variables. [Video example here](https://www.youtube.com/watch?v=sOwG0bw0RNU).
5. You will receive a "Hello World" message (Expect a 60-120 second delay for the message).

Creating an access that works longer then 24 hours
1. Create a [system user at the Meta Business account level](https://business.facebook.com/settings/system-users).
2. On the System Users page, configure the assets for your System User, assigning your WhatsApp app with full control. Don't forget to click the Save Changes button.
   - [See step 1 here](https://github.com/daveebbelaar/python-whatsapp-bot/blob/main/img/meta-business-system-user-token.png)
   - [See step 2 here](https://github.com/daveebbelaar/python-whatsapp-bot/blob/main/img/adding-assets-to-system-user.png)
3. Now click `Generate new token` and select the app, and then choose how long the access token will be valid. You can choose 60 days or never expire.
4. Select all the permissions, as I was running into errors when I only selected the WhatsApp ones.
5. Confirm and copy the access token.

Now we have to find the following information on the **App Dashboard**:

- **APP_ID**: "<YOUR-WHATSAPP-BUSINESS-APP_ID>" (Found at App Dashboard)
- **APP_SECRET**: "<YOUR-WHATSAPP-BUSINESS-APP_SECRET>" (Found at App Dashboard)
- **RECIPIENT_WAID**: "<YOUR-RECIPIENT-TEST-PHONE-NUMBER>" (This is your WhatsApp ID, i.e., phone number. Make sure it is added to the account as shown in the example test message.)
- **VERSION**: "v20.0" (The latest version of the Meta Graph API)
- **ACCESS_TOKEN**: "<YOUR-SYSTEM-USER-ACCESS-TOKEN>" (Created in the previous step)

> You can only send a template type message as your first message to a user. That's why you have to send a reply first before we continue. Took me 2 hours to figure this out.


## Step 3: Configure Webhooks to Receive Messages

> Please note, this is the hardest part of this tutorial.

#### Start your app
- Make you have a python installation or environment and install the requirements: `pip install -r requirements.txt`
- Run your Flask app locally by executing [run.py](https://github.com/daveebbelaar/python-whatsapp-bot/blob/main/run.py)

#### Launch ngrok

The steps below are taken from the [ngrok documentation](https://ngrok.com/docs/integrations/whatsapp/webhooks/).

> You need a static ngrok domain because Meta validates your ngrok domain and certificate!

Once your app is running successfully on localhost, let's get it on the internet securely using ngrok!

1. If you're not an ngrok user yet, just sign up for ngrok for free.
2. Download the ngrok agent.
3. Go to the ngrok dashboard, click Your [Authtoken](https://dashboard.ngrok.com/get-started/your-authtoken), and copy your Authtoken.
4. Follow the instructions to authenticate your ngrok agent. You only have to do this once.
5. On the left menu, expand Cloud Edge and then click Domains.
6. On the Domains page, click + Create Domain or + New Domain. (here everyone can start with [one free domain](https://ngrok.com/blog-post/free-static-domains-ngrok-users))
7. Start ngrok by running the following command in a terminal on your local desktop:
```
ngrok http 8000 --domain your-domain.ngrok-free.app
```
8. ngrok will display a URL where your localhost application is exposed to the internet (copy this URL for use with Meta).


#### Integrate WhatsApp

In the Meta App Dashboard, go to WhatsApp > Configuration, then click the Edit button.
1. In the Edit webhook's callback URL popup, enter the URL provided by the ngrok agent to expose your application to the internet in the Callback URL field, with /webhook at the end (i.e. https://myexample.ngrok-free.app/webhook).
2. Enter a verification token. This string is set up by you when you create your webhook endpoint. You can pick any string you like. Make sure to update this in your `VERIFY_TOKEN` environment variable.
3. After you add a webhook to WhatsApp, WhatsApp will submit a validation post request to your application through ngrok. Confirm your localhost app receives the validation get request and logs `WEBHOOK_VERIFIED` in the terminal.
4. Back to the Configuration page, click Manage.
5. On the Webhook fields popup, click Subscribe to the **messages** field. Tip: You can subscribe to multiple fields.
6. If your Flask app and ngrok are running, you can click on "Test" next to messages to test the subscription. You recieve a test message in upper case. If that is the case, your webhook is set up correctly.


#### Testing the Integration
Use the phone number associated to your WhatsApp product or use the test number you copied before.
1. Add this number to your WhatsApp app contacts and then send a message to this number.
2. Confirm your localhost app receives a message and logs both headers and body in the terminal.
3. Test if the bot replies back to you in upper case.
4. You have now succesfully integrated the bot! 🎉
5. Now it's time to acutally build cool things with this.


## Step 4: Understanding Webhook Security

Below is some information from the Meta Webhooks API docs about verification and security. It is already implemented in the code, but you can reference it to get a better understanding of what's going on in [security.py](https://github.com/daveebbelaar/python-whatsapp-bot/blob/main/app/decorators/security.py)

#### Verification Requests

[Source](https://developers.facebook.com/docs/graph-api/webhooks/getting-started#:~:text=process%20these%20requests.-,Verification%20Requests,-Anytime%20you%20configure)

Anytime you configure the Webhooks product in your App Dashboard, we'll send a GET request to your endpoint URL. Verification requests include the following query string parameters, appended to the end of your endpoint URL. They will look something like this:

```
GET https://www.your-clever-domain-name.com/webhook?
  hub.mode=subscribe&
  hub.challenge=1158201444&
  hub.verify_token=meatyhamhock
```

The verify_token, `meatyhamhock` in the case of this example, is a string that you can pick. It doesn't matter what it is as long as you store in the `VERIFY_TOKEN` environment variable.

#### Validating Verification Requests

[Source](https://developers.facebook.com/docs/graph-api/webhooks/getting-started#:~:text=Validating%20Verification%20Requests)

Whenever your endpoint receives a verification request, it must:
- Verify that the hub.verify_token value matches the string you set in the Verify Token field when you configure the Webhooks product in your App Dashboard (you haven't set up this token string yet).
- Respond with the hub.challenge value.

#### Validating Payloads

[Source](https://developers.facebook.com/docs/graph-api/webhooks/getting-started#:~:text=int-,Validating%20Payloads,-We%20sign%20all)

WhatsApp signs all Event Notification payloads with a SHA256 signature and include the signature in the request's X-Hub-Signature-256 header, preceded with sha256=. You don't have to validate the payload, but you should.

To validate the payload:
- Generate a SHA256 signature using the payload and your app's App Secret.
- Compare your signature to the signature in the X-Hub-Signature-256 header (everything after sha256=). If the signatures match, the payload is genuine.


## Step 5: Learn about the API and Build Your App

Review the developer documentation to learn how to build your app and start sending messages. [See documentation](https://developers.facebook.com/docs/whatsapp/cloud-api).

## Step 6: Integrate AI into the Application

Now that we have an end to end connection, we can make the bot a little more clever then just shouting at us in upper case. All you have to do is come up with your own `generate_response()` function in [whatsapp_utils.py](https://github.com/daveebbelaar/python-whatsapp-bot/blob/main/app/utils/whatsapp_utils.py).

If you want a cookie cutter example to integrate the OpenAI Assistans API with a retrieval tool, then follow these steps.
1. Watch this video: [OpenAI Assistants Tutorial](https://www.youtube.com/watch?v=0h1ry-SqINc)
2. Create your own assistant with OpenAI and update your `OPENAI_API_KEY` and `OPENAI_ASSISTANT_ID` in the environment variables.
3. Provide your assistant with data and instructions
4. Update [openai_service.py](https://github.com/daveebbelaar/python-whatsapp-bot/blob/main/app/services/openai_service.py) to your use case.
5. Import `generate_reponse` into [whatsapp_utils.py](https://github.com/daveebbelaar/python-whatsapp-bot/blob/main/app/utils/)
6. Update `process_whatsapp_message()` with the new `generate_reponse()` function.

## Step 7: Add a Phone Number

When you're ready to use your app for a production use case, you need to use your own phone number to send messages to your users.

To start sending messages to any WhatsApp number, add a phone number. To manage your account information and phone number, [see the Overview page.](https://business.facebook.com/wa/manage/home/) and the [WhatsApp docs](https://developers.facebook.com/docs/whatsapp/phone-numbers/).

If you want to use a number that is already being used in the WhatsApp customer or business app, you will have to fully migrate that number to the business platform. Once the number is migrated, you will lose access to the WhatsApp customer or business app. [See Migrate Existing WhatsApp Number to a Business Account for information](https://developers.facebook.com/docs/whatsapp/cloud-api/get-started/migrate-existing-whatsapp-number-to-a-business-account).

Once you have chosen your phone number, you have to add it to your WhatsApp Business Account. [See Add a Phone Number](https://developers.facebook.com/docs/whatsapp/cloud-api/get-started/add-a-phone-number).

When dealing with WhatsApp Business API and wanting to experiment without affecting your personal number, you have a few options:

1. Buy a New SIM Card
2. Virtual Phone Numbers
3. Dual SIM Phones
4. Use a Different Device
5. Temporary Number Services
6. Dedicated Devices for Development

**Recommendation**: If this is for a more prolonged or professional purpose, using a virtual phone number service or purchasing a new SIM card for a dedicated device is advisable. For quick tests, a temporary number might suffice, but always be cautious about security and privacy. Remember that once a number is associated with WhatsApp Business API, it cannot be used with regular WhatsApp on a device unless you deactivate it from the Business API and reverify it on the device.

## Datalumina

This document is provided to you by Datalumina. We help data analysts, engineers, and scientists launch and scale a successful freelance business — $100k+ /year, fun projects, happy clients. If you want to learn more about what we do, you can visit our [website](https://www.datalumina.com/) and subscribe to our [newsletter](https://www.datalumina.com/newsletter). Feel free to share this document with your data friends and colleagues.

## Tutorials
For video tutorials, visit the YouTube channel: [youtube.com/@daveebbelaar](youtube.com/@daveebbelaar)

# Tslil & Daniel Docs

## Running the app

### Prerequisites

1. Build the app docker container: `docker build -f Dockerfile . -t <commit SHA> --platform=linux/amd64`
2. Save the docker container: `docker save -o nadlan-bot.tar <docker image>`
3. Copy the docker container: `scp nadlan-bot.tar <ssh hostname>:~`
4. Load the docker container to the local registry: `docker load --input nadlan-bot.tar`

### Follow the steps on the VM

1. `docker run -d -p 8000:8000 --rm -v ~/NadlanBot/.env:/app/.env <docker image uploaded local registry>`
2. `docker run -d --net=host -it -e NGROK_AUTHTOKEN=<ngrok auth token> ngrok/ngrok:latest http --domain=peaceful-jaguar-social.ngrok-free.app 8000`

### To launch ngrok locally: 
1. Make sure the docker is down in the server
2. `ngrok http --domain=peaceful-jaguar-social.ngrok-free.app 8000`

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

### Deployment

For deploying to production, follow these steps:

1. Build the Docker image:
   ```bash
   docker build -t nadlanbot . --platform=linux/amd64
   ```

2. Before deploying, ensure port 8000 is available on the server:
   ```bash
   ssh <server> "lsof -i :8000"
   ```

3. Stop any existing containers:
   ```bash
   ssh <server> "docker stop nadlanbot && docker rm nadlanbot"
   ```

4. Deploy the new container:
   ```bash
   ssh <server> "docker run -d -p 8000:8000 -v /path/to/.env:/app/.env -v /path/to/data:/app/data --name nadlanbot <docker image>"
   ```

5. Verify deployment:
   ```bash
   curl -i http://<server-ip>:8000/health
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
3. Create a `.env` file in the root directory with the required environment variables (see `example.env` for reference)

### Starting the Docker Container

1. Build and start the Docker container:

```bash
# Build and start the container in detached mode
docker-compose up --build -d
```

2. Check if the container is running:

```bash
docker-compose ps
```

3. View the logs:

```bash
# View all logs
docker-compose logs

# View the last 50 lines
docker-compose logs --tail=50

# Follow the logs in real-time
docker-compose logs --follow
```

4. Stop the container:

```bash
docker-compose down
```

### Rebuilding After Code Changes

When you make changes to the code, you need to rebuild the Docker container:

```bash
docker-compose down && docker-compose up --build -d
```

## Exposing Your Local Server with Localtunnel

To test webhooks, you need to expose your local server to the internet. [Localtunnel](https://github.com/localtunnel/localtunnel) is a simple and lightweight tool for this purpose.

### Installing Localtunnel

```bash
# Install localtunnel globally using npm
npm install -g localtunnel
```

### Using Localtunnel

1. Start your Docker container as described above
2. In a separate terminal, run localtunnel to expose your local server:

```bash
# Basic usage (random subdomain)
lt --port 8080

# With a specific subdomain (if available)
lt --port 8080 --subdomain your-preferred-subdomain
```

3. Localtunnel will provide a URL (e.g., `https://wicked-swans-rule.loca.lt`) that you can use to access your local server from the internet

4. To check if the tunnel is working, visit the health endpoint:

```bash
curl https://your-tunnel-url.loca.lt/health
```

5. To stop localtunnel, press `Ctrl+C` in the terminal where it's running

### Important Notes About Localtunnel

- The URL changes each time you restart localtunnel unless you specify a subdomain
- If you're configuring webhooks in external services (like Meta Developer Portal), you'll need to update the URL whenever it changes
- For the WhatsApp webhook, use the URL with `/webhook` appended (e.g., `https://wicked-swans-rule.loca.lt/webhook`)
- Localtunnel sessions may expire after some time of inactivity

### Checking the Localtunnel URL

If you need to check the current localtunnel URL:

```bash
# Start localtunnel with the print-url option
lt --port 8080 --print-url

# Or check running processes
ps aux | grep lt
```

## Configuring WhatsApp Webhook for Local Development

1. Start your Docker container and localtunnel as described above
2. In the Meta Developer Portal, configure your webhook with:
   - **Callback URL**: Your localtunnel URL + `/webhook` (e.g., `https://wicked-swans-rule.loca.lt/webhook`)
   - **Verify Token**: The value you set in your `.env` file for `VERIFY_TOKEN` (e.g., `1234`)
   - **Subscribe to**: The `messages` field
3. Test the webhook verification by visiting:
   ```
   https://your-tunnel-url.loca.lt/webhook?hub.mode=subscribe&hub.verify_token=YOUR_VERIFY_TOKEN&hub.challenge=CHALLENGE_ACCEPTED
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

When developing locally, you need to ensure that WhatsApp messages can reach your local development server. There are two main approaches:

### Option 1: Update the webhook URL in Meta Developer Dashboard

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

4. Verify your webhook is working:
   ```
   python verify_webhook.py
   ```

### Option 2: Use a proxy on your production server

If you prefer to keep the webhook URL in Meta Developer Dashboard unchanged (`https://idrea.diligent-devs.com/webhook`), you can deploy a proxy on your production server:

1. Copy `webhook_proxy.py` to your production server
2. Set the environment variable `TARGET_WEBHOOK_URL` to your localtunnel URL:
   ```
   export TARGET_WEBHOOK_URL="https://your-localtunnel-url.loca.lt/webhook"
   ```
3. Run the proxy:
   ```
   python webhook_proxy.py
   ```

This will forward all webhook requests from your production server to your local development server.

### Troubleshooting Webhook Issues

If you're not receiving messages from WhatsApp:

1. Check that your webhook URL is correctly configured in the Meta Developer Dashboard
2. Verify that your localtunnel is running and accessible
3. Check the logs for any errors:
   ```
   docker-compose logs --follow
   ```
4. Test your webhook with the verification script:
   ```
   python verify_webhook.py
   ```

Remember that each time you restart localtunnel, you'll get a new URL, and you'll need to update the webhook URL in the Meta Developer Dashboard or the `TARGET_WEBHOOK_URL` environment variable accordingly.