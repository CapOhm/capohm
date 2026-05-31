import audioop
import queue
import re
import subprocess
import tempfile
import threading
import time
import wave
from collections import deque
from pathlib import Path

import pyaudio


class STT:
    """
    Whisper.cpp STT with simple voice activity detection (VAD).

    Flow:
      1. Open a PyAudio input device once at the mic's native sample rate, usually 48000 Hz.
      2. Watch RMS level until speech starts.
      3. Record until silence.
      4. Convert the captured phrase to 16 kHz mono.
      5. Send only that phrase to whisper.cpp.

    This avoids the slow fixed-chunk behavior of stt_whispercpp.py.

    Important:
      - arecord uses device strings like plughw:CARD=Audio_1,DEV=0.
      - PyAudio uses numeric device indexes.
      - This backend can auto-pick a usable input device instead of blindly using mic_index.
    """

    def __init__(self, config, ui=None):
        self.config = config
        self.ui = ui

        self.whisper_bin = Path(config.get(
            "whispercpp_binary",
            str(Path.home() / "whisper.cpp/build/bin/whisper-cli")
        ))

        self.model = Path(config.get(
            "whispercpp_model",
            str(Path.home() / "whisper.cpp/models/ggml-tiny.en.bin")
        ))

        # PyAudio wants a numeric input device index.
        # If whispercpp_device_index is null/missing, we auto-select a usable input device.
        self.requested_device_index = config.get(
            "whispercpp_device_index",
            config.get("mic_index", None)
        )
        self.device_name_hint = str(config.get("whispercpp_device_name", "") or "").strip().lower()
        self.arecord_device = str(config.get("whispercpp_arecord_device", "") or "")

        self.input_sample_rate = int(config.get("whispercpp_input_sample_rate", 48000))
        self.recognition_sample_rate = int(config.get("whispercpp_recognition_sample_rate", 16000))
        self.language = config.get("whispercpp_language", "en")
        self.min_chars = int(config.get("whispercpp_min_chars", 2))

        self.frame_ms = int(config.get("whispercpp_vad_frame_ms", 30))
        self.frame_samples = max(160, int(self.input_sample_rate * self.frame_ms / 1000))
        self.rms_threshold = int(config.get("whispercpp_vad_rms_threshold", 450))
        self.start_frames_required = int(config.get("whispercpp_vad_start_frames", 2))
        self.silence_seconds = float(config.get("whispercpp_vad_silence_seconds", 0.75))
        self.min_speech_seconds = float(config.get("whispercpp_vad_min_speech_seconds", 0.45))
        self.max_speech_seconds = float(config.get("whispercpp_vad_max_speech_seconds", 10.0))
        self.preroll_seconds = float(config.get("whispercpp_vad_preroll_seconds", 0.35))
        self.debug = bool(config.get("whispercpp_vad_debug", False))

        # Optional second gate after resampling. Defaults to same threshold as VAD.
        self.final_rms_threshold = int(config.get("whispercpp_rms_threshold", self.rms_threshold))

        self.text_queue = queue.Queue()
        self.running = False
        self.thread = None

        self.audio = None
        self.stream = None
        self.device_index = None

    def start(self):
        if self.running:
            return

        if not self.whisper_bin.exists():
            raise FileNotFoundError(f"whisper.cpp binary not found: {self.whisper_bin}")

        if not self.model.exists():
            raise FileNotFoundError(f"Whisper model not found: {self.model}")

        self.audio = pyaudio.PyAudio()
        self.device_index = self._resolve_input_device()

        self.stream = self.audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.input_sample_rate,
            input=True,
            input_device_index=self.device_index,
            frames_per_buffer=self.frame_samples,
        )
        self.stream.start_stream()

        self.running = True
        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()

        device_name = self._device_name(self.device_index)
        msg = (
            "Whisper.cpp VAD STT active. "
            f"Device {self.device_index} ({device_name}). "
            f"Input {self.input_sample_rate} Hz -> recognition {self.recognition_sample_rate} Hz. "
            f"RMS gate {self.rms_threshold}."
        )
        self._log(msg)

    def _device_name(self, index):
        try:
            info = self.audio.get_device_info_by_index(index)
            return info.get("name", "unknown")
        except Exception:
            return "unknown"

    def _input_devices(self):
        devices = []
        for i in range(self.audio.get_device_count()):
            try:
                info = self.audio.get_device_info_by_index(i)
            except Exception:
                continue

            if int(info.get("maxInputChannels", 0) or 0) > 0:
                devices.append((i, info))
        return devices

    def _supports_input(self, index) -> bool:
        try:
            self.audio.is_format_supported(
                self.input_sample_rate,
                input_device=index,
                input_channels=1,
                input_format=pyaudio.paInt16,
            )
            return True
        except Exception:
            return False

    def _resolve_input_device(self):
        devices = self._input_devices()

        if not devices:
            raise RuntimeError("No PyAudio input devices found. Check USB mic / audio permissions.")

        def log_reject(index, reason):
            if self.debug:
                self._log(f"Rejected input device {index}: {reason}")

        def usable(index):
            try:
                info = self.audio.get_device_info_by_index(index)
            except Exception as e:
                log_reject(index, f"not found: {e}")
                return False

            if int(info.get("maxInputChannels", 0) or 0) < 1:
                log_reject(index, "no input channels")
                return False

            if not self._supports_input(index):
                log_reject(index, f"does not support mono {self.input_sample_rate} Hz S16")
                return False

            return True

        # 1) Explicit numeric config wins if it is valid.
        if self.requested_device_index is not None:
            try:
                requested = int(self.requested_device_index)
                if usable(requested):
                    return requested

                self._log(
                    f"Configured mic index {requested} is not usable for Whisper VAD. "
                    "Auto-selecting another input device."
                )
            except Exception:
                self._log(
                    f"Invalid configured mic index {self.requested_device_index!r}. "
                    "Auto-selecting input device."
                )

        # 2) Name hint, if provided.
        hints = []
        if self.device_name_hint:
            hints.append(self.device_name_hint)

        # Try to derive hints from arecord-style device strings.
        # Example: plughw:CARD=Audio_1,DEV=0
        if "card=" in self.arecord_device.lower():
            lower = self.arecord_device.lower()
            after = lower.split("card=", 1)[1].split(",", 1)[0]
            if after:
                hints.append(after.replace("_", " "))
                hints.append(after)

        # Common fallback hint for your USB mic.
        hints.extend(["usb audio", "audio_1", "usb"])

        for hint in hints:
            hint = hint.strip().lower()
            if not hint:
                continue

            for index, info in devices:
                name = str(info.get("name", "")).lower()
                if hint in name and usable(index):
                    return index

        # 3) First usable input device.
        for index, _info in devices:
            if usable(index):
                return index

        details = []
        for index, info in devices:
            details.append(
                f"{index}: {info.get('name')} inputs={info.get('maxInputChannels')} "
                f"rate={info.get('defaultSampleRate')}"
            )

        raise RuntimeError(
            "No input device supports mono "
            f"{self.input_sample_rate} Hz S16. Available inputs: "
            + " | ".join(details)
        )

    def _listen_loop(self):
        while self.running:
            try:
                phrase_frames = self._record_until_silence()
                if not phrase_frames:
                    continue

                text = self._transcribe_frames(phrase_frames).strip()

                if self._is_junk_transcript(text):
                    if self.config.get("show_ignored_stt", False) and text:
                        self._log(f"Ignored Whisper VAD STT junk: {text!r}")
                    continue

                if len(text) >= self.min_chars:
                    if self.ui:
                        self.ui.heard(text)
                    self.text_queue.put(text)

            except Exception as e:
                if self.ui:
                    self.ui.error(f"Whisper.cpp VAD STT error: {e}")
                else:
                    print(f"Whisper.cpp VAD STT error: {e}")
                time.sleep(0.5)

    def _record_until_silence(self):
        """Return raw 16-bit mono PCM frames containing one spoken phrase."""
        max_preroll_frames = max(1, int(self.preroll_seconds / (self.frame_ms / 1000)))
        pre_buffer = deque(maxlen=max_preroll_frames)

        speaking = False
        speech_frames = []
        loud_frame_count = 0
        silent_seconds = 0.0
        speech_seconds = 0.0

        while self.running:
            data = self.stream.read(self.frame_samples, exception_on_overflow=False)
            rms = audioop.rms(data, 2)

            if self.debug:
                self._log(f"VAD rms={rms}")

            if not speaking:
                pre_buffer.append(data)

                if rms >= self.rms_threshold:
                    loud_frame_count += 1
                else:
                    loud_frame_count = 0

                if loud_frame_count >= self.start_frames_required:
                    speaking = True
                    speech_frames = list(pre_buffer)
                    silent_seconds = 0.0
                    speech_seconds = len(speech_frames) * self.frame_ms / 1000
                    if self.debug:
                        self._log("VAD speech start")
                continue

            speech_frames.append(data)
            speech_seconds += self.frame_ms / 1000

            if rms < self.rms_threshold:
                silent_seconds += self.frame_ms / 1000
            else:
                silent_seconds = 0.0

            if speech_seconds >= self.max_speech_seconds:
                if self.debug:
                    self._log("VAD max speech duration reached")
                break

            if speech_seconds >= self.min_speech_seconds and silent_seconds >= self.silence_seconds:
                if self.debug:
                    self._log("VAD silence reached")
                break

        return speech_frames

    def _transcribe_frames(self, frames) -> str:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            raw_wav = tmpdir / "input_48k.wav"
            clean_wav = tmpdir / "input_16k.wav"
            out_base = tmpdir / "whisper_out"
            out_txt = Path(str(out_base) + ".txt")

            self._write_wav(raw_wav, frames, self.input_sample_rate)

            subprocess.run(
                [
                    "sox",
                    str(raw_wav),
                    "-r", str(self.recognition_sample_rate),
                    "-c", "1",
                    str(clean_wav),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )

            # Final RMS check after conversion. This catches very quiet false starts.
            rms = self._wav_rms(clean_wav)
            if rms < self.final_rms_threshold:
                if self.config.get("show_ignored_stt", False):
                    self._log(
                        f"Ignored Whisper VAD STT quiet phrase rms={rms} "
                        f"threshold={self.final_rms_threshold}"
                    )
                return ""

            subprocess.run(
                [
                    str(self.whisper_bin),
                    "-m", str(self.model),
                    "-f", str(clean_wav),
                    "-l", self.language,
                    "-nt",
                    "-otxt",
                    "-of", str(out_base),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )

            if not out_txt.exists():
                return ""

            return out_txt.read_text(encoding="utf-8", errors="ignore").strip()

    def _write_wav(self, path: Path, frames, sample_rate: int):
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(b"".join(frames))

    def _wav_rms(self, wav_path: Path) -> int:
        with wave.open(str(wav_path), "rb") as wf:
            frames = wf.readframes(wf.getnframes())
            sample_width = wf.getsampwidth()
            return audioop.rms(frames, sample_width)

    def _is_junk_transcript(self, text: str) -> bool:
        cleaned = text.strip().lower()

        if not cleaned:
            return True

        if self.config.get("whispercpp_ignore_bracketed", True):
            # Ignore pure subtitles/sound labels like "[BLANK_AUDIO]" or "(birds chirping)".
            if re.fullmatch(r"[\[\(].*[\]\)]", cleaned):
                return True

        junk_phrases = self.config.get("whispercpp_junk_phrases", [])
        return any(phrase.lower() in cleaned for phrase in junk_phrases)

    def _log(self, message: str):
        if self.ui:
            self.ui.log(message)
        else:
            print(message)

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
