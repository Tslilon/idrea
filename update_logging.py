#!/usr/bin/env python3
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

def setup_logging(app=None, log_to_stdout=True):
    """
    Configure logging for the application.
    
    Args:
        app: Flask app instance (optional)
        log_to_stdout: Whether to also log to stdout
    """
    # Create logs directory if it doesn't exist
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    # Determine log file path - use /app/app.log if running in Docker (which will be mounted)
    if os.path.exists('/app'):
        log_file = '/app/app.log'
    else:
        log_file = os.path.join(log_dir, 'app.log')
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Clear existing handlers to avoid duplicate logs
    if root_logger.handlers:
        for handler in root_logger.handlers:
            root_logger.removeHandler(handler)
    
    # Create formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Configure file handler with rotation (max 10MB, keep 5 backups)
    file_handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5)
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    
    # Add stdout handler if requested
    if log_to_stdout:
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setFormatter(formatter)
        stdout_handler.setLevel(logging.INFO)
        root_logger.addHandler(stdout_handler)
    
    # Configure Flask app logging if provided
    if app:
        app.logger.setLevel(logging.INFO)
        # Flask uses the root logger's handlers by default
    
    logging.info("Logging configured. Log file: %s", log_file)
    return root_logger

if __name__ == "__main__":
    # This can be run directly to test logging configuration
    logger = setup_logging()
    logger.info("Test log entry")
    logger.warning("Test warning entry")
    logger.error("Test error entry")
    print("Logging test complete. Check the log file.") 