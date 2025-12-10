"""Read and print the LLM response file"""
with open("test_monorepo_llm_response.txt", "r", encoding="utf-8") as f:
    content = f.read()

# Find and print the docker files sections
print("=" * 60)
print("EXTRACTED DOCKER FILES FROM LLM RESPONSE")
print("=" * 60)

# Print lines 10-100 (after the header)
lines = content.split('\n')
for i, line in enumerate(lines[10:100], start=10):
    print(f"{i}: {line}")
