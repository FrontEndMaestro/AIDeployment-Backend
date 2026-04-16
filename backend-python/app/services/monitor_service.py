import os
import subprocess
from typing import Dict, Any
from app.utils.k8s_deployer import diagnose_pod_health

class MonitorService:
    @staticmethod
    def get_k8s_health(deployment_name: str) -> Dict[str, Any]:
        """Check Kubernetes health."""
        if not deployment_name:
            return {"status": "not_deployed", "healthy": False}
        return diagnose_pod_health(deployment_name)

    @staticmethod
    def get_aws_health(project_id: str) -> Dict[str, Any]:
        """Check AWS Terraform state health."""
        tf_dir = os.path.join("terraform", project_id)
        if not os.path.exists(os.path.join(tf_dir, "terraform.tfstate")):
            return {"status": "not_deployed", "healthy": False}
        
        try:
            # We check terraform output locally to see if it's deployed
            cmd = ["terraform", "output", "-json"]
            process = subprocess.Popen(cmd, cwd=tf_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, _ = process.communicate(timeout=10)
            
            if process.returncode == 0:
                 return {"status": "deployed", "healthy": True, "details": "Terraform state exists"}
            else:
                 return {"status": "unknown", "healthy": False, "details": "Could not read outputs"}
        except Exception as e:
            return {"status": "error", "healthy": False, "details": str(e)}

    @staticmethod
    def trigger_self_healing(deployment_name: str) -> Dict[str, Any]:
        """Triggers a rollout restart of a Kubernetes deployment."""
        try:
            cmd = ["kubectl", "rollout", "restart", f"deployment/{deployment_name}"]
            process = subprocess.run(cmd, capture_output=True, timeout=30)
            
            if process.returncode == 0:
                return {"success": True, "message": f"Successfully triggered restart for {deployment_name}"}
            else:
                err = process.stderr.decode('utf-8', errors='replace')
                return {"success": False, "message": f"Failed to restart: {err}"}
        except Exception as e:
            return {"success": False, "message": str(e)}

monitor_service = MonitorService()
