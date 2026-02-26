import os
import subprocess
from typing import Dict, Any

def get_vitis_compiler_status() -> Dict[str, Any]:
    """Check if AMD Vitis AI compiler (Vai_c) is available."""
    # Depends on specifically the Vitis docker container or local install
    status = {"available": False, "version": None, "error": "vai_c command not found"}
    try:
        r = subprocess.run(["vai_c_xir", "--version"], capture_output=True, text=True, timeout=5.0)
        if r.returncode == 0:
            status = {"available": True, "version": r.stdout.strip(), "error": None}
    except FileNotFoundError:
        pass
    except Exception as e:
        status["error"] = str(e)
    return status

def compile_vitis_dpu(model_path: str, arch: str, output_dir: str, net_name: str) -> Dict[str, Any]:
    """Compile a quantized model (.xmodel) for a specific Vitis DPU architecture."""
    status = get_vitis_compiler_status()
    if not status["available"]:
        return {"success": False, "error": "Vitis AI Compiler (vai_c_xir) is not installed in the current environment."}

    os.makedirs(output_dir, exist_ok=True)
    
    cmd = [
        "vai_c_xir",
        "-x", model_path,
        "-a", arch,
        "-o", output_dir,
        "-n", net_name
    ]
    
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return {
            "success": True, 
            "output_model": os.path.join(output_dir, f"{net_name}.xmodel"),
            "logs": r.stdout
        }
    except subprocess.CalledProcessError as e:
        return {"success": False, "error": e.stderr}
    except Exception as e:
        return {"success": False, "error": str(e)}
