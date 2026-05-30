import pytesseract
import cv2
import numpy as np
import pyautogui
import time
import os

custom_config = r'--oem 3 --psm 6'
target_word = "geluid"  # <- Word we want to click!

def zoom_image(img, scale=2.0):
    height, width = img.shape[:2]
    new_size = (int(width * scale), int(height * scale))
    return cv2.resize(img, new_size, interpolation=cv2.INTER_LINEAR)

def capture_screen_cv():
    screenshot = pyautogui.screenshot()
    return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)

def find_text_position(img_cv, search_word):
    zoomed = zoom_image(img_cv, scale=2.0)
    gray = cv2.cvtColor(zoomed, cv2.COLOR_BGR2GRAY)

    data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT, config=custom_config)

    for i in range(len(data['text'])):
        word = data['text'][i].strip().lower()
        if word == search_word.lower():
            x = data['left'][i] // 2  # adjust for zoom
            y = data['top'][i] // 2
            w = data['width'][i] // 2
            h = data['height'][i] // 2
            center_x = x + w // 2
            center_y = y + h // 2
            return (center_x, center_y)

    return None

def main():
    print("🔎 Searching for:", target_word)
    time.sleep(2)

    while True:
        img = capture_screen_cv()
        pos = find_text_position(img, target_word)

        if pos:
            print(f"✅ Found '{target_word}' at {pos}")
            pyautogui.moveTo(pos[0], pos[1], duration=0.5)
            pyautogui.click()
            print("🖱️ Clicked!")
            break
        else:
            print(".", end="", flush=True)

        time.sleep(2)

if __name__ == "__main__":
    main()
