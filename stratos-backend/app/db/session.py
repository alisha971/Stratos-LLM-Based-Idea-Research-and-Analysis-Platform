from app.db.database import SessionLocal

def get_db():
    db = SessionLocal()
    try:
        yield db # what does this do?
    finally:
        db.close()
