"""
AWS Deployment Service - Handles Terraform execution for AWS EC2 Free Tier deployments.

This service manages:
- Writing Terraform files to project directories
- Running terraform init, apply, destroy
- EC2 instance management (start/stop)
- Streaming terraform output for real-time progress
"""

import os
import subprocess
import json
import re
from typing import Dict, Generator, List, Optional, Any
from pathlib import Path


class AWSDeploymentService:
    """Service for executing Terraform commands and managing AWS deployments."""
    
    def __init__(self, project_path: str, terraform_path: str = "terraform"):
        """
        Initialize the AWS deployment service.
        
        Args:
            project_path: Root path of the project
            terraform_path: Path to terraform CLI binary
        """
        self.project_path = project_path
        self.infra_path = os.path.join(project_path, "infra")
        self.terraform_path = terraform_path
        
        # Ensure infra directory exists
        os.makedirs(self.infra_path, exist_ok=True)
    
    def write_terraform(self, hcl_content: str, filename: str = "main.tf") -> str:
        """
        Write Terraform HCL content to the infra directory.
        
        Args:
            hcl_content: The Terraform HCL code to write
            filename: Name of the file (default: main.tf)
        
        Returns:
            Full path to the written file
        """
        filepath = os.path.join(self.infra_path, filename)
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(hcl_content)
        
        print(f"✅ Wrote Terraform config to: {filepath}")
        return filepath
    
    def terraform_init(self) -> Generator[Dict[str, Any], None, None]:
        """
        Run terraform init and yield progress logs.
        
        Yields:
            Dict with keys: type, message, stage, exit_code (on completion)
        """
        yield from self._run_terraform_command(["init", "-input=false"], "init")
    
    def terraform_plan(self, variables: Optional[Dict[str, Any]] = None) -> Generator[Dict[str, Any], None, None]:
        """
        Run terraform plan and yield progress logs.
        
        Args:
            variables: Optional dict of Terraform variables to pass via -var
        
        Yields:
            Dict with keys: type, message, stage, exit_code (on completion)
        """
        cmd = ["plan"]
        if variables:
            for key, value in variables.items():
                cmd.extend(["-var", f"{key}={value}"])
        
        yield from self._run_terraform_command(cmd, "plan")
    
    def terraform_apply(
        self,
        variables: Optional[Dict[str, Any]] = None,
        auto_approve: bool = True
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Run terraform apply and yield progress logs.
        
        Args:
            variables: Optional dict of Terraform variables to pass via -var
            auto_approve: Whether to auto-approve (default: True)
        
        Yields:
            Dict with keys: type, message, stage, exit_code (on completion)
        """
        cmd = ["apply"]
        if auto_approve:
            cmd.append("-auto-approve")
        
        if variables:
            for key, value in variables.items():
                if isinstance(value, bool):
                    value = str(value).lower()
                cmd.extend(["-var", f"{key}={value}"])
        
        yield from self._run_terraform_command(cmd, "apply")
    
    def terraform_destroy(
        self,
        variables: Optional[Dict[str, Any]] = None,
        auto_approve: bool = True
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Run terraform destroy and yield progress logs.
        
        Args:
            variables: Optional dict of Terraform variables
            auto_approve: Whether to auto-approve (default: True)
        
        Yields:
            Dict with keys: type, message, stage, exit_code (on completion)
        """
        cmd = ["destroy"]
        if auto_approve:
            cmd.append("-auto-approve")
        
        if variables:
            for key, value in variables.items():
                if isinstance(value, bool):
                    value = str(value).lower()
                cmd.extend(["-var", f"{key}={value}"])
        
        yield from self._run_terraform_command(cmd, "destroy")
    
    def terraform_output(self) -> Dict[str, Any]:
        """
        Get terraform outputs as a dictionary.
        
        Returns:
            Dict of output name -> value
        """
        try:
            result = subprocess.run(
                [self.terraform_path, "output", "-json"],
                cwd=self.infra_path,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0 and result.stdout.strip():
                outputs = json.loads(result.stdout)
                # Extract just the values from Terraform output format
                return {
                    key: data.get("value") 
                    for key, data in outputs.items()
                }
            
            return {}
            
        except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as e:
            print(f"Error getting terraform outputs: {e}")
            return {}
    
    def get_deployment_status(self) -> Dict[str, Any]:
        """
        Get current deployment status by checking terraform state.
        
        Returns:
            Dict with status info: deployed, public_ip, frontend_url, etc.
        """
        state_file = os.path.join(self.infra_path, "terraform.tfstate")
        
        if not os.path.exists(state_file):
            return {
                "status": "not_deployed",
                "public_ip": None,
                "frontend_url": None,
                "instance_id": None,
                "vpc_id": None
            }
        
        # Get outputs from terraform
        outputs = self.terraform_output()
        
        return {
            "status": "deployed" if outputs else "unknown",
            "public_ip": outputs.get("instance_public_ip"),
            "frontend_url": outputs.get("frontend_url"),
            "backend_url": outputs.get("backend_url"),
            "instance_id": outputs.get("instance_id"),
            "vpc_id": outputs.get("vpc_id")
        }
    
    def stop_instance(self) -> Generator[Dict[str, Any], None, None]:
        """
        Stop the EC2 instance (cost savings - no compute charges when stopped).
        Uses AWS CLI to stop the instance directly.
        
        Yields:
            Progress logs
        """
        outputs = self.terraform_output()
        instance_id = outputs.get("instance_id")
        
        if not instance_id:
            yield {
                "type": "error",
                "message": "No instance found to stop",
                "stage": "stop"
            }
            return
        
        yield {
            "type": "info",
            "message": f"Stopping EC2 instance: {instance_id}",
            "stage": "stop"
        }
        
        try:
            result = subprocess.run(
                ["aws", "ec2", "stop-instances", "--instance-ids", instance_id],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                yield {
                    "type": "success",
                    "message": f"✅ Instance {instance_id} stopping. No compute charges when stopped.",
                    "stage": "stop",
                    "exit_code": 0
                }
            else:
                yield {
                    "type": "error",
                    "message": f"Failed to stop instance: {result.stderr}",
                    "stage": "stop",
                    "exit_code": result.returncode
                }
        except Exception as e:
            yield {
                "type": "error",
                "message": f"Error stopping instance: {str(e)}",
                "stage": "stop",
                "exit_code": -1
            }
    
    def start_instance(self) -> Generator[Dict[str, Any], None, None]:
        """
        Start a stopped EC2 instance.
        Uses AWS CLI to start the instance directly.
        
        Yields:
            Progress logs
        """
        outputs = self.terraform_output()
        instance_id = outputs.get("instance_id")
        
        if not instance_id:
            yield {
                "type": "error",
                "message": "No instance found to start",
                "stage": "start"
            }
            return
        
        yield {
            "type": "info",
            "message": f"Starting EC2 instance: {instance_id}",
            "stage": "start"
        }
        
        try:
            result = subprocess.run(
                ["aws", "ec2", "start-instances", "--instance-ids", instance_id],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                yield {
                    "type": "success",
                    "message": f"✅ Instance {instance_id} starting. It may take a minute to be accessible.",
                    "stage": "start",
                    "exit_code": 0
                }
            else:
                yield {
                    "type": "error",
                    "message": f"Failed to start instance: {result.stderr}",
                    "stage": "start",
                    "exit_code": result.returncode
                }
        except Exception as e:
            yield {
                "type": "error",
                "message": f"Error starting instance: {str(e)}",
                "stage": "start",
                "exit_code": -1
            }
    
    # Keep old method name for compatibility
    def scale_to_zero(self) -> Generator[Dict[str, Any], None, None]:
        """Alias for stop_instance for backward compatibility."""
        yield from self.stop_instance()
    
    def scale_up(self, desired_count: int = 1) -> Generator[Dict[str, Any], None, None]:
        """
        Scale ECS services back up.
        Runs terraform apply with scale_to_zero=false.
        
        Args:
            desired_count: Number of tasks per service
        
        Yields:
            Progress logs from terraform apply
        """
        yield from self.terraform_apply(variables={
            "scale_to_zero": False,
            "desired_count": desired_count
        })
    
    def check_terraform_installed(self) -> bool:
        """Check if Terraform CLI is installed and accessible."""
        try:
            result = subprocess.run(
                [self.terraform_path, "version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def _get_terraform_env(self) -> Dict[str, str]:
        """Build environment dict with AWS credentials for terraform subprocess."""
        from ..config.settings import settings
        
        env = {**os.environ, "TF_IN_AUTOMATION": "1"}
        
        # Add AWS credentials from settings (Pydantic loads .env but doesn't export to os.environ)
        if settings.AWS_PROFILE:
            env["AWS_PROFILE"] = settings.AWS_PROFILE
        if settings.AWS_DEFAULT_REGION:
            env["AWS_DEFAULT_REGION"] = settings.AWS_DEFAULT_REGION
            env["AWS_REGION"] = settings.AWS_DEFAULT_REGION
        
        return env
    
    def _strip_ansi(self, text: str) -> str:
        """Strip ANSI escape codes from terraform output."""
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)
    
    def _run_terraform_command(
        self,
        args: List[str],
        stage: str
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Run a terraform command and yield log lines as they come.
        
        Args:
            args: List of terraform arguments (e.g., ["init", "-input=false"])
            stage: Stage name for logging (e.g., "init", "apply")
        
        Yields:
            Dict with keys: type, message, stage, exit_code (on completion)
        """
        cmd = [self.terraform_path] + args
        
        yield {
            "type": "info",
            "message": f"Running: {' '.join(cmd)}",
            "stage": stage
        }
        # Also echo to backend console for visibility
        print(f"[terraform:{stage}] {' '.join(cmd)}")
        
        try:
            process = subprocess.Popen(
                cmd,
                cwd=self.infra_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=self._get_terraform_env()
            )
            
            for line in process.stdout:
                line = self._strip_ansi(line.rstrip())
                if line:
                    # Determine message type based on content
                    msg_type = "info"
                    if "Error" in line or "error" in line:
                        msg_type = "error"
                    elif "Warning" in line or "warning" in line:
                        msg_type = "warning"
                    elif "Apply complete" in line or "Destroy complete" in line:
                        msg_type = "success"
                    
                    # Mirror terraform output to backend console
                    print(f"[terraform:{stage}] {line}")
                    
                    yield {
                        "type": msg_type,
                        "message": line,
                        "stage": stage
                    }
            
            process.wait()
            
            yield {
                "type": "success" if process.returncode == 0 else "error",
                "message": f"Terraform {stage} {'completed' if process.returncode == 0 else 'failed'}",
                "stage": stage,
                "exit_code": process.returncode
            }
            
        except FileNotFoundError:
            yield {
                "type": "error",
                "message": f"Terraform CLI not found at: {self.terraform_path}",
                "stage": stage,
                "exit_code": -1
            }
        except Exception as e:
            yield {
                "type": "error",
                "message": f"Error running terraform: {str(e)}",
                "stage": stage,
                "exit_code": -1
            }


def verify_aws_credentials() -> Dict[str, Any]:
    """
    Verify that AWS credentials are configured.
    Checks for AWS_PROFILE or AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY.
    Also verifies by calling aws sts get-caller-identity.
    
    Returns:
        Dict with is_valid (bool) and message (str)
    """
    profile = os.environ.get("AWS_PROFILE")
    access_key = os.environ.get("AWS_ACCESS_KEY_ID")
    secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
    region = os.environ.get("AWS_DEFAULT_REGION", os.environ.get("AWS_REGION", "us-east-1"))
    
    # If AWS_PROFILE is set, try to verify credentials
    if profile:
        try:
            result = subprocess.run(
                ["aws", "sts", "get-caller-identity", "--profile", profile],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return {
                    "is_valid": True,
                    "message": f"AWS profile '{profile}' configured",
                    "region": region,
                    "profile": profile
                }
            else:
                return {
                    "is_valid": False,
                    "message": f"AWS profile '{profile}' is invalid or expired",
                    "region": region
                }
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return {
                "is_valid": False,
                "message": "AWS CLI not found. Install AWS CLI or set AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY",
                "region": region
            }
    
    # Fall back to checking env vars
    if not access_key or not secret_key:
        return {
            "is_valid": False,
            "message": "Set AWS_PROFILE in .env or configure AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY",
            "region": region
        }
    
    return {
        "is_valid": True,
        "message": "AWS credentials configured via environment variables",
        "region": region
    }
