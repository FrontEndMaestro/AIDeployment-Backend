"""
monitor_service.py — Production-grade Kubernetes monitoring.

Key fixes vs old version:
 - Pod discovery uses ALL namespace labels, not just app=<deployment_name>
 - Events fetched namespace-wide then filtered for relevance
 - Deployment status parsed from kubectl JSON (replicas/readyReplicas)
 - Rollout health includes CrashLoopBackOff / ImagePullBackOff / Pending detection
 - Resource metrics via kubectl top (graceful if metrics-server absent)
 - Cluster overview: nodes, namespaces, deployments, services
"""
import json
import os
import re
import subprocess
import time
from datetime import datetime
from typing import Any, Dict, List, Optional


# ── small helpers ─────────────────────────────────────────────────────────────

def _run(cmd: List[str], timeout: int = 15) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )


def _json(proc: subprocess.CompletedProcess) -> Optional[Dict]:
    try:
        return json.loads(proc.stdout.decode("utf-8", errors="replace"))
    except Exception:
        return None


def _sanitize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9\-]", "-", name.lower()).strip("-")


# ── pod status parsing ────────────────────────────────────────────────────────

def _parse_pod(item: Dict) -> Dict[str, Any]:
    meta = item.get("metadata") or {}
    spec = item.get("spec") or {}
    status = item.get("status") or {}
    container_statuses = status.get("containerStatuses") or []
    init_statuses = status.get("initContainerStatuses") or []

    phase = status.get("phase", "Unknown")
    ready = False
    restarts = 0
    state_str = phase
    waiting_reason = ""

    if container_statuses:
        cs = container_statuses[0]
        ready = cs.get("ready", False)
        restarts = cs.get("restartCount", 0)
        sd = cs.get("state") or {}
        if "running" in sd:
            state_str = "Running"
        elif "waiting" in sd:
            reason = sd["waiting"].get("reason", "")
            state_str = f"Waiting ({reason})" if reason else "Waiting"
            waiting_reason = reason
        elif "terminated" in sd:
            reason = sd["terminated"].get("reason", "")
            exit_code = sd["terminated"].get("exitCode", 0)
            state_str = f"Terminated ({reason})" if reason else "Terminated"

    # Accumulate restarts across ALL containers
    total_restarts = sum(
        c.get("restartCount", 0) for c in container_statuses + init_statuses
    )

    # Conditions
    conditions = {c.get("type"): c.get("status") for c in (status.get("conditions") or [])}
    node_name = spec.get("nodeName", "")

    return {
        "name": meta.get("name", ""),
        "namespace": meta.get("namespace", "default"),
        "status": state_str,
        "phase": phase,
        "ready": ready,
        "restart_count": total_restarts,
        "pod_ip": status.get("podIP", ""),
        "node": node_name,
        "labels": meta.get("labels") or {},
        "created_at": meta.get("creationTimestamp", ""),
        "waiting_reason": waiting_reason,
        "conditions": conditions,
        "containers": [c.get("name") for c in (item.get("spec") or {}).get("containers") or []],
    }


def _classify_deployment_health(dep: Dict, pods: List[Dict]) -> str:
    """Return HEALTHY | DEGRADED | FAILED | SCALING | RECOVERING | PENDING"""
    status = dep.get("status") or {}
    replicas = status.get("replicas", 0) or 0
    ready = status.get("readyReplicas", 0) or 0
    available = status.get("availableReplicas", 0) or 0

    crash_pods = [p for p in pods if "crashloop" in p.get("waiting_reason", "").lower()]
    pull_pods = [p for p in pods if "imagepull" in p.get("waiting_reason", "").lower()
                 or "errimagepull" in p.get("waiting_reason", "").lower()]
    pending_pods = [p for p in pods if p.get("phase") == "Pending"]

    if pull_pods:
        return "FAILED"
    if crash_pods:
        return "FAILED"
    if replicas == 0:
        return "PENDING"
    if ready == replicas:
        return "HEALTHY"
    if ready == 0 and pending_pods:
        return "PENDING"
    if ready < replicas and available > 0:
        return "DEGRADED"
    if ready == 0:
        return "RECOVERING"
    return "SCALING"


