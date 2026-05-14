"""
port_forward_manager.py

Manages persistent kubectl port-forward processes per project.
On kind/Docker Desktop clusters, NodePort is not reachable on localhost,
so we start a port-forward subprocess per deployed service and keep it alive.

Usage:
    from app.utils.port_forward_manager import port_forward_manager

    # Start forwarding (called automatically after K8s deploy)
    result = await port_forward_manager.start(project_id, service_name, container_port, namespace)
    # → {"success": True, "local_port": 34501, "url": "http://localhost:34501"}

    # Stop forwarding (called on undeploy)
    port_forward_manager.stop(project_id)

    # Get current tunnel info
    info = port_forward_manager.get(project_id)
"""

import asyncio
import subprocess
import socket
import time
import threading
import sys
from typing import Dict, Optional

# ── helpers ─────────────────────────────────────────────────────────────────

def _find_free_port(start: int = 34000, end: int = 35999) -> int:
    """Find a free TCP port in the given range."""
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port found in range {start}-{end}")


def _safe_print(msg: str):
    try:
        print(msg)
        sys.stdout.flush()
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="replace").decode("ascii"))
        sys.stdout.flush()


# ── manager ──────────────────────────────────────────────────────────────────

class PortForwardManager:
    """
    Singleton that maps project_id → live port-forward subprocess.
    Each project gets a randomly assigned local port that stays stable
    as long as the backend is running.
    """

    def __init__(self):
        # project_id → { process, local_port, service_name, namespace, url }
        self._tunnels: Dict[str, Dict] = {}
        self._lock = threading.Lock()

    # ── public API ───────────────────────────────────────────────────────────

    def start(
        self,
        project_id: str,
        service_name: str,
        container_port: int,
        namespace: str = "default",
    ) -> Dict:
        """
        Start (or restart) a port-forward for a project.
        Returns { success, local_port, url }.
        """
        with self._lock:
            # Kill any stale tunnel for this project first
            self._kill(project_id)

            try:
                local_port = _find_free_port()

                cmd = [
                    "kubectl", "port-forward",
                    f"service/{service_name}",
                    f"{local_port}:{container_port}",
                    "-n", namespace,
                ]

                _safe_print(f"[PF] Starting port-forward: {service_name} -> localhost:{local_port}")

                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    # Keep running in background; don't create a new console window on Windows
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )

                # Give kubectl 2 s to confirm the tunnel is up
                time.sleep(2)

                if proc.poll() is not None:
                    err = proc.stderr.read().decode("utf-8", errors="replace").strip()
                    return {
                        "success": False,
                        "message": f"port-forward failed: {err}",
                        "local_port": None,
                        "url": None,
                    }

                url = f"http://localhost:{local_port}"
                self._tunnels[project_id] = {
                    "process": proc,
                    "local_port": local_port,
                    "service_name": service_name,
                    "namespace": namespace,
                    "container_port": container_port,
                    "url": url,
                    "started_at": time.time(),
                }

                # Start a watchdog thread that restarts on crash
                t = threading.Thread(
                    target=self._watchdog,
                    args=(project_id,),
                    daemon=True,
                )
                t.start()

                _safe_print(f"[PF-OK] Tunnel active: {url}")
                return {
                    "success": True,
                    "local_port": local_port,
                    "url": url,
                }

            except Exception as e:
                _safe_print(f"[PF-ERROR] {e}")
                return {
                    "success": False,
                    "message": str(e),
                    "local_port": None,
                    "url": None,
                }

    def stop(self, project_id: str) -> None:
        """Stop the port-forward for a project (called on undeploy)."""
        with self._lock:
            self._kill(project_id)

    def get(self, project_id: str) -> Optional[Dict]:
        """Return tunnel info dict or None if not active."""
        entry = self._tunnels.get(project_id)
        if not entry:
            return None
        proc = entry["process"]
        if proc.poll() is not None:
            # Process has died — clean up
            with self._lock:
                self._tunnels.pop(project_id, None)
            return None
        return {
            "active": True,
            "local_port": entry["local_port"],
            "url": entry["url"],
            "service_name": entry["service_name"],
            "namespace": entry["namespace"],
        }

    def get_url(self, project_id: str) -> Optional[str]:
        info = self.get(project_id)
        return info["url"] if info else None

    def all_active(self) -> Dict[str, str]:
        """Return {project_id: url} for all live tunnels."""
        result = {}
        for pid, entry in list(self._tunnels.items()):
            if entry["process"].poll() is None:
                result[pid] = entry["url"]
        return result

    # ── internals ────────────────────────────────────────────────────────────

    def _kill(self, project_id: str) -> None:
        """Terminate the port-forward process. Must be called under self._lock."""
        entry = self._tunnels.pop(project_id, None)
        if entry:
            proc = entry["process"]
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            _safe_print(f"[PF] Stopped tunnel for project {project_id}")

    def _watchdog(self, project_id: str) -> None:
        """
        Runs in a daemon thread.  If the kubectl process exits unexpectedly,
        restart it using the same service/port metadata.
        """
        while True:
            time.sleep(5)
            with self._lock:
                entry = self._tunnels.get(project_id)
                if not entry:
                    return  # Project was undeployed; exit watchdog

                proc = entry["process"]
                if proc.poll() is None:
                    continue  # Still running

                # Process died — restart
                _safe_print(f"[PF-WATCH] Tunnel for {project_id} crashed — restarting...")
                service_name = entry["service_name"]
                container_port = entry["container_port"]
                namespace = entry["namespace"]
                local_port = entry["local_port"]

            # Release lock before blocking call
            try:
                new_proc = subprocess.Popen(
                    [
                        "kubectl", "port-forward",
                        f"service/{service_name}",
                        f"{local_port}:{container_port}",
                        "-n", namespace,
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )
                time.sleep(2)

                with self._lock:
                    if project_id not in self._tunnels:
                        new_proc.terminate()
                        return  # Was removed while restarting
                    self._tunnels[project_id]["process"] = new_proc
                    _safe_print(f"[PF-OK] Tunnel restarted for {project_id}")
            except Exception as e:
                _safe_print(f"[PF-ERROR] Watchdog restart failed: {e}")
                time.sleep(10)  # back-off before next attempt


# ── singleton ────────────────────────────────────────────────────────────────
port_forward_manager = PortForwardManager()
