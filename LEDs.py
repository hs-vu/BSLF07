import serial
from collections import Counter


class ledcontroller:
    def __init__(self, port="/dev/ttyACM0", baudrate=9600):
        self.ser = serial.Serial(port, baudrate, timeout=1)
        self.ledstate = 0

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
        self.ledstate = 0
        self.__send_byte(self.ledstate)

    def show_feedback(self, guess: list, secret: list):
        """
        Wordle-Style-Auswertung: pro Stelle wird die passende LED gesetzt.
        - grün  = richtige Ziffer an richtiger Stelle
        - gelb  = Ziffer kommt im Code vor, aber an anderer Stelle
        - aus   = Ziffer kommt im Code gar nicht (mehr) vor

        Behandelt doppelte Ziffern korrekt (wie beim echten Wordle):
        z.B. secret=[1,1,2,3], guess=[1,4,1,1]
        -> Stelle 0: grün (1 an richtiger Stelle)
        -> Stelle 2: gelb (1 kommt noch vor, an anderer Stelle) - aber nur
           EINMAL gelb, da die zweite '1' im Code schon durch die grüne
           Stelle 0 "verbraucht" ist
        -> Stelle 3: aus (keine 1 mehr übrig zum Zuordnen)
        """
        if len(guess) != 4 or len(secret) != 4:
            raise ValueError("guess und secret müssen je 4 Elemente haben")

        result = [None] * 4
        remaining = Counter(secret)

        # 1. Durchgang: exakte Treffer (grün) zuerst, damit die richtige
        #    Anzahl an "verbrauchten" Ziffern für den Gelb-Durchgang übrig bleibt
        for i in range(4):
            if guess[i] == secret[i]:
                result[i] = "green"
                remaining[guess[i]] -= 1

        # 2. Durchgang: vorhandene, aber falsch platzierte Ziffern (gelb)
        for i in range(4):
            if result[i] is None:
                if remaining[guess[i]] > 0:
                    result[i] = "yellow"
                    remaining[guess[i]] -= 1
                else:
                    result[i] = "off"

        new_state = 0
        for i, r in enumerate(result):
            if r == "green":
                new_state |= (1 << self._green_bits[i])
            elif r == "yellow":
                new_state |= (1 << self._yellow_bits[i])

        self.ledstate = new_state
        self.__send_byte(self.ledstate)
        return result

    def _set_bit(self, bit_index):
        self.ledstate = self.ledstate | (1 << bit_index)
        self.__send_byte(self.ledstate)

    def _clear_bit(self, bit_index):
        self.ledstate = self.ledstate & ~(1 << bit_index) & 0xFF
        self.__send_byte(self.ledstate)

    def __send_byte(self, byte_val: int):
        if not (0 <= byte_val <= 255):
            raise ValueError("byte_val muss zwischen 0 und 255 liegen")
        self.ser.write(bytes([byte_val]))

    def close(self):
        self.ser.close()