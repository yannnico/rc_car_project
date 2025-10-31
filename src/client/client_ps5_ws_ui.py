"""
Client with simple UI: shows control status and three video streams served by MediaMTX.

Dependencies (install if missing):
  pip install python-vlc pillow

Usage:
  WS_URL=ws://localhost:8443 TOKEN=my-token \
  STREAM1=rtsp://localhost:8554/stream1 \
  STREAM2=rtsp://localhost:8554/stream2 \
  STREAM3=rtsp://localhost:8554/stream3 \
  python src/client/client_ps5_ws_ui.py

This script runs a Tkinter UI (main thread) and an asyncio websocket sender in a background thread.
It reads the local controller via pygame and sends `ch1..ch8` JSON (same format as `client_ps5_ws.py`).
Video is rendered via python-vlc embedded into Tk labels.
"""
import os
import sys
import time
import threading
import asyncio
import json

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:
    raise SystemExit("Tkinter is required (usually included with Python).")

try:
    from PIL import Image, ImageTk
except Exception:
    Image = None
    ImageTk = None

try:
    import vlc
except Exception:
    vlc = None

import pygame
import websockets

WS_URL = os.getenv("WS_URL", "ws://0.0.0.0:8443")
TOKEN = os.getenv("TOKEN", "my-super-secret")

STREAM1 = os.getenv("STREAM1", "rtsp://192.168.1.55:8554/cam0")
STREAM2 = os.getenv("STREAM2", "rtsp://192.168.1.55:8554/cam1")
STREAM3 = os.getenv("STREAM3", "rtsp://192.168.1.55:8554/cam2")
# Optional: force RTSP transport to TCP (helps avoid decoding errors)
STREAM_TRANSPORT = os.getenv("STREAM_TRANSPORT", "")  # set to 'tcp' to prefer TCP
# Option to disable video (useful when VLC/python-vlc is problematic)
DISABLE_VIDEO = os.getenv("NO_VIDEO", "0") in ("1", "true", "True")

FPS = 30


class SharedControls:
    def __init__(self):
        self.lock = threading.Lock()
        self.steering = 0.0
        self.throttle = 0.0
        self.winch = 0.0
        self.swaybar = 0.0
        self.lights = 0.0
        self.rotating_lights = 0.0
        self.speed = 0.0
        self.dig = 0.0
        self.buttons = {}

    def update(self, **kwargs):
        with self.lock:
            for k, v in kwargs.items():
                setattr(self, k, v)

    def snapshot(self):
        with self.lock:
            return {
                "steering": self.steering,
                "throttle": self.throttle,
                "winch": self.winch,
                "swaybar": self.swaybar,
                "lights": self.lights,
                "rotating_lights": self.rotating_lights,
                "speed": self.speed,
                "dig": self.dig,
                "buttons": dict(self.buttons),
            }


class VideoVLC(threading.Thread):
    """Embed VLC player into a Tk widget (label)."""

    def __init__(self, url, tk_widget):
        super().__init__(daemon=True)
        self.url = url
        self.widget = tk_widget
        self._stop = threading.Event()
        self.instance = None
        self.player = None

    def run(self):
        if vlc is None:
            print("python-vlc is not installed; video disabled")
            return

        options = []
        if STREAM_TRANSPORT == "tcp" and self.url.startswith("rtsp://"):
            options.append(":rtsp-tcp")

        try:
            self.instance = vlc.Instance()
            media = self.instance.media_new(self.url)
            for opt in options:
                media.add_option(opt)
            self.player = self.instance.media_player_new()
            self.player.set_media(media)

            # Attach to widget
            wid = self.widget.winfo_id()
            if sys.platform.startswith("linux"):
                try:
                    self.player.set_xwindow(wid)
                except Exception:
                    try:
                        self.player.set_hwnd(wid)
                    except Exception:
                        pass
            elif sys.platform == "win32":
                try:
                    self.player.set_hwnd(wid)
                except Exception:
                    pass
            elif sys.platform == "darwin":
                try:
                    self.player.set_nsobject(wid)
                except Exception:
                    pass

            self.player.play()
        except Exception as e:
            print("VLC playback error:", e)
            return

        try:
            while not self._stop.is_set():
                time.sleep(0.1)
        finally:
            try:
                self.player.stop()
            except Exception:
                pass

    def stop(self):
        self._stop.set()


