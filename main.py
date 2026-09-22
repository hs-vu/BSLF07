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

code: list[int] = [0, 0, 0, 0]
guessed_code: list[int] = [0, 0, 0, 0]
code_index: int = 0
tries: int = 4

IDLE_CHANGE_INTERVAL = .5   # Sekunden zwischen Zahlenwechseln im Idle-Modus
WRONG_GUESS_HOLD_TIME = 3    # wie lange Blinken + LED-Feedback bei Falscheingabe angezeigt wird
CORRECT_GUESS_BLINK_TIME = 1.5
CORRECT_CODE_DISPLAY_HOLD = 2  # wie lange der richtige Code danach ruhig stehen bleibt

idle_active = False              # einfaches Flag: läuft der Idle-Modus gerade?
idle_stop_event = threading.Event()   # NUR zum sofortigen Aufwecken beim Beenden
idle_thread: threading.Thread | None = None


def updateScreen():
    global guessed_code
    i = 0
    for number in guessed_code:
        screen.set_digit(i, number)
        i += 1


def run_led_test():
    for x in range(0, 4, 1):
        led.enableGreenLED(x)
        time.sleep(0.1)
    for x in range(0, 4, 1):
        led.enableYellowLED(x)
        time.sleep(0.1)
    led.disableAllLED()


def start_new_round():
    """Generiert einen neuen Code, setzt Rateversuch + Anzeige zurück."""
    global code, guessed_code, code_index, tries
    code = [random.randint(0, 9) for _ in range(4)]
    mqtt.report_answer(code)
    guessed_code = [0, 0, 0, 0]
    code_index = 0
    tries = 4

    updateScreen()
    singlescreen.set_digit(tries)
    print(f"Neuer Code generiert: {code}")


def idle_loop():
    """Läuft im Hintergrund, solange idle_active True ist - lässt die
    4-stellige Anzeige langsam zufällige Ziffern durchwechseln."""
    while idle_active:
        for i in range(4):
            screen.set_digit(i, random.randint(0, 9))
        # idle_stop_event.wait() statt time.sleep() - wartet die volle
        # IDLE_CHANGE_INTERVAL Zeit ab, kehrt aber SOFORT zurück, falls
        # exit_idle_and_restart() währenddessen das Stop-Signal setzt
        # (gibt True zurück, wenn wegen des Signals geweckt, sonst False
        # nach Ablauf des Timeouts - beides führt hier einfach zur
        # nächsten Prüfung von idle_active oben in der while-Bedingung)
        idle_stop_event.wait(timeout=IDLE_CHANGE_INTERVAL)


def enter_idle():
    """Startet den Idle-Screensaver (langsam zufällig wechselnde Zahlen)."""
    global idle_active, idle_thread
    if idle_active:
        return
    print("Idle-Modus gestartet")
    led.disableAllLED()
    singlescreen.stop()
    idle_active = True
    idle_stop_event.clear()
    idle_thread = threading.Thread(target=idle_loop, daemon=True)
    idle_thread.start()


def exit_idle_and_restart():
    """Wird durch einen Tastendruck während des Idle-Modus ausgelöst:
    Screensaver stoppen, kurz alles aus, LED-Test, neue Runde starten."""
    global idle_active, idle_thread
    print("Aufgewacht - starte neue Runde")

    idle_active = False
    idle_stop_event.set()   # weckt idle_loop() sofort aus dem Warten auf
    if idle_thread:
        idle_thread.join(timeout=1)
        idle_thread = None

    # einmal alles aus
    screen.stop()
    singlescreen.stop()
    led.disableAllLED()
    time.sleep(0.3)

    # Anzeige wieder aktivieren, LED-Testlauf
    screen.start()
    run_led_test()

    # neue Runde: zuerst 0000 anzeigen, dann normaler Ablauf wie gehabt
    start_new_round()


def wildcard(x):
    global code_index, tries, guessed_code

    # Falls gerade Idle-Modus läuft: dieser Tastendruck weckt nur auf,
    # zählt NICHT als Ratewert
    if idle_active:
        exit_idle_and_restart()
        return

    print("Wildcard aufgerufen")
    guessed_code[code_index] = x
    code_index += 1
    updateScreen()

    if code_index > 3:
        print(guessed_code)
        if guessed_code == code:
            # Richtig geraten - alle LEDs grün als Bestätigung, kurz feiern
            for i in range(4):
                led.enableGreenLED(i)
            screen.blink(0.1)
            time.sleep(CORRECT_GUESS_BLINK_TIME)
            screen.end_blink()
            led.disableAllLED()

            # Den richtigen Code jetzt noch kurz RUHIG (ohne Blinken) stehen
            # lassen, bevor der Screensaver übernimmt
            updateScreen()
            time.sleep(CORRECT_CODE_DISPLAY_HOLD)

            print("Code geknackt! Gehe in Idle-Modus.")
            enter_idle()
            return

        # Falsch geraten - Wordle-Style-Feedback auf den LEDs anzeigen
        result = led.show_feedback(guessed_code, code)
        print(f"Feedback: {result}")

        screen.blink(0.5)
        time.sleep(WRONG_GUESS_HOLD_TIME)
        screen.end_blink()
        led.disableAllLED()

        guessed_code = [0, 0, 0, 0]
        updateScreen()

        tries -= 1
        singlescreen.set_digit(tries)
        print(f"Noch {tries} Versuche")
        code_index = 0

        if tries <= 0:
            print("Keine Versuche mehr übrig. Gehe in Idle-Modus.")
            enter_idle()


pad.registerWildcard(wildcard)

# Erste Runde starten
run_led_test()
start_new_round()

print(code)

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("Beende Programm...")
finally:
    idle_active = False
    idle_stop_event.set()
    if idle_thread:
        idle_thread.join(timeout=1)
    pad.stop()
    screen.close()
    singlescreen.close()
    led.close()