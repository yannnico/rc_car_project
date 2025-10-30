# save as send_ps5.py
import pygame, socket, json, time

DEST = ("192.168.1.84", 5005)  # ESP32 IP on your LAN
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
pygame.init()
pygame.joystick.init()
if pygame.joystick.get_count() == 0:
    raise SystemExit("No joystick found")

joy = pygame.joystick.Joystick(0)
joy.init()
print("Joystick:", joy.get_name())

def read_state():
    pygame.event.pump()
    # axis mapping may vary; tweak after testing
    ax = joy.get_axis(0)   # left stick X
    ay = -joy.get_axis(1)  # left stick Y (invert)
    lg = joy.get_axis(2)   # left trigger
    bx = joy.get_axis(3)  # right stick X
    by = -joy.get_axis(4)  # right stick Y (invert)
    rg = joy.get_axis(5)   # right trigger
    buttons = { "cross": joy.get_button(0) , "square": joy.get_button(3), "round": joy.get_button(1), "triangle": joy.get_button(2) }
    print(f"AX: {ax:.3f} AY: {ay:.3f} LG: {lg:.3f} BX: {bx:.3f} BY: {by:.3f} RG: {rg:.3f} CROSS: {buttons['cross']} SQUARE: {buttons['square']} ROUND: {buttons['round']} TRIANGLE: {buttons['triangle']}")
    return {"ax": round(ax,3), "ay": round(ay,3), "lg": round(lg,3), "bx": round(bx,3), "by": round(by,3), "rg": round(rg,3), "buttons": buttons, "ts": time.time()}

try:
    while True:
        pkt = json.dumps(read_state()).encode('utf-8')
        sock.sendto(pkt, DEST)
        time.sleep(1/40)  # 25 Hz
except KeyboardInterrupt:
    print("Stopped")
