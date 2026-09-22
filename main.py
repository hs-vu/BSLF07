import numpad
import display
import LEDs
import random
import sys
import time 

pad = numpad.Numpad()
screen = display.SevenSegmentDisplay([2,3,4,17,27,22,0,5], [6,13,19,26],digit_active_high=True)
screen.start()
led = LEDs.ledcontroller(port="/dev/ttyACM0", baudrate=9600)
singlescreen = display.SingleDigitDisplay([1,12,25,18,20,21,23,24])
singlescreen.set_digit(8)
time.sleep(2)

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
singlescreen.set_digit(tries)


for x in range (0,4,1):
    led.enableGreenLED(x)
    time.sleep(0.1)
for x in range (0,4,1):
    led.enableYellowLED(x)
    time.sleep(0.1)
led.disableAllLED()

for x in range(0,4,1):
    code[x] = random.randint(0,9)

def wildcard(x):
    global code_index, tries, guessed_code
    print("Wildcard aufgerufen")
    guessed_code[code_index] = x
    code_index += 1
    updateScreen()
    if code_index > 3:
        print(guessed_code)
        if guessed_code != code:
            screen.blink(0.5)
            time.sleep(3)
            screen.end_blink()
            guessed_code = [0,0,0,0]
            updateScreen()
        else:
            screen.blink(0.1)
            time.sleep(1)
            screen.end_blink()
        tries -= 1
        singlescreen.set_digit(tries)
        print(f"Noch {tries} Versuche")
        code_index = 0

pad.registerWildcard(wildcard)

print(code)

while tries > 0:
    time.sleep(1)

print("Loop verlassen")
pad.stop()
screen.stop()
led.close()
sys.exit()
print("???")