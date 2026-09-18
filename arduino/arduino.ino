const int ledPins[8] = {4, 5, 6, 7, 8, 9, 10, 11};

void setup() {
  for (int i = 0; i<8;i++)
  {
    pinMode(ledPins[i], OUTPUT);
    digitalWrite(ledPins[i], LOW);
  }
  Serial.begin(9600);
}

void loop() {
  if (Serial.available() > 0) {
    byte data = Serial.read();
    
    for (int i = 0; i < 8; i++) {
      bool on = bitRead(data, 7 - i);
      digitalWrite(ledPins[i], on ? HIGH : LOW);
    }

    Serial.print("Empfangenes Byte: ");
    Serial.println(data, BIN);
  }
}
