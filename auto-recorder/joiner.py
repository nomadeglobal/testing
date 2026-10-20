"""Rejoint une réunion Meet / Teams / Zoom via le client web (Playwright).

Best-effort : les interfaces changent. En cas d'échec, une capture d'écran est
enregistrée pour comprendre où ça a bloqué. Non testé contre les vraies
plateformes : à valider sur une réunion de test avant usage.
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse, parse_qs

JOIN_RE = re.compile(r"join now|ask to join|join|rejoindre|participer|demander à participer", re.I)
WEB_RE = re.compile(r"continue on this browser|continuer sur ce navigateur|join from your browser|depuis votre navigateur", re.I)
MUTE_RE = re.compile(r"turn off (microphone|camera)|désactiver (le micro|la caméra|le microphone)", re.I)


def detect_platform(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "meet.google" in host:
        return "meet"
    if "teams.microsoft" in host or "teams.live" in host:
        return "teams"
    if "zoom.us" in host or "zoom.com" in host:
        return "zoom"
    return "unknown"


def zoom_web_url(url: str) -> str:
    """https://zoom.us/j/123?pwd=x  ->  https://zoom.us/wc/123/join?pwd=x (client web)."""
    m = re.search(r"/j/(\d+)", url)
    if not m:
        return url
    pwd = parse_qs(urlparse(url).query).get("pwd", [""])[0]
    base = f"https://{urlparse(url).netloc}/wc/{m.group(1)}/join"
    return f"{base}?pwd={pwd}" if pwd else base


class Joiner:
    def __init__(self, cfg: dict, log_dir: Path):
        self.cfg, self.log_dir = cfg, log_dir
        self._pw = self._ctx = self.page = None

    def join(self, url: str) -> None:
        from playwright.sync_api import sync_playwright  # import tardif : optionnel

        platform = detect_platform(url)
        if platform == "zoom":
            url = zoom_web_url(url)
        self._pw = sync_playwright().start()
        self._ctx = self._pw.chromium.launch_persistent_context(
            self.cfg.get("profile_dir", "browser-profile"),
            headless=False,                      # fenêtre visible : OBS peut la capturer
            permissions=[],                      # micro/caméra refusés : on écoute seulement
            args=["--start-maximized"],
            no_viewport=True,
        )
        self.page = self._ctx.new_page()
        try:
            self.page.goto(url, wait_until="domcontentloaded")
            self._click_optional(WEB_RE, timeout=15000)       # Teams / Zoom : « continuer dans le navigateur »
            self._fill_name()
            self._click_optional(MUTE_RE, timeout=3000, repeat=2)
            self._click_optional(JOIN_RE, timeout=20000, required=True)
        except Exception:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            shot = self.log_dir / "join-failure.png"
            self.page.screenshot(path=str(shot))
            raise RuntimeError(f"Impossible de rejoindre ({platform}). Capture : {shot}")

    def _fill_name(self) -> None:
        name = self.cfg.get("participant_name", "")
        box = self.page.get_by_placeholder(re.compile(r"your name|nom|name", re.I)).first
        try:
            box.wait_for(timeout=5000)
            box.fill(name)
        except Exception:
            pass  # pas de champ nom : compte déjà connecté

    def _click_optional(self, pattern, timeout: int, repeat: int = 1, required: bool = False) -> None:
        for _ in range(repeat):
            try:
                btn = self.page.get_by_role("button", name=pattern).first
                btn.click(timeout=timeout)
            except Exception:
                if required:
                    raise

    def leave(self) -> None:
        try:
            if self._ctx:
                self._ctx.close()
        finally:
            if self._pw:
                self._pw.stop()
