"""
Test LLM Docker generation with multiple MERN scenarios.
Uses the correct model from Ollama.
"""
import requests
import json
import time

# Settings
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen2.5-coder:7b"

# Import the system prompt
SYSTEM_PROMPT = """You are a Docker Configuration Engine. Generate Docker files based on metadata.

CRITICAL RULES:
1. Use EXACT values from metadata (runtime, ports, entry_point)
2. Include verification comment: # VERIFICATION: runtime=..., port=...
3. Never use default ports (3000, 8000) unless metadata specifies them
4. For frontends: CRA uses /app/build, Vite uses /app/dist
5. Use 'serve -s' for SPAs, not nginx
6. For cloud databases: DO NOT add database container
7. For local databases: ADD database container to compose

Respond with only the Dockerfile or docker-compose.yml content."""

TEST_SCENARIOS = [
    {
        "name": "CRA Frontend + Express Backend (Cloud MongoDB)",
        "prompt": """Generate Docker files for a MERN project:

METADATA:
- Backend: port 4000, entry point server.js, node:20-alpine
- Frontend: CRA (react-scripts), build_output: build
- Database: MongoDB Atlas (CLOUD - don't add container)

Service Definitions:
- backend: port 4000, start_command: node server.js
- frontend: port 3000, build_output: build (CRA uses /app/build)

Generate:
1. backend/Dockerfile
2. frontend/Dockerfile  
3. docker-compose.yml""",
        "checks": [
            ("backend_port_4000", "4000", True, "Backend should expose port 4000"),
            ("/app/build", "/app/build", True, "Frontend should use /app/build for CRA"),
            ("no_mongo_service", "mongo:", False, "Should NOT have mongo service (cloud DB)"),
            ("serve", "serve", True, "Frontend should use serve"),
        ]
    },
    {
        "name": "Vite Frontend + Express Backend (Local MongoDB)",
        "prompt": """Generate Docker files for a MERN project:

METADATA:
- Backend: port 8888, entry point src/server.js, node:20-alpine
- Frontend: Vite, build_output: dist
- Database: MongoDB LOCAL - ADD container

Service Definitions:
- backend: port 8888, start_command: node src/server.js
- frontend: port 5173, build_output: dist (Vite uses /app/dist)
- mongodb: LOCAL database, image: mongo:latest

Generate:
1. backend/Dockerfile (port 8888)
2. frontend/Dockerfile (dist output)
3. docker-compose.yml (with mongo service)""",
        "checks": [
            ("backend_port_8888", "8888", True, "Backend should expose port 8888"),
            ("/app/dist", "/app/dist", True, "Frontend should use /app/dist for Vite"),
            ("has_mongo", "mongo:", True, "Should have mongo service (local DB)"),
            ("src/server.js", "src/server.js", True, "Should use correct entry point"),
        ]
    },
    {
        "name": "Next.js Static Export",
        "prompt": """Generate Dockerfile for Next.js static export:

METADATA:
- Framework: Next.js with static export
- build_output: out (NOT dist, NOT .next)
- node:20-alpine

Generate a Dockerfile that:
1. Builds with: npm run build
2. Copies from /app/out (Next.js export outputs to 'out' folder)
3. Serves with serve package""",
        "checks": [
            ("/app/out", "/app/out", True, "Should use /app/out for Next.js export"),
            ("serve", "serve", True, "Should use serve"),
            ("not_dist", "/app/dist", False, "Should NOT use /app/dist for Next.js export"),
        ]
    }
]

def call_llm(prompt):
    """Call Ollama API."""
    full_prompt = f"System: {SYSTEM_PROMPT}\n\nUser: {prompt}\n\nAssistant:"
    
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL_NAME,
                "prompt": full_prompt,
                "stream": False,
                "options": {"temperature": 0.1, "num_ctx": 8192}
            },
            timeout=180
        )
        resp.raise_for_status()
        return resp.json().get("response", "")
    except Exception as e:
        return f"ERROR: {e}"

def run_checks(output, checks):
    """Run checks on LLM output."""
    results = []
    for check_id, pattern, should_exist, desc in checks:
        found = pattern.lower() in output.lower()
        passed = found if should_exist else not found
        results.append({
            "id": check_id,
            "passed": passed,
            "description": desc,
            "found": found,
            "expected": should_exist
        })
    return results

def run_all_tests():
    """Run all test scenarios."""
    print("=" * 70)
    print("LLM DOCKER GENERATION TEST")
    print(f"Model: {MODEL_NAME}")
    print("=" * 70)
    
    all_results = []
    total_passed = 0
    total_checks = 0
    
    for i, scenario in enumerate(TEST_SCENARIOS, 1):
        print(f"\n[{i}/{len(TEST_SCENARIOS)}] {scenario['name']}")
        print("-" * 50)
        
        start = time.time()
        output = call_llm(scenario["prompt"])
        elapsed = time.time() - start
        
        if output.startswith("ERROR:"):
            print(f"  LLM Error: {output}")
            continue
        
        print(f"  Response time: {elapsed:.1f}s")
        print(f"  Output length: {len(output)} chars")
        
        # Run checks
        check_results = run_checks(output, scenario["checks"])
        
        print(f"\n  Checks:")
        for r in check_results:
            status = "[PASS]" if r["passed"] else "[FAIL]"
            print(f"    {status} {r['description']}")
            total_checks += 1
            if r["passed"]:
                total_passed += 1
        
        all_results.append({
            "scenario": scenario["name"],
            "output_preview": output[:300],
            "checks": check_results
        })
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total checks: {total_checks}")
    print(f"Passed: {total_passed}")
    print(f"Failed: {total_checks - total_passed}")
    if total_checks > 0:
        rate = total_passed / total_checks * 100
        print(f"Success rate: {rate:.1f}%")
        
        if rate >= 90:
            print("\n>>> LLM is following metadata correctly <<<")
        elif rate >= 70:
            print("\n>>> Some prompt improvements needed <<<")
        else:
            print("\n>>> CRITICAL: Major prompt improvements needed <<<")
    
    # Save to file
    with open("llm_test_results.json", "w") as f:
        json.dump(all_results, f, indent=2)
    
    print("\nDetailed results saved to llm_test_results.json")
    return all_results

if __name__ == "__main__":
    run_all_tests()
