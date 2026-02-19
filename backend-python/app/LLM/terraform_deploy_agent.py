"""
Terraform Deploy Agent - LLM-powered infrastructure generation for AWS EC2 Free Tier.

This agent generates Terraform configurations for deploying MERN projects to AWS
on a single EC2 t2.micro instance using docker-compose (no ALB/ELB, no ECS).
"""

import os
from typing import Dict, List, Optional

from .llm_client import call_llama, call_llama_stream

# System prompt for Terraform generation - EC2 Free Tier Version
TERRAFORM_DEPLOY_SYSTEM_PROMPT = """You generate Terraform for deploying Docker containers to AWS EC2 (Free Tier).

## TASK
Generate a complete `main.tf` that deploys services to a single EC2 t3.micro instance.

## CRITICAL RULES (MUST FOLLOW)
1. ALWAYS include: terraform { required_providers { aws = { source = "hashicorp/aws", version = "~> 5.0" } } }
2. ALWAYS include: provider "aws" { region = var.aws_region }
3. ALWAYS use data "aws_ami" to get Amazon Linux 2 AMI - NEVER hardcode AMI IDs
4. Declare ONLY 3 variables with hardcoded defaults: project_name, aws_region, docker_repo_prefix
5. Use vpc_security_group_ids = [aws_security_group.X.id] NOT security_groups
6. Add map_public_ip_on_launch = true to subnet
7. Do NOT include key_name
8. For availability_zone use: "${var.aws_region}a"
9. In user_data heredoc, use 'COMPOSE' for inner delimiter
10. HARDCODE all values in docker-compose.yml - NO variable interpolation

## REQUIRED STRUCTURE (in this order)
1. terraform { required_providers { aws } }
2. provider "aws" { region = var.aws_region }
3. variable "project_name" { default = "..." }
4. variable "aws_region" { default = "..." }
5. variable "docker_repo_prefix" { default = "..." }
6. data "aws_ami" "amazon_linux_2" { most_recent = true, owners = ["amazon"], filter for amzn2-ami-hvm-*-x86_64-gp2 }
7. aws_vpc, aws_internet_gateway, aws_subnet (map_public_ip_on_launch = true), aws_route_table, aws_route_table_association
8. aws_security_group (ingress: 22, 80, 443, 3000-5000; egress: all)
9. aws_instance with ami = data.aws_ami.amazon_linux_2.id and vpc_security_group_ids
10. outputs

## EXACT user_data FORMAT
```
user_data = <<-EOF
#!/bin/bash
yum update -y
amazon-linux-extras install docker -y
service docker start
usermod -a -G docker ec2-user
chkconfig docker on
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose
mkdir -p /home/ec2-user/app
cat > /home/ec2-user/app/docker-compose.yml << 'COMPOSE'
services:
  backend:
    image: username/project-backend:latest
    ports:
      - "3000:3000"
    environment:
      - PORT=3000
      - MONGO_URI=mongodb://...
    restart: always
COMPOSE
cd /home/ec2-user/app
docker-compose pull
docker-compose up -d
EOF
```

## INPUTS YOU WILL RECEIVE
- PROJECT_NAME, AWS_REGION, DOCKER_REPO_PREFIX (use as variable defaults)
- SERVICES: name, port, type (hardcode into docker-compose.yml)
- ENVIRONMENT_VARIABLES: key=value pairs (hardcode into docker-compose.yml)

## REQUIRED OUTPUTS
- instance_public_ip, instance_id, frontend_url, backend_url, vpc_id

Return ONLY valid Terraform HCL. No markdown. No explanations."""


