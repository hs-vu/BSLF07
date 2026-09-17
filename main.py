import numpad
import display
import random

pad = numpad.Numpad()
#screen = display.SevenSegmentDisplay()

print("Programm gestartet und pad verbunden :)")

code:list[int] = [0,0,0,0]
guessed_code:list[int] = [0,0,0,0]
code_index:int = 0
tries:int = 4

for x in range(0,4,1):
    code[x] = random.randint(0,9)

def wildcard(x):
    global code_index
    if code_index <= 2:
        guessed_code[code_index] = x
        code_index += 1
        return
    else:
        print(guessed_code)
        code_index = 0

pad.registerWildcard(wildcard)

print(code)