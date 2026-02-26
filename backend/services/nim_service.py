import os
import subprocess
import json
import httpx
from typing import Dict, Any, List

# Try to get API key from environment
NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "")
NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"

def get_nim_status() -> Dict[str, Any]:
    """Check NVIDIA NIM API status and local container availability."""
    
    # 1. Check Cloud API Access
    cloud_status = {"available": False, "error": "NVIDIA_API_KEY not set"}
    if NVIDIA_API_KEY:
        try:
            # Simple check by trying to hit models endpoint
            r = httpx.get(f"{NIM_BASE_URL}/models", headers={"Authorization": f"Bearer {NVIDIA_API_KEY}"}, timeout=5.0)
            if r.status_code == 200:
                cloud_status = {"available": True, "status": "Connected"}
            else:
                cloud_status = {"available": False, "error": f"API Error HTTP {r.status_code}"}
        except Exception as e:
            cloud_status = {"available": False, "error": str(e)}

    # 2. Check local Docker availability for NIM containers
    local_status = {"available": False, "containers": []}
    try:
        r = subprocess.run(["docker", "ps", "--format", "{{json .}}"], capture_output=True, text=True, check=True)
        containers = []
        for line in r.stdout.strip().split("\n"):
            if not line:
                continue
            container = json.loads(line)
            # Detect NVIDIA NIM containers (typically start with nvcr.io/nim/)
            if "nvcr.io/nim" in container.get("Image", ""):
                containers.append({
                    "id": container.get("ID"),
                    "name": container.get("Names"),
                    "image": container.get("Image"),
                    "status": container.get("Status"),
                    "ports": container.get("Ports")
                })
        
        local_status = {"available": True, "containers": containers}
    except Exception as e:
        local_status = {"available": False, "error": "Docker not running or not installed"}

    return {
        "cloud_api": cloud_status,
        "local_containers": local_status
    }

async def fetch_cloud_models() -> List[Dict[str, Any]]:
    """Fetch available models from NVIDIA NIM Cloud API."""
    if not NVIDIA_API_KEY:
        return []
    
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{NIM_BASE_URL}/models", 
                headers={"Authorization": f"Bearer {NVIDIA_API_KEY}"}
            )
            r.raise_for_status()
            data = r.json()
            return data.get("data", [])
    except Exception as e:
        print(f"Error fetching NIM cache: {e}")
        return []

def start_local_nim(image: str, port: int = 8000, gpus: str = "all") -> Dict[str, Any]:
    """Start a local NVIDIA NIM container."""
    if not NVIDIA_API_KEY:
        return {"success": False, "error": "NGC_API_KEY (NVIDIA_API_KEY) required to pull NIMs"}

    try:
        cmd = [
            "docker", "run", "-d", "--rm", 
            "--name", f"nim-{image.split('/')[-1].split(':')[0]}",
            "--runtime=nvidia",
            f"--gpus={gpus}",
            "-e", f"NGC_API_KEY={NVIDIA_API_KEY}",
            "-p", f"{port}:8000",
            image
        ]
        
        r = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return {"success": True, "container_id": r.stdout.strip()}
    except subprocess.CalledProcessError as e:
        return {"success": False, "error": e.stderr}
    except Exception as e:
        return {"success": False, "error": str(e)}

def stop_local_nim(container_id_or_name: str) -> Dict[str, Any]:
    """Stop a local NIM container."""
    try:
        subprocess.run(["docker", "stop", container_id_or_name], capture_output=True, text=True, check=True)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

