import time, pytest
from core.models import Macro, Action, validate
from core.engine import Engine, State
from storage.store import Store


def m(*acts, repeat=1): return Macro("t", actions=list(acts), repeat=repeat)


def wait_idle(e):
    for _ in range(300):
        if e.state in (State.IDLE, State.ERROR): return
        time.sleep(0.01)


def test_validation_rejects_bad():
    assert validate(Macro("", repeat=0, actions=[Action("exec", "x", 99999)]))
    with pytest.raises(ValueError):
        Macro.from_dict({"name": "x", "actions": [{"type": "__import__"}]})


def test_runs_in_order():
    e = Engine(); e.start(m(Action("key_down", "a"), Action("key_up", "a")))
    wait_idle(e); assert e.sandbox.log == ["down a", "up a"]


def test_cancel_during_wait_releases_held():
    e = Engine(); e.start(m(Action("key_down", "w"), Action("wait", "", 5000)))
    time.sleep(0.1); t = time.time(); e.emergency_stop(); wait_idle(e)
    assert time.time() - t < 0.5 and not e.sandbox.held and e.state is State.IDLE


def test_shutdown_cleans_up():
    e = Engine(); e.start(m(Action("key_down", "w"), Action("wait", "", 5000)))
    time.sleep(0.05); e.shutdown(); assert not e.sandbox.held


def test_conflicting_start_blocked():
    e = Engine(); e.start(m(Action("wait", "", 2000)))
    with pytest.raises(RuntimeError): e.start(m(Action("wait", "", 10)))
    e.shutdown()


def test_pause_resume():
    e = Engine(); e.start(m(Action("wait", "", 100), Action("key_down", "a")))
    e.pause(); time.sleep(0.2); assert e.state is State.PAUSED and not e.sandbox.log
    e.resume(); wait_idle(e); assert e.sandbox.log


def test_store_corruption_falls_back(tmp_path):
    s = Store(str(tmp_path / "d.json")); s.save([m(Action("wait", "", 5))]); s.save([m()])
    (tmp_path / "d.json").write_text("{broken")
    macros, warn = s.load(); assert macros and warn
