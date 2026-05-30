import time
import sys
import os

spinner_frames = [
    "     ( o )     ",
    "     ( O )     ",
    "     ( @ )     ",
    "     ( O )     ",
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
    print("\n" * 2)  # Two lines below logo

def startup_screen():
    spinner_frames = ["░", "▒", "▓", "█", "▓", "▒"]
    idx = 0

    os.system('clear')
    print_capohm_logo()
    time.sleep(5)
    for _ in range(2):  # Spin for 2 full cycles
        for frame in spinner_frames:
            print("\033[1;0H")  # Always reset cursor
            print(frame)
            time.sleep(0.2)

    # Print the divider and status exactly once
    sys.stdout.write("\033[25;0H" + "="*146)
    sys.stdout.write("\033[24;115HSystem: AWAKE")
    sys.stdout.flush()

    while True:
        sys.stdout.write("\033[26;0H")  # Move cursor to line 21, start of output
        sys.stdout.write("Listening " + spinner_frames[idx % len(spinner_frames)] + "   ")
        sys.stdout.flush()
        time.sleep(0.2)
        idx += 1

try:
    startup_screen()
except KeyboardInterrupt:
    print("\n[Capohm Spinner Stopped]")
