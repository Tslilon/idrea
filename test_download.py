import requests
import logging
import os
from app.utils.whatsapp_utils import get_image_url_from_whatsapp

logging.basicConfig(level=logging.INFO)
logging.info('Testing image download')

url = get_image_url_from_whatsapp('948999130682341')
if url:
    logging.info(f'Got URL: {url[:50]}...')
    
    # Try different User-Agent values that have been reported to work
    user_agents = [
        'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
        'node',
        'curl/7.64.1',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    ]
    
    for ua in user_agents:
        logging.info(f'Attempting download with User-Agent: {ua}')
        
        headers = {
            'User-Agent': ua,
            'Authorization': f"Bearer {os.getenv('ACCESS_TOKEN')}"
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=30)
            logging.info(f'Response status: {response.status_code}')
            logging.info(f'Response content type: {response.headers.get("Content-Type")}')
            
            if response.status_code == 200:
                content_type = response.headers.get('Content-Type', '')
                
                # Check if we got an image back (not HTML)
                if 'text/html' not in content_type and len(response.content) > 1000:
                    logging.info(f'SUCCESS with User-Agent: {ua}')
                    logging.info(f'Content length: {len(response.content)} bytes')
                    
                    # Save the image to verify it's valid
                    with open(f'test_image_{ua.replace("/", "_")}.jpg', 'wb') as f:
                        f.write(response.content)
                    logging.info(f'Image saved to test_image_{ua.replace("/", "_")}.jpg')
                    break
                else:
                    logging.error(f'Got HTML response with User-Agent: {ua}')
            else:
                logging.error(f'Failed with response code {response.status_code} for User-Agent: {ua}')
        except Exception as e:
            logging.error(f'Error with User-Agent {ua}: {str(e)}')
else:
    logging.error('Failed to get URL') 