# ── MonitorService ────────────────────────────────────────────────────────────

class MonitorService:

    # ── cluster overview ──────────────────────────────────────────────────────

    @staticmethod
    def get_cluster_overview() -> Dict[str, Any]:
        overview: Dict[str, Any] = {
            "reachable": False,
            "nodes": [],
            "namespaces": [],
            "total_deployments": 0,
            "total_services": 0,
            "total_pods": 0,
            "running_pods": 0,
            "failed_pods": 0,
        }
        try:
            # nodes
            proc = _run(["kubectl", "get", "nodes", "-o", "json"])
            if proc.returncode == 0:
                data = _json(proc) or {}
                for n in data.get("items") or []:
                    meta = n.get("metadata") or {}
                    conds = {c["type"]: c["status"] for c in (n.get("status") or {}).get("conditions") or []}
                    overview["nodes"].append({
                        "name": meta.get("name", ""),
                        "ready": conds.get("Ready") == "True",
                        "roles": [
                            k.replace("node-role.kubernetes.io/", "")
                            for k in (meta.get("labels") or {})
                            if k.startswith("node-role.kubernetes.io/")
                        ],
                    })
                overview["reachable"] = True

            # namespaces
            proc = _run(["kubectl", "get", "namespaces", "-o", "jsonpath={.items[*].metadata.name}"])
            if proc.returncode == 0:
                overview["namespaces"] = proc.stdout.decode("utf-8", errors="replace").split()

            # deployments count
            proc = _run(["kubectl", "get", "deployments", "--all-namespaces", "--no-headers"])
            if proc.returncode == 0:
                lines = [l for l in proc.stdout.decode("utf-8", errors="replace").splitlines() if l.strip()]
                overview["total_deployments"] = len(lines)

            # services count
            proc = _run(["kubectl", "get", "services", "--all-namespaces", "--no-headers"])
            if proc.returncode == 0:
                lines = [l for l in proc.stdout.decode("utf-8", errors="replace").splitlines() if l.strip()]
                overview["total_services"] = len(lines)

            # pods
            pods = MonitorService.get_all_pods_status()
            overview["total_pods"] = len(pods)
            overview["running_pods"] = sum(1 for p in pods if "running" in p.get("status", "").lower())
            overview["failed_pods"] = sum(
                1 for p in pods
                if any(k in p.get("status", "").lower() for k in ("crashloop", "error", "failed", "imagepull"))
            )
        except Exception as e:
            overview["error"] = str(e)
        return overview

    # ── deployment detail ─────────────────────────────────────────────────────

    @staticmethod
    def get_deployment_detail(deployment_name: str, namespace: str = "default") -> Dict[str, Any]:
        """Full deployment status including health classification."""
        result: Dict[str, Any] = {
            "found": False,
            "name": deployment_name,
            "namespace": namespace,
            "health": "UNKNOWN",
            "replicas": 0,
            "ready_replicas": 0,
            "available_replicas": 0,
            "pods": [],
        }
        try:
            proc = _run(["kubectl", "get", "deployment", deployment_name, "-n", namespace, "-o", "json"])
            if proc.returncode != 0:
                # Try all namespaces
                proc2 = _run(["kubectl", "get", "deployment", deployment_name, "--all-namespaces", "-o", "json"])
                if proc2.returncode != 0:
                    return result
                data = _json(proc2) or {}
            else:
                data = _json(proc) or {}

            result["found"] = True
            dep_status = data.get("status") or {}
            result["replicas"] = dep_status.get("replicas", 0) or 0
            result["ready_replicas"] = dep_status.get("readyReplicas", 0) or 0
            result["available_replicas"] = dep_status.get("availableReplicas", 0) or 0

            # Get pods for this deployment (match by label selector from spec)
            spec = data.get("spec") or {}
            match_labels = (spec.get("selector") or {}).get("matchLabels") or {}
            if match_labels:
                label_sel = ",".join(f"{k}={v}" for k, v in match_labels.items())
                pods = MonitorService.get_pods_by_selector(label_sel, namespace)
            else:
                pods = MonitorService.get_pods_by_name_prefix(deployment_name, namespace)

            result["pods"] = pods
            result["health"] = _classify_deployment_health(data, pods)

            # Conditions
            result["conditions"] = [
                {
                    "type": c.get("type"),
                    "status": c.get("status"),
                    "reason": c.get("reason"),
                    "message": c.get("message"),
                }
                for c in dep_status.get("conditions") or []
            ]
        except Exception as e:
            result["error"] = str(e)
        return result

    # ── pod discovery ─────────────────────────────────────────────────────────

    @staticmethod
    def get_pods_by_selector(label_selector: str, namespace: str = "default") -> List[Dict]:
        pods = []
        try:
            proc = _run(["kubectl", "get", "pods", "-n", namespace, "-l", label_selector, "-o", "json"])
            if proc.returncode == 0:
                data = _json(proc) or {}
                pods = [_parse_pod(item) for item in (data.get("items") or [])]
        except Exception:
            pass
        return pods

    @staticmethod
    def get_pods_by_name_prefix(prefix: str, namespace: str = "default") -> List[Dict]:
        """Find pods whose name starts with the given prefix."""
        all_pods = MonitorService.get_all_pods_status(namespace)
        return [p for p in all_pods if p["name"].startswith(prefix)]

    @staticmethod
    def get_all_pods_status(namespace: str = "default") -> List[Dict[str, Any]]:
        pods: List[Dict[str, Any]] = []
        try:
            cmd = ["kubectl", "get", "pods", "-n", namespace, "-o", "json"]
            proc = _run(cmd)
            if proc.returncode == 0:
                data = _json(proc) or {}
                pods = [_parse_pod(item) for item in (data.get("items") or [])]
        except Exception as e:
            pods.append({"name": "error", "status": f"Error: {e}", "ready": False, "restart_count": 0})
        return pods

    # ── k8s health (for monitor_controller compatibility) ────────────────────

    @staticmethod
    def get_k8s_health(deployment_name: str, namespace: str = "default") -> Dict[str, Any]:
        """
        Returns pod-level health for the first pod matching the deployment.
        Falls back to name-prefix search if label selector not found.
        """
        # Try exact deployment lookup first
        detail = MonitorService.get_deployment_detail(deployment_name, namespace)
        pods = detail.get("pods") or []

        if not pods:
            # fallback: name prefix
            pods = MonitorService.get_pods_by_name_prefix(deployment_name, namespace)

        if not pods:
            return {
                "healthy": False,
                "state": "Not Found",
                "reason": "No pods matched",
                "restart_count": 0,
                "pod_name": None,
                "deployment_found": detail.get("found", False),
            }

        pod = pods[0]
        state = pod.get("status", "Unknown")
        healthy = pod.get("ready", False) and "running" in state.lower()

        return {
            "healthy": healthy,
            "state": state,
            "reason": pod.get("waiting_reason") or pod.get("status", ""),
            "restart_count": pod.get("restart_count", 0),
            "pod_name": pod.get("name"),
            "pod_ip": pod.get("pod_ip"),
            "deployment_found": detail.get("found", False),
            "replicas": detail.get("replicas", 0),
            "ready_replicas": detail.get("ready_replicas", 0),
            "health": detail.get("health", "UNKNOWN"),
        }

    # ── AWS health (unchanged) ─────────────────────────────────────────────

    @staticmethod
    def get_aws_health(project_id: str) -> Dict[str, Any]:
        tf_dir = os.path.join("terraform", project_id)
        if not os.path.exists(os.path.join(tf_dir, "terraform.tfstate")):
            return {"status": "not_deployed", "healthy": False}
        try:
            proc = subprocess.run(
                ["terraform", "output", "-json"],
                cwd=tf_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10,
            )
            if proc.returncode == 0:
                return {"status": "deployed", "healthy": True, "details": "Terraform state exists"}
            return {"status": "unknown", "healthy": False, "details": "Could not read outputs"}
        except Exception as e:
            return {"status": "error", "healthy": False, "details": str(e)}

    # ── events ────────────────────────────────────────────────────────────────

    @staticmethod
    def get_recent_k8s_events(deployment_name: str, namespace: str = "default", limit: int = 50) -> List[Dict]:
        """
        Fetches ALL namespace events sorted by time, then filters for relevance
        to the deployment (by name prefix match on involvedObject.name).
        Falls back to unfiltered if no matches found.
        """
        events: List[Dict[str, Any]] = []
        try:
            # All events in namespace sorted by time
            cmd = [
                "kubectl", "get", "events",
                "-n", namespace,
                "--sort-by=.lastTimestamp",
                "-o", "json",
            ]
            proc = _run(cmd, timeout=20)
            if proc.returncode == 0:
                data = _json(proc) or {}
                items = data.get("items") or []

                # Filter: items related to this deployment or its pods
                related = [
                    item for item in items
                    if deployment_name in (item.get("involvedObject") or {}).get("name", "")
                ]
                # If no matches, return all (user can see cluster events)
                source_items = related if related else items

                for item in source_items[-limit:]:
                    obj = item.get("involvedObject") or {}
                    events.append({
                        "type": item.get("type", "Normal"),
                        "reason": item.get("reason", ""),
                        "message": item.get("message", ""),
                        "timestamp": item.get("lastTimestamp") or item.get("firstTimestamp") or "",
                        "count": item.get("count", 1),
                        "object_kind": obj.get("kind", ""),
                        "object_name": obj.get("name", ""),
                    })
        except Exception as e:
            events.append({
                "type": "Warning",
                "reason": "MonitorError",
                "message": f"Could not fetch k8s events: {e}",
                "timestamp": datetime.utcnow().isoformat(),
                "count": 1,
                "object_kind": "",
                "object_name": "",
            })
        return events

    # ── rollout status ─────────────────────────────────────────────────────────

    @staticmethod
    def get_rollout_status(deployment_name: str, namespace: str = "default", timeout_s: int = 120) -> Dict[str, Any]:
        """Stream rollout status for up to timeout_s seconds."""
        try:
            proc = _run(
                ["kubectl", "rollout", "status", f"deployment/{deployment_name}",
                 "-n", namespace, f"--timeout={timeout_s}s"],
                timeout=timeout_s + 5,
            )
            out = proc.stdout.decode("utf-8", errors="replace").strip()
            err = proc.stderr.decode("utf-8", errors="replace").strip()
            success = proc.returncode == 0
            return {
                "success": success,
                "output": out,
                "error": err,
                "deployment_name": deployment_name,
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "output": "",
                "error": f"Rollout status timed out after {timeout_s}s",
                "deployment_name": deployment_name,
            }
        except Exception as e:
            return {"success": False, "output": "", "error": str(e), "deployment_name": deployment_name}

    # ── pod logs ─────────────────────────────────────────────────────────────

    @staticmethod
    def get_pod_logs(
        deployment_name: str,
        namespace: str = "default",
        tail_lines: int = 100,
        container: Optional[str] = None,
    ) -> List[str]:
        """Snapshot of recent pod logs. Tries label selector first, then name prefix."""
        lines: List[str] = []
        try:
            # Discover pod
            detail = MonitorService.get_deployment_detail(deployment_name, namespace)
            pods = detail.get("pods") or []
            if not pods:
                pods = MonitorService.get_pods_by_name_prefix(deployment_name, namespace)
            if not pods:
                return [f"No pod found for deployment '{deployment_name}'"]

            # Pick first Running pod, else first pod
            running = [p for p in pods if "running" in p.get("status", "").lower()]
            pod = (running or pods)[0]
            pod_name = pod["name"]

            log_cmd = ["kubectl", "logs", pod_name, "-n", namespace,
                       f"--tail={tail_lines}", "--timestamps=true"]
            if container:
                log_cmd += ["-c", container]

            proc = _run(log_cmd, timeout=30)
            if proc.returncode == 0:
                lines = proc.stdout.decode("utf-8", errors="replace").splitlines()
            else:
                err = proc.stderr.decode("utf-8", errors="replace").strip()
                lines = [f"[kubectl logs error] {err}"]
        except subprocess.TimeoutExpired:
            lines = ["[kubectl logs] timed out"]
        except Exception as e:
            lines = [f"[pod log error] {e}"]
        return lines

    # ── resource metrics ──────────────────────────────────────────────────────

    @staticmethod
    def get_resource_metrics(namespace: str = "default") -> Dict[str, Any]:
        """kubectl top pods/nodes — requires metrics-server. Graceful if absent."""
        result: Dict[str, Any] = {"pods": [], "nodes": [], "metrics_server_available": False}
        try:
            proc = _run(["kubectl", "top", "pods", "-n", namespace, "--no-headers"], timeout=20)
            if proc.returncode == 0:
                result["metrics_server_available"] = True
                for line in proc.stdout.decode("utf-8", errors="replace").splitlines():
                    parts = line.split()
                    if len(parts) >= 3:
                        result["pods"].append({"name": parts[0], "cpu": parts[1], "memory": parts[2]})

            proc = _run(["kubectl", "top", "nodes", "--no-headers"], timeout=20)
            if proc.returncode == 0:
                for line in proc.stdout.decode("utf-8", errors="replace").splitlines():
                    parts = line.split()
                    if len(parts) >= 5:
                        result["nodes"].append({
                            "name": parts[0], "cpu": parts[1],
                            "cpu_pct": parts[2], "memory": parts[3], "memory_pct": parts[4],
                        })
        except Exception as e:
            result["error"] = str(e)
        return result

    # ── self healing ─────────────────────────────────────────────────────────

    @staticmethod
    def trigger_self_healing(deployment_name: str, namespace: str = "default") -> Dict[str, Any]:
        try:
            cmd = ["kubectl", "rollout", "restart",
                   f"deployment/{deployment_name}", "-n", namespace]
            proc = subprocess.run(cmd, capture_output=True, timeout=30)
            if proc.returncode == 0:
                return {"success": True, "message": f"Restarted {deployment_name}"}
            err = proc.stderr.decode("utf-8", errors="replace")
            return {"success": False, "message": f"Restart failed: {err}"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ── services ─────────────────────────────────────────────────────────────

    @staticmethod
    def get_services(namespace: str = "default") -> List[Dict[str, Any]]:
        services: List[Dict[str, Any]] = []
        try:
            proc = _run(["kubectl", "get", "services", "-n", namespace, "-o", "json"])
            if proc.returncode == 0:
                data = _json(proc) or {}
                for svc in (data.get("items") or []):
                    meta = svc.get("metadata") or {}
                    spec = svc.get("spec") or {}
                    services.append({
                        "name": meta.get("name", ""),
                        "type": spec.get("type", ""),
                        "cluster_ip": spec.get("clusterIP", ""),
                        "external_ip": (spec.get("externalIPs") or [""])[0],
                        "ports": [
                            f"{p.get('port')}/{p.get('protocol','TCP')}"
                            + (f":{p['nodePort']}" if p.get("nodePort") else "")
                            for p in (spec.get("ports") or [])
                        ],
                        "selector": spec.get("selector") or {},
                    })
        except Exception as e:
            services.append({"name": "error", "error": str(e)})
        return services


monitor_service = MonitorService()
