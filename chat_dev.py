# added some animations
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
import ordering
import sys
import shutil
import inventorymod
import ascii_animation

width = shutil.get_terminal_size().columns
# ========== Capohm Logo & Display Setup ==========

eye_animation_frames = [
    """
     .-.
    (o o)
     |=|
    __|__
    """,
    """
     .-.
    (O O)
     |=|
    __|__
    """,
    """
     .-.
    (o O)
     |=|
    __|__
    """,
    """
     .-.
    (O o)
     |=|
    __|__
    """
]


def print_capohm_logo():
    logo = """                                                                                           
                                                           .-*#+.   :##=.                    
                                                      ..   .+@@@*..-@@@%:   ..               
                                                    .#@@#--*@@@@@@@@@@@@#=-*@@@-            
                                                    .*@@@@@@@@@@@@@@@@@@@@@@@@@.            
                                               ......#@@@@@%=.:=*##*+-.:*@@@@@@-.....       
                                              .-@@@@@@@@#-=##+-..  ..:=*%*-+@@@@@@@@*.      
                                              ..*@@@@@@-*%-..  :#+.%=  ..:*%=+@@@@@%:.      
                                                .%@@@+-@=.     :#+.%=     .:##:@@@@=.      
                                            .-=+%@@@++@:       :#+.%=       .*@-@@@@*=-:.  
                                            =@@@@@@#=@:        :#+.%=        .@#+@@@@@@#.      
                                            .:#@@@@**%         :#+.%=         :%=%@@@%=.       
                                              .=@@@**%*********#@+.@%*********#@=%@@%:         
                                             .+@@@@**%         :#+.%=         :%=%@@@#:         
                                           .=@@@@@@#=@:        :#+.%=        .@#+@@@@@@#.   
                                            .-+*%@@@++@:       :#+.%=       .#@-%@@@#+=:.   
                                                :%@@@=-@=.     :#+.%=     .:#%.@@@@+.       
                                               .+@@@@@%-*%=.   :#+.%=   .:*%=+@@@@@%:.      
                                              .=@@@@@@@@#-=%%+........-#%*:+@@@@@@@@#.      
                                               .::..-%@@@@@++@-      .%%-%@@@@@+. .:.       
                                                    .+@@@@@#+@=      .@%=%@@@@@.            
                                                    .:::::::+@+      :@#:::::::.            
                                                    .#%%%%%%%%*      :%%%%%%%%%+            
    """
    print("\033[96m" + logo + "\033[0m")
    print("\n" * 2)

    # print(logo)
    # print("\n" * 2)


# Code Forge Mode: generate + run code from a task description
# Dramatic screen blink and clear
def dramatic_clear():
    height = 30  # Adjust if your terminal is taller
    for _ in range(3):
        for row in range(1, height):
            sys.stdout.write(f"\033[{row};0H" + '▓' * width)
        sys.stdout.flush()
        time.sleep(0.2)
        os.system('clear')
        time.sleep(0.1)
    os.system('clear')


# Code Forge Mode: generate + run code from a task description
def code_forge(task_description, language="python"):
    dramatic_clear()
    assistant_output(f"🔧 Generating {language} code for: {task_description}")
    speak(f"Forging {language} code for your task.")

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": f"Write clean {language} code only. No explanations."},
                {"role": "user", "content": task_description}
            ]
        )
        code_snippet = response.choices[0].message.content.strip()

        if code_snippet.startswith("```"):
            code_snippet = "\n".join(code_snippet.splitlines()[1:-1])

        with open("test.py", "w") as f:
            f.write(code_snippet)

        # Print full code across the screen
        row = 1
        for line in code_snippet.splitlines():
            sys.stdout.write(f"\033[{row};0H" + line[:width])
            row += 1
        sys.stdout.flush()

        speak("Do you want to run this code? Say yes or no.")
        answer = None
        start_time = time.time()
        while time.time() - start_time < 10:
            check = listen()
            if check:
                answer = check
                break
            time.sleep(0.5)

        if answer and "yes" in answer.lower():
            speak("Understood. Running your code now.")
            os.system('clear')
            subprocess.run(["python3", "test.py"])
            time.sleep(5)  # Show result for a few seconds
            restore_main_screen()
        else:
            assistant_output("🚫 Code not executed.")
            speak("Code was saved but not executed.")
            time.sleep(3)
            restore_main_screen()

    except Exception as e:
        assistant_output(f"❌ Error during Code Forge: {e}")
        speak("There was an error generating the code.")
        time.sleep(3)
        restore_main_screen()

