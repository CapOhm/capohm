import subprocess
from pathlib import Path
from typing import Optional

class TTS:
    def __init__(self, config: dict):
        self.script = str(config.get("borg_script", "./borg_speak.sh"))
        self.process: Optional[subprocess.Popen] = None

    def speak(self, text: str) -> None:
        text = str(text or "").strip()
        if not text:
            return
        script_path = Path(self.script)
        if not script_path.exists():
            raise FileNotFoundError(f"TTS script not found: {self.script}")
        self.process = subprocess.Popen([self.script, text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
        self.process = None
