import atexit
import signal
import threading
import time
from typing import Optional, List

try:
    import lgpio
    LGPIO_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    LGPIO_AVAILABLE = False

try:
    import pigpio
    PIGPIO_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    PIGPIO_AVAILABLE = False


class SevenSegmentDisplay:
    """
    Ansteuerung eines rohen (treiberlosen) 4-Digit-7-Segment-Displays per
    Software-Multiplexing.

    backend:
      "lgpio"  - Standard, nutzt das lgpio-Kernelmodul direkt. Funktioniert
                 immer, aber jeder gpio_write()-Aufruf hat Syscall-Overhead -
                 bei 12+ Schreibvorgängen pro Refresh-Zyklus kann das auf
                 langsameren Systemen/unter Last zu Jitter/Flackern führen.
      "pigpio" - Nutzt den pigpio-Daemon. Braucht `sudo pigpiod` laufend im
                 Hintergrund (siehe unten). Schreibvorgänge laufen über einen
                 Sockel zum Daemon, der die Pins mit Hardware-Timing bedient -
                 spürbar ruhigeres Bild, da weniger Jitter durch den
                 Python-/Linux-Scheduler.

    Optimierung ggü. der ersten Version: pro Refresh-Zyklus wird nur noch der
    VORHER aktive Digit-Pin ausgeschaltet statt aller vier - spart 3 von 4
    unnötigen Schreibvorgängen pro Durchlauf.
    """

    # Segment-Reihenfolge: a, b, c, d, e, f, g, dp
    DIGIT_PATTERNS = {
        0: (1, 1, 1, 1, 1, 1, 0, 0),
        1: (0, 1, 1, 0, 0, 0, 0, 0),
        2: (1, 1, 0, 1, 1, 0, 1, 0),
        3: (1, 1, 1, 1, 0, 0, 1, 0),
        4: (0, 1, 1, 0, 0, 1, 1, 0),
        5: (1, 0, 1, 1, 0, 1, 1, 0),
        6: (1, 0, 1, 1, 1, 1, 1, 0),
        7: (1, 1, 1, 0, 0, 0, 0, 0),
        8: (1, 1, 1, 1, 1, 1, 1, 0),
        9: (1, 1, 1, 1, 0, 1, 1, 0),
        None: (0, 0, 0, 0, 0, 0, 0, 0),  # aus/leer
    }

    def __init__(self, segment_pins, digit_pins, chip=0, refresh_delay=0.003,
                 debug: bool = False, digit_active_high: bool = True,
                 segment_active_high: bool = True, backend: str = "lgpio"):
        """
        segment_pins: Liste [a, b, c, d, e, f, g, dp] als GPIO-Nummern (BCM)
        digit_pins:   Liste [digit1, digit2, digit3, digit4] als GPIO-Nummern
        debug:        True = keine echten GPIO-Schreibvorgänge, stattdessen
                       Ausgabe ins Terminal.
        digit_active_high: True (Standard) = Digit-Pin auf 1 aktiviert die Ziffer.
                       False = Digit-Pin muss auf 0 gezogen werden (Common Cathode).
        segment_active_high: True (Standard) = Segment-Pin auf 1 schaltet das
                       Segment an.
        backend:      "lgpio" (Standard) oder "pigpio" (braucht laufenden
                       pigpiod-Daemon, dafür ruhigeres Timing).
        """
        if len(segment_pins) != 8:
            raise ValueError("segment_pins braucht genau 8 Einträge (a-g, dp)")
        if len(digit_pins) != 4:
            raise ValueError("digit_pins braucht genau 4 Einträge")
        if backend not in ("lgpio", "pigpio"):
            raise ValueError('backend muss "lgpio" oder "pigpio" sein')

        self.segment_pins = segment_pins
        self.digit_pins = digit_pins
        self.refresh_delay = refresh_delay
        self.digit_active_high = digit_active_high
        self.segment_active_high = segment_active_high
        self.backend = backend

        # Debug wird erzwungen, wenn explizit angefordert ODER wenn das
        # gewählte Backend gar nicht verfügbar ist (z.B. beim Testen auf dem Mac)
        backend_available = LGPIO_AVAILABLE if backend == "lgpio" else PIGPIO_AVAILABLE
        self.debug = debug or not backend_available

        self._handle = None   # lgpio chip handle
        self._pi = None       # pigpio.pi() Instanz

        segment_off_level = 0 if self.segment_active_high else 1
        digit_off_level = 1 if self.digit_active_high else 0

        if self.debug:
            if debug:
                reason = "explizit angefordert"
            else:
                reason = f"Backend '{backend}' nicht verfügbar"
            print(f"[SevenSegmentDisplay] Debug-Modus aktiv ({reason}) - keine echte GPIO-Ausgabe")
        elif backend == "lgpio":
            self._handle = lgpio.gpiochip_open(chip)
            for pin in self.segment_pins:
                lgpio.gpio_claim_output(self._handle, pin, segment_off_level)
            for pin in self.digit_pins:
                lgpio.gpio_claim_output(self._handle, pin, digit_off_level)
        else:  # pigpio
            self._pi = pigpio.pi()
            if not self._pi.connected:
                raise RuntimeError(
                    "Konnte nicht mit pigpiod verbinden. Läuft der Daemon? "
                    "Starten mit: sudo systemctl start pigpiod  (oder: sudo pigpiod)"
                )
            for pin in self.segment_pins:
                self._pi.set_mode(pin, pigpio.OUTPUT)
                self._pi.write(pin, segment_off_level)
            for pin in self.digit_pins:
                self._pi.set_mode(pin, pigpio.OUTPUT)
                self._pi.write(pin, digit_off_level)

        self._digits: List[Optional[int]] = [None, None, None, None]
        self._dots: List[bool] = [False, False, False, False]

        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_active_digit: Optional[int] = None  # für reduzierte Writes

        self._blinking = False
        self._blink_visible = True
        self._blink_thread: Optional[threading.Thread] = None

        # Sicherstellen, dass close() auch bei Strg+C / SIGTERM / normalem
        # Programmende aufgerufen wird, damit keine Ziffer statisch anbleibt.
        atexit.register(self.close)
        try:
            signal.signal(signal.SIGTERM, self._handle_signal)
            signal.signal(signal.SIGINT, self._handle_signal)
        except ValueError:
            # signal.signal() funktioniert nur im Main-Thread
            pass

    def _handle_signal(self, signum, frame):
        self.close()
        signal.signal(signum, signal.SIG_DFL)
        signal.raise_signal(signum)

    # ---------- Öffentliche API ----------

    def set_digit(self, position: int, value: Optional[int]):
        """value: 0-9 oder None für leer. position: 0-3"""
        if not (0 <= position <= 3):
            raise ValueError("position muss 0-3 sein")
        if value is not None and not (0 <= value <= 9):
            raise ValueError("value muss 0-9 oder None sein")
        with self._lock:
            self._digits[position] = value

    def set_dot(self, position: int, on: bool):
        if not (0 <= position <= 3):
            raise ValueError("position muss 0-3 sein")
        with self._lock:
            self._dots[position] = on

    def set_number(self, number: int):
        """Zeigt eine 4-stellige Zahl an (führende Leerstellen bei Bedarf)."""
        s = f"{number:4d}" if -999 <= number <= 9999 else str(number)[-4:]
        with self._lock:
            for i, ch in enumerate(s.rjust(4)):
                self._digits[i] = int(ch) if ch.isdigit() else None

    def clear(self):
        with self._lock:
            self._digits = [None, None, None, None]
            self._dots = [False, False, False, False]

    def blink(self, interval: float = 0.5):
        """
        Lässt die aktuell angezeigten Zahlen im festen Zeitabstand
        blinken (an -> aus -> an -> ...), bis end_blink() aufgerufen wird.
        Die zugrunde liegenden Werte (set_digit/set_number) bleiben davon
        unberührt - es wird nur die Sichtbarkeit periodisch umgeschaltet.

        interval: Zeit in Sekunden zwischen den Umschaltungen
                   (0.5 = Zahl 0.5s an, dann 0.5s aus, usw.)
        """
        if self._blinking:
            return
        self._blinking = True
        self._blink_thread = threading.Thread(
            target=self._blink_loop, args=(interval,), daemon=True
        )
        self._blink_thread.start()

    def end_blink(self):
        """Beendet das Blinken; die Zahlen bleiben danach dauerhaft sichtbar."""
        self._blinking = False
        if self._blink_thread:
            self._blink_thread.join(timeout=1)
            self._blink_thread = None
        with self._lock:
            self._blink_visible = True

    def _blink_loop(self, interval: float):
        while self._blinking:
            time.sleep(interval)
            with self._lock:
                self._blink_visible = not self._blink_visible

    def start(self):
        """Startet den Hintergrund-Thread, der die Anzeige aktuell hält."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._refresh_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._blinking = False
        if self._blink_thread:
            self._blink_thread.join(timeout=1)
            self._blink_thread = None
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)
        self._all_off()

    def close(self):
        if getattr(self, "_closed", False):
            return
        self._closed = True
        self.stop()
        if not self.debug:
            if self.backend == "lgpio" and self._handle is not None:
                lgpio.gpiochip_close(self._handle)
            elif self.backend == "pigpio" and self._pi is not None:
                self._pi.stop()

    # ---------- Intern: GPIO-Zugriff, backend-unabhängig ----------

    def _write(self, pin: int, level: int):
        if self.backend == "lgpio":
            lgpio.gpio_write(self._handle, pin, level)
        else:
            self._pi.write(pin, level)

    # ---------- Intern: Multiplexing ----------

    def _refresh_loop(self):
        while self._running:
            with self._lock:
                visible = self._blink_visible
                digits = list(self._digits) if visible else [None, None, None, None]
                dots = list(self._dots) if visible else [False, False, False, False]

            for i in range(4):
                self._show_single_digit(i, digits[i], dots[i])
                time.sleep(self.refresh_delay)

    def _show_single_digit(self, index: int, value: Optional[int], dot: bool):
        pattern = list(self.DIGIT_PATTERNS[value])
        if dot:
            pattern[7] = 1

        if self.debug:
            print(f"[DEBUG] Digit {index}: value={value} dot={dot} pattern={pattern}")
            return

        digit_off_level = 1 if self.digit_active_high else 0
        digit_on_level = 0 if digit_off_level == 1 else 1

        # Nur den VORHER aktiven Digit-Pin ausschalten (nicht alle 4) -
        # spart 3 unnötige Writes pro Zyklus gegenüber "alle aus, dann einen an"
        if self._last_active_digit is not None and self._last_active_digit != index:
            self._write(self.digit_pins[self._last_active_digit], digit_off_level)

        for pin, bit in zip(self.segment_pins, pattern):
            level = bit if self.segment_active_high else (1 - bit)
            self._write(pin, level)

        self._write(self.digit_pins[index], digit_on_level)
        self._last_active_digit = index

    def _all_off(self):
        if self.debug:
            print("[DEBUG] Alle Segmente aus")
            return
        digit_off_level = 1 if self.digit_active_high else 0
        segment_off_level = 0 if self.segment_active_high else 1
        for pin in self.segment_pins:
            self._write(pin, segment_off_level)
        for pin in self.digit_pins:
            self._write(pin, digit_off_level)
        self._last_active_digit = None

    # Context-Manager-Support (with-Statement)
    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

class SingleDigitDisplay:
    """
    Ansteuerung einer einzelnen 7-Segment-Ziffer direkt über GPIO.
    Kein Multiplexing nötig, da nur eine Ziffer - die Segmente werden
    einmal gesetzt und bleiben statisch an, bis sich der Wert ändert.
    """
 
    # Segment-Reihenfolge: a, b, c, d, e, f, g, dp
    DIGIT_PATTERNS = {
        0: (1, 1, 1, 1, 1, 1, 0, 0),
        1: (0, 1, 1, 0, 0, 0, 0, 0),
        2: (1, 1, 0, 1, 1, 0, 1, 0),
        3: (1, 1, 1, 1, 0, 0, 1, 0),
        4: (0, 1, 1, 0, 0, 1, 1, 0),
        5: (1, 0, 1, 1, 0, 1, 1, 0),
        6: (1, 0, 1, 1, 1, 1, 1, 0),
        7: (1, 1, 1, 0, 0, 0, 0, 0),
        8: (1, 1, 1, 1, 1, 1, 1, 0),
        9: (1, 1, 1, 1, 0, 1, 1, 0),
        None: (0, 0, 0, 0, 0, 0, 0, 0),  # aus/leer
    }
 
    def __init__(self, segment_pins, chip=0, debug: bool = False,
                 segment_active_high: bool = True):
        """
        segment_pins: Liste [a, b, c, d, e, f, g, dp] als GPIO-Nummern (BCM)
        debug:        True = keine echten GPIO-Schreibvorgänge, stattdessen
                       Ausgabe ins Terminal.
        segment_active_high: True (Standard) = Segment-Pin auf 1 schaltet das
                       Segment an. False, falls dein Display umgekehrt gepolt ist
                       (z.B. bei Common Cathode mit invertierter Logik).
        """
        if len(segment_pins) != 8:
            raise ValueError("segment_pins braucht genau 8 Einträge (a-g, dp)")
 
        self.segment_pins = segment_pins
        self.segment_active_high = segment_active_high
        self.debug = debug or not LGPIO_AVAILABLE
 
        self._handle = None
        self._value: Optional[int] = None
        self._dot = False
        self._lock = threading.Lock()
 
        self._blinking = False
        self._blink_visible = True
        self._blink_thread: Optional[threading.Thread] = None
 
        if self.debug:
            reason = "explizit angefordert" if debug else "lgpio nicht verfügbar"
            print(f"[SingleDigitDisplay] Debug-Modus aktiv ({reason}) - keine echte GPIO-Ausgabe")
        else:
            self._handle = lgpio.gpiochip_open(chip)
            off_level = 0 if self.segment_active_high else 1
            for pin in self.segment_pins:
                lgpio.gpio_claim_output(self._handle, pin, off_level)
 
        # Sicherstellen, dass close() auch bei Strg+C / SIGTERM / normalem
        # Programmende aufgerufen wird, damit keine Ziffer statisch anbleibt.
        atexit.register(self.close)
        try:
            signal.signal(signal.SIGTERM, self._handle_signal)
            signal.signal(signal.SIGINT, self._handle_signal)
        except ValueError:
            pass
 
    def _handle_signal(self, signum, frame):
        self.close()
        signal.signal(signum, signal.SIG_DFL)
        signal.raise_signal(signum)
 
    # ---------- Öffentliche API ----------
 
    def set_digit(self, value: Optional[int]):
        """value: 0-9 oder None für leer/aus."""
        if value is not None and not (0 <= value <= 9):
            raise ValueError("value muss 0-9 oder None sein")
        with self._lock:
            self._value = value
        self._render()
 
    def set_dot(self, on: bool):
        with self._lock:
            self._dot = on
        self._render()
 
    def clear(self):
        self.set_digit(None)
 
    def stop(self):
        """Schaltet die Anzeige aus (alle Segmente aus, Blinken wird beendet),
        ohne den GPIO-Handle zu schließen - das Display kann danach mit
        set_digit() sofort wieder genutzt werden."""
        self._blinking = False
        if self._blink_thread:
            self._blink_thread.join(timeout=1)
            self._blink_thread = None
        self._blink_visible = True
        with self._lock:
            self._value = None
            self._dot = False
        self._render()
 
    def blink(self, interval: float = 0.5):
        """Lässt die aktuell angezeigte Ziffer im festen Abstand blinken,
        bis end_blink() aufgerufen wird."""
        if self._blinking:
            return
        self._blinking = True
        self._blink_thread = threading.Thread(
            target=self._blink_loop, args=(interval,), daemon=True
        )
        self._blink_thread.start()
 
    def end_blink(self):
        self._blinking = False
        if self._blink_thread:
            self._blink_thread.join(timeout=1)
            self._blink_thread = None
        self._blink_visible = True
        self._render()
 
    def close(self):
        if getattr(self, "_closed", False):
            return
        self._closed = True
        self.stop()
        if not self.debug and self._handle is not None:
            lgpio.gpiochip_close(self._handle)
 
    # ---------- Intern ----------
 
    def _blink_loop(self, interval: float):
        while self._blinking:
            time.sleep(interval)
            self._blink_visible = not self._blink_visible
            self._render()
 
    def _render(self):
        with self._lock:
            value = self._value if self._blink_visible else None
            dot = self._dot if self._blink_visible else False
 
        pattern = list(self.DIGIT_PATTERNS[value])
        if dot:
            pattern[7] = 1
 
        if self.debug:
            print(f"[DEBUG] value={value} dot={dot} pattern={pattern}")
            return
 
        for pin, bit in zip(self.segment_pins, pattern):
            level = bit if self.segment_active_high else (1 - bit)
            lgpio.gpio_write(self._handle, pin, level)
 
    # Context-Manager-Support (with-Statement)
    def __enter__(self):
        return self
 
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()