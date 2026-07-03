"""Patch hermes-webui server.py CSP to allow framing from NPU-STACK."""
server = r"J:\NPU-STACK\hermes-webui\server.py"
with open(server, "r", encoding="utf-8") as f:
    content = f.read()

# Replace the CSP frame-ancestors directive
content = content.replace(
    '"frame-ancestors \'self\';"',
    '"frame-ancestors http://localhost:5180 http://127.0.0.1:5180 http://127.0.0.1:8010;"'
)

with open(server, "w", encoding="utf-8", newline="") as f:
    f.write(content)

print("Patched CSP frame-ancestors")
