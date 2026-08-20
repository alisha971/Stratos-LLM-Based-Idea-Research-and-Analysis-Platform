import os
from dotenv import load_dotenv

load_dotenv()


def _as_bool(value: str | None) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "on")


class Settings:
    # Runtime environment: development | production
    ENV = os.getenv("ENV", "development")

    # --- Database ---
    DATABASE_URL = os.getenv("DATABASE_URL")

    # --- Redis (broker for Celery, separate DB for pub/sub) ---
    REDIS_BROKER_URL = os.getenv("REDIS_BROKER_URL", "redis://localhost:6379/0")
    REDIS_PUBSUB_URL = os.getenv("REDIS_PUBSUB_URL", "redis://localhost:6379/1")

    # --- Astra (vector evidence store) ---
    ASTRA_DB_ENDPOINT = os.getenv("ASTRA_DB_API_ENDPOINT")
    ASTRA_DB_APPLICATION_TOKEN = os.getenv("ASTRA_DB_APPLICATION_TOKEN")
    ASTRA_DB_KEYSPACE = os.getenv("ASTRA_DB_KEYSPACE")

    # --- Auth ---
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
    JWT_SECRET = os.getenv("JWT_SECRET", "supersecret")
    JWT_ALGO = "HS256"
    # Dev-only escape hatch: literal token "dev" authenticates as "dev-user".
    DEV_AUTH_BYPASS = _as_bool(os.getenv("DEV_AUTH_BYPASS", "false"))

    # --- LLM ---
    LLM_PROVIDER = os.getenv("LLM_PROVIDER")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")

    # --- Research ---
    SERP_API_KEY = os.getenv("SERP_API_KEY")

    # --- Exports / storage ---
    # local -> serve PDFs from disk (fast-ship). r2 -> presigned object storage (premium).
    EXPORT_STORAGE = os.getenv("EXPORT_STORAGE", "local")
    EXPORT_DIR = os.getenv("EXPORT_DIR", "exports")

    # --- CORS ---
    FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")

    # --- Rate limiting / cost guardrails ---
    START_SESSION_RATE = os.getenv("START_SESSION_RATE", "5/hour")
    CLARIFICATION_CHAT_RATE = os.getenv("CLARIFICATION_CHAT_RATE", "60/hour")
    GLOBAL_DAILY_SESSION_CAP = int(os.getenv("GLOBAL_DAILY_SESSION_CAP", "100"))

    # --- Input caps (security §3) ---
    MAX_TEXT_LENGTH = int(os.getenv("MAX_TEXT_LENGTH", "2000"))

    def validate(self) -> None:
        """Fail fast on dangerous production misconfiguration (security §1)."""
        if self.ENV == "production":
            if not self.GOOGLE_CLIENT_ID:
                # Without this, google-auth would skip the audience check
                # entirely and accept a valid Google ID token issued to ANY
                # app -> account takeover via the email-fallback match in
                # api/auth.py. (google_oauth.py also refuses to verify with
                # no client id configured, in every environment, as a second
                # layer -- this boot check just fails loudly in prod instead
                # of silently disabling Google login.)
                raise RuntimeError(
                    "GOOGLE_CLIENT_ID is not set in production. Real Google "
                    "sign-in cannot be verified safely without it."
                )
            if self.JWT_SECRET == "supersecret":
                raise RuntimeError(
                    "JWT_SECRET is still the default in production. "
                    "Set a strong (>=64 char) JWT_SECRET before booting."
                )
            if self.DEV_AUTH_BYPASS:
                raise RuntimeError(
                    "DEV_AUTH_BYPASS must be false in production. "
                    "The 'dev' token would bypass all authentication."
                )


settings = Settings()
settings.validate()
