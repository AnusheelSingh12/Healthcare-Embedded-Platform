// Esp_32_MedAccess_Final

// Pins
const int trigPin  = 5;
const int echoPin  = 18;
const int leds[]   = {19, 21, 22};  // LED1, LED2, LED3
const int buzzer   = 23;

// State
bool          accidentOccurred = false;
unsigned long accidentTime     = 0;
const long    RESET_INTERVAL   = 10000;  // 10 s auto-reset


unsigned long lastSirenUpdate = 0;
int sirenFreq = 800;
bool sirenIncreasing = true;


void setup() {
  Serial.begin(115200);

  pinMode(trigPin, OUTPUT);
  pinMode(echoPin, INPUT);
  pinMode(buzzer,  OUTPUT);
  for (int i = 0; i < 3; i++) pinMode(leds[i], OUTPUT);

  // Self-test blink
  for (int i = 0; i < 3; i++) {
    digitalWrite(leds[i], HIGH);
    delay(150);
    digitalWrite(leds[i], LOW);
  }

  Serial.println("Access Point Started");
  Serial.println("MedAccess Serial Edition ready");
  Serial.println("Waiting for ultrasonic trigger (<5 cm)...");
}


void loop() {
  unsigned long now = millis();


  if (accidentOccurred) {
    updateSiren();
  }

  // Auto-reset
  if (accidentOccurred && (now - accidentTime >= RESET_INTERVAL)) {
    resetSystem();
    return;
  }

  // Sensor check
  if (!accidentOccurred) {
    digitalWrite(trigPin, LOW);
    delayMicroseconds(2);
    digitalWrite(trigPin, HIGH);
    delayMicroseconds(10);
    digitalWrite(trigPin, LOW);

    long duration = pulseIn(echoPin, HIGH, 30000);
    float distance = duration * 0.034 / 2.0;

    if (distance > 0 && distance < 5) {
      triggerEmergency(now);
    }
  }

  delay(50);
}


void updateSiren() {
  unsigned long now = millis();

  if (now - lastSirenUpdate >= 20) {
    lastSirenUpdate = now;

    if (sirenIncreasing) {
      sirenFreq += 20;
      if (sirenFreq >= 1500) sirenIncreasing = false;
    } else {
      sirenFreq -= 20;
      if (sirenFreq <= 800) sirenIncreasing = true;
    }

    tone(buzzer, sirenFreq);
  }
}


void triggerEmergency(unsigned long ts) {
  accidentOccurred = true;
  accidentTime     = ts;

  int h = random(1, 4);

  digitalWrite(leds[h - 1], HIGH);



  Serial.println("Emergency Broadcast Sent: LED" + String(h));
}

// ============================================================
void resetSystem() {
  accidentOccurred = false;

  noTone(buzzer);

  for (int i = 0; i < 3; i++) {
    digitalWrite(leds[i], LOW);
  }

  Serial.println("System Reset");
}