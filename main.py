import numpad

pad = numpad.Numpad()

def print9():
    print("9 wurde gedrückt :D")

pad.register(print9,9)
