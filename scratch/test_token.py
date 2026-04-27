import asyncio
from datetime import timedelta
from app.core import create_access_token, decode_token
from app.core.config import settings

def test_token():
    print(f"JWT Secret: {settings.jwt_secret}")
    print(f"JWT Algorithm: {settings.jwt_algorithm}")
    
    data = {"sub": "1", "role": "guard"}
    token = create_access_token(data=data, expires_delta=timedelta(minutes=30))
    print(f"Generated Token: {token}")
    
    payload = decode_token(token)
    print(f"Decoded Payload: {payload}")
    
    if payload.get("type") != "access":
        print("FAIL: Type is not access")
    if payload.get("role") != "guard":
        print("FAIL: Role is not guard")
    else:
        print("SUCCESS: Token is valid")

if __name__ == "__main__":
    test_token()