#Use like; restore_main_screen(current_state="ASLEEP")    Awake is default.
def restore_main_screen(current_state="AWAKE"):
    os.system('clear')
    print_capohm_logo()
    sys.stdout.write("\033[25;0H" + "\033[94m" + "=" * width + "\033[0m")
    update_status_line(current_state)
    sys.stdout.flush()

# Restore Capohm's main UI
#def restore_main_screen():
#    os.system('clear')
#    print_capohm_logo()
#    sys.stdout.write("\033[25;0H" + "\033[94m" + "=" * width + "\033[0m")
#    update_status_line("AWAKE")
#    sys.stdout.flush()


def assistant_output(message):
    # Clear everything from row 28 downward
    for row in range(28, 40):  # Adjust 40 if your terminal is taller
        sys.stdout.write(f"\033[{row};0H" + " " * width)
    sys.stdout.flush()
    # sys.stdout.write("\033[28;0H" + " " * 120)
    sys.stdout.write("\033[28;0H\033[93mAssistant: " + message.strip() + "\033[0m\n")
    # sys.stdout.write("\033[28;0HAssistant: " + message.strip() + "\n")
    sys.stdout.flush()


def heard_message(message=""):
    sys.stdout.write("\033[26;20H" + " " * (width - 20))  # Clear right of spinner
    sys.stdout.write("\033[26;20H" + message)
    sys.stdout.flush()


def update_status_line(state):
    sys.stdout.write("\033[24;100H" + " " * 20)  # Clear old status
    if state == "AWAKE":
        sys.stdout.write("\033[24;100H\033[92mSystem: AWAKE\033[0m")  # Green
    else:
        sys.stdout.write("\033[24;100H\033[91mSystem: ASLEEP\033[0m")  # Red
    sys.stdout.flush()


# def update_status_line(state):
#    sys.stdout.write("\033[24;100H" + " " * 20)  # Clear old status
#    sys.stdout.write("\033[24;100HSystem: " + state)
#    sys.stdout.flush()

