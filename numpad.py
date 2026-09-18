import adafruit_matrixkeypad
import board
import digitalio
import threading
import typing
import time

class Numpad:
    def __init__(self):
        rows = []
        coloumns = []
        self.events:dict[int,list[callable]] = {}
        self.wildcard:callable

        for x in range(0,10,1):
            self.events[x] = []

        for x in (board.D14, board.D15, board.D10, board.D9):
            rows.append(digitalio.DigitalInOut(x))

        for x in (board.D16, board.D11, board.D8, board.D7):
            coloumns.append(digitalio.DigitalInOut(x))

        keys = ((1,2,3,"A"), (4,5,6,"B"), (7,8,9,"C"), ("*",0,"#","D"))

        self.keypad = adafruit_matrixkeypad.Matrix_Keypad(rows, coloumns, keys)
        self.old_pressed = [10]

        self.thread = threading.Thread(target=self.check)
        self.thread.start()

    def check(self):
        while True:
            time.sleep(0.2)
            pressed = self.keypad.pressed_keys
    
            if pressed and not pressed == self.old_pressed:
                self.old_pressed = pressed
                if type(pressed[0]) == type(0):
                    for func in self.events[pressed[0]]:
                        func()
                    try:
                        self.wildcard(pressed[0])
                    except Exception:
                        pass
            if not pressed:
                self.old_pressed = [10]

    def register(self, func:callable, num:int):
        self.events[num].append(func)

    def registerWildcard(self, func:callable):
        self.wildcard = func

    def stop(self):
        self.thread.join(timeout=1)

if __name__ == "__main__":
    numpad = Numpad()