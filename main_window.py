import json
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, Signal, QObject
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import (QApplication, QWidget, QMainWindow, QHBoxLayout, QVBoxLayout, QListWidget,
    QStackedWidget, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QComboBox, QProgressBar,
    QFileDialog, QMessageBox, QGraphicsOpacityEffect, QPlainTextEdit, QInputDialog, QSpinBox, QFrame)
from core.models import Macro, Action, TEMPLATES, ACTION_TYPES, validate
from core.engine import Engine
from storage.store import Store
from input_devices.controllers import ControllerManager, HAVE

QSS = """
QWidget{background:%(bg)s;color:%(fg)s;font-family:'Segoe UI';font-size:13px}
QListWidget,QTableWidget,QPlainTextEdit,QComboBox,QSpinBox{background:%(card)s;border:1px solid %(bd)s;border-radius:8px;padding:4px}
QListWidget::item{padding:10px}QListWidget::item:selected{background:%(acc)s;color:white;border-radius:6px}
QPushButton{background:%(card)s;border:1px solid %(bd)s;border-radius:8px;padding:7px 14px}
QPushButton:hover{background:%(acc)s;color:white}
QPushButton#stop{background:#b3261e;color:white;font-weight:bold}
QProgressBar{border-radius:6px;background:%(card)s;text-align:center}QProgressBar::chunk{background:%(acc)s;border-radius:6px}
QLabel#h{font-size:20px;font-weight:600}QLabel#warn{color:#e0a030}"""
THEMES = {"Dark": dict(bg="#0e1420", fg="#e6e9f0", card="#161d2c", bd="#26314a"),
          "Light": dict(bg="#f4f6fa", fg="#1a2233", card="#ffffff", bd="#cfd6e4")}


class Bridge(QObject):
    event = Signal(str, object)


def h(text): l = QLabel(text); l.setObjectName("h"); return l


