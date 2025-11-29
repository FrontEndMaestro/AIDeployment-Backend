import requests
from typing import List, Dict

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "llama3.1"  # fixed to Llama 3.1 for Docker deployment logic

def call_llama(messages: List[Dict[str, str]]) -> str:
    """
    messages: [
      {"role": "system", "content": "..."},
      {"role": "user", "content": "..."},
      ...
    ]
    """
    resp = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL_NAME,
            "messages": messages,
            "stream": False,
            "options": {
            "temperature": 0.1,
            "top_p": 0.9,
        },
        },
        timeout=600,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["message"]["content"]
