=== Nirvana OS — SD Card Assets ===

Copy these files to the root of your microSD card
before inserting into the AMB82-Mini.

=== Setup ===

1. Pop the microSD card out of the AMB82-Mini
2. Insert it into your PC via a card reader
3. Copy config.example.json → /config.json on SD root
4. Fill in your actual API keys in config.json
5. Eject safely, reinsert into AMB82-Mini
6. Power on — Nirvana OS reads config on boot

=== Required: /config.json ===

Fields you MUST set:
  openai_key     — OpenAI Vision (GPT-4V) + Whisper STT
  deepseek_key   — primary chat provider
  voicebox_host  — LAN IP of your Voicebox server

Optional fields:
  gemini_key     — Google Gemini Vision
  lmstudio_key   — local LLM (LM Studio on tailnet)
  lmstudio_url   — LM Studio URL (default: http://100.100.2.93:443/v1)
  ngc_key        — NVIDIA NGC cloud
  hf_token       — HuggingFace model downloads
  elevenlabs_key — ElevenLabs TTS

=== File Structure on SD Card ===

/config.json              — settings (loaded on boot)
/tts_output.mp3           — Google TTS output (auto-created)
/recordings/              — voice memos saved here
/recordings/memo_NNN.wav  — individual recordings
/apps/                    — MicroPython .py or WASM .wasm files

=== Notes ===

- The Arduino IDE does NOT push files to the SD card.
  Only firmware is flashed to onboard flash memory.
- SD card files must be placed manually via PC card reader.
- config.json is read every boot — edit it anytime.
