import numpad
import display
import random
import sys
import time 

pad = numpad.Numpad()
screen = display.SevenSegmentDisplay([2,3,4,17,27,22,0,5], [6,13,19,26],digit_active_high=True)

print("Programm gestartet und pad verbunden :)")

code:list[int] = [0,0,0,0]
guessed_code:list[int] = [0,0,0,0]
code_index:int = 0
tries:int = 4

def updateScreen():
    global guessed_code
    i = 0
    for number in guessed_code:
        screen.set_digit(i,number)
        i+=1

updateScreen()
screen.start()


for x in range(0,4,1):
    code[x] = random.randint(0,9)

def wildcard(x):
    global code_index, tries
    guessed_code[code_index] = x
    code_index += 1
    updateScreen()
    if code_index > 3:
        print(guessed_code)
        if guessed_code != code:
            screen.blink(0.2)
            time.sleep(1.5)
            screen.end_blink()
        tries -= 1
        code_index = 0

pad.registerWildcard(wildcard)

print(code)

while tries >= 0:
    time.sleep(1)

sys.exit()