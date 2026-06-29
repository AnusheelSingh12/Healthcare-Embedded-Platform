#include <SPI.h>
#include <MFRC522.h>
#include <RTClib.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>

// --- PIN DEFINITIONS ---
#define SS_PIN    5
#define RST_PIN   4
#define BUZZER    26
#define RED_LED   27
#define GRN_LED   14
#define BTN_RESET 13 // Button 1
#define BTN_ADD   12 // Button 2 - "Add Tool" Toggle

#define MAX_TOOLS 10

MFRC522 mfrc522(SS_PIN, RST_PIN);
RTC_DS3231 rtc;
LiquidCrystal_I2C lcd(0x27, 16, 2);

// --- GLOBAL STATE ---
bool registrationMode = false;
int toolsOutCount = 0;
int totalGauzeUsed = 0;

struct Tool {
  String uid;
  String name;
  String shortName; // For LCD display
  bool isOut;
  bool isConsumable; 
};

// Hardcoded Tool Inventory
Tool inventory[MAX_TOOLS] = {
  {"4D055B06", "Gauze Pack", "Gauze", false, true},
  {"426F3406", "Kidney Tray", "K-Tray", false, false},
  {"D3CCF605", "Straight Artery Forceps", "StrArt", false, false},
  {"EEF73206", "Curved Artery Forceps", "CrvArt", false, false},
  {"ACA54A06", "Scalpel", "Scalpl", false, false},
  {"D1663806", "Forceps", "Frcp  ", false, false}
};

int toolInventoryCount = 6; 
String lastScannedUid = "";
unsigned long lastScanMs = 0;
const unsigned long SCAN_DEBOUNCE_MS = 1500;

// --- JSON EMITTER ---
void emitJson(String uid, String name, String action, String timestamp) {
  Serial.print("{");
  Serial.print("\"UID\":\"" + uid + "\",");
  Serial.print("\"item_name\":\"" + name + "\",");
  Serial.print("\"action\":\"" + action + "\",");
  Serial.print("\"timestamp\":\"" + timestamp + "\",");
  Serial.print("\"gauze_count\":" + String(totalGauzeUsed) + ",");
  Serial.print("\"tools_missing\":" + String(toolsOutCount));
  Serial.println("}");
}

void setup() {
  Serial.begin(9600);
  SPI.begin();
  mfrc522.PCD_Init();
  lcd.init();
  lcd.backlight();

  pinMode(BUZZER, OUTPUT);
  pinMode(RED_LED, OUTPUT);
  pinMode(GRN_LED, OUTPUT);
  pinMode(BTN_RESET, INPUT_PULLUP);
  pinMode(BTN_ADD, INPUT_PULLUP);

  if (!rtc.begin()) {
    lcd.print("RTC ERROR");
    while (1);
  }

  if (rtc.lostPower()) {
    rtc.adjust(DateTime(F(__DATE__), F(__TIME__)));
  }

  updateLEDs();
  lcd.clear();
  lcd.print("SYSTEM ONLINE");
  delay(1000);
  updateLCDStatus();
}

void loop() {
  DateTime now = rtc.now();
  String timestamp = now.timestamp(DateTime::TIMESTAMP_FULL);

  // 1. Button 2: Toggle Add Tool Mode
  if (digitalRead(BTN_ADD) == LOW) {
    registrationMode = !registrationMode;
    lcd.clear();
    lcd.print(registrationMode ? "MODE: ADD TOOL" : "MODE: NORMAL");
    tone(BUZZER, 1000, 200);
    delay(800); // Debounce
    updateLCDStatus();
  }

  // 2. Normal Mode Functions
  if (!registrationMode) {
    // Button 1: System Reset
    if (digitalRead(BTN_RESET) == LOW) {
      handleReset(timestamp);
    }
  }

  // 3. RFID Scanning Logic
  if (mfrc522.PICC_IsNewCardPresent() && mfrc522.PICC_ReadCardSerial()) {
    String uid = "";
    for (byte i = 0; i < mfrc522.uid.size; i++) {
      uid += String(mfrc522.uid.uidByte[i] < 0x10 ? "0" : "");
      uid += String(mfrc522.uid.uidByte[i], HEX);
    }
    uid.toUpperCase();

    if (uid == lastScannedUid && (millis() - lastScanMs < SCAN_DEBOUNCE_MS)) return;
    lastScannedUid = uid;
    lastScanMs = millis();

    if (registrationMode) {
      registerTool(uid);
    } else {
      processScan(uid, timestamp);
    }

    mfrc522.PICC_HaltA();
    mfrc522.PCD_StopCrypto1();
  }
}

