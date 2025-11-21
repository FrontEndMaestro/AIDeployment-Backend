import subprocess
from typing import Dict


def push_docker_image(image_tag: str) -> Dict:
    """Push Docker image to Docker Hub"""
    
    try:
        print(f"Pushing: {image_tag}")
        
        # ✅ BULLETPROOF FIX: Read as raw bytes, then decode
        login_check = subprocess.Popen(
            ["docker", "info"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
            # NO encoding parameter
        )
        
        stdout_bytes, stderr_bytes = login_check.communicate(timeout=10)
        
        if login_check.returncode != 0:
            return {
                "success": False,
                "message": "Docker not running or not logged in"
            }
        
        cmd = ["docker", "push", image_tag]
        
        # ✅ BULLETPROOF FIX: Read as raw bytes, then decode
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
            # NO encoding parameter
        )
        
        stdout_bytes, stderr_bytes = process.communicate(timeout=600)
        
        # Decode bytes with error handling
        stdout = stdout_bytes.decode('utf-8', errors='replace') if stdout_bytes else ""
        stderr = stderr_bytes.decode('utf-8', errors='replace') if stderr_bytes else ""
        
        if process.returncode != 0:
            print(f"Push failed: {stderr}")
            return {
                "success": False,
                "message": stderr
            }
        
        print(f"Push successful: {image_tag}")
        
        return {
            "success": True,
            "image_tag": image_tag,
            "registry_url": f"docker.io/{image_tag}"
        }
    
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "message": "Push timeout"
        }
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            "success": False,
            "message": str(e)
        }