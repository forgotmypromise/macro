"""Validated action definitions. Imported data is never executed."""
from dataclasses import dataclass, field

ACTION_TYPES = {"key_down", "key_up", "key_tap", "wait", "note"}
TEMPLATES = ["Drag Macro", "Double Edit Macro", "Triple Action Sequence",
             "Rapid Sequence", "Toggle Sequence", "Custom Sequence"]
MAX_WAIT_MS, MAX_REPEAT, MAX_ACTIONS = 10_000, 100, 500


@dataclass
class Action:
    type: str
    value: str = ""
    duration_ms: int = 0


@dataclass
class Macro:
    name: str
    template: str = "Custom Sequence"
    category: str = "General"
    repeat: int = 1
    actions: list = field(default_factory=list)

    def to_dict(self):
        return {"name": self.name, "template": self.template, "category": self.category,
                "repeat": self.repeat, "actions": [vars(a).copy() for a in self.actions]}

    @staticmethod
    def from_dict(d):
        if not isinstance(d, dict):
            raise ValueError("macro must be an object")
        acts = d.get("actions", [])
        if not isinstance(acts, list):
            raise ValueError("actions must be a list")
        m = Macro(str(d.get("name", "")), str(d.get("template", "Custom Sequence")),
                  str(d.get("category", "General")), int(d.get("repeat", 1)),
                  [Action(str(a.get("type", "")), str(a.get("value", "")),
                          int(a.get("duration_ms", 0))) for a in acts if isinstance(a, dict)])
        errs = validate(m)
        if errs:
            raise ValueError("; ".join(errs))
        return m


def validate(m: Macro):
    e = []
    if not m.name.strip():
        e.append("name is empty")
    if m.template not in TEMPLATES:
        e.append(f"unknown template {m.template!r}")
    if not 1 <= m.repeat <= MAX_REPEAT:
        e.append(f"repeat must be 1..{MAX_REPEAT}")
    if len(m.actions) > MAX_ACTIONS:
        e.append(f"max {MAX_ACTIONS} actions")
    for i, a in enumerate(m.actions, 1):
        if a.type not in ACTION_TYPES:
            e.append(f"action {i}: unknown type {a.type!r}")
        elif a.type in ("key_down", "key_up", "key_tap") and not a.value:
            e.append(f"action {i}: key required")
        if not 0 <= a.duration_ms <= MAX_WAIT_MS:
            e.append(f"action {i}: duration must be 0..{MAX_WAIT_MS} ms")
    return e
