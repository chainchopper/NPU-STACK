# XiaoZhi server — config directory

The main server mounts this directory as `/workspace/config` and reads
`config.yaml` / `config.json` / `mqtt_config.json` from it.

**Do not hand-write these** — use the web console's configuration wizard
(`http://<host>:8080`) to set VAD/ASR/LLM/TTS engines against **our own
providers** (DeepSeek, Ollama, OpenAI-compatible endpoints, etc.). The wizard
writes the files here; restart the `main-server` container afterwards.

This keeps setup + auth entirely in-org — the server never reaches
`xiaozhi.me` / `tenclass.net`.
