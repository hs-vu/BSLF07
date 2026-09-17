import display
import time

screen = display.SevenSegmentDisplay([2,3,4,17,27,22,0,5], [6,13,19,26],digit_active_high=True)

timer = 60
screen.set_number(timer)
screen.start()

while timer > 0:
    time.sleep(1)
    timer -= 1
    screen.set_number(timer)