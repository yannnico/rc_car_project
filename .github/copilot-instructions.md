## Project overview

This repository implements a small RC-car control stack used for local testing and development.
Main components:
- `src/send_ps5.py`: simple UDP sender that reads a local PS5 (via pygame) and sends JSON packets directly to an ESP32 on your LAN.
- `src/client/client_ps5_ws.py`: PS5 client that streams controller state to a WebSocket relay instead of sending UDP directly.
- `src/server/relay.py`: lightweight WebSocket relay that validates a shared token, arbitrates a single "driver", and forwards normalized `{ax,ay}` JSON payloads to the ESP32 over UDP.

Why this structure
- Two client modes (direct UDP vs. WebSocket relay) allow local quick-testing (`send_ps5.py`) and multi-host setups where many clients can connect to a relay (`client_ps5_ws.py` + `relay.py`).
- The relay provides a simple driver/spectator arbitration and a failsafe watchdog that sends a neutral command when the driver stops sending updates.

Key files to inspect
- `src/send_ps5.py` — axis/button mapping and UDP send loop (~25Hz) with `DEST` configured in-file.
- `src/client/client_ps5_ws.py` — websocket client; env vars: `WS_URL`, `TOKEN` (defaults are in the file).
- `src/server/relay.py` — env vars: `ESP32_HOST`, `ESP32_PORT`, `WS_BIND`, `WS_PORT`, `TOKEN`, `FAILSAFE_MS`. Contains `watchdog()` and `handle_client()`.

Important runtime behaviors and patterns
- Payload shape: JSON with at least `ax`, `ay`, `ts` and `token` for WS mode. Example: `{"ax":0.12, "ay":-0.98, "ts":1680000000.0, "token":"..."}`.
- Authentication: a shared `TOKEN` string—relay ignores packets missing the expected token. The client includes `token` in each message.
- Driver arbitration: the first connected WebSocket becomes the driver (no explicit lock API). Spectators may send `{"acquire": true}` but acquisition is opportunistic.
- Failsafe: relay's `watchdog()` sends `NEUTRAL = {"ax":0.0, "ay":0.0}` if no messages arrive for `FAILSAFE_MS` milliseconds.
- Production note: `relay.py` runs a plain `ws://` server by default; terminate TLS at a reverse proxy (Caddy/Nginx) or change to `wss://` and supply an SSL context in the client.

Developer workflows
- Install dependencies from `requirements.txt` (used in CI / local dev). The tests use `pytest`.
- Unit tests: run `pytest` from the repo root. Tests import `src` modules directly (PYTHONPATH is repo root for pytest).
- Run relay for local testing: `python src/server/relay.py` (set `ESP32_HOST`/`ESP32_PORT` to a blackhole or your device).
- Run client (websocket mode): `WS_URL=ws://localhost:8443 TOKEN=my-token python src/client/client_ps5_ws.py`
- Run direct UDP sender: `python src/send_ps5.py` (edit `DEST` in-file or refactor to read env var if desired).

Conventions & project-specific notes for AI agents
- Minimal defensive programming: normalize and clamp `ax`/`ay` to [-1,1] in `relay.py`. New code should follow this pattern for safety.
- Keep payloads compact (rounded floats) and avoid adding large nested structures to control messages.
- The code prefers small, self-contained scripts over complex frameworks — keep changes lightweight and well documented near the changed file.
- Token-based auth is implemented simply; do not assume advanced session management exists.

Integration points to be careful about
- UDP to ESP32: `send_udp()` serializes payload with `json.dumps` and sends via a raw UDP socket. Don't block the asyncio loop when sending to the device.
- Websockets: the project uses `websockets` package with `max_size=2**16`; keep messages small to avoid reconfiguration.
- Optional `uvloop` installation is attempted in `relay.py` — it's safe to keep but not required on all platforms.

Small examples to copy (from repo)
- Client packet example (from `client_ps5_ws.py`):

```json
{"ax": 0.123, "ay": -0.987, "ts": 1700000000.0, "token": "my-super-secret"}
```

- Relay neutral payload: `{"ax": 0.0, "ay": 0.0}` (used in `watchdog()` and on shutdown).

Testing & validation notes
- Running `pytest` validates a tiny unit-test that imports `src.main.greet`. Use `pytest -q` for concise output.
- After behavior changes, run the relay locally and send a small scripted UDP packet to validate formatting before testing on hardware.

If you need more
- The top-level `README.md` is currently empty; add usage examples or a quick-start if you’d like the instructions exposed to humans as well.
- If you want stricter control arbitration or TLS in the relay, mention the requirement and I can propose a concrete design and implementation.

Please review this draft and point out any missing details or behaviors you want the agent to prioritize.
