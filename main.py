import numpad
import display
import LEDs
import MQTT
import random
import threading
import time

pad = numpad.Numpad()
screen = display.SevenSegmentDisplay([2, 3, 4, 17, 27, 22, 0, 5], [6, 13, 19, 26], digit_active_high=True)
screen.start()
led = LEDs.ledcontroller(port="/dev/ttyACM0", baudrate=9600)
mqtt = MQTT.MqttReporter("192.168.188.90")
singlescreen = display.SingleDigitDisplay([1, 12, 25, 18, 20, 21, 23, 24])
singlescreen.set_digit(8)
time.sleep(2)

print("Programm gestartet und pad verbunden :)")

# ---------------- Einstellungen ----------------
IDLE_CHANGE_INTERVAL = .5         # 4-stellige Anzeige: Sekunden zwischen Zahlenwechseln
IDLE_SINGLE_INTERVAL = 2.0        # Einzelziffer: Sekunden zwischen Zahlenwechseln
IDLE_LED_INTERVAL = 0.4           # LEDs: Sekunden zwischen zufälligem An/Aus
WRONG_GUESS_HOLD_TIME = 3         # Blinken + Wordle-Feedback bei Falscheingabe
CORRECT_GUESS_BLINK_TIME = 1.5    # Feier-Blinken bei richtigem Code
CORRECT_CODE_DISPLAY_HOLD = 2     # richtiger Code bleibt danach ruhig stehen
SOLUTION_DISPLAY_TIME = 3         # Lösung anzeigen, wenn alle Versuche aufgebraucht sind
IDLE_TIMEOUT = 30                 # Sekunden ohne Tastendruck, bis Idle startet
FEEDBACK_SHOW_TIME = 1.5          # gewählte Bewertung kurz anzeigen

# ---------------- Zustände ----------------
STATE_PLAYING = "playing"
STATE_FEEDBACK = "feedback"
STATE_IDLE = "idle"
STATE_BUSY = "busy"   # Animation/Test läuft - Tastendrücke werden ignoriert

state = STATE_BUSY
state_lock = threading.Lock()

code: list[int] = [0, 0, 0, 0]
guessed_code: list[int] = [0, 0, 0, 0]
code_index: int = 0
tries: int = 4

last_input_time: float = time.monotonic()

idle_stop_event = threading.Event()
idle_thread: threading.Thread | None = None
shutdown_event = threading.Event()


reported_status: str | None = None


def report_status(new_state):
    """Per MQTT gibt es nur zwei Zustände: 'idle', solange der Idle-Loop
    läuft, sonst 'busy' (jemand ist an der Station). Gesendet wird nur,
    wenn sich der gemeldete Zustand ändert."""
    global reported_status
    status = "idle" if new_state == STATE_IDLE else "busy"
    if status != reported_status:
        reported_status = status
        mqtt.report_status(status)


def set_state(new_state):
    global state
    with state_lock:
        state = new_state
        report_status(new_state)


def try_transition(expected, new_state) -> bool:
    """Wechselt nur dann den Zustand, wenn er aktuell 'expected' ist.
    Verhindert, dass z.B. Feedback-Timeout und Tastendruck gleichzeitig
    denselben Übergang auslösen."""
    global state
    with state_lock:
        if state != expected:
            return False
        state = new_state
        report_status(new_state)
    return True


# ---------------- Anzeige-Helfer ----------------

def show_on_screen(digits):
    for i, number in enumerate(digits):
        screen.set_digit(i, number)


def all_off():
    screen.clear()
    singlescreen.stop()
    led.disableAllLED()


def run_led_test():
    for x in range(4):
        led.enableGreenLED(x)
        time.sleep(0.1)
    for x in range(4):
        led.enableYellowLED(x)
        time.sleep(0.1)
    led.disableAllLED()


def run_startup_tests():
    """Kurzer Selbsttest aller Anzeigen: alle Segmente an, dann LED-Lauf."""
    for i in range(4):
        screen.set_digit(i, 8)
        screen.set_dot(i, True)
    singlescreen.set_digit(8)
    singlescreen.set_dot(True)
    time.sleep(1)

    run_led_test()

    for i in range(4):
        screen.set_dot(i, False)
    singlescreen.set_dot(False)
    all_off()
    time.sleep(0.3)


# ---------------- Spielrunde ----------------

def start_new_round():
    global code, guessed_code, code_index, tries
    code = random.sample(range(10), 4)   # jede Ziffer nur einmal
    mqtt.report_answer(code)
    guessed_code = [0, 0, 0, 0]
    code_index = 0
    tries = 4

    show_on_screen(guessed_code)
    singlescreen.set_digit(tries)
    print(f"Neuer Code generiert: {code}")
    reset_inactivity()
    set_state(STATE_PLAYING)


