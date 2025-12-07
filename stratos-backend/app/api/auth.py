from fastapi import APIRouter, HTTPException
from app.utils.google_oauth import verify_google_token
from app.utils.jwt_utils import create_jwt

router = APIRouter()

@router.post("/google")
def login_google(id_token: str):
    user_info = verify_google_token(id_token)
    if not user_info:
        raise HTTPException(status_code=401, detail="Invalid Google token")

    token = create_jwt({
        "email": user_info["email"],
        "name": user_info.get("name"),
        "picture": user_info.get("picture"),
    })

    return {
        "token": token,
        "email": user_info["email"],
        "name": user_info.get("name"),
        "picture": user_info.get("picture"),
    }
