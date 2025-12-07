import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    DATABASE_URL = os.getenv("DATABASE_URL")
    REDIS_BROKER_URL = "redis://localhost:6379/0"
    REDIS_PUBSUB_URL = "redis://localhost:6379/1"

    ASTRA_DB_ENDPOINT = os.getenv("ASTRA_DB_API_ENDPOINT")
    ASTRA_DB_APPLICATION_TOKEN = os.getenv("ASTRA_DB_APPLICATION_TOKEN")

    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
    JWT_SECRET = os.getenv("JWT_SECRET", "supersecret")
    JWT_ALGO = "HS256"

settings = Settings()
