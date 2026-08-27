import os
from groq import Groq
from typing import List, Dict

_clients = {
    "alisha": Groq(api_key=os.getenv("GROQ_API_KEY_ALISHA")),
    "encril": Groq(api_key=os.getenv("GROQ_API_KEY_ENCRIL")),
}


def generate_chat(
    messages: List[Dict[str, str]],
    key_label: str,
    model: str,
    temperature: float = 0.2,
) -> str:
    """
    Multi-turn chat completion against a specific named Groq credential.

    messages format:
    [
      {"role": "system", "content": "..."},
      {"role": "user", "content": "..."},
      {"role": "assistant", "content": "..."},
      ...
    ]
    """

    response = _clients[key_label].chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=768,
        response_format={"type": "json_object"},
    )

    return response.choices[0].message.content.strip()
