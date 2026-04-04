from app.core.config import settings
from app.core.firebase import init_firebase, firebase_app
import json

def verify():
    print(f"ENV: {settings.env}")
    print(f"Has JSON string: {bool(settings.firebase_credentials_json)}")
    
    app = init_firebase()
    if app:
        print("SUCCESS: Firebase Admin SDK initialized successfully!")
        print(f"Project ID: {app.project_id}")
    else:
        print("FAILED: Firebase Admin SDK failed to initialize.")

if __name__ == "__main__":
    verify()
