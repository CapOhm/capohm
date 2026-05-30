#version that listens during talking
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
import pytesseract
import pyautogui
import webbrowser

# Init OpenAI client
client = openai.OpenAI(api_key="ai_key")

MEMORY_FILE = "borg_memory.json"
MEMORY_LIMIT = 10
pending_text = None
speak_process = None

# Load or initialize long-term memory
if os.path.exists(MEMORY_FILE):
    with open(MEMORY_FILE, "r") as f:
        long_term_memory = json.load(f)
else:
    long_term_memory = {}

# Save memory to file
def save_memory():
    with open(MEMORY_FILE, "w") as f:
        json.dump(long_term_memory, f)

# Speak with Borg voice using custom script
def speak(text):
    global speak_process
    try:
        speak_process = subprocess.Popen(['./borg_speak.sh', text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"Borg voice failed: {e}")

def stop_speaking():
    global speak_process
    if speak_process and speak_process.poll() is None:
        speak_process.terminate()
        speak_process = None

# OCR-based automation to launch Chromium and find login button
def launch_and_click_login():
    webbrowser.get("chromium-browser").open("https://www.technischeunie.nl")
    time.sleep(6)  # Let browser load

    print("📸 Searching for 'inloggen' button...")
    for attempt in range(5):
        button_location = pyautogui.locateOnScreen("inloggen.png", confidence=0.8)
        if button_location:
            print("✅ Found 'inloggen' button. Clicking it...")
            pyautogui.click(pyautogui.center(button_location))
            return
        else:
            print(f"🔄 Attempt {attempt + 1}: Button not found. Retrying...")
            time.sleep(2)

    print("❌ 'Inloggen' button could not be found after several attempts.")

# Find and type in search bar using provided search term
def find_and_type_search(itemnumber="123456789"):
    print("📸 Looking for search bar...")

    search_location = pyautogui.locateOnScreen("search.png", confidence=0.8)

    if search_location:
        print("✅ Found search bar via image.")
        pyautogui.click(pyautogui.center(search_location))
        time.sleep(0.5)
        pyautogui.write(itemnumber, interval=0.1)
        pyautogui.press('enter')
    else:
        print("❌ Search bar image not found. Trying OCR as backup...")
        screenshot = pyautogui.screenshot()
        screenshot_np = np.array(screenshot)
        screenshot_rgb = cv2.cvtColor(screenshot_np, cv2.COLOR_BGR2RGB)
        gray = cv2.cvtColor(screenshot_rgb, cv2.COLOR_RGB2GRAY)

        data = pytesseract.image_to_data(gray, config="--psm 6", output_type=pytesseract.Output.DICT)
        for i in range(len(data["text"])):
            if "doorzoek" in data["text"][i].lower():
                x = data["left"][i] + data["width"][i] // 2
                y = data["top"][i] + data["height"][i] // 2
                pyautogui.click(x, y)
                pyautogui.write(itemnumber, interval=0.1)
                pyautogui.press('enter')
                print("✅ Found and typed using OCR fallback.")
                return
        print("❌ Could not find search bar via OCR either.")

def add_to_cart():
    time.sleep(4)
    print("🔻 Scrolling down a bit to reveal more content...")
    pyautogui.scroll(-2)
    time.sleep(2)
    print("🛒 Looking for 'Add to Cart' (wagen.png)...")
    wagen_location = pyautogui.locateOnScreen("wagen.png", confidence=0.8)

    if wagen_location:
        pyautogui.click(pyautogui.center(wagen_location))
        print("✅ Clicked 'Add to Cart' button.")
    else:
        print("❌ Could not find 'Add to Cart' button (wagen.png).")

if __name__ == "__main__":
    itemnumber = "021103"
    launch_and_click_login()
    time.sleep(5)
    find_and_type_search(itemnumber)
    add_to_cart()
