import logging
from update_logging import setup_logging
from app import create_app

# Set up enhanced logging
app = create_app()
setup_logging(app)

if __name__ == "__main__":
    logging.info("Flask app starting on 0.0.0.0:8000")
    app.run(host="0.0.0.0", port=8000)
