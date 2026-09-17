import threading
import time
from typing import Optional, List

try:
    import lgpio
    LGPIO_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    LGPIO_AVAILABLE = False


class SevenSegmentDisplay:
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

    def __init__(self, segment_pins, digit_pins, chip=0, refresh_delay=0.003, debug: bool = False):
        """
        segment_pins: Liste [a, b, c, d, e, f, g, dp] als GPIO-Nummern (BCM)
        digit_pins:   Liste [digit1, digit2, digit3, digit4] als GPIO-Nummern
        debug:        True = keine echten GPIO-Schreibvorgänge, stattdessen
                       Ausgabe ins Terminal (z.B. wenn kein Display angeschlossen ist,
                       egal ob lgpio verfügbar ist oder nicht)
        """
        if len(segment_pins) != 8:
            raise ValueError("segment_pins braucht genau 8 Einträge (a-g, dp)")
        if len(digit_pins) != 4:
            raise ValueError("digit_pins braucht genau 4 Einträge")

        self.segment_pins = segment_pins
        self.digit_pins = digit_pins
        self.refresh_delay = refresh_delay

        # Debug wird erzwungen, wenn explizit angefordert ODER wenn lgpio
        # gar nicht verfügbar ist (z.B. beim Testen auf dem Mac)
        self.debug = debug or not LGPIO_AVAILABLE

        if self.debug:
            reason = "explizit angefordert" if debug else "lgpio nicht verfügbar"
            print(f"[SevenSegmentDisplay] Debug-Modus aktiv ({reason}) - keine echte GPIO-Ausgabe")
            self._handle = None
        else:
            self._handle = lgpio.gpiochip_open(chip)
            for pin in self.segment_pins + self.digit_pins:
                lgpio.gpio_claim_output(self._handle, pin, 0)

        self._digits: List[Optional[int]] = [None, None, None, None]
        self._dots: List[bool] = [False, False, False, False]

        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

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
        """Zeigt eine 4-stellige Zahl an (führende Leerstellen statt Nullen bei Bedarf)."""
        s = f"{number:4d}" if -999 <= number <= 9999 else str(number)[-4:]
        with self._lock:
            for i, ch in enumerate(s.rjust(4)):
                self._digits[i] = int(ch) if ch.isdigit() else None

    def clear(self):
        with self._lock:
            self._digits = [None, None, None, None]
            self._dots = [False, False, False, False]

    def start(self):
        """Startet den Hintergrund-Thread, der die Anzeige aktuell hält."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._refresh_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)
        self._all_off()

    def close(self):
        self.stop()
        if not self.debug:
            lgpio.gpiochip_close(self._handle)

    # ---------- Intern ----------

    def _refresh_loop(self):
        while self._running:
            with self._lock:
                digits = list(self._digits)
                dots = list(self._dots)

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

        # alle Digit-Pins aus
        for pin in self.digit_pins:
            lgpio.gpio_write(self._handle, pin, 0)

        for pin, bit in zip(self.segment_pins, pattern):
            lgpio.gpio_write(self._handle, pin, bit)

        lgpio.gpio_write(self._handle, self.digit_pins[index], 1)

    def _all_off(self):
        if self.debug:
            print("[DEBUG] Alle Segmente aus")
            return
        for pin in self.segment_pins + self.digit_pins:
            lgpio.gpio_write(self._handle, pin, 0)

    # Context-Manager-Support (with-Statement)
    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()