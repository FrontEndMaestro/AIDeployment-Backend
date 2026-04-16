"""
AWS Deployment Controller - Handles API requests for AWS EC2 (Free Tier) docker-compose deployment.

Provides handlers for:
- Generating Terraform configurations via LLM
- Applying Terraform to deploy infrastructure
- Destroying deployed infrastructure
- Scaling services to zero (cost control)
- Getting deployment status
"""

import os
from datetime import datetime
from typing import Dict, List, Optional, Any

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from bson import ObjectId

from ..config.database import get_projects_collection
from ..config.settings import settings
from ..LLM.terraform_deploy_agent import (
    run_terraform_deploy_chat,
    run_terraform_deploy_chat_stream,
    get_service_env_vars_for_terraform,
    fix_terraform_error,
)
from ..services.aws_service import AWSDeploymentService, verify_aws_credentials


def get_compose_and_env_for_terraform(extracted_path: str, services: List[Dict]) -> Dict[str, Any]:
    """
    Read existing docker-compose.yml and .env files from the project.
    
    Args:
        extracted_path: Path to the extracted project
        services: List of service dicts with 'name' and 'path'
    
    Returns:
        Dict with compose_content (str or None), env_files (dict of service_name -> env content)
    """
    result = {"compose_content": None, "env_files": {}}
    
    # Read docker-compose.yml
    compose_path = os.path.join(extracted_path, "docker-compose.yml")
    if os.path.exists(compose_path):
        try:
            with open(compose_path, 'r', encoding='utf-8') as f:
                result["compose_content"] = f.read()
            print(f"📄 Read docker-compose.yml: {len(result['compose_content'])} bytes")
        except Exception as e:
            print(f"⚠️ Error reading docker-compose.yml: {e}")
    
    # Read .env files for each service
    for svc in services:
        svc_name = svc.get("name", "app")
        svc_path = svc.get("path", ".")
        
        # Normalize service path
        if svc_path.endswith("/"):
            svc_path = svc_path[:-1]
        
        # Try to find .env file
        for env_name in [".env", ".env.local", ".env.production"]:
            env_path = os.path.join(extracted_path, svc_path, env_name)
            if os.path.exists(env_path):
                try:
                    with open(env_path, 'r', encoding='utf-8') as f:
                        result["env_files"][svc_name] = f.read()
                    print(f"📄 Read {svc_name} env file: {env_path}")
                    break
                except Exception as e:
                    print(f"⚠️ Error reading {env_path}: {e}")
    
    return result

async def check_aws_prerequisites(project_id: str, current_user: dict) -> Dict[str, Any]:
    """
    Check prerequisites for AWS deployment.
    
    Returns:
        Dict with can_deploy, missing items, and project info
    """
    collection = get_projects_collection()
    project = await collection.find_one({"_id": ObjectId(project_id)})
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if project.get("user_id") != str(current_user["_id"]):
        raise HTTPException(status_code=403, detail="Access denied: Not project owner")
    
    issues = []
    
    # Check if Docker build succeeded
    docker_push_success = project.get("docker_push_success", False)
    if not docker_push_success:
        issues.append("Docker images must be built and pushed first")
    
    # Check AWS credentials
    aws_creds = verify_aws_credentials()
    if not aws_creds["is_valid"]:
        issues.append(aws_creds["message"])
    
    # Check if terraform is installed
    terraform_path = getattr(settings, "TERRAFORM_PATH", "terraform")
    test_service = AWSDeploymentService(".", terraform_path)
    if not test_service.check_terraform_installed():
        issues.append("Terraform CLI not found. Please install Terraform.")
    
    # Check if docker-compose.yml exists (Docker deployment must be done first)
    extracted_path = project.get("extracted_path", "")
    compose_path = os.path.join(extracted_path, "docker-compose.yml") if extracted_path else ""
    docker_compose_exists = os.path.exists(compose_path) if compose_path else False
    if not docker_compose_exists:
        issues.append("Run Docker deployment first to generate docker-compose.yml")
    
    return {
        "can_deploy": len(issues) == 0,
        "issues": issues,
        "project_name": project.get("project_name", "app"),
        "aws_region": aws_creds.get("region", "us-east-1"),
        "docker_push_success": docker_push_success,
        "docker_hub_username": settings.DOCKER_HUB_USERNAME or "",
        "terraform_exists": os.path.exists(os.path.join(project.get("extracted_path", ""), "infra", "main.tf")) if project.get("extracted_path") else False,
        "aws_deployment_status": project.get("aws_deployment_status", "not_deployed"),
    }


