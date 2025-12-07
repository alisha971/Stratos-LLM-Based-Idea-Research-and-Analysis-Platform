from jose import jwt
from datetime import datetime, timedelta
from app.config import settings

def create_jwt(payload: dict):
    payload["exp"] = datetime.utcnow() + timedelta(days=7)
    return jwt.encode(payload, settings.JWT_SECRET, settings.JWT_ALGO)

def verify_jwt(token: str):
    try:
        decoded = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGO])
        return decoded
    except:
        return None
