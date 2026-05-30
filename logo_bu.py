import time
import sys
import os

def print_capohm_logo():
    logo = """
                                           =@%. .+@*             
                                     .-%-..#@@@%@@@@:.:#+.       
                                     .#@@@@@@@@@@@@@@@@@@.       
                                  :*--@@@@:-%@%#%@@+.%@@@*:+=    
                                 .*@@@@#-%-. .+:+. ..%+=@@@@%.   
                                  .@@@-%-    .%:%.    .%:@@@:    
                               .%@@@@+@:     .%:%.     .@=@@@@@: 
                               .-@@@@=%      .%:%.      .**@@@+. 
                                 .@@@=%*******@:%********%=@@=   
                               .%@@@@-@.     .%:%.     .*+%@@@@- 
                               .:=#@@#++     .%:%.     :@+@@%+-. 
                                  .@@@@=%:.  .%:%.   .**+@@@:    
                                 .@@@@@@*=%*:......+%+=@@@@@@-   
                                  ....*@@@%*#     *%-@@@@. ..    
                                     .@@@@@+%     ##+@@@@.       
                                     .#######     *%###%%-             
"""
    print(logo)
    print("\n" * 2)  # Two lines below logo

def startup_screen():
    spinner_frames = ["░", "▒", "▓", "█", "▓", "▒"]
    idx = 0

    os.system('clear')
    print_capohm_logo()

    # Print the divider and status exactly once
    sys.stdout.write("\033[19;0H" + "="*97)
    sys.stdout.write("\033[20;83HSystem: AWAKE")
    sys.stdout.flush()

    while True:
        sys.stdout.write("\033[20;0H")  # Move cursor to line 21, start of output
        sys.stdout.write("Listening " + spinner_frames[idx % len(spinner_frames)] + "   ")
        sys.stdout.flush()
        time.sleep(0.2)
        idx += 1

try:
    startup_screen()
except KeyboardInterrupt:
    print("\n[Capohm Spinner Stopped]")
