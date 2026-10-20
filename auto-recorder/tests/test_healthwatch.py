import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from healthwatch import AudioWatch, FileWatch, mul_to_db  # noqa: E402


def test_mul_to_db():
    assert mul_to_db(1.0) == 0.0
    assert math.isclose(mul_to_db(0.1), -20.0)
    assert mul_to_db(0) == float("-inf")


def test_silence_alert_once_and_reset():
    w = AudioWatch(floor_db=-55, silence_alert_s=60, stop_after_silence_s=0)
    w.feed(-20, 0)
    w.feed(-80, 30)
    assert not w.should_alert(30)
    w.feed(-80, 70)
    assert w.should_alert(70)
    assert not w.should_alert(80)      # une seule alerte
    w.feed(-10, 90)                    # le son revient
    w.feed(-80, 200)
    assert w.should_alert(200)         # ré-armée


def test_silence_from_start_alerts():
    w = AudioWatch(-55, 60, 0)
    w.feed(-90, 0)
    assert w.should_alert(61)


def test_stop_only_after_sound_heard():
    w = AudioWatch(-55, 60, 900)
    w.feed(-90, 0)
    assert not w.should_stop(5000)     # jamais de son : pas d'arrêt auto
    w.feed(-20, 5000)
    w.feed(-90, 5100)
    assert not w.should_stop(5800)
    assert w.should_stop(5900)


def test_file_stall():
    f = FileWatch(stall_s=45)
    f.feed(100, 0)
    f.feed(200, 20)
    assert not f.should_alert(60)
    assert f.should_alert(70)
    assert not f.should_alert(80)
    f.feed(300, 90)
    assert not f.should_alert(100)