async def generate_terraform_handler(
    project_id: str,
    current_user: dict,
    aws_config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Generate Terraform configuration using LLM.
    
    Args:
        project_id: Project ID
        current_user: Current authenticated user
        aws_config: Dict with aws_region, docker_repo_prefix, db_engine, db_url, desired_count
    
    Returns:
        Dict with status, terraform_path, message
    """
    try:
        if not ObjectId.is_valid(project_id):
            raise HTTPException(status_code=400, detail="Invalid project ID format")
        
        collection = get_projects_collection()
        project = await collection.find_one({"_id": ObjectId(project_id)})
        
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        if project.get("user_id") != str(current_user["_id"]):
            raise HTTPException(status_code=403, detail="Access denied: Not project owner")
        
        # Extract project info
        project_name = project.get("project_name", "app").replace(" ", "-").lower()
        extracted_path = project.get("extracted_path")
        metadata = project.get("metadata", {})
        
        if not extracted_path or not os.path.exists(extracted_path):
            raise HTTPException(status_code=400, detail="Extracted project files not found")
        
        # Build services list from metadata
        services = _build_services_from_metadata(metadata)
        
        # Get environment variables for each service
        service_env_vars = get_service_env_vars_for_terraform(extracted_path, services)
        
        # Merge any extra env vars from user
        extra_env = aws_config.get("extra_env", {})
        if extra_env:
            # Ensure every service gets extra_env, even if none were detected initially
            for svc in services:
                svc_name = svc.get("name", "app")
                env_dict = service_env_vars.setdefault(svc_name, {})
                env_dict.update(extra_env)
        
        # Read existing docker-compose.yml and .env files (from Docker deployment)
        compose_data = get_compose_and_env_for_terraform(extracted_path, services)
        
        # Generate Terraform via LLM
        print(f"🏗️ Generating Terraform for project: {project_name}")
        
        terraform_code = run_terraform_deploy_chat(
            project_name=project_name,
            services=services,
            docker_repo_prefix=aws_config.get("docker_repo_prefix", ""),
            aws_region=aws_config.get("aws_region", "us-east-1"),
            db_engine=aws_config.get("db_engine"),
            db_url=aws_config.get("mongo_db_url") or aws_config.get("rds_db_url"),
            desired_count=aws_config.get("desired_count", 1),
            service_env_vars=service_env_vars,
            existing_compose=compose_data.get("compose_content"),
            existing_env_files=compose_data.get("env_files"),
        )
        
        if not terraform_code or terraform_code.startswith("ERROR"):
            raise HTTPException(
                status_code=500,
                detail=f"LLM failed to generate Terraform: {terraform_code[:200]}"
            )
        
        # Write Terraform to project's infra directory
        terraform_path = getattr(settings, "TERRAFORM_PATH", "terraform")
        aws_service = AWSDeploymentService(extracted_path, terraform_path)
        tf_file_path = aws_service.write_terraform(terraform_code)
        
        # Update project with terraform status
        await collection.update_one(
            {"_id": ObjectId(project_id)},
            {
                "$set": {
                    "aws_deployment_status": "terraform_generated",
                    "aws_region": aws_config.get("aws_region", "us-east-1"),
                    "aws_terraform_path": tf_file_path,
                    "updated_at": datetime.now()
                },
                "$push": {
                    "logs": {
                        "message": "Terraform configuration generated",
                        "timestamp": datetime.now()
                    }
                }
            }
        )
        
        print(f"✅ Terraform generated: {tf_file_path}")
        
        return {
            "status": "generated",
            "terraform_path": tf_file_path,
            "message": "Terraform configuration generated successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Terraform generation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Terraform generation failed: {str(e)}")


async def apply_terraform_handler(
    project_id: str,
    current_user: dict,
    variables: Optional[Dict[str, Any]] = None
):
    """
    Apply Terraform configuration and stream progress.
    
    Returns:
        StreamingResponse with SSE events for progress
    """
    if not ObjectId.is_valid(project_id):
        raise HTTPException(status_code=400, detail="Invalid project ID format")
    
    collection = get_projects_collection()
    project = await collection.find_one({"_id": ObjectId(project_id)})
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if project.get("user_id") != str(current_user["_id"]):
        raise HTTPException(status_code=403, detail="Access denied: Not project owner")
    
    extracted_path = project.get("extracted_path")
    if not extracted_path or not os.path.exists(extracted_path):
        raise HTTPException(status_code=400, detail="Project path not found")
    
    # Initialize AWS service
    terraform_path = getattr(settings, "TERRAFORM_PATH", "terraform")
    aws_service = AWSDeploymentService(extracted_path, terraform_path)
    
    # Update status
    await collection.update_one(
        {"_id": ObjectId(project_id)},
        {
            "$set": {
                "aws_deployment_status": "deploying",
                "updated_at": datetime.now()
            }
        }
    )
    
    async def event_generator():
        """Generate SSE events for terraform apply progress."""
        import json
        
        try:
            # Run terraform init first
            for event in aws_service.terraform_init():
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("exit_code", 0) != 0:
                    # Init failed
                    await _update_aws_status(project_id, "failed")
                    return
            
            # Run terraform apply
            for event in aws_service.terraform_apply(variables=variables):
                yield f"data: {json.dumps(event)}\n\n"
                
                if "exit_code" in event:
                    if event["exit_code"] == 0:
                        # Apply succeeded - get outputs
                        outputs = aws_service.get_deployment_status()
                        await _update_aws_status(
                            project_id,
                            "deployed",
                            frontend_url=outputs.get("frontend_url"),
                            backend_url=outputs.get("backend_url")
                        )
                        yield f"data: {json.dumps({'type': 'complete', 'outputs': outputs})}\n\n"
                    else:
                        await _update_aws_status(project_id, "failed")
            
        except Exception as e:
            await _update_aws_status(project_id, "failed")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )


async def destroy_terraform_handler(
    project_id: str,
    current_user: dict
):
    """
    Destroy Terraform infrastructure and stream progress.
    
    Returns:
        StreamingResponse with SSE events for progress
    """
    if not ObjectId.is_valid(project_id):
        raise HTTPException(status_code=400, detail="Invalid project ID format")
    
    collection = get_projects_collection()
    project = await collection.find_one({"_id": ObjectId(project_id)})
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if project.get("user_id") != str(current_user["_id"]):
        raise HTTPException(status_code=403, detail="Access denied: Not project owner")
    
    extracted_path = project.get("extracted_path")
    if not extracted_path:
        raise HTTPException(status_code=400, detail="Project path not found")
    
    terraform_path = getattr(settings, "TERRAFORM_PATH", "terraform")
    aws_service = AWSDeploymentService(extracted_path, terraform_path)
    
    await collection.update_one(
        {"_id": ObjectId(project_id)},
        {"$set": {"aws_deployment_status": "destroying", "updated_at": datetime.now()}}
    )
    
    async def event_generator():
        import json
        
        try:
            for event in aws_service.terraform_destroy():
                yield f"data: {json.dumps(event)}\n\n"
                
                if "exit_code" in event:
                    if event["exit_code"] == 0:
                        await _update_aws_status(project_id, "not_deployed")
                        yield f"data: {json.dumps({'type': 'complete', 'message': 'Infrastructure destroyed'})}\n\n"
                    else:
                        await _update_aws_status(project_id, "destroy_failed")
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")


async def scale_to_zero_handler(project_id: str, current_user: dict):
    """
    Stop the EC2 instance (cost savings - no compute charges when stopped).
    
    Returns:
        StreamingResponse with SSE events
    """
    if not ObjectId.is_valid(project_id):
        raise HTTPException(status_code=400, detail="Invalid project ID format")
    
    collection = get_projects_collection()
    project = await collection.find_one({"_id": ObjectId(project_id)})
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if project.get("user_id") != str(current_user["_id"]):
        raise HTTPException(status_code=403, detail="Access denied")
    
    extracted_path = project.get("extracted_path")
    terraform_path = getattr(settings, "TERRAFORM_PATH", "terraform")
    aws_service = AWSDeploymentService(extracted_path, terraform_path)
    
    async def event_generator():
        import json
        for event in aws_service.scale_to_zero():
            yield f"data: {json.dumps(event)}\n\n"
            if event.get("exit_code") == 0:
                await _update_aws_status(project_id, "scaled_to_zero")
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")


async def get_aws_status_handler(project_id: str, current_user: dict) -> Dict[str, Any]:
    """
    Get AWS deployment status.
    
    Returns:
        Dict with status, frontend_url (public IP), instance info, etc.
    """
    if not ObjectId.is_valid(project_id):
        raise HTTPException(status_code=400, detail="Invalid project ID format")
    
    collection = get_projects_collection()
    project = await collection.find_one({"_id": ObjectId(project_id)})
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if project.get("user_id") != str(current_user["_id"]):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get basic status from DB
    status = {
        "aws_deployment_status": project.get("aws_deployment_status", "not_deployed"),
        "aws_region": project.get("aws_region"),
        "aws_frontend_url": project.get("aws_frontend_url"),
        "aws_backend_url": project.get("aws_backend_url"),
        "aws_instance_id": project.get("aws_instance_id"),
        "aws_last_deployed": project.get("aws_last_deployed"),
        "docker_push_success": project.get("docker_push_success", False)
    }
    
    # If deployed, try to get live status from terraform
    extracted_path = project.get("extracted_path")
    if extracted_path and status["aws_deployment_status"] == "deployed":
        terraform_path = getattr(settings, "TERRAFORM_PATH", "terraform")
        aws_service = AWSDeploymentService(extracted_path, terraform_path)
        live_status = aws_service.get_deployment_status()
        status.update({
            "live_public_ip": live_status.get("public_ip"),
            "live_frontend_url": live_status.get("frontend_url"),
            "live_backend_url": live_status.get("backend_url"),
            "live_instance_id": live_status.get("instance_id"),
            "live_vpc_id": live_status.get("vpc_id")
        })
    
    return status


async def fix_terraform_handler(
    project_id: str,
    current_user: dict,
    error_output: str
) -> Dict[str, Any]:
    """
    Fix Terraform errors using LLM.
    
    Reads the current main.tf, sends it with the error to LLM,
    and writes the corrected version.
    
    Args:
        project_id: Project ID
        current_user: Current authenticated user
        error_output: The error message from terraform
    
    Returns:
        Dict with status and message
    """
    if not ObjectId.is_valid(project_id):
        raise HTTPException(status_code=400, detail="Invalid project ID format")
    
    collection = get_projects_collection()
    project = await collection.find_one({"_id": ObjectId(project_id)})
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if project.get("user_id") != str(current_user["_id"]):
        raise HTTPException(status_code=403, detail="Access denied")
    
    extracted_path = project.get("extracted_path")
    if not extracted_path:
        raise HTTPException(status_code=400, detail="Project path not found")
    
    # Ensure terraform is available before attempting a fix
    terraform_path = getattr(settings, "TERRAFORM_PATH", "terraform")
    if not AWSDeploymentService(".", terraform_path).check_terraform_installed():
        raise HTTPException(
            status_code=400,
            detail=f"Terraform CLI not found at: {terraform_path}. Install Terraform or set TERRAFORM_PATH."
        )
    
    # Read current Terraform
    tf_path = os.path.join(extracted_path, "infra", "main.tf")
    if not os.path.exists(tf_path):
        raise HTTPException(status_code=400, detail="No Terraform file found. Generate first.")
    
    with open(tf_path, "r", encoding="utf-8") as f:
        current_terraform = f.read()
    
    project_name = project.get("project_name", "app")
    
    print(f"🔧 Fixing Terraform for {project_name}...")
    print(f"   Error: {error_output[:200]}...")
    
    # Call LLM to fix
    fixed_terraform = fix_terraform_error(
        current_terraform=current_terraform,
        error_output=error_output,
        project_name=project_name
    )
    
    if not fixed_terraform or len(fixed_terraform) < 100:
        raise HTTPException(status_code=500, detail="LLM failed to generate fix")
    
    # Write fixed Terraform
    with open(tf_path, "w", encoding="utf-8") as f:
        f.write(fixed_terraform)
    
    # Update status
    await collection.update_one(
        {"_id": ObjectId(project_id)},
        {
            "$set": {"updated_at": datetime.now()},
            "$push": {
                "logs": {
                    "message": "Terraform fixed by LLM",
                    "timestamp": datetime.now()
                }
            }
        }
    )
    
    print(f"✅ Terraform fixed and saved!")
    
    return {
        "status": "fixed",
        "message": "Terraform configuration fixed. Try deploying again."
    }


# ============ Helper Functions ============

def _build_services_from_metadata(metadata: Dict) -> List[Dict]:
    """
    Build a list of service definitions from project metadata.
    
    Returns:
        List of dicts with {name, port, path, type} for each service
    """
    services = []
    
    # Check for fullstack project (has both backend and frontend)
    is_fullstack = metadata.get("is_fullstack", False)
    
    if is_fullstack:
        # Backend service
        backend_port = metadata.get("backend_port", 3000)
        services.append({
            "name": "backend",
            "port": backend_port,
            "path": "backend",
            "type": "backend"
        })
        
        # Frontend service (nginx serves on 80)
        services.append({
            "name": "frontend",
            "port": 80,  # nginx container port
            "path": "frontend",
            "type": "frontend"
        })
    else:
        # Single service - determine type
        framework = metadata.get("framework", "").lower()
        
        if any(fw in framework for fw in ["react", "vue", "angular", "next", "vite"]):
            # Frontend-only project
            services.append({
                "name": "frontend",
                "port": 80,
                "path": ".",
                "type": "frontend"
            })
        else:
            # Backend-only project
            port = metadata.get("port", metadata.get("backend_port", 3000))
            services.append({
                "name": "backend",
                "port": port,
                "path": ".",
                "type": "backend"
            })
    
    return services


async def _update_aws_status(
    project_id: str,
    status: str,
    frontend_url: Optional[str] = None,
    backend_url: Optional[str] = None
):
    """Update AWS deployment status in database."""
    collection = get_projects_collection()
    
    update_data = {
        "aws_deployment_status": status,
        "updated_at": datetime.now()
    }
    
    if frontend_url:
        update_data["aws_frontend_url"] = frontend_url
        update_data["aws_last_deployed"] = datetime.now()
    if backend_url:
        update_data["aws_backend_url"] = backend_url
        update_data["aws_last_deployed"] = datetime.now()
    
    await collection.update_one(
        {"_id": ObjectId(project_id)},
        {"$set": update_data}
    )
