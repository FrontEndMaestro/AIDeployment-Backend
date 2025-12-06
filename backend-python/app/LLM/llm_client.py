import requests
from typing import List, Dict, Optional

from ..config.settings import settings

# LLM Configuration - loaded from settings
OLLAMA_URL = settings.OLLAMA_URL
MODEL_NAME = settings.LLM_MODEL_NAME
LLM_TEMPERATURE = settings.LLM_TEMPERATURE
LLM_TOP_P = settings.LLM_TOP_P
LLM_TIMEOUT = settings.LLM_TIMEOUT


def call_llama(messages: List[Dict[str, str]], custom_options: Optional[Dict] = None) -> str:
    """
    Call the LLM (via Ollama) with the given messages.
    
    Args:
        messages: List of message dicts with 'role' and 'content' keys.
                  Roles are typically 'system' and 'user'.
        custom_options: Optional dict to override default options.
    
    Returns:
        The LLM's response content as a string.
    """
    try:
        # Convert messages to a single prompt
        prompt = ""
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "system":
                prompt += f"System: {content}\n\n"
            elif role == "user":
                prompt += f"User: {content}\n\n"
        
        prompt += "Assistant:"
        
        # Build options with defaults
        options = {
            "temperature": LLM_TEMPERATURE,
            "top_p": LLM_TOP_P,
            "num_ctx": 8192,  # 8k context window
        }
        
        # Merge custom options if provided
        if custom_options:
            options.update(custom_options)
        
        resp = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL_NAME,
                "prompt": prompt,
                "stream": False,
                "options": options,
            },
            timeout=LLM_TIMEOUT,
        )
        resp.raise_for_status()
        
        # Parse response
        response_text = resp.text.strip()
        
        # Handle newline-delimited JSON (ndjson)
        if '\n' in response_text:
            lines = response_text.strip().split('\n')
            data = None
            for line in lines:
                if line.strip():
                    import json
                    data = json.loads(line)
        else:
            data = resp.json()
        
        return data.get("response", "")
    except requests.exceptions.ConnectionError as e:
        return f"ERROR: Cannot connect to Ollama at {OLLAMA_URL}. Details: {str(e)}"
    except requests.exceptions.Timeout:
        return f"ERROR: LLM request timed out after {LLM_TIMEOUT} seconds."
    except requests.exceptions.HTTPError as e:
        return f"ERROR: HTTP {e.response.status_code} - {e.response.reason}. URL: {OLLAMA_URL}"
    except Exception as e:
        import traceback
        return f"ERROR: LLM call failed - {str(e)}\nTraceback: {traceback.format_exc()[:500]}"
