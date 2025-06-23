from flask import Flask
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from app.config import load_configurations, configure_logging
from .views import webhook_blueprint


def get_real_ip():
    """Get the real IP address from X-Forwarded-For header when behind a proxy"""
    from flask import request
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    elif request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP')
    else:
        return get_remote_address()


def create_app():
    app = Flask(__name__)

    # Load configurations and logging settings
    load_configurations(app)
    configure_logging()

    # Initialize rate limiter with proxy-aware IP detection
    limiter = Limiter(
        app=app,
        key_func=get_real_ip,
        default_limits=["200 per day", "50 per hour"],
        storage_uri="memory://",
        headers_enabled=True  # Enable rate limit headers in response
    )

    # Import and register blueprints, if any
    app.register_blueprint(webhook_blueprint)

    return app
