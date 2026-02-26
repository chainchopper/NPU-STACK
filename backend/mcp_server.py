"""
NPU-STACK MCP Server (Model Context Protocol).
Exposes NPU-STACK functionalities (Hardware detection, Conversion, etc.) to LLMs via FastMCP.
"""

import sys
import os
import subprocess
from mcp.server.fastmcp import FastMCP

# Ensure the backend directory is in the path so we can import services
sys.path.insert(0, os.path.dirname(__file__))

from services.benchmark_service import get_system_info
from services.cross_converter import get_conversion_paths

# Create FastMCP server
mcp = FastMCP("NPU-STACK MCP Server", json_response=True)


@mcp.tool()
def detect_hardware() -> dict:
    """
    Detect system hardware capabilities relevant to AI acceleration.
    Returns info on CPU, NVIDIA GPU, OpenVINO (Intel NPU), and general system stats.
    """
    return get_system_info()


@mcp.tool()
def list_conversion_paths() -> dict:
    """
    List all supported neural network model conversion paths.
    Shows the available source formats and target accelerator formats.
    """
    return get_conversion_paths()


@mcp.tool()
def start_fastapi_backend() -> str:
    """
    Start the main NPU-STACK FastAPI backend process in the background.
    """
    try:
        # Launching the backend process
        backend_dir = os.path.dirname(__file__)
        subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"],
            cwd=backend_dir
        )
        return "Successfully launched NPU-STACK FastAPI backend on http://0.0.0.0:8000"
    except Exception as e:
        return f"Failed to start backend: {str(e)}"

# A dynamic greeting resource (optional, just to show how resources work)
@mcp.resource("info://welcome")
def get_welcome_info() -> str:
    """Get welcome info about NPU-STACK."""
    return (
        "Welcome to NPU-STACK MCP Server! "
        "You can use this server to detect hardware, "
        "compile edge models, and launch the NPU-STACK AI Factory."
    )


if __name__ == "__main__":
    # Launch the stdio transport by default (standard for Claude Desktop)
    mcp.run(transport="stdio")
