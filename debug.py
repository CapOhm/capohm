import pytesseract
import pyautogui
import time
import cv2
import numpy as np

def zoom_image(img, scale=2.0):
    width = int(img.shape[1] * scale)
    height = int(img.shape[0] * scale)
    return cv2.resize(img, (width, height), interpolation=cv2.INTER_LINEAR)

def capture_and_read():
    screenshot = pyautogui.screenshot()
    img_np = np.array(screenshot)
    img_cv = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)

    zoomed_img = zoom_image(img_cv, scale=2.0)

    # Show the zoomed image for inspection
    cv2.imshow('Zoomed Screenshot', zoomed_img)
    cv2.waitKey(1)

    text = pytesseract.image_to_string(zoomed_img)

    interesting_words = ["Order", "Add to Cart", "Checkout", "Product", "Login", "Quantity"]
    found = any(word.lower() in text.lower() for word in interesting_words)

    if found:
        print("\n✨ Interesting detected! ✨")
        print(text)
    else:
        print(".", end="", flush=True)

while True:
    capture_and_read()
    time.sleep(3)
