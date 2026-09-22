import serial


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