import queue
import threading
from typing import Optional
import speech_recognition as sr

class STT:
    def __init__(self, config: dict, ui=None):
        self.ui = ui
        self.q: queue.Queue[str] = queue.Queue(maxsize=3)
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.recognizer = sr.Recognizer()
        self.recognizer.dynamic_energy_threshold = bool(config.get("dynamic_energy_threshold", False))
        self.recognizer.energy_threshold = int(config.get("energy_threshold", 300))
        self.recognizer.pause_threshold = float(config.get("pause_threshold", 0.8))
        self.mic = sr.Microphone(
            device_index=int(config.get("mic_index", 1)),
            sample_rate=int(config.get("sample_rate", 48000)),
            chunk_size=int(config.get("chunk_size", 1024)),
        )

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        with self.mic as source:
            if self.ui:
                self.ui.log("Calibrating microphone...")
            self.recognizer.adjust_for_ambient_noise(source, duration=1)
            if self.ui:
                self.ui.log("Microphone calibrated.")
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _loop(self) -> None:
        while self.running:
            try:
                with self.mic as source:
                    audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=8)
                try:
                    result = self.recognizer.recognize_google(audio).strip()
                    if result:
                        if self.ui:
                            self.ui.heard(result)
                        if self.q.full():
                            try:
                                self.q.get_nowait()
                            except queue.Empty:
                                pass
                        self.q.put_nowait(result)
                except sr.UnknownValueError:
                    pass
                except sr.RequestError as e:
                    if self.ui:
                        self.ui.error(f"STT service error: {e}")
            except sr.WaitTimeoutError:
                continue
            except Exception as e:
                if self.ui:
                    self.ui.error(f"STT loop error: {e}")

    def listen(self) -> Optional[str]:
        try:
            return self.q.get_nowait()
        except queue.Empty:
            return None
