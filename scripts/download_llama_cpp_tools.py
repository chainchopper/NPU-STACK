import os
import io
import zipfile
import urllib.request
import json
import shutil

REPO = "ggerganov/llama.cpp"
TARGET_DIR = r"J:\NPU-STACK\llama.cpp"

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
    os.makedirs(TARGET_DIR, exist_ok=True)
    
    dl_url = get_latest_release_url()
    if not dl_url:
        print("Could not find a suitable release zip.")
        exit(1)
        
    download_and_extract(dl_url, TARGET_DIR)
    download_convert_script(TARGET_DIR)
    print("All llama.cpp tools successfully downloaded and extracted to J:\\NPU-STACK\\llama.cpp!")
