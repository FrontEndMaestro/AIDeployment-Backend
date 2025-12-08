"""
Quick LLM test - single scenario only
"""
import requests
import json

# Settings
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen2.5-coder:7b"

# Simple test metadata
test_metadata = {
    "framework": "MERN Stack",
    "runtime": "node:20-alpine",
    "backend_port": 4000,
    "frontend_port": 3000,
    "database": "MongoDB",
    "database_is_cloud": True,
    "build_output": "build",
    "start_command": "node server.js",
    "entry_point": "server.js"
}

# Create a simple prompt
prompt = """You are a Docker Configuration Engine.

Generate a Dockerfile for a Node.js Express backend with these specs:
- Runtime: node:20-alpine
- Port: 4000 (MUST use this exact port, not 3000)
- Entry point: server.js
- Start command: node server.js

Requirements:
1. Include verification comment: # VERIFICATION: runtime=node:20-alpine, port=4000
2. Use EXPOSE 4000 (NOT 3000)
3. CMD ["node", "server.js"]

Respond with ONLY the Dockerfile content, no explanation."""

print("Calling Ollama API...")
print(f"Model: {MODEL_NAME}")
print(f"Expected port: 4000")
print("-" * 50)

try:
    resp = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL_NAME,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1, "num_ctx": 4096}
        },
        timeout=120
    )
    resp.raise_for_status()
    data = resp.json()
    output = data.get("response", "")
    
    print("\nLLM Output:")
    print("=" * 50)
    print(output)
    print("=" * 50)
    
    # Check for expected patterns
    checks = [
        ("Port 4000 in EXPOSE", "expose 4000" in output.lower()),
        ("Port 4000 in verification", "4000" in output),
        ("Correct entry point", "server.js" in output),
        ("No port 3000", "3000" not in output),
        ("Has verification comment", "verification" in output.lower()),
    ]
    
    print("\nValidation:")
    passed = 0
    for name, result in checks:
        status = "PASS" if result else "FAIL"
        print(f"  [{status}] {name}")
        if result:
            passed += 1
    
    print(f"\nResult: {passed}/{len(checks)} checks passed")
    
except requests.exceptions.ConnectionError:
    print("ERROR: Cannot connect to Ollama")
except Exception as e:
    print(f"ERROR: {e}")
