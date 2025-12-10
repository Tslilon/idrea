import logging
import os
from update_logging import setup_logging
from app import create_app

# Set up enhanced logging
app = create_app()
setup_logging(app)

# Only run the development server when executed directly
# In production, Gunicorn imports the 'app' object directly
if __name__ == "__main__":
    # Check if we're in development mode
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    logging.info(f"Flask app starting on 0.0.0.0:8000 (debug={debug_mode})")
    
    if debug_mode:
        # Development server with auto-reload
        app.run(host="0.0.0.0", port=8000, debug=True)
    else:
        # Production should use Gunicorn, but fallback to Flask if run directly
        logging.warning("Running Flask development server in production mode. Use Gunicorn for better stability!")
        app.run(host="0.0.0.0", port=8000)
