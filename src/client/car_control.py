class CarControl:
    def __init__(self):
        self.steering = 0.0
        self.throttle = 0.0

        self.servo_cam = 0.0

        self.last_buttons = {}

    def update(self, ax, ay, lg, bx, by, rg, buttons):


        self.steering = ax
        self.throttle = (rg - lg)/2  # example: right trigger - left trigger

        self.servo_cam = bx


class RGT_control(CarControl):
    def __init__(self):
        super().__init__()
        self.winch = 0.0 # same as throttle
        self.lights = -1.0
        self.rotating_lights = 1.0
        self.speed = 1.0
        self.dig = 1.0
        self.swaybar = 1.0

    def update(self, ax, ay, lg, bx, by, rg, buttons):
        # RGT car specific control logic can be added here
        super().update(ax, ay, lg, bx, by, rg, buttons)

        changed_buttons = buttons_updated(self.last_buttons, buttons)

        self.winch = by if buttons.get("lb",0) == 1 else 0
        self.lights = - self.lights if "triangle" in changed_buttons else self.lights
        self.rotating_lights = - self.rotating_lights if "square" in changed_buttons else self.rotating_lights
        self.speed = -self.speed if "rb" in changed_buttons else self.speed
        self.dig = (self.dig + 1) if "cross" in changed_buttons else self.dig
        if self.dig > 1:
            self.dig = -1.0
        self.swaybar = -self.swaybar if "round" in changed_buttons else self.swaybar

        status = {
            "lights": "on" if self.lights > 0 else "off",
            "speed": "high" if self.speed < 0 else "low",
            "dig": "locked rear" if self.dig < 0 else ("2wd" if self.dig == 0 else "4wd"),
            "swaybar": "deactivated" if self.swaybar > 0 else "activated"
        }

        print(status, end="\r")
        self.last_buttons = buttons

    def get_control(self):
        return {
            "steering": self.steering,
            "throttle": self.throttle,
            "winch": self.winch,
            "lights": self.lights,
            "rotating_lights": self.rotating_lights,
            "speed": self.speed,
            "dig": self.dig *0.7,
            "swaybar": self.swaybar,
            "servo_cam": self.servo_cam
        }


def buttons_updated(last, current):
    """Return list of changed buttons from last to current state."""
    all_keys = set(last.keys()).union(current.keys())
    changed_buttons = []
    for k in all_keys:
        if last.get(k) == 1 and current.get(k) == 0:
            changed_buttons.append(k)
    return changed_buttons