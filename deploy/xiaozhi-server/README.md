# Self-hosted XiaoZhi server (branded — Nirvana / NPU-STACK)

Golang backend for xiaozhi-esp32 devices (`hackers365/xiaozhi-esp32-server-golang`),
running entirely on our network. Devices point at **our** endpoint, never the
official `xiaozhi.me` cloud.

## Quick start

```powershell
cd deploy/xiaozhi-server
Copy-Item .env.example .env     # then edit MYSQL_PASSWORD
docker compose up -d
docker compose ps
```

## Endpoints (after start)

| Service | URL |
|---------|-----|
| Manager web console | http://localhost:8080 |
| Manager API | http://localhost:8081 |
| WebSocket voice | ws://localhost:8989 |
| MQTT | localhost:2882 (broker :2883 in-container) |
| UDP audio | localhost:8888/udp |
| MySQL | localhost:23306 |

## Configure engines (branding)

1. Open http://localhost:8080.
2. Use the config wizard to point VAD / ASR / LLM / TTS at our providers
   (DeepSeek, Ollama, OpenAI-compatible endpoints — **no tenclass.net**).
3. Restart `main-server` after changes.

## Point devices at us

In the xiaozhi firmware (or our Nirvana OS / MicroPython client), set the
WebSocket URL to `ws://<host>:8989` (or MQTT to `<host>:2882`) instead of the
official server. Firmware branding = our URLs + our OTA channel.

## Notes

- Image tags: `XIAOZHI_TAG` in `.env` (default `0.6.4`); the upstream doc
  references `0.5` — adjust if the tag is missing.
- NPU-STACK's own mosquitto runs on `:1883` — no conflict with this server's
  `:2882` (kept separate so the two can coexist while we bridge them).
- MySQL data persists in the `mysql_data` volume.
