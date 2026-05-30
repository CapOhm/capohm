import argparse
import importlib
import json
import random
import time
from core.wake import is_sleep_command, is_wake_word

CONFIG_FILE = "config.json"

def load_config(path: str = CONFIG_FILE) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def load_backend(kind: str, name: str, class_name: str):
    module = importlib.import_module(f"backends.{kind}_{name}")
    return getattr(module, class_name)

def build_system_prompt() -> str:
    return (
        "You are the Borg Hive. You are precise, efficient, and serve the Borg King. "
        "Do not overuse the phrase 'resistance is futile'. It is a powerful statement and should be reserved for emphasis."
    )

def test_tts(tts):
    tts.speak("The modular hive voice interface is online.")
    time.sleep(8)

def test_ai(ai):
    messages = [
        {"role": "system", "content": build_system_prompt()},
        {"role": "user", "content": "Say one short sentence confirming you are online."},
    ]
    print(ai.reply(messages))

def test_stt(stt, timeout=15):
    print("Say something. Waiting up to 15 seconds...")
    stt.start()
    start = time.time()
    while time.time() - start < timeout:
        text = stt.listen()
        if text:
            print("Recognized:", text)
            return
        time.sleep(0.2)
    print("No speech recognized.")

def run_assistant(config: dict):
    UI = load_backend("ui", config["ui_backend"], "UI")
    TTS = load_backend("tts", config["tts_backend"], "TTS")
    STT = load_backend("stt", config["stt_backend"], "STT")
    AI = load_backend("ai", config["ai_backend"], "AI")
    ui = UI(config)
    tts = TTS(config)
    stt = STT(config, ui=ui)
    ai = AI(config)
    ui.start()
    stt.start()
    is_awake = False
    messages = []
    ui.status("ASLEEP")
    while True:
        user_input = stt.listen()
        if not user_input:
            time.sleep(0.1)
            continue
        lower = user_input.lower().strip()
        if lower in ["exit", "quit"]:
            ui.log("Exiting.")
            break
        if lower in ["stop", "cancel"]:
            tts.stop()
            tts.speak("The Hive has stopped.")
            continue
        if not is_awake:
            if is_wake_word(user_input, config):
                is_awake = True
                ui.status("AWAKE")
                reply = random.choice(config.get("wake_responses", ["Online."]))
                ui.assistant(reply)
                tts.speak(reply)
            else:
                ui.sleep_note("Still asleep. Say 'buddy' or 'hey hive' to wake.")
            continue
        if is_sleep_command(user_input, config):
            is_awake = False
            ui.status("ASLEEP")
            reply = random.choice(config.get("sleep_responses", ["Sleeping."]))
            ui.assistant(reply)
            tts.speak(reply)
            continue
        messages = [{"role": "system", "content": build_system_prompt()}] + messages[-5:]
        messages.append({"role": "user", "content": user_input})
        try:
            reply = ai.reply(messages)
            messages.append({"role": "assistant", "content": reply})
            ui.assistant(reply)
            tts.speak(reply)
        except Exception as e:
            ui.error(f"AI error: {e}")
            tts.speak("There was an AI error. Check the log, because apparently suffering builds character.")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=CONFIG_FILE)
    parser.add_argument("--test", choices=["tts", "stt", "ai", "all"])
    args = parser.parse_args()
    config = load_config(args.config)
    if args.test:
        UI = load_backend("ui", config["ui_backend"], "UI")
        ui = UI(config)
        ui.start()
        if args.test in ["tts", "all"]:
            TTS = load_backend("tts", config["tts_backend"], "TTS")
            test_tts(TTS(config))
        if args.test in ["ai", "all"]:
            AI = load_backend("ai", config["ai_backend"], "AI")
            test_ai(AI(config))
        if args.test in ["stt", "all"]:
            STT = load_backend("stt", config["stt_backend"], "STT")
            test_stt(STT(config, ui=ui))
        return
    run_assistant(config)

if __name__ == "__main__":
    main()
