import subprocess
import tempfile
import threading
from pathlib import Path


class TTS:
    def __init__(self, config):
        self.model = config.get("piper_model", "voices/piper/en_US-joe-medium.onnx")
        self.player = config.get("piper_player", "aplay")
        self.process = None
        self.thread = None
        self.stop_requested = False

    def speak(self, text: str) -> None:
        self.stop()
        self.stop_requested = False
        self.thread = threading.Thread(target=self._speak_worker, args=(text,), daemon=True)
        self.thread.start()

    def _speak_worker(self, text: str) -> None:
        model_path = Path(self.model)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = tmp.name

        try:
            # Generate wav with Piper
            self.process = subprocess.Popen(
                [
                    "piper",
                    "--model",
                    str(model_path),
                    "--output_file",
                    wav_path,
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            self.process.communicate(input=text.encode("utf-8"))

            if self.stop_requested:
                return

            if self.process.returncode != 0:
                print("Piper TTS failed.")
                return

            # Play generated wav
            self.process = subprocess.Popen(
                [self.player, wav_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.process.wait()

        finally:
            try:
                Path(wav_path).unlink(missing_ok=True)
            except Exception:
                pass

            self.process = None

    def stop(self) -> None:
        self.stop_requested = True

        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
            except Exception:
                pass

        self.process = None
    def is_speaking(self) -> bool:
        if self.process and self.process.poll() is None:
            return True
        if self.thread and self.thread.is_alive():
            return True
        return False