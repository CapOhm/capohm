import json
import queue
import threading
import time
from pathlib import Path

import audioop
import pyaudio
from vosk import Model, KaldiRecognizer, SetLogLevel


class STT:
    def __init__(self, config, ui=None):
        self.config = config
        self.ui = ui

        self.model_path = Path(config.get(
            "vosk_model_path",
            "models/vosk/vosk-model-small-en-us-0.15"
        ))

        self.device_index = config.get("mic_index", None)

        # The USB mic is opened at the rate it actually supports.
        # The audio is then resampled before it is sent to Vosk.
        self.input_sample_rate = int(config.get(
            "vosk_input_sample_rate",
            config.get("vosk_sample_rate", config.get("sample_rate", 48000))
        ))
        self.recognition_sample_rate = int(config.get(
            "vosk_recognition_sample_rate",
            16000
        ))

        self.chunk_size = int(config.get("vosk_chunk_size", 4096))

        self.text_queue = queue.Queue()
        self.running = False
        self.thread = None

        self.audio = None
        self.stream = None
        self.model = None
        self.recognizer = None
        self._resample_state = None

    def start(self):
        if self.running:
            return

        if not self.model_path.exists():
            raise FileNotFoundError(
                f"Vosk model not found: {self.model_path}. "
                "Download/unzip the model first."
            )

        SetLogLevel(-1)  # silence Vosk model spam

        self.model = Model(str(self.model_path))
        self.recognizer = KaldiRecognizer(self.model, self.recognition_sample_rate)

        self.audio = pyaudio.PyAudio()

        self.stream = self.audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.input_sample_rate,
            input=True,
            input_device_index=self.device_index,
            frames_per_buffer=self.chunk_size,
        )

        self.stream.start_stream()

        self.running = True
        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()

        msg = (
            f"Vosk STT active. Input {self.input_sample_rate} Hz"
            f" -> recognition {self.recognition_sample_rate} Hz."
        )
        if self.ui:
            self.ui.log(msg)
        else:
            print(msg)

    def _prepare_audio_for_vosk(self, data: bytes) -> bytes:
        if self.input_sample_rate == self.recognition_sample_rate:
            return data

        # 16-bit samples, mono channel.
        converted, self._resample_state = audioop.ratecv(
            data,
            2,
            1,
            self.input_sample_rate,
            self.recognition_sample_rate,
            self._resample_state,
        )
        return converted

    def _listen_loop(self):
        while self.running:
            try:
                data = self.stream.read(self.chunk_size, exception_on_overflow=False)
                data = self._prepare_audio_for_vosk(data)

                if self.recognizer.AcceptWaveform(data):
                    result = json.loads(self.recognizer.Result())
                    text = result.get("text", "").strip()

                    if text:
                        if self.ui:
                            self.ui.heard(text)
                        self.text_queue.put(text)

            except Exception as e:
                if self.ui:
                    self.ui.error(f"Vosk STT error: {e}")
                else:
                    print(f"Vosk STT error: {e}")
                time.sleep(0.5)

    def listen(self):
        try:
            return self.text_queue.get_nowait()
        except queue.Empty:
            return None

    def stop(self):
        self.running = False

        try:
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
        except Exception:
            pass

        try:
            if self.audio:
                self.audio.terminate()
        except Exception:
            pass
