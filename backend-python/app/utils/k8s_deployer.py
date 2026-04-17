import subprocess
import json
import os
import tempfile
import time
import asyncio
from typing import Dict, AsyncGenerator


def check_kubernetes_connection() -> Dict:
    """Check if Kubernetes cluster is accessible"""
    try:
        process = subprocess.Popen(
            ["kubectl", "cluster-info"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout_bytes, stderr_bytes = process.communicate(timeout=10)
        
        if process.returncode == 0:
            return {"success": True, "message": "Kubernetes cluster is reachable"}
        else:
            stderr = stderr_bytes.decode('utf-8', errors='replace') if stderr_bytes else ""
            return {"success": False, "message": f"Kubernetes not accessible: {stderr}"}
    except Exception as e:
        return {"success": False, "message": f"Kubernetes check failed: {str(e)}"}


def apply_manifest_with_retry(manifest_file: str, manifest_type: str, max_retries: int = 3) -> tuple:
    """Apply Kubernetes manifest with retry logic"""
    
    for attempt in range(1, max_retries + 1):
        try:
            if attempt > 1:
                print(f"🔄 Retry {attempt}/{max_retries} for {manifest_type}...")
                time.sleep(2)  # Wait before retry
            
            # Try with --validate=false and --force
            process = subprocess.Popen(
                ["kubectl", "apply", "-f", manifest_file, "--validate=false", "--force"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            stdout_bytes, stderr_bytes = process.communicate(timeout=60)
            stdout = stdout_bytes.decode('utf-8', errors='replace') if stdout_bytes else ""
            stderr = stderr_bytes.decode('utf-8', errors='replace') if stderr_bytes else ""
            
            if process.returncode == 0:
                return True, stdout
            
            # Check if it's an EOF/connection error that might succeed on retry
            if 'EOF' in stderr or 'timeout' in stderr.lower() or 'connection' in stderr.lower():
                if attempt < max_retries:
                    print(f"⚠️ Connection issue, retrying...")
                    continue
            
            # Other errors, fail immediately
            return False, stderr
            
        except subprocess.TimeoutExpired:
            if attempt < max_retries:
                print(f"⚠️ Timeout, retrying...")
                continue
            return False, f"{manifest_type} timeout after {max_retries} attempts"
        except Exception as e:
            if attempt < max_retries:
                print(f"⚠️ Error: {str(e)}, retrying...")
                continue
            return False, str(e)
    
    return False, f"Failed after {max_retries} attempts"


def deploy_to_kubernetes(manifests: Dict) -> Dict:
    """Apply Kubernetes manifests to cluster"""
    
    try:
        deployment_name = manifests.get("deployment_name")
        print(f"Deploying: {deployment_name}")
        
        # Check Kubernetes connection first
        k8s_check = check_kubernetes_connection()
        if not k8s_check["success"]:
            print(f"⚠️ Warning: {k8s_check['message']}")
            print("ℹ️ Attempting deployment anyway...")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            deployment_file = os.path.join(temp_dir, "deployment.yaml")
            service_file = os.path.join(temp_dir, "service.yaml")
            configmap_file = os.path.join(temp_dir, "configmap.yaml")
            
            # Write manifests to files
            with open(deployment_file, 'w', encoding='utf-8') as f:
                f.write(manifests["deployment"])
            
            with open(service_file, 'w', encoding='utf-8') as f:
                f.write(manifests["service"])
            
            with open(configmap_file, 'w', encoding='utf-8') as f:
                f.write(manifests["configmap"])
            
            print(f"📄 Manifests written to: {temp_dir}")
            
            # Apply ConfigMap with retry
            print("Applying ConfigMap...")
            success, output = apply_manifest_with_retry(configmap_file, "ConfigMap", max_retries=3)
            if not success:
                raise Exception(f"ConfigMap failed: {output}")
            print("✅ ConfigMap applied")
            
            # Apply Deployment with retry
            print("Applying Deployment...")
            success, output = apply_manifest_with_retry(deployment_file, "Deployment", max_retries=3)
            if not success:
                raise Exception(f"Deployment failed: {output}")
            print("✅ Deployment applied")

            # Force pod restart to use new image
            print("♻️ Forcing pod restart...")
            restart_cmd = ["kubectl", "rollout", "restart", f"deployment/{deployment_name}"]
            subprocess.run(restart_cmd, capture_output=True, timeout=30)
            
            # Apply Service with retry
            print("Applying Service...")
            success, output = apply_manifest_with_retry(service_file, "Service", max_retries=3)
            if not success:
                raise Exception(f"Service failed: {output}")
            print("✅ Service applied")
        
        # Wait for pod to be created
        print("⏳ Waiting for pod creation...")
        time.sleep(5)
        
        pod_status = get_pod_status(deployment_name)
        
        return {
            "success": True,
            "deployment_name": deployment_name,
            "pod_name": pod_status.get("pod_name"),
            "pod_status": pod_status.get("status", "pending"),
            "service_port": manifests.get("service_port")
        }
    
    except Exception as e:
        error_msg = str(e)
        print(f"❌ K8s Error: {error_msg}")
        
        # Provide helpful error messages
        if "EOF" in error_msg or "connection refused" in error_msg.lower():
            helpful_msg = (
                f"{error_msg}\n\n"
                "💡 Possible solutions:\n"
                "1. Check if Docker Desktop Kubernetes is enabled and running\n"
                "2. Run: kubectl cluster-info\n"
                "3. Restart Docker Desktop\n"
                "4. Check if 'kubernetes.docker.internal' is accessible"
            )
            return {
                "success": False,
                "message": helpful_msg
            }
        
        return {
            "success": False,
            "message": error_msg
        }


def get_pod_status(deployment_name: str, max_retries: int = 3) -> Dict:
    """Get pod info with retry logic"""
    
    for attempt in range(1, max_retries + 1):
        try:
            if attempt > 1:
                time.sleep(2)
            
            cmd = ["kubectl", "get", "pods", "-l", f"app={deployment_name}", "-o", "json"]
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            stdout_bytes, stderr_bytes = process.communicate(timeout=15)
            stdout = stdout_bytes.decode('utf-8', errors='replace') if stdout_bytes else ""
            stderr = stderr_bytes.decode('utf-8', errors='replace') if stderr_bytes else ""
            
            if process.returncode == 0:
                pods_data = json.loads(stdout)
                if pods_data.get("items"):
                    pod = pods_data["items"][0]
                    pod_name = pod["metadata"]["name"]
                    pod_status = pod["status"]["phase"]
                    
                    return {"pod_name": pod_name, "status": pod_status}
                
                return {"pod_name": None, "status": "pending"}
            
            # Retry on connection errors
            if 'EOF' in stderr and attempt < max_retries:
                continue
            
            return {"pod_name": None, "status": "unknown"}
        
        except Exception as e:
            if attempt < max_retries:
                continue
            print(f"Error getting pod status: {str(e)}")
            return {"pod_name": None, "status": "unknown"}
    
    return {"pod_name": None, "status": "unknown"}


def get_deployment_status(deployment_name: str) -> Dict:
    """Get deployment status"""
    
    try:
        cmd = ["kubectl", "get", "deployment", deployment_name, "-o", "json"]
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        stdout_bytes, stderr_bytes = process.communicate(timeout=15)
        stdout = stdout_bytes.decode('utf-8', errors='replace') if stdout_bytes else ""
        stderr = stderr_bytes.decode('utf-8', errors='replace') if stderr_bytes else ""
        
        if process.returncode != 0:
            return {"status": "not_found"}
        
        deploy_data = json.loads(stdout)
        status = deploy_data["status"]
        pod_status = get_pod_status(deployment_name)
        
        return {
            "status": "running" if status.get("replicas") == status.get("readyReplicas") else "pending",
            "pod_name": pod_status.get("pod_name"),
            "replicas": status.get("replicas"),
            "ready_replicas": status.get("readyReplicas")
        }
    
    except Exception as e:
        print(f"Error getting deployment status: {str(e)}")
        return {"status": "unknown"}


def cleanup_deployment(deployment_name: str) -> Dict:
    """Remove deployment from cluster"""
    
    try:
        print(f"🗑️ Cleaning up: {deployment_name}")
        
        cmd = ["kubectl", "delete", "deployment,service,configmap", "-l", f"app={deployment_name}", "--ignore-not-found=true"]
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        stdout_bytes, stderr_bytes = process.communicate(timeout=60)
        stdout = stdout_bytes.decode('utf-8', errors='replace') if stdout_bytes else ""
        stderr = stderr_bytes.decode('utf-8', errors='replace') if stderr_bytes else ""
        
        if process.returncode != 0:
            print(f"⚠️ Cleanup warning: {stderr}")
        else:
            print("✅ Cleaned up successfully")
        
        return {
            "success": True,
            "deployment_name": deployment_name
        }
    
    except Exception as e:
        print(f"❌ Cleanup error: {str(e)}")
        return {
            "success": False,
            "message": str(e)
        }


async def stream_pod_logs(deployment_name: str) -> AsyncGenerator[str, None]:
    """
    Streams live pod logs for a deployment using asyncio subprocess.
    Includes timestamps, stderr, and heartbeat SSE comments to keep connections alive.
    """
    # First get the pod name
    pod_status = get_pod_status(deployment_name)
    pod_name = pod_status.get("pod_name")

    if not pod_name:
        yield "data: {\"type\": \"error\", \"message\": \"No pod found for deployment. Is it running?\"}\n\n"
        return

    yield f"data: {{\"type\": \"info\", \"message\": \"Streaming logs for pod: {pod_name}\"}}\n\n"

    # Run kubectl logs -f with timestamps
    process = await asyncio.create_subprocess_exec(
        "kubectl", "logs", "-f", pod_name, "--timestamps=true",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    last_heartbeat_time = asyncio.get_event_loop().time()

    try:
        while True:
            # Use asyncio.wait_for to implement heartbeat while waiting for a line
            try:
                line = await asyncio.wait_for(process.stdout.readline(), timeout=15.0)
            except asyncio.TimeoutError:
                # Send a heartbeat comment every 15 seconds of silence
                yield ": heartbeat\n\n"
                last_heartbeat_time = asyncio.get_event_loop().time()
                # Check if process ended
                if process.returncode is not None:
                    break
                continue

            if not line:
                break

            decoded_line = line.decode("utf-8", errors="replace").strip()
            yield f"data: {{\"type\": \"log\", \"message\": {json.dumps(decoded_line)}}}\n\n"

            # Opportunistically send heartbeat if a lot of time has passed
            now = asyncio.get_event_loop().time()
            if now - last_heartbeat_time > 15:
                yield ": heartbeat\n\n"
                last_heartbeat_time = now

    except asyncio.CancelledError:
        process.terminate()
        try:
            await process.wait()
        except Exception:
            pass
        raise

    # Check stderr for errors
    await process.wait()
    if process.returncode is not None and process.returncode != 0:
        err = await process.stderr.read()
        err_msg = err.decode("utf-8", errors="replace").strip() if err else ""
        if err_msg:
            yield f"data: {{\"type\": \"error\", \"message\": {json.dumps(err_msg)}}}\n\n"

    yield "data: {\"type\": \"done\", \"message\": \"Log stream ended\"}\n\n"


def diagnose_pod_health(deployment_name: str) -> Dict:
    """Gets detailed health info including restarts and current state reasons."""
    try:
        cmd = ["kubectl", "get", "pods", "-l", f"app={deployment_name}", "-o", "json"]
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout_bytes, _ = process.communicate(timeout=10)
        
        if process.returncode != 0:
            return {"healthy": False, "reason": "Failed to get pod"}
            
        pods_data = json.loads(stdout_bytes)
        if not pods_data.get("items"):
             return {"healthy": False, "reason": "Pod Not Found", "restart_count": 0}
             
        pod = pods_data["items"][0]
        status = pod.get("status", {})
        container_statuses = status.get("containerStatuses", [])
        
        restart_count = 0
        state = "Unknown"
        reason = "None"
        healthy = False
        
        if container_statuses:
            c_status = container_statuses[0]
            restart_count = c_status.get("restartCount", 0)
            state_dict = c_status.get("state", {})
            
            if "running" in state_dict:
                state = "Running"
                healthy = True
            elif "waiting" in state_dict:
                state = "Waiting"
                reason = state_dict["waiting"].get("reason", "Unknown")
            elif "terminated" in state_dict:
                state = "Terminated"
                reason = state_dict["terminated"].get("reason", "Unknown")
                
        # Phase fallback
        if state == "Unknown":
            state = status.get("phase", "Unknown")
            if state == "Running":
                healthy = True

        return {
            "healthy": healthy,
            "state": state,
            "reason": reason,
            "restart_count": restart_count,
            "pod_name": pod["metadata"]["name"],
            "pod_ip": status.get("podIP")
        }
    except Exception as e:
        return {"healthy": False, "reason": str(e), "restart_count": 0}