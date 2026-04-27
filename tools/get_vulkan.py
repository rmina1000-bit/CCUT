import urllib.request
import json
import zipfile
import os
import sys

req = urllib.request.Request("https://api.github.com/repos/ggml-org/llama.cpp/releases")
try:
    with urllib.request.urlopen(req) as response:
        releases = json.loads(response.read().decode())
except Exception as e:
    print("API Error:", e)
    sys.exit(1)

target_url = None
for rel in releases:
    for asset in rel.get('assets', []):
        name = asset['name']
        if 'bin-win-vulkan-x64.zip' in name:
            target_url = asset['browser_download_url']
            break
    if target_url:
        break

if not target_url:
    print("Could not find vulkan release!")
    sys.exit(1)

print("Downloading:", target_url)
os.makedirs("llama.cpp-vulkan", exist_ok=True)
zip_path = "llama.cpp-vulkan/vulkan.zip"

urllib.request.urlretrieve(target_url, zip_path)
print("Extracting...")
with zipfile.ZipFile(zip_path, 'r') as zip_ref:
    zip_ref.extractall("llama.cpp-vulkan")

print("Done. Removing zip.")
os.remove(zip_path)