void processScan(String uid, String time) {
  for (int i = 0; i < toolInventoryCount; i++) {
    if (inventory[i].uid == uid) {
      if (inventory[i].isConsumable) {
        totalGauzeUsed++;
        lcd.clear();
        lcd.print(inventory[i].shortName + " USED");
        lcd.setCursor(0, 1);
        lcd.print("TOTAL: " + String(totalGauzeUsed));
        emitJson(uid, inventory[i].name, "CONSUMED", time);
        tone(BUZZER, 2000, 150);
      } 
      else {
        inventory[i].isOut = !inventory[i].isOut;
        lcd.clear();
        lcd.print(inventory[i].shortName);
        lcd.setCursor(8, 0); 
        lcd.print(inventory[i].isOut ? "[OUT]" : "[IN]");

        if (inventory[i].isOut) {
          toolsOutCount++;
          emitJson(uid, inventory[i].name, "TOOL_OUT", time);
          tone(BUZZER, 800, 200);
        } else {
          if (toolsOutCount > 0) toolsOutCount--;
          emitJson(uid, inventory[i].name, "TOOL_IN", time);
          tone(BUZZER, 1200, 200);
        }
      }
      updateLEDs();
      delay(2000);
      updateLCDStatus();
      return;
    }
  }
  lcd.clear(); lcd.print("UNKNOWN ID");
  emitJson(uid, "Unknown", "UNKNOWN_SCAN", time);
  tone(BUZZER, 400, 500);
  delay(1000);
  updateLCDStatus();
}

void registerTool(String uid) {
  if (toolInventoryCount >= MAX_TOOLS) return;
  inventory[toolInventoryCount] = {uid, "New Item", "NewItm", false, false};
  toolInventoryCount++;
  lcd.clear();
  lcd.print("REGISTERED:");
  lcd.setCursor(0,1);
  lcd.print(uid.substring(0,8));
  tone(BUZZER, 1500, 200);
  delay(1000);
}

void handleReset(String time) {
  toolsOutCount = 0;
  totalGauzeUsed = 0;
  for (int i = 0; i < toolInventoryCount; i++) inventory[i].isOut = false;
  updateLEDs();
  lcd.clear();
  lcd.print("SYSTEM RESET");
  emitJson("BTN_RESET", "ALL", "RESET_STATE", time);
  tone(BUZZER, 500, 500);
  delay(1000);
  updateLCDStatus();
}

void updateLEDs() {
  if (toolsOutCount > 0) {
    digitalWrite(RED_LED, HIGH);
    digitalWrite(GRN_LED, LOW);
  } else {
    digitalWrite(RED_LED, LOW);
    digitalWrite(GRN_LED, HIGH);
  }
}

void updateLCDStatus() {
  lcd.clear();
  if (registrationMode) {
    lcd.print("MODE: ADD TOOL");
    lcd.setCursor(0, 1);
    lcd.print("Scan RFID Tag");
  } else {
    lcd.print("Gauze Count: " + String(totalGauzeUsed));
    lcd.setCursor(0, 1);
    if (toolsOutCount == 0) lcd.print("TOOLS: ALL IN");
    else lcd.print("TOOLS OUT: " + String(toolsOutCount));
  }
}