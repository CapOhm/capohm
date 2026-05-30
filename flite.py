import cv2
import numpy as np
import tflite_runtime.interpreter as tflite

# Load labels
with open('imagenet_labels.txt', 'r') as f:
    labels = [line.strip() for line in f.readlines() if line.strip()]

# Clean up labels to remove HTML or SVG artifacts
cleaned_labels = []
for label in labels:
    if '<' in label and '>' in label:
        cleaned_labels.append('unknown')
    else:
        cleaned_labels.append(label)

# Initialize the interpreter
interpreter = tflite.Interpreter(model_path="mobilenet_v1_1.0_224.tflite")
interpreter.allocate_tensors()

# Get input & output details
input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()

# Initialize camera
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

print("Press 'q' to quit.")

# List of items to look out for
target_items = ['crow', 'raven', 'blackbird', 'lighter', 'cigarette lighter', 'remote control', 'telephone', 'cellular telephone', 'dial telephone', 'pay-phone', 'mobile phone', 'zippo']

while True:
    ret, frame = cap.read()
    if not ret or frame is None:
        print("Failed to grab frame")
        break

    # Handle flat frames (reshape if needed)
    if frame.ndim == 2 and frame.shape == (1, 921600):
        print("🔧 Detected flat frame with shape (1, 921600), reshaping to (480, 640, 3)...")
        frame = np.reshape(frame, (480, 640, 3))
    elif frame.ndim == 1 and frame.size == 921600:
        print("🔧 Detected 1D flat frame with size 921600, reshaping to (480, 640, 3)...")
        frame = np.reshape(frame, (480, 640, 3))

    # Preprocess for MobileNet
    input_shape = input_details[0]['shape']
    frame_resized = cv2.resize(frame, (input_shape[1], input_shape[2]))
    input_data = np.expand_dims(frame_resized, axis=0).astype(np.float32) / 127.5 - 1

    # Run inference
    interpreter.set_tensor(input_details[0]['index'], input_data)
    interpreter.invoke()

    # Get predictions
    output_data = interpreter.get_tensor(output_details[0]['index'])
    top_idx = np.argmax(output_data)
    label = cleaned_labels[top_idx]

    # Show result
    print(f"Detected: {label}")
    for item in target_items:
        if item in label.lower():
            print(f"🚨 Detected target item: {item.upper()} 🚨")
            break

    # Show frame
    frame_display = cv2.resize(frame, (640, 480))
    cv2.imshow('Crow Detector', frame_display)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
