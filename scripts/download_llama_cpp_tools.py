import os
import io
import sys
import zipfile
import urllib.request
import json
import shutil

REPO = "ggerganov/llama.cpp"

# Resolve target directory:
#   1. Explicit env var LLAMA_CPP_TOOLS_DIR (if set)
#   2. Repo-local default: <repo_root>/llama.cpp
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_SCRIPT_DIR)
TARGET_DIR = os.environ.get("LLAMA_CPP_TOOLS_DIR", os.path.join(_REPO_ROOT, "llama.cpp"))

def get_latest_release_url():
    url = f"https://api.github.com/repos/{REPO}/releases/latest"
    print(f"Fetching latest release from {url}...")
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode())
        
    # Prefer Vulkan as it's highly portable and hardware accelerated
    for asset in data.get("assets", []):
        if "bin-win-vulkan-x64.zip" in asset["name"]:
            return asset["browser_download_url"]
    
    # Fallback to AVX2 CPU version
    for asset in data.get("assets", []):
        if "bin-win-avx2-x64.zip" in asset["name"]:
            return asset["browser_download_url"]
            
    return None

def download_and_extract(url, target_dir):
    print(f"Downloading tool binaries from {url}...")
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response:
        content = response.read()
        
    print(f"Extracting to {target_dir}...")
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        for zip_info in z.infolist():
            # We don't want directories, just the flat files
            if zip_info.is_dir():
                continue
            # Extract .exe, .dll files required
            if zip_info.filename.endswith(".exe") or zip_info.filename.endswith(".dll"):
                filename = os.path.basename(zip_info.filename)
                source = z.open(zip_info.filename)
                target = open(os.path.join(target_dir, filename), "wb")
                with source, target:
                    shutil.copyfileobj(source, target)
                print(f"Extracted {filename}")

def download_convert_script(target_dir):
    # Download convert_hf_to_gguf.py
    url = f"https://raw.githubusercontent.com/{REPO}/master/convert_hf_to_gguf.py"
    print(f"Downloading {url}...")
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response:
        content = response.read().decode('utf-8')
        
    with open(os.path.join(target_dir, "convert_hf_to_gguf.py"), "w", encoding="utf-8") as f:
        f.write(content)
    print("Downloaded convert_hf_to_gguf.py")
    
    # Download convert_llama_ggml_to_gguf.py as well just in case
    url2 = f"https://raw.githubusercontent.com/{REPO}/master/convert_llama_ggml_to_gguf.py"
    try:
        req2 = urllib.request.Request(url2, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req2) as response:
            content2 = response.read().decode('utf-8')
        with open(os.path.join(target_dir, "convert_llama_ggml_to_gguf.py"), "w", encoding="utf-8") as f:
            f.write(content2)
        print("Downloaded convert_llama_ggml_to_gguf.py")
    except Exception as e:
        print(f"Could not download secondary script: {e}")

if __name__ == "__main__":
    try:
        os.makedirs(TARGET_DIR, exist_ok=True)
        print(f"llama.cpp tools target directory: {TARGET_DIR}")
    except OSError as e:
        print(f"[WARN] Could not create target directory '{TARGET_DIR}': {e}")
        print("[WARN] Skipping llama.cpp tools download.")
        print("[WARN] Set LLAMA_CPP_TOOLS_DIR to a writable path and re-run, or use Docker.")
        sys.exit(0)

    try:
        dl_url = get_latest_release_url()
    except Exception as e:
        print(f"[WARN] Could not fetch llama.cpp release info: {e}")
        print("[WARN] Skipping llama.cpp tools download. Check your internet connection.")
        sys.exit(0)

    if not dl_url:
        print("[WARN] Could not find a suitable release zip in the latest llama.cpp release.")
        print("[WARN] Skipping llama.cpp tools download.")
        sys.exit(0)

    try:
        download_and_extract(dl_url, TARGET_DIR)
    except Exception as e:
        print(f"[WARN] Failed to download/extract llama.cpp binaries: {e}")
        print("[WARN] GGUF conversion features will be unavailable until tools are downloaded.")
        sys.exit(0)

    try:
        download_convert_script(TARGET_DIR)
    except Exception as e:
        print(f"[WARN] Failed to download conversion scripts: {e}")

    print(f"All llama.cpp tools successfully downloaded and extracted to: {TARGET_DIR}")
