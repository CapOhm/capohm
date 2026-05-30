# speech.py

import speech_recognition as sr
import subprocess
import time

recognizer = sr.Recognizer()
recognizer.pause_threshold = 0.8

mic = sr.Microphone(device_index=1)  # Set your mic index here

# Initial mic calibration
with mic as source:
    recognizer.adjust_for_ambient_noise(source, duration=1)
print("Microphone calibrated.")

# Borg speak function
# Speak with Borg voice using custom script (ARMOR PLATED)
def speak(text):
    try:
        subprocess.run(['./borg_speak.sh', text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Borg voice process failed: {e}")
    except Exception as e:
        print(f"⚠️ Borg voice unexpected error: {e}")


# Listen function
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
