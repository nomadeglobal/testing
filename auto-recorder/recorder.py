#!/usr/bin/env python3
"""Enregistre un webinaire avec OBS, sans surveillance, avec contrôles de santé.

Exemple :
    python recorder.py --url "https://meet.google.com/abc-defg-hij" --duration 90 --join
"""
from __future__ import annotations

import argparse
import socket
import sys
import time
import tomllib
import urllib.request
import webbrowser
from pathlib import Path

import obsws_python as obs

from healthwatch import AudioWatch, FileWatch, mul_to_db

HERE = Path(__file__).parent


def notify(cfg: dict, title: str, msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {title}: {msg}", flush=True)
    topic = cfg.get("alerts", {}).get("ntfy_topic")
    if not topic:
        return
    try:
        req = urllib.request.Request(
            f"https://ntfy.sh/{topic}", data=msg.encode(), headers={"Title": title.encode("ascii", "ignore").decode()}
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:  # une alerte ratée ne doit jamais arrêter l'enregistrement
        print(f"  (alerte non envoyée : {e})")


def net_latency_ms(host: str, port: int, timeout: float = 3.0) -> float | None:
    t0 = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return (time.perf_counter() - t0) * 1000
    except OSError:
        return None


class Recorder:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        o, h = cfg["obs"], cfg["health"]
        self.req = obs.ReqClient(host=o["host"], port=o["port"], password=o["password"], timeout=5)
        self.audio = AudioWatch(h["silence_floor_db"], h["silence_alert_s"], h.get("stop_after_silence_min", 0) * 60)
        self.files = FileWatch(h["file_stall_s"])
        self._peak_db = float("-inf")
        self.events = None

    # -- OBS ---------------------------------------------------------------
    def preflight(self) -> list[str]:
        problems, o, h = [], self.cfg["obs"], self.cfg["health"]
        scenes = [s["sceneName"] for s in self.req.get_scene_list().scenes]
        if o["scene"] not in scenes:
            problems.append(f"Scène OBS introuvable : {o['scene']!r} (existantes : {scenes})")
        inputs = [i["inputName"] for i in self.req.get_input_list().inputs]
        if o["audio_source"] not in inputs:
            problems.append(f"Source audio introuvable : {o['audio_source']!r} (existantes : {inputs})")
        lat = net_latency_ms(h["net_host"], h["net_port"])
        if lat is None:
            problems.append("Pas de connexion Internet")
        elif lat > h["net_max_latency_ms"]:
            problems.append(f"Réseau lent : {lat:.0f} ms")
        return problems

    def _on_meters(self, data) -> None:
        name = self.cfg["obs"]["audio_source"]
        for inp in getattr(data, "inputs", []):
            if inp.get("inputName") != name:
                continue
            peaks = [ch[1] for ch in inp.get("inputLevelsMul", []) if len(ch) > 1]
            self._peak_db = mul_to_db(max(peaks, default=0.0))

    def start(self) -> None:
        self.req.set_current_program_scene(self.cfg["obs"]["scene"])
        self.events = obs.EventClient(
            host=self.cfg["obs"]["host"], port=self.cfg["obs"]["port"], password=self.cfg["obs"]["password"],
            subs=obs.Subs.LOW_VOLUME | obs.Subs.INPUTVOLUMEMETERS,
        )
        self.events.callback.register(self.on_input_volume_meters)
        self.req.start_record()

    def on_input_volume_meters(self, data) -> None:  # nom imposé par obsws-python
        self._on_meters(data)

    def newest_file(self) -> Path | None:
        d = Path(self.req.get_record_directory().record_directory)
        files = sorted(d.glob("*.*"), key=lambda p: p.stat().st_mtime, reverse=True)
        return files[0] if files else None

    def stop(self) -> str:
        try:
            return self.req.stop_record().output_path
        finally:
            if self.events:
                self.events.disconnect()

    # -- Boucle de surveillance -------------------------------------------
    def monitor(self, duration_s: float) -> str:
        h, t_end = self.cfg["health"], time.monotonic() + duration_s
        net_alerted = False
        while time.monotonic() < t_end:
            time.sleep(h["check_every_s"])
            now = time.monotonic()
            if not self.req.get_record_status().output_active:
                notify(self.cfg, "Enregistrement arrêté", "OBS n'enregistre plus : relance automatique.")
                self.req.start_record()
            f = self.newest_file()
            if f:
                self.files.feed(f.stat().st_size, now)
                if self.files.should_alert(now):
                    notify(self.cfg, "Fichier figé", f"{f.name} ne grossit plus depuis {h['file_stall_s']} s")
            self.audio.feed(self._peak_db, now)
            if self.audio.should_alert(now):
                notify(self.cfg, "Pas de son", f"Silence depuis {self.audio.silent_for(now):.0f} s")
            if self.audio.should_stop(now):
                notify(self.cfg, "Fin probable", "Silence prolongé après la séance : arrêt.")
                break
            lat = net_latency_ms(h["net_host"], h["net_port"])
            bad = lat is None or lat > h["net_max_latency_ms"]
            if bad and not net_alerted:
                notify(self.cfg, "Réseau", "perdu" if lat is None else f"lent ({lat:.0f} ms)")
            net_alerted = bad
        return self.stop()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True, help="Lien Meet / Teams / Zoom")
    ap.add_argument("--duration", type=float, required=True, help="Durée max en minutes")
    ap.add_argument("--join", action="store_true", help="Rejoindre automatiquement (Playwright)")
    ap.add_argument("--config", default=str(HERE / "config.toml"))
    args = ap.parse_args()

    with open(args.config, "rb") as fh:
        cfg = tomllib.load(fh)

    rec = Recorder(cfg)
    problems = rec.preflight()
    if problems:
        notify(cfg, "Contrôle initial échoué", " | ".join(problems))
        return 2

    joiner = None
    if args.join:
        from joiner import Joiner
        joiner = Joiner(cfg.get("join", {}), HERE / "logs")
        try:
            joiner.join(args.url)
        except RuntimeError as e:
            notify(cfg, "Connexion à la réunion échouée", str(e))
            return 3
    else:
        webbrowser.open(args.url)

    rec.start()
    notify(cfg, "Enregistrement démarré", f"durée max {args.duration:.0f} min")
    try:
        path = rec.monitor(args.duration * 60)
        size = Path(path).stat().st_size / 1e6 if path and Path(path).exists() else 0
        notify(cfg, "Enregistrement terminé", f"{path} ({size:.0f} Mo)")
    finally:
        if joiner:
            joiner.leave()
    return 0


if __name__ == "__main__":
    sys.exit(main())
