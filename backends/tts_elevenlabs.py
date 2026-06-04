import json
import os
import signal
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class TTS:
    """ElevenLabs TTS backend for Capohm, with stop() and dB volume support."""

    def __init__(self, config: dict):
        self.config = config
        self.api_key = (
            config.get("elevenlabs_api_key")
            or os.environ.get("ELEVENLABS_API_KEY")
            or self._read_dotenv("ELEVENLABS_API_KEY")
        )
        self.voice_id = (
            config.get("elevenlabs_voice_id")
            or os.environ.get("ELEVENLABS_VOICE_ID")
            or self._read_dotenv("ELEVENLABS_VOICE_ID")
        )
        self.model_id = str(config.get("elevenlabs_model_id") or os.environ.get("ELEVENLABS_MODEL_ID") or "eleven_flash_v2_5")
        self.output_format = str(config.get("elevenlabs_output_format") or os.environ.get("ELEVENLABS_OUTPUT_FORMAT") or "pcm_16000")
        self.language_code = config.get("elevenlabs_language_code") or os.environ.get("ELEVENLABS_LANGUAGE_CODE") or None
        self.timeout = float(config.get("elevenlabs_timeout_seconds", 45))
        self.enable_logging = bool(config.get("elevenlabs_enable_logging", True))
        self.apply_text_normalization = config.get("elevenlabs_text_normalization", "auto")
        self.voice_settings = config.get("elevenlabs_voice_settings", None)
        try:
            self.volume_db = float(config.get("elevenlabs_volume_db", config.get("tts_volume_db", 0.0)) or 0.0)
        except Exception:
            self.volume_db = 0.0
        self.volume_debug = bool(config.get("tts_volume_debug", False))

        self._thread = None
        self._process = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    def _read_dotenv(self, key: str) -> str | None:
        path = Path(self.config.get("dotenv_path", ".env"))
        if not path.exists():
            return None
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == key:
                    return v.strip().strip('"').strip("'")
        except Exception:
            return None
        return None

    def speak(self, text: str) -> None:
        text = str(text or "").strip()
        if not text:
            return
        self.stop()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._speak_worker, args=(text,), daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        with self._lock:
            proc = self._process
        if proc and proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except Exception:
                try:
                    proc.terminate()
                except Exception:
                    pass
        with self._lock:
            self._process = None

    def is_speaking(self) -> bool:
        with self._lock:
            proc = self._process
            thread = self._thread
        if proc is not None and proc.poll() is None:
            return True
        return bool(thread and thread.is_alive())

    def _speak_worker(self, text: str) -> None:
        if not self.api_key:
            print("[elevenlabs] Missing ELEVENLABS_API_KEY in environment or .env", flush=True)
            return
        if not self.voice_id:
            print("[elevenlabs] Missing elevenlabs_voice_id or ELEVENLABS_VOICE_ID", flush=True)
            return

        raw_path = None
        processed_path = None
        try:
            audio = self._request_audio(text)
            if self._stop_event.is_set() or not audio:
                return
            raw_path = self._write_temp_audio(audio)
            processed_path = self._prepare_playback_path(raw_path)
            self._play(processed_path)
        except Exception as exc:
            print(f"[elevenlabs] TTS failed: {exc}", flush=True)
        finally:
            for path in (raw_path, processed_path):
                if path:
                    try:
                        Path(path).unlink(missing_ok=True)
                    except Exception:
                        pass
            with self._lock:
                self._process = None

    def _request_audio(self, text: str) -> bytes:
        query = urlencode({
            "output_format": self.output_format,
            "enable_logging": "true" if self.enable_logging else "false",
        })
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}?{query}"

        payload = {
            "text": text,
            "model_id": self.model_id,
            "apply_text_normalization": self.apply_text_normalization,
        }
        if self.language_code:
            payload["language_code"] = self.language_code
        if isinstance(self.voice_settings, dict):
            payload["voice_settings"] = self.voice_settings

        data = json.dumps(payload).encode("utf-8")
        req = Request(
            url,
            data=data,
            headers={
                "xi-api-key": str(self.api_key),
                "Content-Type": "application/json",
                "Accept": "audio/*",
            },
            method="POST",
        )
        with urlopen(req, timeout=self.timeout) as res:
            return res.read()

    def _write_temp_audio(self, audio: bytes) -> str:
        suffix = ".raw" if self.output_format.startswith("pcm_") else ".mp3"
        fd, path = tempfile.mkstemp(prefix="capohm_elevenlabs_", suffix=suffix)
        with os.fdopen(fd, "wb") as f:
            f.write(audio)
        return path

    def _prepare_playback_path(self, path: str) -> str:
        if self.volume_debug:
            print(f"[elevenlabs] voice={self.voice_id} volume_db={self.volume_db} format={self.output_format}", flush=True)

        # For raw PCM, convert to WAV with optional dB gain. This makes volume adjustment reliable.
        if self.output_format.startswith("pcm_"):
            rate = self.output_format.split("_", 1)[1]
            fd, out = tempfile.mkstemp(prefix="capohm_elevenlabs_play_", suffix=".wav")
            os.close(fd)
            if shutil.which("sox"):
                cmd = [
                    "sox", "-q",
                    "-t", "raw",
                    "-r", str(rate),
                    "-e", "signed-integer",
                    "-b", "16",
                    "-c", "1",
                    path,
                    out,
                ]
                if abs(self.volume_db) > 0.01:
                    cmd += ["gain", f"{self.volume_db:.2f}"]
                subprocess.run(cmd, check=True)
                return out
            else:
                print("[elevenlabs] sox not installed; volume cannot be adjusted for PCM", flush=True)
                return path

        # For compressed formats, keep the original file and use player volume where possible.
        return path

    def _play(self, path: str) -> None:
        cmd = self._player_command(path)
        if not cmd:
            print(f"[elevenlabs] No audio player found. Audio saved temporarily at {path}", flush=True)
            return
        with self._lock:
            self._process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=os.setsid)
            proc = self._process
        proc.wait()

    def _player_command(self, path: str) -> list[str] | None:
        custom = self.config.get("elevenlabs_player")
        if custom:
            if isinstance(custom, list):
                return [str(x) for x in custom] + [path]
            return str(custom).split() + [path]

        if self.output_format.startswith("pcm_"):
            # _prepare_playback_path converts PCM to WAV if sox is available.
            if path.endswith(".wav") and shutil.which("aplay"):
                return ["aplay", "-q", path]
            rate = self.output_format.split("_", 1)[1]
            if shutil.which("aplay"):
                return ["aplay", "-q", "-f", "S16_LE", "-r", rate, "-c", "1", path]

        if shutil.which("mpv"):
            cmd = ["mpv", "--no-terminal", "--really-quiet"]
            if abs(self.volume_db) > 0.01:
                percent = max(1, int(round(100 * (10 ** (self.volume_db / 20.0)))))
                cmd.append(f"--volume={percent}")
            return cmd + [path]
        if shutil.which("ffplay"):
            cmd = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"]
            if abs(self.volume_db) > 0.01:
                cmd.extend(["-af", f"volume={self.volume_db}dB"])
            return cmd + [path]
        if shutil.which("mpg123"):
            return ["mpg123", "-q", path]
        return None
