import firebase_admin
from firebase_admin import credentials, messaging
from app.core.config import settings
import os
import logging
import json

logger = logging.getLogger(__name__)

# Initialize Firebase Admin SDK
firebase_app = None

def init_firebase():
    global firebase_app
    if firebase_app is not None:
        return firebase_app

    try:
        # Check if JSON string is provided in env
        if settings.firebase_credentials_json:
            try:
                cred_dict = json.loads(settings.firebase_credentials_json)
                cred = credentials.Certificate(cred_dict)
                firebase_app = firebase_admin.initialize_app(cred)
                logger.info("Firebase Admin SDK initialized successfully from JSON string.")
                return firebase_app
            except Exception as e:
                logger.error(f"Error parsing firebase_credentials_json: {e}")

        # Fallback to file path
        if not os.path.exists(settings.firebase_credentials_path):
            logger.error(f"Firebase credentials file not found at: {settings.firebase_credentials_path}")
            return None

        cred = credentials.Certificate(settings.firebase_credentials_path)
        firebase_app = firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin SDK initialized successfully from file.")
        return firebase_app
    except Exception as e:
        logger.error(f"Error initializing Firebase Admin SDK: {e}")
        return None

# Attempt initialization on import
init_firebase()