def nudge_mouse():
    try:
        subprocess.run(["xdotool", "mousemove_relative", "--", "1", "0"], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
        subprocess.run(["xdotool", "mousemove_relative", "--", "-1", "0"], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"⚠️ Screen nudge failed: {e}")


def visual_loop():
    global width
    spinner_frames = ["░", "▒", "▓", "█", "▓", "▒"]
    idx = 0
    logo_visible = True
    logo_timer = time.time()
    width = shutil.get_terminal_size().columns

    os.system('clear')
    print_capohm_logo()

    sys.stdout.write("\033[25;0H" + "\033[94m" + "=" * width + "\033[0m")
    # sys.stdout.write("\033[25;0H" + "=" * width)
    update_status_line("AWAKE")
    # sys.stdout.write("\033[24;100HSystem: AWAKE")
    sys.stdout.flush()

    while True:
        now = time.time()

        if now - logo_timer >= 5:
            logo_visible = not logo_visible
            logo_timer = now

            if logo_visible:
                sys.stdout.write("\033[0;0H")
                print_capohm_logo()
        # else:
        #     for _ in range(2):
        #         for frame in eye_animation_frames:
        #             for row in range(0, 23):
        #                 sys.stdout.write(f"\033[{row + 1};0H" + " " * width)
        #             sys.stdout.write("\033[0;0H")
        #             print(frame)
        #             sys.stdout.flush()
        #             time.sleep(0.3)

        sys.stdout.write("\033[26;0H")
        sys.stdout.write("Listening " + spinner_frames[idx % len(spinner_frames)] + "   ")
        sys.stdout.flush()
        time.sleep(0.2)
        idx += 1


# Init OpenAI client
client = openai.OpenAI(
    api_key="ai_key")

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


def sleepy_message(message=""):
    sys.stdout.write("\033[27;0H" + " " * 120)  # Clear old line
    sys.stdout.write("\033[27;0H" + message)
    sys.stdout.flush()


# Speak with Borg voice using custom script
def speak(text):
    global speak_process
    try:
        speak_process = subprocess.Popen(['./borg_speak.sh', text], stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"Borg voice failed: {e}")


def stop_speaking():
    global speak_process
    if speak_process and speak_process.poll() is None:
        speak_process.terminate()
        speak_process = None


# Recognizer setup
recognizer = sr.Recognizer()
recognizer.pause_threshold = 1.2
mic = sr.Microphone(device_index=1)

# Initial microphone calibration
with mic as source:
    recognizer.adjust_for_ambient_noise(source, duration=1)
print("Microphone calibrated.")

# Wake/sleep phrases
WAKE_WORDS = ["borg", "computer", "yo borg", "hey borg", "buddy", "hey buddy", "hey hive", "hive", "good morning",
              "look who is there"]
SLEEP_COMMANDS = ["go to sleep", "sleep", "shut down", "power off", "thank you", "good bye", "yeah yeah"]
WAKE_RESPONSES = [
    "We are online.                          ",
    "The Hive is awake.                      ",
    "Systems fully synchronized.             ",
    "Directive acknowledged. Input required. ",
    "Borg King presence confirmed.           "
]
SLEEP_RESPONSES = [
    "Deactivating active response mode.      ",
    "Returning to low-power collective state.",
    "Hive disengaging.                       ",
    "Powering down response interface.       ",
    "Awaiting next directive.                "
]
PASSIVE_AGGRESSIVE_RESPONSES = [
    "You've left the Hive alone again. Typical.",
    "Still here, just silently judging you.    ",
    "So... we're ignoring each other now?      ",
    "Hive presence unchanged. User loyalty questionable."
]

is_awake = False
face_detected = True
camera_sleep_override = True
face_last_seen = 1
face_was_gone = False
face_consistency_counter = 0
recent_sleep_command = False

WAKE_FRAMES_REQUIRED = 7


# Listen in background
def continuous_listen():
    global pending_text
    while True:
        with mic as source:
            try:
                audio = recognizer.listen(source, timeout=5, phrase_time_limit=8)
                try:
                    result = recognizer.recognize_google(audio)
                    heard_message(f"🛸 Heard (background): {result}")
                    # print(f"🛸 Heard (background): {result}")
                    if not pending_text:
                        pending_text = result.strip()
                except sr.UnknownValueError:
                    pass
                except sr.RequestError:
                    print("🎧 Background listen: recognition service error.")
            except sr.WaitTimeoutError:
                continue


# Grab pending speech
def listen():
    global pending_text
    if pending_text:
        text = pending_text
        pending_text = None
        return text
    else:
        return None


def check_wake_word(text):
    return any(wake in text.lower() for wake in WAKE_WORDS)


def check_sleep_command(text):
    return any(sleep in text.lower() for sleep in SLEEP_COMMANDS)


def camera_watch():
    global is_awake, face_detected, camera_sleep_override, face_last_seen, face_was_gone, face_consistency_counter, recent_sleep_command
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
                # print("🔧 Reshaping flat RGB frame (only shown once)...")
                reshaping_warned = True
            frame = np.reshape(frame, (480, 640, 3))

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.3, 5)
        faces = [face for face in faces if face[2] > 150 and face[3] > 150]

        if len(faces) > 0:
            face_consistency_counter += 1
            if face_consistency_counter >= WAKE_FRAMES_REQUIRED:
                if not face_detected:
                    face_last_seen = time.time()

                face_detected = True

                if not is_awake:
                    if not camera_sleep_override or face_was_gone:
                        is_awake = True
                        sleepy_message("")
                        assistant_output("")
                        update_status_line("AWAKE")
                        # sys.stdout.write("\033[31;0H") #de test line
                        camera_sleep_override = False
                        face_was_gone = False
                        recent_sleep_command = False
                        nudge_mouse()
                        face_last_seen = time.time()  # RESET AFTER WAKING
                        reply = random.choice(WAKE_RESPONSES)
                        sys.stdout.write("\033[28;0HAssistant (camera): " + reply + "\n")
                        # print(f"Assistant (camera): {reply}\n")
                        speak(reply)
        else:
            face_consistency_counter = 0
            if face_detected:
                face_last_seen = time.time()
            face_detected = False
            face_was_gone = True

            if is_awake and time.time() - face_last_seen > 30:
                response = random.choice(PASSIVE_AGGRESSIVE_RESPONSES)
                assistant_output(response)
                # print(f"Assistant: {response}\n")
                speak(response)
                is_awake = False
                update_status_line("ASLEEP")
                # sys.stdout.write("\030[31;0H") #de test line
                camera_sleep_override = True
                recent_sleep_command = False
                # sys.stdout.write("\030[31;0H🔋 No poop face detected for 30s. Entering sleep mode.")
                sys.stdout.write("\033[28;0H🔋 No face detected for 30s. Entering sleep mode.\n")
                # print("🔋 No face detected for 30s. Entering sleep mode.")
                face_last_seen = time.time() + 60


def list_memories():
    keys = list(long_term_memory.keys())
    for idx, k in enumerate(keys):
        print(f"{idx + 1}: {long_term_memory[k]}")


