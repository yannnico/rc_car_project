import asyncio, json, os, time, socket, signal
import websockets

# ===== Config =====
ESP32_HOST = os.getenv("ESP32_HOST", "192.168.1.84")  # set to your ESP32 IP
ESP32_PORT = int(os.getenv("ESP32_PORT", "5005"))
WS_BIND    = os.getenv("WS_BIND", "0.0.0.0")
WS_PORT    = int(os.getenv("WS_PORT", "8443"))  # behind TLS terminator or use ws for quick test
SHARED_TOKEN = os.getenv("TOKEN", "change-me")

# Failsafe
FAILSAFE_MS = 500

# Networking
udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
last_pkt_ms = 0

# Control arbitration
current_driver = None  # websocket object that currently holds control
clients = set()

# Neutral payload (explicit ch1..ch8) — sketch expects ch1..ch8 or will default missing keys to 0.0
NEUTRAL = {f"ch{i}": 0.0 for i in range(1, 9)}

def send_udp(payload: dict):
    data = json.dumps(payload).encode("utf-8")
    print(f"UDP -> {ESP32_HOST}:{ESP32_PORT} : {data}", end="\r")
    udp_sock.sendto(data, (ESP32_HOST, ESP32_PORT))

async def watchdog():
    global last_pkt_ms
    while True:
        await asyncio.sleep(0.05)
        if (time.monotonic() * 1000) - last_pkt_ms > FAILSAFE_MS:
            send_udp(NEUTRAL)

async def handle_client(ws):
    global current_driver, last_pkt_ms
    clients.add(ws)
    try:
        # Simple control lock: first client becomes driver; can be improved with explicit "acquire/release"
        if current_driver is None:
            current_driver = ws

        await ws.send(json.dumps({
            "type": "hello",
            "role": "driver" if current_driver is ws else "spectator",
        }))

        async for msg in ws:
            # Each message should be a JSON control packet
            try:
                pkt = json.loads(msg)
            except Exception:
                continue

            if pkt.get("token") != SHARED_TOKEN:
                # optional: close or ignore
                continue

            # Only the driver can command the car
            if current_driver is ws:
                # Support both legacy {ax,ay} packets and new ch1..ch8 channel packets.
                def clamp(v, lo=-1.0, hi=1.0):
                    try:
                        fv = float(v)
                    except Exception:
                        return 0.0
                    return max(lo, min(hi, fv))

                # If client sends channel-format data, forward those channels.
                if any(k in pkt for k in ("ch1", "ch2", "ch3", "ch4", "ch5", "ch6", "ch7", "ch8")):
                    out = {}
                    for i in range(1, 9):
                        key = f"ch{i}"
                        if key in pkt:
                            out[key] = clamp(pkt.get(key, 0.0))
                        else:
                            out[key] = 0.0
                    send_udp(out)
                    last_pkt_ms = int(time.monotonic() * 1000)
                # Legacy: map ax/ay to ch1/ch2 for compatibility
                elif "ax" in pkt or "ay" in pkt:
                    ax = clamp(pkt.get("ax", 0.0))
                    ay = clamp(pkt.get("ay", 0.0))
                    send_udp({"ch1": ax, "ch2": ay})
                    last_pkt_ms = int(time.monotonic() * 1000)
            else:
                # spectator can send "acquire": True to request control (optional)
                if pkt.get("acquire"):
                    if current_driver is None:
                        current_driver = ws
                        await ws.send(json.dumps({"type": "role", "role": "driver"}))
    except websockets.ConnectionClosed:
        pass
    finally:
        if current_driver is ws:
            current_driver = None
        clients.discard(ws)

async def main():
    # watchdog
    asyncio.create_task(watchdog())
    # WebSocket server (plain ws for local test; for production, put behind TLS reverse proxy like Caddy/Nginx)
    async with websockets.serve(handle_client, WS_BIND, WS_PORT, max_size=2**16):
        print(f"Relay listening on ws://{WS_BIND}:{WS_PORT}")
        await asyncio.Future()  # run forever

def _shutdown(*_):
    # Neutral on exit
    send_udp(NEUTRAL)
    raise SystemExit

if __name__ == "__main__":
    try:
        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)
    except Exception:
        pass
    try:
        import uvloop
        uvloop.install()
    except Exception:
        pass
    asyncio.run(main())
