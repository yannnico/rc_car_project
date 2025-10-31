# client_ps5_ws.py
import pygame, asyncio, websockets, json, time, os, ssl

from car_control import RGT_control
import sys

WS_URL = os.getenv("WS_URL", "ws://0.0.0.0:8443")
TOKEN  = os.getenv("TOKEN", "my-super-secret")

SEND_HZ = 40

pygame.init(); pygame.joystick.init()
if pygame.joystick.get_count() == 0:
    raise SystemExit("No joystick found")
joy = pygame.joystick.Joystick(0); joy.init()
print("Joystick:", joy.get_name())

controls = RGT_control()

def read_state():
    pygame.event.pump()
    # Different pygame axis ordering on macOS (Darwin). Adjust indices if your device differs.
    if sys.platform == "darwin":
        try:
            ax = joy.get_axis(0)   # left stick X
            ay = -joy.get_axis(1)  # left stick Y (invert)
            bx = joy.get_axis(4)   # right stick X
            by = -joy.get_axis(2)  # right stick Y (invert)
            lg = joy.get_axis(3)   # left trigger
            rg = joy.get_axis(5)   # right trigger

            buttons = { "cross": joy.get_button(0) , "square": joy.get_button(2), "round": joy.get_button(1), "triangle": joy.get_button(3), "lb": joy.get_button(9), "rb": joy.get_button(10), "left_stick": joy.get_button(7), "right_stick": joy.get_button(8), "flash": joy.get_button(4), "menu": joy.get_button(6) }

        except Exception:
            ax = ay = lg = bx = by = rg = 0.0
    else:
        ax = joy.get_axis(0)   # left stick X
        ay = -joy.get_axis(1)  # left stick Y (invert)
        lg = joy.get_axis(2)   # left trigger
        bx = joy.get_axis(3)   # right stick X
        by = -joy.get_axis(4)  # right stick Y (invert)
        rg = joy.get_axis(5)   # right trigger

        buttons = { "cross": joy.get_button(0) , "square": joy.get_button(3), "round": joy.get_button(1), "triangle": joy.get_button(2), "lb": joy.get_button(4), "rb": joy.get_button(5), "left_stick": joy.get_button(11), "right_stick": joy.get_button(12), "flash": joy.get_button(8), "menu": joy.get_button(9) }

    

    controls.update(ax, ay, lg, bx, by, rg, buttons)

    calibrated_controls = controls.get_control()

    return {"ch1": round(max(-1,min(1,calibrated_controls["steering"])),3),
            "ch2": round(max(-1,min(1,calibrated_controls["throttle"])),3),
            "ch3": round(max(-1,min(1,calibrated_controls["winch"])),3),
            "ch4": round(max(-1,min(1,calibrated_controls["swaybar"])),3),
            "ch5": round(max(-1,min(1,calibrated_controls["lights"])),3),
            "ch6": round(max(-1,min(1,calibrated_controls["rotating_lights"])),3),
            "ch7": round(max(-1,min(1,calibrated_controls["speed"])),3),
            "ch8": round(max(-1,min(1,calibrated_controls["dig"])),3),
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

async def drive_once():
    """Connect once, send acquire exactly once, then stream controls while driver."""
    async with websockets.connect(WS_URL, max_size=2**16) as ws:
        # 1) Send acquire ONCE per connection
        await ws.send(json.dumps({"acquire": True, "token": TOKEN}))
        role = "spectator"
        acquired = False
        print("Connected. Sent acquire request.")

        # Optionally: wait up to 2s for server to confirm role
        try:
            async def wait_for_role():
                nonlocal role, acquired
                deadline = time.time() + 2.0
                while time.time() < deadline:
                    msg = await asyncio.wait_for(ws.recv(), timeout=0.2)
                    pkt = json.loads(msg)
                    if pkt.get("type") == "role":
                        role = pkt.get("role", role)
                        acquired = (role == "driver")
                        print("Role:", role)
                        return
                    elif pkt.get("type") == "busy":
                        print("Server says: busy (someone else is driving).")
                        return
                    # ignore other messages (hello, telemetry echoes, etc.)
            await wait_for_role()
        except asyncio.TimeoutError:
            # no explicit role message; we can still start and let server ignore if not driver
            pass

        # 2) Main loop: send controls; only the driver will be honored
        try:
            period = 1.0 / SEND_HZ
            while True:
                st = read_state()
                payload = st
                await ws.send(json.dumps(payload))
                await asyncio.sleep(period)
        except websockets.ConnectionClosed:
            print("Disconnected.")
            return

async def main():
    # Simple reconnect loop with backoff
    delay = 1.0
    while True:
        try:
            await drive_once()
            delay = 1.0  # reset on clean exit
        except (OSError, websockets.InvalidURI, websockets.InvalidHandshake) as e:
            print("Conn error:", e)
        await asyncio.sleep(delay)
        delay = min(delay * 2, 10)


if __name__ == "__main__":
    asyncio.run(main())
