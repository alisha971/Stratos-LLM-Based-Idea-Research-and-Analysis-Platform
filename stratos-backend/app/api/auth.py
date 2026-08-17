from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import models
from app.db.session import get_db
from app.utils.google_oauth import verify_google_token
from app.utils.jwt_utils import create_jwt

router = APIRouter()


class GoogleLoginRequest(BaseModel):
    id_token: str


@router.post("/google")
def login_google(body: GoogleLoginRequest, db: Session = Depends(get_db)):
    user_info = verify_google_token(body.id_token)
    if not user_info:
        raise HTTPException(status_code=401, detail="Invalid Google token")

    google_sub = user_info.get("sub")
    email = user_info.get("email")
    if not email:
        raise HTTPException(status_code=401, detail="Google token missing email")

    # Upsert user: match on google_sub first, then email.
    user = None
    if google_sub:
        user = db.query(models.User).filter_by(google_sub=google_sub).first()
    if not user:
        user = db.query(models.User).filter_by(email=email).first()

    if not user:
        user = models.User(
            email=email,
            google_sub=google_sub,
            name=user_info.get("name"),
            picture_url=user_info.get("picture"),
        )
        db.add(user)
    else:
        user.google_sub = google_sub or user.google_sub
        user.name = user_info.get("name") or user.name
        user.picture_url = user_info.get("picture") or user.picture_url

    db.commit()
    db.refresh(user)

    token = create_jwt({"sub": user.id, "email": user.email})

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "plan": "free",
        },
    }
