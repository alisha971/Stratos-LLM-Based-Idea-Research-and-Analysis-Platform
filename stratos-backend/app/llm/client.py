from app.config import settings

if settings.LLM_PROVIDER == "groq":
    from .client_groq import generate_text   
else:
    raise ValueError("Unsupported LLM_PROVIDER")