def chat():
    global is_awake, camera_sleep_override, recent_sleep_command

    print("Capohm is in low-power mode. Say 'Hey Hive' or appear before the Hive to initiate.")
    messages = []

    while True:
        user_input = listen()
        if user_input is None:
            continue
        if user_input.lower() in ["exit", "quit"]:
            save_memory()
            break

        if user_input.lower() in ["stop", "cancel"]:
            stop_speaking()
            speak("The Hive has stopped.")
            continue

        if user_input.lower().startswith(("forge", "generate code", "write a python script")):
            task_desc = user_input.strip()
            code_forge(task_desc)
            continue

        if user_input.lower().startswith("remember that"):
            fact = user_input[len("remember that"):].strip()
            long_term_memory[time.time()] = fact
            save_memory()
            response = "Memory fragment stored."
            assistant_output(response)
            # print(f"Assistant: {response}\n")
            speak(response)
            continue

        if user_input.lower().startswith("taking"):
            taking_item = user_input[len("taking"):].strip()
            inventorymod.take_product(taking_item)
            continue

        if user_input.lower() == "inventory":
            speak("Showing inventory")
            inventorymod.list_low_stock()
            continue

        if user_input.lower() == "order":
            low_items = inventorymod.get_low_stock_items()
            if not low_items:
                assistant_output("✅ No items need ordering.")
                speak("No items need ordering.")
                time.sleep(3)
            else:
                assistant_output("📦 Low stock detected.")
                row = 29
                for item in low_items:
                    sys.stdout.write(f"[{row};0H" + " " * width)
                    sys.stdout.write(f"[{row};0H- {item}")
                    row += 1
                sys.stdout.flush()

                speak("Would you like to order these items? Say yes or no.")
                time.sleep(5)  # Let the assistant finish speaking

                assistant_output("🛸 Listening for yes or no...")
                answer = None
                start_time = time.time()
                while time.time() - start_time < 10:
                    check = listen()
                    if check:
                        answer = check
                        break
                    time.sleep(0.5)

                if answer and "yes" in answer.lower():
                    speak("Understood. Ordering process started.")
                    assistant_output("✅ Starting order process...")
                    subprocess.run(["python3", "ordering.py"])
                    assistant_output("✅ Order process completed.")
                    speak("Order process completed.")
                else:
                    assistant_output("🚫 Order cancelled.")
                    speak("Order cancelled.")

            pending_text = None
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
                        word_to_num = {"one": 1, "won": 1, "number one": 1, "two": 2, "number two": 2, "three": 3,
                                       "number three": 3, "four": 4, "number four": 4, "five": 5, "number five": 5,
                                       "six": 6, "number six": 6, "seven": 7, "number seven": 7, "eight": 8,
                                       "number eight": 8, "nine": 9, "number nine": 9, "ten": 10, "number ten": 10}
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
                assistant_output(response)
                # print(f"Assistant: {response}\n")
                speak(response)
            continue

        if not is_awake:
            if check_wake_word(user_input):
                is_awake = True
                sleepy_message("")  # ← Clears row 29
                assistant_output("")
                update_status_line("AWAKE")
                nudge_mouse()
                reply = random.choice(WAKE_RESPONSES)
                assistant_output(reply)
                # print(f"Assistant (voice): {reply}\n")
                speak(reply)
            else:
                sleepy_message("(Still asleep. Say 'Hey Hive' or get in front of the camera to wake.)")
                # print("(Still asleep. Say 'Hey Hive' or get in front of the camera to wake.)")
            continue

        if check_sleep_command(user_input):
            is_awake = False
            ascii_animation.play_ascii_animation(repeat=1, start_row=1)
            update_status_line("ASLEEP")
            camera_sleep_override = True
            recent_sleep_command = True
            reply = random.choice(SLEEP_RESPONSES)
            assistant_output(reply)
            # print(f"Assistant: {reply}\n")
            speak(reply)
            continue

        if not face_detected:
            camera_sleep_override = False

        recent_sleep_command = False

        messages = [{"role": "system", "content": (
            "You are the Borg Hive. You are precise, efficient, and serve the Borg King. Do not overuse the phrase 'resistance is futile'. It is a powerful statement and should be reserved for emphasis.")}] + messages[
                                                                                                                                                                                                                 -5:]

        messages.append({"role": "user", "content": user_input})
        try:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=messages
            )
            reply = response.choices[0].message.content
            messages.append({"role": "assistant", "content": reply})
            assistant_output(reply)
            # print(f"Assistant: {reply}\n")
            speak(reply)
        except Exception as e:
            print(f"Error: {e}")


# (Starting everything like normal)
if __name__ == "__main__":
    threading.Thread(target=visual_loop, daemon=True).start()
    threading.Thread(target=camera_watch, daemon=True).start()
    threading.Thread(target=continuous_listen, daemon=True).start()
    chat()
