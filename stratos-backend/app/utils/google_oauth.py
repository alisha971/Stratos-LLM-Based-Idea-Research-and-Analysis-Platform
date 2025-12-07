from google.oauth2 import id_token
from google.auth.transport import requests
from app.config import settings

def verify_google_token(google_token: str):
    try:
        user_info = id_token.verify_oauth2_token(
            google_token,
            requests.Request(),
            settings.GOOGLE_CLIENT_ID,
        )
        return user_info
    except:
        return None
