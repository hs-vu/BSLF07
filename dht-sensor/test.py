import time
import board
import digitalio

test_pin = digitalio.DigitalInOut(board.D16)
test_pin.direction = digitalio.Direction.INPUT
test_pin.pull = digitalio.Pull.UP

while True:
    print(test_pin.value)
    time.sleep(.5)
