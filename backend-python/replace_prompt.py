import re

# Read the new prompt
with open('app/LLM/new_docker_prompt.py', 'r', encoding='utf-8') as f:
    new_content = f.read()

# Extract just the prompt variable assignment
new_prompt_match = re.search(r'DOCKER_DEPLOY_SYSTEM_PROMPT = """.*?"""', new_content, re.DOTALL)
if not new_prompt_match:
    print('Error: Could not find prompt in new file')
    exit(1)
new_prompt = new_prompt_match.group(0)
print(f'New prompt length: {len(new_prompt)} chars')

# Read the original file
with open('app/LLM/docker_deploy_agent.py', 'r', encoding='utf-8') as f:
    original = f.read()

# Replace the old prompt with the new one
old_pattern = r'DOCKER_DEPLOY_SYSTEM_PROMPT = """.*?"""'
old_match = re.search(old_pattern, original, re.DOTALL)
if not old_match:
    print('Error: Could not find old prompt')
    exit(1)
print(f'Old prompt length: {len(old_match.group(0))} chars')

updated = re.sub(old_pattern, new_prompt, original, flags=re.DOTALL)

# Write back
with open('app/LLM/docker_deploy_agent.py', 'w', encoding='utf-8') as f:
    f.write(updated)

print('Successfully replaced prompt!')
