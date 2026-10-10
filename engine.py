"""Sandbox state machine. Sends NO input to the OS: it only mutates SandboxInput."""
import threading, enum


class State(enum.Enum):
    IDLE = "idle"; RUNNING = "running"; PAUSED = "paused"
    CANCELLING = "cancelling"; ERROR = "error"


class SandboxInput:
    def __init__(self):
        self.held, self.log = set(), []

    def down(self, k): self.held.add(k); self.log.append(f"down {k}")
    def up(self, k): self.held.discard(k); self.log.append(f"up {k}")
    def release_all(self):
        for k in sorted(self.held):
            self.log.append(f"cleanup up {k}")
        self.held.clear()


class Engine:
    def __init__(self, on_event=None):
        self.sandbox, self.state = SandboxInput(), State.IDLE
        self.progress, self.error = 0.0, None
        self._cancel, self._resume = threading.Event(), threading.Event()
        self._resume.set()
        self._lock, self._thread = threading.Lock(), None
        self._emit = on_event or (lambda *a: None)

    def start(self, macro):
        from .models import validate
        errs = validate(macro)
        if errs:
            raise ValueError("; ".join(errs))
        with self._lock:
            if self.state in (State.RUNNING, State.PAUSED, State.CANCELLING):
                raise RuntimeError("a sequence is already running")
            self._cancel.clear(); self._resume.set()
            self.state, self.progress, self.error = State.RUNNING, 0.0, None
            self.sandbox = SandboxInput()
        self._thread = threading.Thread(target=self._run, args=(macro,), daemon=True)
        self._thread.start()

    def _sleep(self, ms):
        left = ms / 1000
        while left > 0:
            if self._cancel.is_set(): return False
            if not self._resume.is_set():
                self._resume.wait(0.02); continue
            step = min(0.01, left); self._cancel.wait(step); left -= step
        return not self._cancel.is_set()

    def _run(self, macro):
        total = max(1, macro.repeat * len(macro.actions)); n = 0
        try:
            for _ in range(macro.repeat):
                for a in macro.actions:
                    while not self._resume.is_set():
                        if self._cancel.is_set(): return
                        self._resume.wait(0.02)
                    if self._cancel.is_set(): return
                    if a.type == "key_down": self.sandbox.down(a.value)
                    elif a.type == "key_up": self.sandbox.up(a.value)
                    elif a.type == "key_tap":
                        self.sandbox.down(a.value)
                        if not self._sleep(a.duration_ms): return
                        self.sandbox.up(a.value)
                    elif a.type == "wait":
                        if not self._sleep(a.duration_ms): return
                    n += 1; self.progress = n / total; self._emit("progress", self.progress)
        except Exception as ex:  # error recovery
            self.error = str(ex); self.state = State.ERROR
        finally:
            self.sandbox.release_all()
            if self.state is not State.ERROR:
                self.state = State.IDLE
            self._emit("finished", self.state)

    def pause(self):
        if self.state is State.RUNNING: self.state = State.PAUSED; self._resume.clear()

    def resume(self):
        if self.state is State.PAUSED: self.state = State.RUNNING; self._resume.set()

    def emergency_stop(self):
        if self.state in (State.RUNNING, State.PAUSED):
            self.state = State.CANCELLING
        self._cancel.set(); self._resume.set()

    def shutdown(self):
        self.emergency_stop()
        if self._thread: self._thread.join(timeout=2)
        self.sandbox.release_all()