def handle_guess_digit(x):
    global code_index, tries, guessed_code

    guessed_code[code_index] = x
    code_index += 1
    show_on_screen(guessed_code)

    if code_index <= 3:
        return

    set_state(STATE_BUSY)
    print(guessed_code)
    mqtt.report_guess(list(guessed_code))

    if guessed_code == code:
        for i in range(4):
            led.enableGreenLED(i)
        screen.blink(0.1)
        time.sleep(CORRECT_GUESS_BLINK_TIME)
        screen.end_blink()
        led.disableAllLED()

        show_on_screen(code)
        time.sleep(CORRECT_CODE_DISPLAY_HOLD)

        print("Code geknackt!")
        enter_feedback()
        return

    # Falsch geraten - Wordle-Style-Feedback
    result = led.show_feedback(guessed_code, code)
    print(f"Feedback: {result}")

    screen.blink(0.5)
    time.sleep(WRONG_GUESS_HOLD_TIME)
    screen.end_blink()
    led.disableAllLED()

    tries -= 1
    singlescreen.set_digit(tries)
    print(f"Noch {tries} Versuche")
    code_index = 0
    guessed_code = [0, 0, 0, 0]

    if tries <= 0:
        print(f"Keine Versuche mehr. Lösung war {code}")
        show_on_screen(code)
        time.sleep(SOLUTION_DISPLAY_TIME)
        start_new_round()
        return

    show_on_screen(guessed_code)
    set_state(STATE_PLAYING)


# ---------------- Feedback (1-5) ----------------

def enter_feedback():
    """Nach richtigem Code: Bewertung 1-5 per Numpad abfragen.
    Anzeige: '1  5' als Hinweis auf den Bereich, Einzelziffer blinkt."""
    show_on_screen([1, None, None, 5])
    singlescreen.set_digit(None)
    singlescreen.set_dot(True)
    singlescreen.blink(0.4)

    print("Bitte Feedback 1-5 eingeben")
    reset_inactivity()
    set_state(STATE_FEEDBACK)


def handle_feedback(rating: int):
    singlescreen.end_blink()
    singlescreen.set_dot(False)
    singlescreen.set_digit(rating)
    screen.clear()

    mqtt.report_feedback(rating)
    print(f"Feedback erhalten: {rating}")
    time.sleep(FEEDBACK_SHOW_TIME)
    enter_idle()


# ---------------- Inaktivität ----------------

def reset_inactivity():
    global last_input_time
    last_input_time = time.monotonic()


def inactivity_watchdog():
    """Geht in den Idle-Modus, wenn beim Spielen oder bei der Bewertung
    IDLE_TIMEOUT Sekunden lang keine Taste gedrückt wurde."""
    while not shutdown_event.wait(timeout=0.5):
        with state_lock:
            current = state
        if current not in (STATE_PLAYING, STATE_FEEDBACK):
            continue
        if time.monotonic() - last_input_time < IDLE_TIMEOUT:
            continue
        if try_transition(current, STATE_BUSY):
            print(f"{IDLE_TIMEOUT}s keine Eingabe - gehe in Idle-Modus")
            enter_idle()


# ---------------- Idle-Modus ----------------

def idle_loop():
    """Animiert alle drei Anzeigen unabhängig voneinander, jeweils mit
    eigenem Intervall."""
    leds_on = {("green", i): False for i in range(4)}
    leds_on.update({("yellow", i): False for i in range(4)})

    next_digits = next_single = next_led = 0.0

    while not idle_stop_event.is_set():
        now = time.monotonic()

        if now >= next_digits:
            for i in range(4):
                screen.set_digit(i, random.randint(0, 9))
            next_digits = now + IDLE_CHANGE_INTERVAL

        if now >= next_single:
            singlescreen.set_digit(random.randint(0, 9))
            next_single = now + IDLE_SINGLE_INTERVAL

        if now >= next_led:
            key = random.choice(list(leds_on.keys()))
            color, index = key
            if leds_on[key]:
                (led.disableGreenLED if color == "green" else led.disableYellowLED)(index)
            else:
                (led.enableGreenLED if color == "green" else led.enableYellowLED)(index)
            leds_on[key] = not leds_on[key]
            next_led = now + IDLE_LED_INTERVAL

        # Kleiner Takt; kehrt sofort zurück, wenn stop_idle() das Event setzt
        idle_stop_event.wait(timeout=0.05)


def enter_idle():
    global idle_thread
    print("Idle-Modus gestartet")
    led.disableAllLED()
    singlescreen.end_blink()
    singlescreen.set_dot(False)

    idle_stop_event.clear()
    idle_thread = threading.Thread(target=idle_loop, daemon=True)
    idle_thread.start()
    set_state(STATE_IDLE)


def stop_idle():
    global idle_thread
    idle_stop_event.set()
    if idle_thread:
        idle_thread.join(timeout=1)
        idle_thread = None


def wake_up():
    """Tastendruck im Idle: alles aus, Tests, neue Runde."""
    print("Aufgewacht - starte neue Runde")
    stop_idle()

    screen.stop()
    all_off()
    time.sleep(0.5)

    screen.start()
    run_startup_tests()
    start_new_round()


# ---------------- Numpad-Eingang ----------------

def wildcard(x):
    reset_inactivity()
    with state_lock:
        current = state

    if current == STATE_IDLE:
        if try_transition(STATE_IDLE, STATE_BUSY):
            wake_up()
        return

    if current == STATE_FEEDBACK:
        if 1 <= x <= 5 and try_transition(STATE_FEEDBACK, STATE_BUSY):
            handle_feedback(x)
        return

    if current == STATE_PLAYING:
        handle_guess_digit(x)

    # STATE_BUSY: Eingabe ignorieren


pad.registerWildcard(wildcard)
threading.Thread(target=inactivity_watchdog, daemon=True).start()

# ---------------- Start ----------------
run_startup_tests()
start_new_round()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("Beende Programm...")
finally:
    shutdown_event.set()
    stop_idle()
    pad.stop()
    screen.close()
    singlescreen.close()
    led.close()
    mqtt.close()