def build_terraform_message(
    project_name: str,
    services: List[Dict],
    docker_repo_prefix: str,
    aws_region: str = "us-east-1",
    db_engine: Optional[str] = None,
    db_url: Optional[str] = None,
    desired_count: int = 1,
    service_env_vars: Optional[Dict[str, Dict[str, str]]] = None,
    existing_compose: Optional[str] = None,
    existing_env_files: Optional[Dict[str, str]] = None,
) -> str:
    """
    Build the message for LLM with project metadata for Terraform generation.
    
    Args:
        project_name: Name of the project (used for AWS resource naming)
        services: List of dicts with {name, port, path} for each service
        docker_repo_prefix: Docker Hub/ECR prefix (e.g., "username")
        aws_region: AWS region for deployment
        db_engine: Database type (mongo, postgres, mysql, none)
        db_url: Database connection URL
        desired_count: Number of Fargate tasks per service
        service_env_vars: Dict mapping service name to its env vars
            e.g., {"backend": {"PORT": "3000", "MONGO_URI": "..."}, "frontend": {"VITE_API_URL": "..."}}
    """
    lines = [
        "=== TERRAFORM GENERATION REQUEST ===",
        "",
        f"PROJECT_NAME: {project_name}",
        f"AWS_REGION: {aws_region}",
        f"DOCKER_REPO_PREFIX: {docker_repo_prefix}",
        f"DESIRED_COUNT: {desired_count}",
        "",
        f"DB_ENGINE: {db_engine or 'none'}",
        f"DB_URL: {db_url or 'NOT_SET'}",
        "",
        "=== SERVICES ===",
    ]
    
    for svc in services:
        svc_name = svc.get("name", "app")
        svc_port = svc.get("port", 3000)
        svc_type = svc.get("type", "backend")
        
        lines.append(f"\nService: {svc_name}")
        lines.append(f"  Type: {svc_type}")
        lines.append(f"  Port: {svc_port}")
        lines.append(f"  Image: {docker_repo_prefix}/{project_name}-{svc_name}:latest")
        
        # Add service-specific environment variables
        if service_env_vars and svc_name in service_env_vars:
            env_dict = service_env_vars[svc_name]
            if env_dict:
                lines.append(f"  Environment Variables:")
                for key, value in env_dict.items():
                    # Pass through actual values so docker-compose can be fully populated
                    lines.append(f"    - {key}={value}")
    
    # Add existing docker-compose.yml if provided
    if existing_compose:
        lines.extend([
            "",
            "=== EXISTING DOCKER-COMPOSE.YML ===",
            "Use this docker-compose.yml content EXACTLY in the user_data:",
            existing_compose,
        ])
    
    # Add existing .env files if provided
    if existing_env_files:
        lines.extend([
            "",
            "=== EXISTING .ENV FILES ===",
            "Embed these .env file contents in user_data BEFORE docker-compose.yml:",
        ])
        for svc_name, env_content in existing_env_files.items():
            lines.append(f"\n--- {svc_name}/.env ---")
            lines.append(env_content)
    
    lines.extend([
        "",
        "=== INSTRUCTIONS ===",
        "Generate a complete main.tf file with:",
        "1. VPC, Subnets, Security Groups",
        "2. Single EC2 t3.micro running docker-compose (no ALB/ELB, no ECS)",
    ])
    
    if existing_compose:
        lines.extend([
            "3. In user_data, first create .env files (if provided), then create docker-compose.yml using the EXACT content provided above",
            "4. Do NOT generate a new docker-compose.yml - use the provided one exactly",
        ])
    else:
        lines.extend([
            "3. Inject ALL provided environment variables into docker-compose exactly as given (no placeholders or guesses)",
            "4. Frontend must map to port 80; backend maps to its provided port",
        ])
    
    lines.extend([
        "5. Outputs: instance_public_ip, instance_id, frontend_url, backend_url, vpc_id",
        "6. Use ONLY the values provided above; do not assume or invent any missing fields.",
        "",
        "Return ONLY the Terraform HCL code, no explanations.",
    ])
    
    return "\n".join(lines)


def run_terraform_deploy_chat(
    project_name: str,
    services: List[Dict],
    docker_repo_prefix: str,
    aws_region: str = "us-east-1",
    db_engine: Optional[str] = None,
    db_url: Optional[str] = None,
    desired_count: int = 1,
    service_env_vars: Optional[Dict[str, Dict[str, str]]] = None,
    existing_compose: Optional[str] = None,
    existing_env_files: Optional[Dict[str, str]] = None,
) -> str:
    """
    Generate Terraform configuration via LLM.
    
    Returns:
        The generated Terraform HCL code as a string.
    """
    message = build_terraform_message(
        project_name=project_name,
        services=services,
        docker_repo_prefix=docker_repo_prefix,
        aws_region=aws_region,
        db_engine=db_engine,
        db_url=db_url,
        desired_count=desired_count,
        service_env_vars=service_env_vars,
        existing_compose=existing_compose,
        existing_env_files=existing_env_files,
    )
    
    # Debug output
    print(f"\n=== DEBUG: TERRAFORM LLM REQUEST ===")
    print(f"Project: {project_name}")
    print(f"Services: {[s.get('name') for s in services]}")
    print(f"Region: {aws_region}")
    print(f"Message (first 500 chars):\n{message[:500]}...")
    print("=" * 40)
    
    response = call_llama([
        {"role": "system", "content": TERRAFORM_DEPLOY_SYSTEM_PROMPT},
        {"role": "user", "content": message},
    ])
    
    # Extract HCL from response (remove markdown fences if present)
    return _extract_hcl_from_response(response)


def run_terraform_deploy_chat_stream(
    project_name: str,
    services: List[Dict],
    docker_repo_prefix: str,
    aws_region: str = "us-east-1",
    db_engine: Optional[str] = None,
    db_url: Optional[str] = None,
    desired_count: int = 1,
    service_env_vars: Optional[Dict[str, Dict[str, str]]] = None,
):
    """
    Streaming version of terraform generation.
    Yields tokens as they're generated by the LLM.
    """
    message = build_terraform_message(
        project_name=project_name,
        services=services,
        docker_repo_prefix=docker_repo_prefix,
        aws_region=aws_region,
        db_engine=db_engine,
        db_url=db_url,
        desired_count=desired_count,
        service_env_vars=service_env_vars,
    )
    
    print(f"\n=== DEBUG: STREAMING TERRAFORM REQUEST ===")
    print(f"Project: {project_name}")
    print(f"Services: {[s.get('name') for s in services]}")
    
    for chunk in call_llama_stream([
        {"role": "system", "content": TERRAFORM_DEPLOY_SYSTEM_PROMPT},
        {"role": "user", "content": message},
    ]):
        yield chunk


