import pygame
import numpy as np
import pyaudio
import audioop

# Settings
CHUNK = 1024
SAMPLERATE = 44100
FPS = 30

# Initialize Pygame display
def init_display():
    pygame.init()
    screen = pygame.display.set_mode((800, 480), pygame.FULLSCREEN)
    pygame.display.set_caption("HAL9000 Visualizer")
    return screen

# Draw HAL eye
def draw_hal_eye(screen, amplitude):
    screen.fill((255, 255, 255))  # TEMP: white background to verify visibility
    center = (screen.get_width() // 2, screen.get_height() // 2)
    base_radius = 60
    radius = int(base_radius + amplitude * 2)
    pygame.draw.circle(screen, (180, 0, 0), center, radius)
    pygame.draw.circle(screen, (255, 0, 0), center, int(radius * 0.7))
    pygame.draw.circle(screen, (255, 200, 200), center, int(radius * 0.2))
    pygame.display.flip()
    print(f"Amplitude: {amplitude:.3f}")  # TEMP: print amplitude to terminal


# Visualize PulseAudio monitor output
def visualize_live_audio():
    screen = init_display()
    clock = pygame.time.Clock()

    pa = pyaudio.PyAudio()

    print("Available audio devices:")
    for i in range(pa.get_device_count()):
        dev = pa.get_device_info_by_index(i)
        print(f"[{i}] {dev['name']} (Input Channels: {dev['maxInputChannels']})")

    try:
        index = int(input("\nEnter the index of the audio monitor to use: "))
    except ValueError:
        print("Invalid input.")
        return

    stream = pa.open(
        format=pyaudio.paInt16,
        channels=2,
        rate=SAMPLERATE,
        input=True,
        input_device_index=index,
        frames_per_buffer=CHUNK
    )

    try:
        while True:
            data = stream.read(CHUNK, exception_on_overflow=False)
            rms = audioop.rms(data, 2)
            amplitude = rms / 32768.0

            draw_hal_eye(screen, amplitude)
            for event in pygame.event.get():
                if event.type == pygame.QUIT or (
                    event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE
                ):
                    raise KeyboardInterrupt

            clock.tick(FPS)

    except KeyboardInterrupt:
        pass
    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()
        pygame.quit()

if __name__ == "__main__":
    visualize_live_audio()