class WebsocketSender(threading.Thread):
    """Runs asyncio websocket client in a background thread and sends periodic control packets."""

    def __init__(self, controls: SharedControls, stop_event: threading.Event):
        super().__init__(daemon=True)
        self.controls = controls
        self.stop_event = stop_event

    def run(self):
        asyncio.run(self._main())

    async def _main(self):
        try:
            async with websockets.connect(WS_URL, max_size=2 ** 16) as ws:
                # wait for hello
                try:
                    hello = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    print("Server:", hello)
                except Exception:
                    pass
                while not self.stop_event.is_set():
                    snap = self.controls.snapshot()
                    pkt = {
                        "ch1": round(max(-1, min(1, snap["steering"])), 3),
                        "ch2": round(max(-1, min(1, snap["throttle"])), 3),
                        "ch3": round(max(-1, min(1, snap["winch"])), 3),
                        "ch4": round(max(-1, min(1, snap["swaybar"])), 3),
                        "ch5": round(max(0, min(1, snap["lights"])), 3),
                        "ch6": round(max(0, min(1, snap["rotating_lights"])), 3),
                        "ch7": round(max(-1, min(1, snap["speed"])), 3),
                        "ch8": round(max(-1, min(1, snap["dig"])), 3),
                        "ts": time.time(),
                        "token": TOKEN,
                    }
                    try:
                        await ws.send(json.dumps(pkt))
                    except Exception:
                        break
                    await asyncio.sleep(1 / 40)
        except Exception as e:
            print("Websocket sender error:", e)


def start_pygame_reader(controls: SharedControls, stop_event: threading.Event):
    pygame.init()
    pygame.joystick.init()
    if pygame.joystick.get_count() == 0:
        print("No joystick found; controller input disabled")
        return
    joy = pygame.joystick.Joystick(0)
    joy.init()
    print("Joystick:", joy.get_name())

    while not stop_event.is_set():
        pygame.event.pump()
        ax = joy.get_axis(0)
        ay = -joy.get_axis(1)
        lg = joy.get_axis(2)
        bx = joy.get_axis(3)
        by = -joy.get_axis(4)
        rg = joy.get_axis(5)
        buttons = {
            "cross": joy.get_button(0),
            "round": joy.get_button(1),
            "triangle": joy.get_button(2),
            "square": joy.get_button(3),
        }
        controls.update(
            steering=ax,
            throttle=ay,
            winch=by,
            swaybar=bx,
            lights=(lg + 1.0) / 2.0,
            rotating_lights=(rg + 1.0) / 2.0,
            speed=0.0,
            dig=1.0 if buttons["cross"] else 0.0,
            buttons=buttons,
        )
        time.sleep(1 / 60)


def make_ui(controls: SharedControls, stop_event: threading.Event):
    root = tk.Tk()
    root.title("RC Client UI")

    vids_frame = ttk.Frame(root)
    vids_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

    labels = []
    for i in range(3):
        lbl = tk.Label(vids_frame, text=f"Stream {i+1}", bg="black", width=320, height=240)
        lbl.grid(row=0, column=i, padx=4, pady=4)
        labels.append(lbl)

    status = ttk.Frame(root)
    status.pack(side=tk.BOTTOM, fill=tk.X)

    status_text = tk.StringVar()
    status_label = ttk.Label(status, textvariable=status_text, anchor=tk.W)
    status_label.pack(side=tk.LEFT, padx=8, pady=4, fill=tk.X, expand=True)

    def update_ui():
        snap = controls.snapshot()
        status_text.set(
            f"steer:{snap['steering']:.2f} thr:{snap['throttle']:.2f} winch:{snap['winch']:.2f} dig:{snap['dig']:.2f} lights:{snap['lights']:.2f}"
        )
        if stop_event.is_set():
            root.quit()
            return
        root.after(50, update_ui)

    root.protocol("WM_DELETE_WINDOW", lambda: stop_event.set())
    root.after(50, update_ui)
    return root, labels


def main():
    controls = SharedControls()
    stop_event = threading.Event()

    # start UI (main thread) first so we can attach VLC players to widget IDs
    root, labels = make_ui(controls, stop_event)

    # start video threads (VLC) after UI created
    video_threads = []
    if not DISABLE_VIDEO and vlc is not None:
        for url, lbl in zip((STREAM1, STREAM2, STREAM3), labels):
            vt = VideoVLC(url, lbl)
            vt.start()
            video_threads.append(vt)
    else:
        if DISABLE_VIDEO:
            print("Video disabled by NO_VIDEO environment variable")
        else:
            print("python-vlc not available; video disabled")

    # start pygame reader thread
    py_thread = threading.Thread(target=start_pygame_reader, args=(controls, stop_event), daemon=True)
    py_thread.start()

    # start websocket sender thread
    ws_sender = WebsocketSender(controls, stop_event)
    ws_sender.start()

    try:
        root.mainloop()
    finally:
        stop_event.set()
        for vt in video_threads:
            vt.stop()


if __name__ == "__main__":
    main()