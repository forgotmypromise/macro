"""Controller abstraction over SDL (pygame.joystick). Read-only: never emits input."""
import os
from dataclasses import dataclass
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
try:
    import pygame
    HAVE = True
except Exception:
    pygame, HAVE = None, False


@dataclass
class DeviceInfo:
    index: int; name: str; axes: int; buttons: int; kind: str


def classify(name):
    n = name.lower()
    if "xbox" in n or "xinput" in n: return "Xbox"
    if "dualsense" in n: return "DualSense"
    if "dualshock" in n or "ps4" in n or "wireless controller" in n: return "DualShock 4"
    return "Generic"


class ControllerManager:
    def __init__(self):
        self.error, self._js = None, {}
        if not HAVE:
            self.error = "pygame not installed"; return
        try:
            pygame.joystick.quit(); pygame.joystick.init()
        except Exception as e:
            self.error = str(e)

    def refresh(self):
        if self.error: return []
        try:
            pygame.joystick.quit(); pygame.joystick.init()  # re-enumerate (hot-plug)
            self._js = {i: pygame.joystick.Joystick(i) for i in range(pygame.joystick.get_count())}
        except Exception as e:
            self.error = str(e); return []
        return [DeviceInfo(i, j.get_name(), j.get_numaxes(), j.get_numbuttons(), classify(j.get_name()))
                for i, j in self._js.items()]

    def state(self, i, deadzone=0.1):
        j = self._js.get(i)
        if not j: return None
        pygame.event.pump()
        ax = [(v if abs(v) >= deadzone else 0.0) for v in (j.get_axis(k) for k in range(j.get_numaxes()))]
        return ax, [bool(j.get_button(k)) for k in range(j.get_numbuttons())]

    def close(self):
        if HAVE and not self.error:
            self._js = {}; pygame.joystick.quit()
