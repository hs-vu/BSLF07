import serial
import threading


class ledcontroller:
    def __init__(self, port="/dev/ttyACM0", baudrate=9600):
        # write_timeout: falls der Arduino mal nicht abnimmt, blockiert der Pi nicht ewig
        self.ser = serial.Serial(port, baudrate, timeout=1, write_timeout=1)
        self.ledstate = 0
        # Idle-Thread und Spiel-Logik schreiben beide auf die LEDs
        self._lock = threading.Lock()

        # Bit-Zuordnung: Index 0-3 = grüne LEDs, Index 0-3 = gelbe LEDs
        # Passe die Zahlen an, falls deine Verkabelung anders ist.
        self._green_bits = [1, 3, 5, 7]
        self._yellow_bits = [0, 2, 4, 6]

    def enableGreenLED(self, index):
        self._set_bit(self._green_bits[index])

    def enableYellowLED(self, index):
        self._set_bit(self._yellow_bits[index])

    def disableGreenLED(self, index):
        self._clear_bit(self._green_bits[index])

    def disableYellowLED(self, index):
        self._clear_bit(self._yellow_bits[index])

    def disableAllLED(self):
        with self._lock:
            self.ledstate = 0
            self.__send_byte(self.ledstate)

    def show_feedback(self, guess: list, secret: list):
        """
        Auswertung pro Stelle:
        - grün = richtige Ziffer an richtiger Stelle
        - gelb = Ziffer kommt im Code vor, aber an anderer Stelle
        - aus  = Ziffer kommt im Code gar nicht vor

        Gelb leuchtet auch dann, wenn dieselbe Ziffer an einer anderen
        Stelle schon grün ist (z.B. Code [1,2,3,4], Eingabe [1,1,5,6]
        -> Stelle 0 grün, Stelle 1 gelb).
        """
        if len(guess) != 4 or len(secret) != 4:
            raise ValueError("guess und secret müssen je 4 Elemente haben")

        result = []
        for i in range(4):
            if guess[i] == secret[i]:
                result.append("green")
            elif guess[i] in secret:
                result.append("yellow")
            else:
                result.append("off")

        new_state = 0
        for i, r in enumerate(result):
            if r == "green":
                new_state |= (1 << self._green_bits[i])
            elif r == "yellow":
                new_state |= (1 << self._yellow_bits[i])

        with self._lock:
            self.ledstate = new_state
            self.__send_byte(self.ledstate)
        return result

    def _set_bit(self, bit_index):
        with self._lock:
            self.ledstate = self.ledstate | (1 << bit_index)
            self.__send_byte(self.ledstate)

    def _clear_bit(self, bit_index):
        with self._lock:
            self.ledstate = self.ledstate & ~(1 << bit_index) & 0xFF
            self.__send_byte(self.ledstate)

    def __send_byte(self, byte_val: int):
        if not (0 <= byte_val <= 255):
            raise ValueError("byte_val muss zwischen 0 und 255 liegen")
        try:
            # Evtl. Antworten vom Arduino verwerfen, damit kein Puffer volläuft
            if self.ser.in_waiting:
                self.ser.reset_input_buffer()
            self.ser.write(bytes([byte_val]))
        except serial.SerialException as e:
            print(f"LED-Update fehlgeschlagen: {e}")

    def close(self):
        self.ser.close()