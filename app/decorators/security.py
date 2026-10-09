from functools import wraps
from flask import current_app, jsonify, request
import logging
import hashlib
import hmac
import os


def validate_signature(payload, signature):
    """
    Validate the incoming payload's signature against our expected signature
    """
    # Use the App Secret to hash the payload
    expected_signature = hmac.new(
        bytes(current_app.config["APP_SECRET"], "latin-1"),
        msg=payload.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()

    # Check if the signature matches
    return hmac.compare_digest(expected_signature, signature)


def signature_required(f):
    """
    Decorator to ensure that the incoming requests to our webhook are valid and signed with the correct signature.

    WEBHOOK_SIGNATURE_MODE controls what happens on a bad signature:
      "log" (default) - log a warning and process the request anyway
      "enforce"       - reject with 403
      "off"           - don't check
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        mode = os.getenv("WEBHOOK_SIGNATURE_MODE", "log").lower()
        if mode == "off":
            return f(*args, **kwargs)
        signature = request.headers.get("X-Hub-Signature-256", "")[
            7:
        ]  # Removing 'sha256='
        try:
            valid = validate_signature(request.data.decode("utf-8"), signature)
        except Exception as e:
            logging.error(f"Signature check error: {str(e)}")
            valid = False
        if not valid:
            if mode == "enforce":
                logging.warning("Signature verification failed, request rejected")
                return jsonify({"status": "error", "message": "Invalid signature"}), 403
            logging.warning("Signature verification failed (log-only mode, request processed)")
        return f(*args, **kwargs)

    return decorated_function
