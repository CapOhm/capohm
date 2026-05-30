import cv2
from ultralytics import YOLO
import time
import os


model = YOLO('/home/terry/capohm/best.pt')  # ✅ Update your path

cap = cv2.VideoCapture(0)
cap.set(3, 640)
cap.set(4, 480)

if not cap.isOpened():
    print("🚫 Failed to open camera.")
    exit()

#print("✅ Crow detector started. Press 'q' to quit.")

last_detection_time = 0
cooldown = 5  # seconds between warnings
frame_counter = 0
detect_every_n_frames = 20  # ~3 seconds at 30 FPS

while True:
    ret, frame = cap.read()
    if not ret:
        print("⚠️ Failed to grab frame.")
        break

    # --- Reshape if needed ---
    if frame is not None and frame.shape == (1, 921600):
        frame = frame.reshape((480, 640, 3))

    frame_counter += 1

    if frame_counter % detect_every_n_frames == 0:
        print("🔍 Running crow detection...")
        results = model(frame, verbose=False)

        # Draw results
        annotated_frame = results[0].plot()

        # Check detections
        found_crow = False
        for detection in results[0].boxes.data:
            class_id = int(detection[5])
            class_name = model.names[class_id].lower()
            if "crow" in class_name:
                found_crow = True
                break

        if found_crow:
            now = time.time()
            if now - last_detection_time > cooldown:
                print("🪶 Crow detected! Warning sounded.")
                # 🔊 Play a quick warning using espeak:
                os.system("espeak 'Warning! Crow detected.'")
                last_detection_time = now

    else:
        # Just show unannotated frame between detections
        annotated_frame = frame

    cv2.imshow("Crow Detector", annotated_frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        print("🛑 'q' pressed, exiting.")
        break

cap.release()
cv2.destroyAllWindows()
print("✅ Camera and windows closed.")
