import os
from groq import Groq
from typing import List, Dict

_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

MODEL = "openai/gpt-oss-20b"


def generate_chat(messages: List[Dict[str, str]], temperature: float = 0.2) -> str:
    """
    Multi-turn chat completion.

    messages format:
    [
      {"role": "system", "content": "..."},
      {"role": "user", "content": "..."},
      {"role": "assistant", "content": "..."},
      ...
    ]
    """

    response = _client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=768,
        response_format={"type": "json_object"},
    )

    return response.choices[0].message.content.strip()