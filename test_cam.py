import cv2
import numpy as np

cap = cv2.VideoCapture(0)
cap.set(3, 640)
cap.set(4, 480)

if not cap.isOpened():
    print("🚫 Failed to open camera.")
    exit()

print("✅ Camera preview started. Press 'q' to quit.")

reshaping_warned = False

while True:
    ret, frame = cap.read()
    if not ret:
        break

    # 🔧 Reshape if it’s a flat buffer
    if frame is not None and frame.shape == (1, 921600):
        if not reshaping_warned:
            print("🔧 Reshaping flat RGB frame (only shown once)...")
            reshaping_warned = True
        frame = np.reshape(frame, (480, 640, 3))

    cv2.imshow("Quick Camera Preview", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
print("✅ Camera preview closed.")
