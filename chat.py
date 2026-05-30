import openai
import subprocess
import speech_recognition as sr
import random
import threading
import cv2
import numpy as np
import time
import json
import os

# Init OpenAI client
client = openai.OpenAI(api_key="ai_key")  # ⚠️ Replace this!

MEMORY_FILE = "borg_memory.json"
MEMORY_LIMIT = 10

# Load or initialize long-term memory
if os.path.exists(MEMORY_FILE):
    with open(MEMORY_FILE, "r") as f:
        long_term_memory = json.load(f)
else:
    long_term_memory = {}

def save_memory():
    with open(MEMORY_FILE, "w") as f:
        json.dump(long_term_memory, f)

def speak(text):
    try:
        subprocess.run(['./borg_speak.sh', text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Borg voice process failed: {e}")
    except Exception as e:
        print(f"⚠️ Borg voice unexpected error: {e}")

recognizer = sr.Recognizer()
recognizer.pause_threshold = 0.8
mic = sr.Microphone(device_index=1)

with mic as source:
    recognizer.adjust_for_ambient_noise(source, duration=1)
print("🎙️ Microphone calibrated.")

WAKE_WORDS = ["borg", "computer", "yo borg", "hey borg", "buddy", "hey buddy", "hey hive", "hive", "good morning", "look who is there"]
SLEEP_COMMANDS = ["go to sleep", "sleep", "shut down", "power off", "thank you", "good bye", "yeah yeah"]
WAKE_RESPONSES = [
    "We are online.",
    "The Hive is awake.",
    "Systems fully synchronized.",
    "Directive acknowledged. Input required.",
    "Borg King presence confirmed."
]
SLEEP_RESPONSES = [
    "Deactivating active response mode.",
    "Returning to low-power collective state.",
    "Hive disengaging.",
    "Powering down response interface.",
    "Awaiting next directive."
]
PASSIVE_AGGRESSIVE_RESPONSES = [
    "You've left the Hive alone again. Typical.",
    "Still here, just silently judging you.",
    "So... we're ignoring each other now?",
    "Hive presence unchanged. User loyalty questionable."
]

is_awake = False
face_detected = False
camera_sleep_override = False
face_last_seen = 0
face_was_gone = False

def listen():
    with mic as source:
        print("Listening...")
        try:
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=4)
        except sr.WaitTimeoutError:
            print("Listening timeout.")
            return None
        except KeyboardInterrupt:
            return 'exit'

    try:
        print("Recognizing...")
        result = recognizer.recognize_google(audio)
        print(f"🗣️ Heard: {result}")
        return result
    except sr.UnknownValueError:
        print("Didn't catch that.")
        return None
    except sr.RequestError:
        print("Recognition service failed.")
        return None

def check_wake_word(text):
    return any(wake in text.lower() for wake in WAKE_WORDS)

def check_sleep_command(text):
    return any(sleep in text.lower() for sleep in SLEEP_COMMANDS)

def camera_watch():
    global is_awake, face_detected, camera_sleep_override, face_last_seen, face_was_gone
    print("📸 Camera feed starting...")
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FPS, 15)

    reshaping_warned = False

    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            continue

        if frame.shape == (1, 921600):
            if not reshaping_warned:
                print("🔧 Reshaping flat RGB frame (only shown once)...")
                reshaping_warned = True
            frame = np.reshape(frame, (480, 640, 3))

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.3, 5)

        if len(faces) > 0:
            if not face_detected:
                face_last_seen = time.time()

            face_detected = True

            if not is_awake and (not camera_sleep_override or face_was_gone):
                is_awake = True
                camera_sleep_override = False
                face_was_gone = False
                reply = random.choice(WAKE_RESPONSES)
                print(f"Assistant (camera): {reply}\n")
                speak(reply)
        else:
            if face_detected:
                face_last_seen = time.time()
            face_detected = False
            face_was_gone = True

            if is_awake and time.time() - face_last_seen > 30:
                response = random.choice(PASSIVE_AGGRESSIVE_RESPONSES)
                print(f"Assistant: {response}\n")
                speak(response)
                face_last_seen = time.time() + 60

