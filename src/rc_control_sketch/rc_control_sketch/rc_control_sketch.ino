#include <WiFi.h>
#include <WiFiUdp.h>
#include <ArduinoJson.h>

// ====== WiFi ======
const char *WIFI_SSID = "NETGEAR_EXT";
const char *WIFI_PASS = "";

// ====== Network ======
WiFiUDP Udp;
const int LOCAL_PORT = 5005;

// ====== Pins ======
const int THROTTLE_PIN = 25;        // ESC signal
const int STEER_PIN = 26;           // Servo signal
const int WINCH_PIN = 27;           // Servo signal
const int SWAYBAR_PIN = 12;         // Servo signal
const int LIGHTS_PIN = 13;          // Servo signal
const int ROTATING_LIGHTS_PIN = 14; // Servo signal
const int SPEED_PIN = 15;           // Servo signal
const int DIG_PIN = 16;             // Servo signal

// ====== PWM (ledc) ======
const int THROTTLE_CH = 0;
const int STEER_CH = 1;
const int WINCH_CH = 2;
const int SWAYBAR_CH = 3;
const int LIGHTS_CH = 4;
const int ROTATING_LIGHTS_CH = 5;
const int SPEED_CH = 6;
const int DIG_CH = 7;
const int PWM_FREQ = 50; // 50 Hz for RC signals
const int PWM_RES = 16;  // 16-bit for fine steps
// ledcWrite in "duty" steps, we’ll compute duty for a given microsecond pulse
// On ESP32, ledc base clock ~80MHz. At 50 Hz and 16 bits, each tick ~ (1/50)/65536 ≈ 305 us
// We'll compute duty by fraction of period: duty = (pulse_us / period_us) * 65535
const float PERIOD_US = 1000000.0f / PWM_FREQ; // 20000 us

// ====== RC ranges ======
int us_min_throttle = 1000;
int us_mid_throttle = 1500;
int us_max_throttle = 2000;

int us_min_steer = 1000;
int us_mid_steer = 1500;
int us_max_steer = 2000;

int us_min_default = 1000;
int us_mid_default = 1500;
int us_max_default = 2000;

// ====== Control state ======
volatile float steer_cmd = 0.0f;           // -1..1
volatile float throttle_cmd = 0.0f;        // -1..1
volatile float winch_cmd = 0.0f;           // -1..1
volatile float swaybar_cmd = 0.0f;         // -1..1
volatile float lights_cmd = 0.0f;          // -1..1
volatile float rotating_lights_cmd = 0.0f; // -1..1
volatile float speed_cmd = 0.0f;           // -1..1
volatile float dig_cmd = 0.0f;             // -1..1

unsigned long last_packet_ms = 0;
const unsigned long FAILSAFE_MS = 500;
bool armed = false;

// ====== Helpers ======
uint16_t usToDuty(int pulse_us)
{
  float frac = pulse_us / PERIOD_US;        // 0..1
  uint32_t duty = (uint32_t)(frac * 65535); // 16-bit
  if (duty > 65535)
    duty = 65535;
  return (uint16_t)duty;
}

void writePulseUS(int channel, int pulse_us)
{
  uint16_t duty = usToDuty(pulse_us);
  ledcWrite(channel, duty);
}

int mapFloatToUs(float v, int us_min, int us_mid, int us_max)
{
  // v in [-1..1]; negative -> below mid; positive -> above mid
  if (v >= 0)
  {
    return us_mid + (int)((us_max - us_mid) * v);
  }
  else
  {
    return us_mid + (int)((us_mid - us_min) * v); // v is negative
  }
}

void sendNeutral()
{
  writePulseUS(THROTTLE_CH, us_mid_throttle);
  writePulseUS(STEER_CH, us_mid_steer);
  writePulseUS(WINCH_CH, us_mid_default);
  writePulseUS(SWAYBAR_CH, us_mid_default);
  writePulseUS(LIGHTS_CH, us_mid_default);
  writePulseUS(ROTATING_LIGHTS_CH, us_mid_default);
  writePulseUS(SPEED_CH, us_mid_default);
  writePulseUS(DIG_CH, us_mid_default);
}

void applyControls()
{
  // Soft clamp
  float s = constrain(steer_cmd, -1.0f, 1.0f);
  float t = constrain(throttle_cmd, -1.0f, 1.0f);

  // Optional: deadzones
  if (fabsf(s) < 0.03f)
    s = 0.0f;
  if (fabsf(t) < 0.03f)
    t = 0.0f;

  int steer_us = mapFloatToUs(s, us_min_steer, us_mid_steer, us_max_steer);
  int throttle_us = mapFloatToUs(t, us_min_throttle, us_mid_throttle, us_max_throttle);

  writePulseUS(STEER_CH, steer_us);
  writePulseUS(THROTTLE_CH, throttle_us);

  // Other axes: winch, swaybar, speed, dig use default ranges
  float w = constrain(winch_cmd, -1.0f, 1.0f);
  float sw = constrain(swaybar_cmd, -1.0f, 1.0f);
  float sp = constrain(speed_cmd, -1.0f, 1.0f);
  float d = constrain(dig_cmd, -1.0f, 1.0f);

  if (fabsf(w) < 0.03f)
    w = 0.0f;
  if (fabsf(sw) < 0.03f)
    sw = 0.0f;
  if (fabsf(sp) < 0.03f)
    sp = 0.0f;
  if (fabsf(d) < 0.03f)
    d = 0.0f;

  int winch_us = mapFloatToUs(w, us_min_default, us_mid_default, us_max_default);
  int swaybar_us = mapFloatToUs(sw, us_min_default, us_mid_default, us_max_default);
  int speed_us = mapFloatToUs(sp, us_min_default, us_mid_default, us_max_default);
  int dig_us = mapFloatToUs(d, us_min_default, us_mid_default, us_max_default);

  // Lights are 0..1 -> map to mid..max
  int lights_us = us_mid_default + (int)((us_max_default - us_mid_default) * lights_cmd);
  int rotating_lights_us = us_mid_default + (int)((us_max_default - us_mid_default) * rotating_lights_cmd);

  writePulseUS(WINCH_CH, winch_us);
  writePulseUS(SWAYBAR_CH, swaybar_us);
  writePulseUS(SPEED_CH, speed_us);
  writePulseUS(DIG_CH, dig_us);
  writePulseUS(LIGHTS_CH, lights_us);
  writePulseUS(ROTATING_LIGHTS_CH, rotating_lights_us);
}

