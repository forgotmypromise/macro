import json, os, shutil, tempfile
from core.models import Macro


class Store:
    def __init__(self, path):
        self.path = path

    def save(self, macros):
        d = os.path.dirname(self.path) or "."
        os.makedirs(d, exist_ok=True)
        if os.path.exists(self.path):
            shutil.copy2(self.path, self.path + ".bak")
        fd, tmp = tempfile.mkstemp(dir=d)
        with os.fdopen(fd, "w") as f:
            json.dump({"version": 1, "macros": [m.to_dict() for m in macros]}, f, indent=2)
        os.replace(tmp, self.path)

    def load(self):
        """Returns (macros, warnings). Falls back to backup on corruption."""
        for p, note in ((self.path, None), (self.path + ".bak", "restored from backup")):
            try:
                with open(p) as f:
                    macros = [Macro.from_dict(d) for d in json.load(f)["macros"]]
                return macros, ([note] if note else [])
            except (FileNotFoundError, ValueError, KeyError, TypeError):
                continue
        return [], ["no valid data file found; starting empty"]
