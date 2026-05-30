import subprocess


class TTS:
    def __init__(self, config):
        self.voice = config.get("espeak_voice", "en+m3")
        self.speed = str(config.get("espeak_speed", 140))
        self.pitch = str(config.get("espeak_pitch", 45))
        self.process = None

    def speak(self, text: str) -> None:
        self.stop()
        self.process = subprocess.Popen(
            ["espeak", "-v", self.voice, "-s", self.speed, "-p", self.pitch, text],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.process = None
    def is_speaking(self) -> bool:
        return self.process is not None and self.process.poll() is None