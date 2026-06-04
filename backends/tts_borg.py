import os
import signal
import subprocess
from pathlib import Path


class TTS:
    """Borg shell-script TTS backend with per-character volume support."""

    def __init__(self, config: dict):
        self.config = config
        script = str(config.get("borg_script") or "./borg_speak.sh")
        p = Path(script).expanduser()
        if not p.is_absolute():
            p = Path.cwd() / p
        self.script = str(p)
        try:
            self.volume_db = float(config.get("borg_volume_db", config.get("tts_volume_db", 0.0)) or 0.0)
        except Exception:
            self.volume_db = 0.0
        self.volume_debug = bool(config.get("tts_volume_debug", False))
        self._process = None

    def speak(self, text: str) -> None:
        text = str(text or "").strip()
        if not text:
            return
        self.stop()
        env = os.environ.copy()
        env["BORG_VOLUME_DB"] = str(self.volume_db)
        if self.volume_debug:
            env["BORG_VOLUME_DEBUG"] = "1"
            print(f"[borg] script={self.script} volume_db={self.volume_db}", flush=True)
        try:
            self._process = subprocess.Popen(
                [self.script, text],
                stdout=subprocess.DEVNULL,
                stderr=None if self.volume_debug else subprocess.DEVNULL,
                env=env,
                preexec_fn=os.setsid,
            )
        except Exception as exc:
            print(f"[borg] TTS failed: {exc}", flush=True)
            self._process = None

    def stop(self) -> None:
        proc = self._process
        if proc and proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except Exception:
                try:
                    proc.terminate()
                except Exception:
                    pass
        self._process = None

    def is_speaking(self) -> bool:
        proc = self._process
        return bool(proc and proc.poll() is None)