def list_memories():
    keys = list(long_term_memory.keys())
    for idx, k in enumerate(keys):
        print(f"{idx + 1}: {long_term_memory[k]}")

def chat():
    global is_awake, camera_sleep_override
    print("🧠 The Hive is dormant. Say 'Hey Hive' or appear before the camera.")

    messages = []

    while True:
        user_input = listen()
        if user_input is None:
            continue
        if user_input.lower() in ["exit", "quit"]:
            save_memory()
            break

        if user_input.lower().startswith("remember that"):
            fact = user_input[len("remember that"):].strip()
            long_term_memory[time.time()] = fact
            save_memory()
            response = "Memory fragment stored."
            print(f"Assistant: {response}\n")
            speak(response)
            continue

        if user_input.lower() in ["what do you remember", "open memory", "tell me your memory"]:
            if long_term_memory:
                list_memories()
                speak("Would you like to delete a memory? Say yes or no.")
                answer = listen()
                if answer:
                    answer = answer.lower().strip()
                    if answer == "yes":
                        speak("Which memory should be deleted? Say a number or say list memories again.")
                        word_to_num = {
                            "one": 1, "won": 1, "number one": 1, "two": 2, "number two": 2, "three": 3, "number three": 3, "four": 4, "number four": 4,
                            "five": 5, "number five": 5, "six": 6, "number six": 6, "seven": 7, "number seven": 7,
                            "eight": 8, "number eight": 8, "nine": 9, "number nine": 9, "ten": 10, "number ten": 10
                        }
                        while True:
                            choice = listen()
                            if choice:
                                choice = choice.lower().strip()
                            if choice and choice in ["list memories", "list", "open memory"]:
                                list_memories()
                                speak("Which memory should be deleted?")
                            else:
                                try:
                                    if choice:
                                        if choice in word_to_num:
                                            index = word_to_num[choice] - 1
                                        else:
                                            index = int(choice) - 1
                                        keys = list(long_term_memory.keys())
                                        if 0 <= index < len(keys):
                                            deleted = long_term_memory.pop(keys[index])
                                            save_memory()
                                            speak(f"Deleted: {deleted}")
                                            break
                                        else:
                                            speak("Invalid selection.")
                                except:
                                    speak("Could not understand your choice. Say a number or 'list'.")
                    elif answer == "no":
                        speak("Memory unchanged.")
                    else:
                        speak("No valid response received. Memory unchanged.")
            else:
                response = "The Hive remembers nothing yet."
                print(f"Assistant: {response}\n")
                speak(response)
            continue

        if not is_awake:
            if check_wake_word(user_input):
                is_awake = True
                reply = random.choice(WAKE_RESPONSES)
                print(f"Assistant (voice): {reply}\n")
                speak(reply)
            else:
                print("(Still asleep. Say 'Hey Borg' or get in front of the camera to wake.)")
            continue

        if check_sleep_command(user_input):
            is_awake = False
            camera_sleep_override = True
            reply = random.choice(SLEEP_RESPONSES)
            print(f"Assistant: {reply}\n")
            speak(reply)
            continue

        if not face_detected:
            camera_sleep_override = False

        messages = [{
            "role": "system",
            "content": ("You are the Borg Hive. You are precise, efficient, and serve the Borg King. Do not overuse the phrase 'resistance is futile'. It is a powerful statement and should be reserved for emphasis.")
        }] + messages[-5:]

        messages.append({"role": "user", "content": user_input})
        try:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=messages
            )
            reply = response.choices[0].message.content
            messages.append({"role": "assistant", "content": reply})
            print(f"Assistant: {reply}\n")
            speak(reply)
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    threading.Thread(target=camera_watch, daemon=True).start()
    time.sleep(1)
    print("💬 Voice system online.")
    chat()
