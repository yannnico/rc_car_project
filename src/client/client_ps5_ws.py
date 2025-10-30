# client_ps5_ws.py
import pygame, asyncio, websockets, json, time, os, ssl

WS_URL = os.getenv("WS_URL", "ws://0.0.0.0:8443")
TOKEN  = os.getenv("TOKEN", "my-super-secret")

pygame.init(); pygame.joystick.init()
if pygame.joystick.get_count() == 0:
    raise SystemExit("No joystick found")
joy = pygame.joystick.Joystick(0); joy.init()
print("Joystick:", joy.get_name())

def read_state():
    pygame.event.pump()
    ax = joy.get_axis(0)
    ay = -joy.get_axis(1)
    # optional deadzone
    if abs(ax) < 0.05: ax = 0.0
    if abs(ay) < 0.05: ay = 0.0
    return {"ax": round(max(-1,min(1,ax)),3),
            "ay": round(max(-1,min(1,ay)),3),
            "ts": time.time(),
            "token": TOKEN}

async def run():
    # If you front with TLS, use wss:// and optionally an SSL context
    async with websockets.connect(WS_URL, max_size=2**16) as ws:
        hello = await ws.recv()
        print("Server:", hello)
        try:
            while True:
                pkt = json.dumps(read_state())
                await ws.send(pkt)
                await asyncio.sleep(1/40)  # ~40Hz
        except KeyboardInterrupt:
            pass

if __name__ == "__main__":
    asyncio.run(run())
