# camera.py

import cv2
import numpy as np
import time
import random
from speech import speak
from config import WAKE_RESPONSES, PASSIVE_AGGRESSIVE_RESPONSES

# Global state
is_awake = False
face_detected = False
camera_sleep_override = False
face_last_seen = 0
face_was_gone = False

def camera_watch(update_awake_callback):
    global is_awake, face_detected, camera_sleep_override, face_last_seen, face_was_gone

    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 15)

    if not cap.isOpened():
        print("❌ Failed to open camera.")
        return

    reshaping_warned = False
    print("📸 Camera feed started successfully.")

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
                update_awake_callback(True)

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
                is_awake = False
                update_awake_callback(False)

def get_face_status():
    return face_detected