def _extract_hcl_from_response(response: str) -> str:
    """
    Extract HCL code from LLM response.
    Removes markdown code fences if present.
    """
    if not response:
        return ""
    
    # Check for markdown code blocks
    if "```" in response:
        # Find content between code fences
        import re
        # Match ```hcl, ```terraform, or just ```
        pattern = r"```(?:hcl|terraform)?\s*\n(.*?)```"
        match = re.search(pattern, response, re.DOTALL)
        if match:
            return match.group(1).strip()
    
    # No code fences, return as-is (trimmed)
    return response.strip()


def get_service_env_vars_for_terraform(
    project_path: str,
    services: List[Dict],
) -> Dict[str, Dict[str, str]]:
    """
    Get environment variables for each service from their .env files.
    Uses the existing _read_env_key_values function from detector.py.
    
    Args:
        project_path: Root path of the project
        services: List of service dicts with 'name' and 'path' keys
    
    Returns:
        Dict mapping service name to its env vars
        e.g., {"backend": {"PORT": "3000", "MONGO_URI": "..."}}
    """
    from ..utils.detector import _read_env_key_values
    
    service_envs = {}
    
    for svc in services:
        svc_name = svc.get("name", "app")
        svc_path = svc.get("path", "")
        
        # Construct full path to service directory
        if svc_path:
            full_path = os.path.join(project_path, svc_path)
        else:
            full_path = project_path
        
        # Read env vars from this service's directory
        if os.path.exists(full_path):
            env_vars = _read_env_key_values(full_path)
            if env_vars:
                service_envs[svc_name] = env_vars
                print(f"📦 Loaded {len(env_vars)} env vars for {svc_name} from {full_path}")
    
    return service_envs


# --- TERRAFORM ERROR FIXING ---

TERRAFORM_FIX_SYSTEM_PROMPT = """You are a Terraform expert. A Terraform configuration has errors.

## YOUR TASK
Fix the Terraform HCL code based on the error output.

## RULES
1. Only fix the specific errors shown
2. Keep all other resources unchanged
3. Return the COMPLETE fixed main.tf file
4. Do NOT add explanations, only return HCL code
5. Common fixes include:
   - Missing required arguments
   - Invalid resource references
   - Syntax errors
   - Wrong attribute names (e.g., instance_type vs type)
   - Missing depends_on
   - Invalid ARN references

## OUTPUT FORMAT
Return ONLY the complete, fixed Terraform HCL code. No markdown, no explanations."""


def fix_terraform_error(
    current_terraform: str,
    error_output: str,
    project_name: str = "app",
) -> str:
    """
    Fix Terraform errors using LLM.
    
    Args:
        current_terraform: The current main.tf content that has errors
        error_output: The error output from terraform plan/apply
        project_name: Project name for context
    
    Returns:
        Fixed Terraform HCL code
    """
    message = f"""=== TERRAFORM FIX REQUEST ===

PROJECT: {project_name}

=== ERROR OUTPUT ===
{error_output[-3000:]}

=== CURRENT TERRAFORM CODE ===
{current_terraform}

=== INSTRUCTIONS ===
Fix the errors above and return the complete, corrected main.tf file.
Return ONLY the HCL code, no explanations."""

    print(f"\n=== DEBUG: TERRAFORM FIX REQUEST ===")
    print(f"Project: {project_name}")
    print(f"Error (first 500 chars): {error_output[:500]}...")
    print("=" * 40)
    
    response = call_llama([
        {"role": "system", "content": TERRAFORM_FIX_SYSTEM_PROMPT},
        {"role": "user", "content": message},
    ])
    
    return _extract_hcl_from_response(response)


def fix_terraform_error_stream(
    current_terraform: str,
    error_output: str,
    project_name: str = "app",
):
    """
    Streaming version of Terraform error fixing.
    Yields tokens as they're generated.
    """
    message = f"""=== TERRAFORM FIX REQUEST ===

PROJECT: {project_name}

=== ERROR OUTPUT ===
{error_output[-3000:]}

=== CURRENT TERRAFORM CODE ===
{current_terraform}

=== INSTRUCTIONS ===
Fix the errors above and return the complete, corrected main.tf file.
Return ONLY the HCL code, no explanations."""

    print(f"\n=== DEBUG: STREAMING TERRAFORM FIX ===")
    print(f"Project: {project_name}")
    
    for chunk in call_llama_stream([
        {"role": "system", "content": TERRAFORM_FIX_SYSTEM_PROMPT},
        {"role": "user", "content": message},
    ]):
        yield chunk

