import time
import sys
import os
import shutil

# Define your "animation frames"
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
    print(logo)
    print("\n" * 2)

def play_animation(frames, width, repeat=2, delay=0.3):
    for _ in range(repeat):
        for frame in frames:
            # Clear old frame (only top)
            for row in range(0, 23):
                sys.stdout.write(f"\033[{row + 1};0H" + " " * width)
            sys.stdout.flush()

            # Draw new frame
            sys.stdout.write("\033[0;0H")
            print(frame)
            sys.stdout.flush()
            time.sleep(delay)

def startup_screen():
    spinner_frames = ["░", "▒", "▓", "█", "▓", "▒"]
    idx = 0
    logo_visible = True
    logo_timer = time.time()

    os.system('clear')
    print_capohm_logo()

    width = shutil.get_terminal_size().columns

    # Divider and status
    sys.stdout.write("\033[25;0H" + "=" * width)
    sys.stdout.write("\033[24;115HSystem: AWAKE")
    sys.stdout.flush()

    while True:
        now = time.time()

        if now - logo_timer >= 5:
            logo_visible = not logo_visible
            logo_timer = now

            if logo_visible:
                sys.stdout.write("\033[0;0H")
                print_capohm_logo()
            else:
                # Play the little "eye" animation instead of blank
                play_animation(eye_animation_frames, width)

        # Spinner always running
        sys.stdout.write("\033[26;0H")
        sys.stdout.write("Listening " + spinner_frames[idx % len(spinner_frames)] + "   ")
        sys.stdout.flush()
        time.sleep(0.2)
        idx += 1

try:
    startup_screen()
except KeyboardInterrupt:
    print("\n[Capohm Animation Stopped]")