class MainWindow(QMainWindow):
    def __init__(self, data_path):
        super().__init__()
        self.setWindowTitle("Macro Studio"); self.resize(1100, 700)
        self.store = Store(data_path); self.macros, self.warnings = self.store.load()
        self.bridge = Bridge(); self.engine = Engine(lambda k, v: self.bridge.event.emit(k, v))
        self.bridge.event.connect(self._on_engine)
        self.ctl = ControllerManager(); self.devices = []; self.current = None
        self.accent, self.theme, self.animate = "#3b82f6", "Dark", True
        self.nav = QListWidget(); self.nav.setFixedWidth(190)
        self.pages = QStackedWidget()
        for name, build in [("Dashboard", self._dash), ("Library", self._library), ("Editor", self._editor),
                            ("Controllers", self._controllers), ("Diagnostics", self._diag), ("Settings", self._settings)]:
            self.nav.addItem(name); self.pages.addWidget(build())
        self.nav.currentRowChanged.connect(self._go)
        root = QWidget(); lay = QHBoxLayout(root); lay.addWidget(self.nav); lay.addWidget(self.pages, 1)
        self.setCentralWidget(root); self.apply_theme()
        QShortcut(QKeySequence("Ctrl+."), self, activated=self.engine.emergency_stop)  # sandbox e-stop
        self.timer = QTimer(self, interval=100, timeout=self._tick); self.timer.start()
        self.nav.setCurrentRow(0); self._refresh_all()

    # ---- infra
    def apply_theme(self):
        QApplication.instance().setStyleSheet(QSS % dict(THEMES[self.theme], acc=self.accent))

    def _go(self, i):
        self.pages.setCurrentIndex(i); self._refresh_all()
        if not self.animate: return
        w = self.pages.currentWidget(); fx = QGraphicsOpacityEffect(w); w.setGraphicsEffect(fx)
        a = QPropertyAnimation(fx, b"opacity", w, duration=220, startValue=0.0, endValue=1.0)
        a.setEasingCurve(QEasingCurve.OutCubic); a.finished.connect(lambda: w.setGraphicsEffect(None)); a.start()
        self._anim = a

    def _save(self): self.store.save(self.macros)

    def _refresh_all(self):
        self.lib.clear(); [self.lib.addItem(f"{m.name}  ·  {m.template}  ·  {m.category}") for m in self.macros]
        self.stats.setText(f"Macros: {len(self.macros)}   |   Controllers: {len(self.devices)}   |   "
                           f"Sandbox state: {self.engine.state.value}")
        self.dash_log.setPlainText("\n".join(self.warnings) or "No warnings.")

    # ---- pages
    def _dash(self):
        w = QWidget(); l = QVBoxLayout(w); l.addWidget(h("Dashboard"))
        self.stats = QLabel(); l.addWidget(self.stats)
        l.addWidget(self._boundary()); self.dash_log = QPlainTextEdit(readOnly=True); l.addWidget(self.dash_log)
        return w

    def _boundary(self):
        b = QLabel("Sandbox only: playback never sends keyboard, mouse or controller input to any game or app. "
                   "Controller compatibility is not permission to automate a game. Not affiliated with or approved by Epic Games.")
        b.setObjectName("warn"); b.setWordWrap(True); return b

    def _library(self):
        w = QWidget(); l = QVBoxLayout(w); l.addWidget(h("Macro Library"))
        self.lib = QListWidget(); l.addWidget(self.lib)
        row = QHBoxLayout()
        for t, f in [("New", self.new_macro), ("Rename", self.rename_macro), ("Duplicate", self.dup_macro),
                     ("Delete", self.del_macro), ("Import", self.import_macro), ("Export", self.export_macro),
                     ("Edit", self.edit_macro)]:
            b = QPushButton(t); b.clicked.connect(f); row.addWidget(b)
        l.addLayout(row); return w

    def _sel(self):
        i = self.lib.currentRow(); return i if 0 <= i < len(self.macros) else None

    def new_macro(self):
        name, ok = QInputDialog.getText(self, "New macro", "Name:")
        if not ok or not name.strip(): return
        t, ok = QInputDialog.getItem(self, "Template", "Template:", TEMPLATES, 5, False)
        if ok: self.macros.append(Macro(name.strip(), t)); self._save(); self._refresh_all()

    def rename_macro(self):
        i = self._sel()
        if i is None: return
        n, ok = QInputDialog.getText(self, "Rename", "Name:", text=self.macros[i].name)
        if ok and n.strip(): self.macros[i].name = n.strip(); self._save(); self._refresh_all()

    def dup_macro(self):
        i = self._sel()
        if i is None: return
        c = Macro.from_dict(self.macros[i].to_dict()); c.name += " copy"
        self.macros.append(c); self._save(); self._refresh_all()

    def del_macro(self):
        i = self._sel()
        if i is not None: del self.macros[i]; self._save(); self._refresh_all()

    def export_macro(self):
        i = self._sel()
        if i is None: return
        p, _ = QFileDialog.getSaveFileName(self, "Export", f"{self.macros[i].name}.json", "JSON (*.json)")
        if p:
            with open(p, "w") as f: json.dump(self.macros[i].to_dict(), f, indent=2)

    def import_macro(self):
        p, _ = QFileDialog.getOpenFileName(self, "Import", "", "JSON (*.json)")
        if not p: return
        try:
            with open(p) as f: self.macros.append(Macro.from_dict(json.load(f)))
            self._save(); self._refresh_all()
        except Exception as e:
            QMessageBox.warning(self, "Import rejected", f"Invalid macro file: {e}")

    def edit_macro(self):
        i = self._sel()
        if i is None: return
        self.current = self.macros[i]; self._load_editor(); self.nav.setCurrentRow(2)

    def _editor(self):
        w = QWidget(); l = QVBoxLayout(w); l.addWidget(h("Macro Editor"))
        self.ed_title = QLabel("No macro selected"); l.addWidget(self.ed_title)
        self.table = QTableWidget(0, 3); self.table.setHorizontalHeaderLabels(["Type", "Key / note", "Duration ms"])
        self.table.horizontalHeader().setStretchLastSection(True); l.addWidget(self.table)
        row = QHBoxLayout()
        self.repeat = QSpinBox(minimum=1, maximum=100); row.addWidget(QLabel("Repeat")); row.addWidget(self.repeat)
        for t, f in [("Add", self.add_action), ("Remove", self.rm_action), ("Up", lambda: self.mv(-1)),
                     ("Down", lambda: self.mv(1)), ("Undo", self.undo), ("Redo", self.redo), ("Save", self.save_editor)]:
            b = QPushButton(t); b.clicked.connect(f); row.addWidget(b)
        l.addLayout(row); l.addWidget(self._boundary())
        run = QHBoxLayout()
        for t, f in [("Run in sandbox", self.run_sandbox), ("Pause/Resume", self.toggle_pause)]:
            b = QPushButton(t); b.clicked.connect(f); run.addWidget(b)
        stop = QPushButton("EMERGENCY STOP (Ctrl+.)"); stop.setObjectName("stop")
        stop.clicked.connect(self.engine.emergency_stop); run.addWidget(stop); l.addLayout(run)
        self.bar = QProgressBar(); l.addWidget(self.bar)
        self.sb_log = QPlainTextEdit(readOnly=True); l.addWidget(self.sb_log)
        self._undo, self._redo = [], []; return w

    def _snapshot(self): return json.dumps(self._read_table())

    def _read_table(self):
        out = []
        for r in range(self.table.rowCount()):
            t = self.table.cellWidget(r, 0).currentText()
            try: d = int(self.table.item(r, 2).text())
            except (ValueError, AttributeError): d = -1
            out.append([t, self.table.item(r, 1).text() if self.table.item(r, 1) else "", d])
        return out

    def _fill(self, rows):
        self.table.setRowCount(0)
        for t, v, d in rows:
            r = self.table.rowCount(); self.table.insertRow(r)
            c = QComboBox(); c.addItems(sorted(ACTION_TYPES)); c.setCurrentText(t); self.table.setCellWidget(r, 0, c)
            self.table.setItem(r, 1, QTableWidgetItem(v)); self.table.setItem(r, 2, QTableWidgetItem(str(d)))

    def _load_editor(self):
        m = self.current; self.ed_title.setText(f"{m.name}  ({m.template})"); self.repeat.setValue(m.repeat)
        self._fill([[a.type, a.value, a.duration_ms] for a in m.actions]); self._undo, self._redo = [], []

    def _push(self): self._undo.append(self._snapshot()); self._redo.clear()
    def add_action(self):
        self._push(); self._fill(self._read_table() + [["key_tap", "a", 50]])
    def rm_action(self):
        r = self.table.currentRow()
        if r >= 0: self._push(); rows = self._read_table(); del rows[r]; self._fill(rows)
    def mv(self, d):
        r = self.table.currentRow(); rows = self._read_table()
        if 0 <= r and 0 <= r + d < len(rows):
            self._push(); rows[r], rows[r + d] = rows[r + d], rows[r]; self._fill(rows); self.table.selectRow(r + d)
    def undo(self):
        if self._undo: self._redo.append(self._snapshot()); self._fill(json.loads(self._undo.pop()))
    def redo(self):
        if self._redo: self._undo.append(self._snapshot()); self._fill(json.loads(self._redo.pop()))

    def _from_editor(self):
        m = Macro(self.current.name, self.current.template, self.current.category, self.repeat.value(),
                  [Action(t, v, d) for t, v, d in self._read_table()]); return m, validate(m)

    def save_editor(self):
        if not self.current: return
        m, errs = self._from_editor()
        if errs: QMessageBox.warning(self, "Validation failed", "\n".join(errs)); return
        self.current.__dict__.update(m.__dict__); self._save(); self.warnings = ["Saved."]

    def run_sandbox(self):
        if not self.current: return
        m, errs = self._from_editor()
        if errs: QMessageBox.warning(self, "Validation failed", "\n".join(errs)); return
        try: self.sb_log.clear(); self.engine.start(m)
        except RuntimeError as e: QMessageBox.information(self, "Busy", str(e))

    def toggle_pause(self):
        self.engine.resume() if self.engine.state.value == "paused" else self.engine.pause()

    def _on_engine(self, kind, val):
        if kind == "progress": self.bar.setValue(int(val * 100))
        else:
            self.sb_log.setPlainText("\n".join(self.engine.sandbox.log) + f"\n[{self.engine.state.value}]"
                                     + (f" error: {self.engine.error}" if self.engine.error else ""))

    def _controllers(self):
        w = QWidget(); l = QVBoxLayout(w); l.addWidget(h("Controllers"))
        self.dev_combo = QComboBox(); l.addWidget(self.dev_combo)
        self.dev_info = QLabel("Scanning…"); l.addWidget(self.dev_info)
        self.axes_bars = []
        for i in range(6):
            b = QProgressBar(minimum=-100, maximum=100, format=f"axis {i}: %v"); self.axes_bars.append(b); l.addWidget(b)
        self.btn_label = QLabel(); l.addWidget(self.btn_label)
        self.dz = QSpinBox(minimum=0, maximum=50, value=10, suffix="% deadzone"); l.addWidget(self.dz)
        l.addStretch(); return w

    def _tick(self):
        if self.pages.currentIndex() == 3:
            devs = self.ctl.refresh() if not hasattr(self, "_n") or self._n % 20 == 0 else self.devices
            self._n = getattr(self, "_n", 0) + 1
            if [d.name for d in devs] != [d.name for d in self.devices] or not self.dev_combo.count():
                self.devices = devs; self.dev_combo.clear(); [self.dev_combo.addItem(f"{d.kind}: {d.name}") for d in devs]
            if self.ctl.error: self.dev_info.setText(f"Controller backend unavailable: {self.ctl.error}")
            elif not devs: self.dev_info.setText("No controllers detected. Connect one; it is rescanned every 2 s.")
            else:
                d = devs[max(0, self.dev_combo.currentIndex())]; s = self.ctl.state(d.index, self.dz.value() / 100)
                self.dev_info.setText(f"{d.name} ({d.kind}) — {d.axes} axes, {d.buttons} buttons")
                if s:
                    for b, v in zip(self.axes_bars, s[0]): b.setValue(int(v * 100))
                    self.btn_label.setText("Pressed: " + (", ".join(str(i) for i, p in enumerate(s[1]) if p) or "none"))
        elif self.pages.currentIndex() == 0: self._refresh_all()

    def _diag(self):
        w = QWidget(); l = QVBoxLayout(w); l.addWidget(h("Diagnostics"))
        self.diag = QPlainTextEdit(readOnly=True); l.addWidget(self.diag)
        b = QPushButton("Refresh / copy report"); b.clicked.connect(self.run_diag); l.addWidget(b); return w

    def run_diag(self):
        import sys, PySide6
        bad = [f"{m.name}: {e}" for m in self.macros for e in validate(m)]
        self.diag.setPlainText(f"Python {sys.version.split()[0]}\nPySide6 {PySide6.__version__}\n"
            f"pygame available: {HAVE}\nController backend error: {self.ctl.error}\nControllers: {len(self.devices)}\n"
            f"Macros: {len(self.macros)}\nInvalid macros: {bad or 'none'}\n(No paths, usernames or tokens included.)")
        QApplication.clipboard().setText(self.diag.toPlainText())

    def _settings(self):
        w = QWidget(); l = QVBoxLayout(w); l.addWidget(h("Settings"))
        th = QComboBox(); th.addItems(THEMES); th.currentTextChanged.connect(lambda t: (setattr(self, "theme", t), self.apply_theme()))
        ac = QComboBox(); ac.addItems(["#3b82f6", "#8b5cf6", "#10b981", "#f59e0b"])
        ac.currentTextChanged.connect(lambda c: (setattr(self, "accent", c), self.apply_theme()))
        rm = QPushButton("Toggle reduced motion"); rm.clicked.connect(lambda: setattr(self, "animate", not self.animate))
        for x in (QLabel("Theme"), th, QLabel("Accent"), ac, rm): l.addWidget(x)
        l.addStretch(); return w

    def closeEvent(self, e):
        self.engine.shutdown(); self.ctl.close(); self._save(); e.accept()