void armSequence()
{
  // Hold neutral for 2s so most ESCs arm safely
  unsigned long start = millis();
  while (millis() - start < 2000)
  {
    sendNeutral();
    delay(20);
  }
  armed = true;
}

// ====== Setup ======
void setup()
{
  Serial.begin(115200);

  // PWM setup
  ledcSetup(THROTTLE_CH, PWM_FREQ, PWM_RES);
  ledcSetup(STEER_CH, PWM_FREQ, PWM_RES);
  ledcSetup(WINCH_CH, PWM_FREQ, PWM_RES);
  ledcSetup(SWAYBAR_CH, PWM_FREQ, PWM_RES);
  ledcSetup(LIGHTS_CH, PWM_FREQ, PWM_RES);
  ledcSetup(ROTATING_LIGHTS_CH, PWM_FREQ, PWM_RES);
  ledcSetup(SPEED_CH, PWM_FREQ, PWM_RES);
  ledcSetup(DIG_CH, PWM_FREQ, PWM_RES);
  ledcAttachPin(THROTTLE_PIN, THROTTLE_CH);
  ledcAttachPin(STEER_PIN, STEER_CH);
  ledcAttachPin(WINCH_PIN, WINCH_CH);
  ledcAttachPin(SWAYBAR_PIN, SWAYBAR_CH);
  ledcAttachPin(LIGHTS_PIN, LIGHTS_CH);
  ledcAttachPin(ROTATING_LIGHTS_PIN, ROTATING_LIGHTS_CH);
  ledcAttachPin(SPEED_PIN, SPEED_CH);
  ledcAttachPin(DIG_PIN, DIG_CH);

  sendNeutral();

  // WiFi
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("Connecting WiFi");
  while (WiFi.status() != WL_CONNECTED)
  {
    delay(300);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("IP: ");
  Serial.println(WiFi.localIP());

  Udp.begin(LOCAL_PORT);
  Serial.print("Listening UDP on port ");
  Serial.println(LOCAL_PORT);

  armSequence();
  last_packet_ms = millis();
}

// ====== Loop ======
void loop()
{
  // Receive packet (JSON: {"ax":float,"ay":float})
  int sz = Udp.parsePacket();
  if (sz > 0)
  {
    static char buf[256];
    int len = Udp.read(buf, sizeof(buf) - 1);
    if (len > 0)
    {
      buf[len] = 0;
      StaticJsonDocument<200> doc;
      DeserializationError err = deserializeJson(doc, buf);
      if (!err)
      {
        // Channel mapping (expected -1..1 for most channels; lights are 0..1)
        float steer = doc["ch1"] | 0.0;    // steering -1..1
        float throttle = doc["ch2"] | 0.0; // throttle -1..1 (forward positive)
        float winch = doc["ch3"] | 0.0;    // winch -1..1
        float swaybar = doc["ch4"] | 0.0;  // swaybar -1..1
        float lights = doc["ch5"] | 0.0;   // lights 0..1
        float rotating = doc["ch6"] | 0.0; // rotating lights 0..1
        float speed = doc["ch7"] | 0.0;    // speed -1..1
        float dig = doc["ch8"] | 0.0;      // dig -1..1

        steer_cmd = constrain(steer, -1.0f, 1.0f);
        throttle_cmd = constrain(throttle, -1.0f, 1.0f);
        winch_cmd = constrain(winch, -1.0f, 1.0f);
        swaybar_cmd = constrain(swaybar, -1.0f, 1.0f);
        // lights and rotating lights expected 0..1; clamp accordingly
        lights_cmd = constrain(lights, 0.0f, 1.0f);
        rotating_lights_cmd = constrain(rotating, 0.0f, 1.0f);
        speed_cmd = constrain(speed, -1.0f, 1.0f);
        dig_cmd = constrain(dig, -1.0f, 1.0f);

        last_packet_ms = millis();
      }
    }
  }

  // Failsafe
  if (millis() - last_packet_ms > FAILSAFE_MS)
  {
    sendNeutral();
  }
  else if (armed)
  {
    applyControls();
  }
  else
  {
    sendNeutral();
  }

  delay(10); // 100 Hz loop
}
