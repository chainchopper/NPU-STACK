from fastapi import APIRouter, HTTPException
from typing import Dict, Any
from pydantic import BaseModel

from services.vitis_compiler import get_vitis_compiler_status, compile_vitis_dpu

router = APIRouter(prefix="/api/vitis", tags=["Vitis Compilation"])

class VitisCompileRequest(BaseModel):
    model_path: str
    arch: str
    output_dir: str
    net_name: str

@router.get("/status")
def vitis_status() -> Dict[str, Any]:
    """Get status of Vitis AI Compiler."""
    return get_vitis_compiler_status()

@router.post("/compile")
def compile_model(req: VitisCompileRequest):
    """Compile a model to Xilinx DPU format."""
    res = compile_vitis_dpu(req.model_path, req.arch, req.output_dir, req.net_name)
    if not res["success"]:
        raise HTTPException(status_code=400, detail=res.get("error"))
    return res
