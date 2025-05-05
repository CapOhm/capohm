## Hi there 👋

capohm/
├── chat_dev.py
├── crow_detector.py
├── ordering.py
├── inventorymod.py
├── borg_speak.sh
├── images/
│   └── bestel.png ...
├── requirements.txt
├── README.md

# Capohm Setup

## 1️⃣ Install dependencies:
sudo apt update
sudo apt install python3-opencv python3-pyaudio espeak portaudio19-dev
pip install -r requirements.txt

shell
Copy
Edit

## 2️⃣ Enable camera:
Ensure your Pi's camera interface is enabled.

## 3️⃣ Run:
python3 chat_dev.py

markdown
Copy
Edit

## 🔧 Notes:
- Crow detection model: place your `best.pt` file in the correct path.
- Audio test: `arecord -d 5 test.wav && aplay test.wav`
✅ On a new Pi:
You just:

1️⃣ git clone https://github.com/yourname/capohm.git
2️⃣ cd capohm
3️⃣ pip install -r requirements.txt
4️⃣ Follow README and boom 🚀.

# 🛠️ Capohm Setup Guide

This repo contains the Capohm assistant and its modules (voice, vision, crow detection, inventory management, ordering, and more).

---

## 🚀 Quick Install (Raspberry Pi)

### 1️⃣ Install system packages:

```bash
sudo apt update
sudo apt install python3-opencv python3-pyaudio espeak portaudio19-dev tesseract-ocr xdotool


<!--
**CapOhm/capohm** is a ✨ _special_ ✨ repository because its `README.md` (this file) appears on your GitHub profile.

Here are some ideas to get you started:

- 🔭 I’m currently working on ...
- 🌱 I’m currently learning ...
- 👯 I’m looking to collaborate on ...
- 🤔 I’m looking for help with ...
- 💬 Ask me about ...
- 📫 How to reach me: ...
- 😄 Pronouns: ...
- ⚡ Fun fact: ...
-->
