#include <ESP8266WiFi.h>
#include <WiFiUdp.h>
#include <Ticker.h>
#include <AsyncMqtt_Generic.h>
#include <ArduinoJson.h>

// WiFi Config
#define WIFI_SSID "Secret WiFi Here"
#define WIFI_PASSWORD "Secret Password Here"

// Current sensor config
#define CALIB_FACTOR 3.27
#define CALIB_VOLTAGE 230.0

// MQTT Config
#define MQTT_HOST IPAddress(10,30,47,148)
#define MQTT_PORT 1883
#define MQTT_TOPIC "power/current1"

// MQTT Config for IOT (Do not change)
#define MQTT_DEVICES_PING_TOPIC "dm2/devices"
#define MQTT_PING_RESPONSE "esp32config/PING"
#define MQTT_ESP32_CONFIG "esp32config/#"

#define MAJOR_APP_VERSION "ESP8266 1.0.0"

typedef enum
{
  SINGLE = 1,
  JSON = 2,
  JSON_LAB = 3
} MQTT_DATA_TYPE;

typedef enum
{
  NONE = 0,
  SET_OFFSET = 1,
  RESET = 2
} MQTT_COMMAND;

#define SENSOR_COLUMN_1 "[\"Power\"]"

WiFiEventHandler wifiConnectHandler;
WiFiEventHandler wifiDisconnectHandler;
WiFiEventHandler wifiGotIpHandler;
WiFiEventHandler wifiDhcpTimeoutHandler;

Ticker wifiReconnectTimer;
AsyncMqttClient mqttClient;

// Wifi UDP for ping
WiFiUDP udp;
const int udpPort = 1234;

const unsigned long publishInterval = 10000;

#define Status_LED 2 // D4

// Gets the MQTT topic associated with this device.
String getDeviceTopic()
{
  String buf = "esp32config/";
  buf.concat(getMacAddress());

  return buf;
}

void onWiFiConnect(const WiFiEventStationModeGotIP &event)
{
  Serial.println("Connected to Wi-Fi.");
  Serial.print("IP address: ");
  Serial.println(WiFi.localIP());

  mqttClient.connect();
}

void onWiFiDisconnect(const WiFiEventStationModeDisconnected &event)
{
  Serial.println("Disconnected from Wi-Fi.");
  wifiReconnectTimer.once(2, connectToWiFi);
}

void onWiFiGotIP(const WiFiEventStationModeGotIP &event)
{
  Serial.println("Connected to Wi-Fi.");
  Serial.print("IP address: ");
  Serial.println(WiFi.localIP());
}

void onWiFiDhcpTimeout()
{
  Serial.println("DHCP Timeout.");
  wifiReconnectTimer.once(2, connectToWiFi);
}

void onMqttConnect(bool sessionPresent)
{
  Serial.println("Connected to MQTT broker.");
  Serial.print("Session present: ");
  Serial.println(sessionPresent);

  // mqttClient.subscribe(MQTT_TOPIC, 2);
  // Serial.println('Subscribed to topic: ' + String(MQTT_TOPIC));
  mqttClient.subscribe(MQTT_ESP32_CONFIG, 2);
  Serial.println("Subscribed to topic: " + String(MQTT_ESP32_CONFIG));
  mqttClient.subscribe(getDeviceTopic().c_str(), 2);
  Serial.println("Subscribed to topic: " + String(getDeviceTopic()));
}

void onMqttDisconnect(AsyncMqttClientDisconnectReason reason)
{
  Serial.println("Disconnected from MQTT broker.");
  if (WiFi.isConnected())
  {
    mqttClient.connect();
  }
}

void onMqttMessage(char *topic, char *payload, AsyncMqttClientMessageProperties properties, size_t len, size_t index, size_t total)
{
  StaticJsonDocument<512> doc;
  int slash_index = String(topic).indexOf('/');
  Serial.println("Message arrived [" + String(topic) + "] " + String(payload) + " (length " + String(len) + ")");
  // Check if topic has slash and valid format i.e. "esp32config/<esp32_mac_address>"
  if (slash_index > 1)
  {

    // Extract the left and right substrings from the topic i.e left_string = "espconfig" and right_string = "<esp32_mac_address"
    String left_string = String(topic).substring(0, slash_index);
    String right_string = String(topic).substring(slash_index);

    // Check if leftstring matches "esp32config"
    if (left_string == "esp32config")
    {

      // Check if the topic matches the device topic (command directed only to this device)
      if (String(topic) == getDeviceTopic())
      {

        // Check if the command is /SOFT_RESET, if yes restart the device
        if (strcmp(payload, "/SOFT_RESET") == 0)
        {
          Serial.println("Reseting ESP32...");
          ESP.restart();
        }

        // Deserialize the JSON payload, if failed exit function
        DeserializationError error = deserializeJson(doc, payload);
        if (error)
        {
          Serial.print(F("deserializeJson() failed: "));
          Serial.println(error.f_str());
          return;
        }

        // Extract values from the JSON
        MQTT_COMMAND command = doc["command"];
        uint32_t hash = doc["hash"];
        JsonArray arr = doc["values"].as<JsonArray>();

        // Set the offset values
        if (command == SET_OFFSET)
        {
          if (hash == 0)
          {
            Serial.println("Wrong hash!");
            Serial.println(hash);
            Serial.println("Payload:");
            Serial.println(payload);
            return;
          }
          // TODO: Implement offset setting
          return;
        }
        else if (command == RESET) // Reset ESP32
        {
          Serial.println("Reseting ESP32...");
          ESP.restart();
        }
      }
      else if (right_string == "/PING")
      {
        // Reply with pong message
        echoPong(mqttClient);
      }
      else
      {
        Serial.println("Unknwon command: " + left_string + " " + right_string);
      }
    }
  }
}

void onMqttSubscribe(uint16_t packetId, uint8_t qos)
{
  Serial.println("Subscribe acknowledged.");
  Serial.print("  packetId: ");
  Serial.println(packetId);
  Serial.print("  qos: ");
  Serial.println(qos);
}

void connectToWiFi()
{
  // Set static IP
  // IPAddress ip(192,168,0,211);
  // IPAddress gateway(192, 168, 0, 233);
  // IPAddress subnet(255, 255, 255, 0);
  // IPAddress dns(192, 168, 0, 233);
  // WiFi.config(ip, gateway, subnet, dns);
  Serial.println("Connecting to Wi-Fi...");
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

// Count the length of a const char string.
size_t cstr_len(const char *str)
{
  for (size_t n = 0;; n++)
    if (str[n] == 0)
      return n;
}

// Generates unique (hopefully) uint32_t hash from string
uint32_t hash_str_to_uint32_t(const char *str)
{
  uint32_t hash = 2443542612;
  for (int i = 0; i < cstr_len(str); ++i)
  {
    char value = str[i];
    hash = 16777619 * (hash ^ value);
  }
  return hash;
}

uint32_t calculateSensorHash(String topic, String columns)
{
  String hash_str;
  uint32_t hash = 1234;
  hash_str.concat(topic);
  hash_str.concat(columns);
  hash = hash_str_to_uint32_t(hash_str.c_str());
  return hash;
}

uint64_t getMacAddress()
{
  uint8_t mac[6];
  WiFi.macAddress(mac);
  uint64_t device_id = ((uint64_t)mac[0] << 40) | ((uint64_t)mac[1] << 32) | ((uint64_t)mac[2] << 24) | ((uint64_t)mac[3] << 16) | ((uint64_t)mac[4] << 8) | (uint64_t)mac[5];
  return device_id;
}

void generateJSONPaylod(JsonDocument &doc)
{
  doc["device_id"] = getMacAddress();
  doc["ip"] = WiFi.localIP().toString();
  doc["rssi"] = WiFi.RSSI();
  doc["timestamp"] = "N/A";
  doc["version"] = MAJOR_APP_VERSION;

  JsonObject sensors = doc.createNestedObject("sensors");
  JsonObject jsonObject[0];
  jsonObject[0] = sensors.createNestedObject(String(0));
  jsonObject[0]["topic"] = MQTT_TOPIC;
  jsonObject[0]["delay"] = publishInterval;
  jsonObject[0]["enabled"] = true;
  jsonObject[0]["mqtt"] = true;
  jsonObject[0]["columns"] = SENSOR_COLUMN_1;
  jsonObject[0]["data_type"] = MQTT_DATA_TYPE::JSON;

  jsonObject[0]["calib"] = "0.00";
  jsonObject[0]["id"] = calculateSensorHash(MQTT_TOPIC, SENSOR_COLUMN_1);
}

void echoPongUDP(WiFiUDP &udp)
{
  StaticJsonDocument<(256 + (256 * 1))> doc;
  String output;

  generateJSONPaylod(doc);
  serializeJson(doc, output);

  udp.beginPacket(udp.remoteIP(), udpPort);
  udp.print(output);
  udp.endPacket();
}

void echoPong(AsyncMqttClient &mqttClient)
{
  StaticJsonDocument<(256 + (256 * 1))> doc;
  String output;

  generateJSONPaylod(doc);
  serializeJson(doc, output);

  uint16_t packetIdPub2 = mqttClient.publish(MQTT_DEVICES_PING_TOPIC, 2, false, output.c_str());
}

void setup()
{
  Serial.begin(115200);
  Serial.println("");
  Serial.println("Version: " + String(MAJOR_APP_VERSION));
  Serial.println("MQTT_HOST: " + MQTT_HOST.toString());
  Serial.println("MQTT Topic: " + String(MQTT_TOPIC));

  pinMode(Status_LED, OUTPUT); // Status LED
  digitalWrite(Status_LED, HIGH);

  wifiConnectHandler = WiFi.onStationModeGotIP(onWiFiConnect);
  wifiDisconnectHandler = WiFi.onStationModeDisconnected(onWiFiDisconnect);
  wifiGotIpHandler = WiFi.onStationModeGotIP(onWiFiGotIP);
  wifiDhcpTimeoutHandler = WiFi.onStationModeDHCPTimeout(onWiFiDhcpTimeout);

  connectToWiFi();

  mqttClient.onConnect(onMqttConnect);
  mqttClient.onDisconnect(onMqttDisconnect);
  mqttClient.onMessage(onMqttMessage);
  mqttClient.onSubscribe(onMqttSubscribe);
  mqttClient.setServer(MQTT_HOST, MQTT_PORT);

  udp.begin(udpPort);
}

c4lass PowerMonitor
{
public:
  PowerMonitor(float calibrationFactor, int lineVoltage, int pin) : CALIBRATION_FACTOR(calibrationFactor),
                                                           LINE_VOLTAGE(lineVoltage),
                                                           PIN(pin)
  {
  }

  void readPower()
  {
    int current = 0;

    for (int i = 0; i <= 600; i++)
    {
      current = analogRead(PIN); 

      if (current >= maxCurrent)
      {
        maxCurrent = current;
      }

      if (current <= minCurrent)
      {
        minCurrent = current;
      }
    }

    peakCurrent = maxCurrent - minCurrent;

    rmsCurrent = (peakCurrent * 0.3535) / CALIBRATION_FACTOR;
    rmsPower = LINE_VOLTAGE * rmsCurrent;           

    maxCurrent = 0;
    minCurrent = 1023;
  }

  float getRmsCurrent() const
  {
    return rmsCurrent;
  }

  int getRmsPower() const
  {
    return rmsPower;
  }

private:
  const float CALIBRATION_FACTOR;
  const int LINE_VOLTAGE;
  const uint8_t PIN;

  int maxCurrent = 0;
  int minCurrent = 1023;
  int peakCurrent = 0;
  float rmsCurrent = 0.0;
  int rmsPower = 0;
};

PowerMonitor powerMonitor(CALIB_FACTOR, CALIB_VOLTAGE, A0);

void loop()
{
  // TODO: We should read power every 10 seconds
  if (!mqttClient.connected())
  {
    return;
  }

  // Check for incoming UDP packets
  int packetSize = udp.parsePacket();
  if (packetSize)
  {
    // Read the packet into a buffer
    char buffer[255];
    int len = udp.read(buffer, 255);
    if (len > 0)
    {
      buffer[len] = 0;
      Serial.printf("Received packet:%s:\n", buffer);

      // Check if the packet is a ping
      if (strcmp(buffer, "ping") == 0)
      {
        // Send a reply
        Serial.println("Sending pong to: " + String(udp.remoteIP().toString()) + ":" + String(udp.remotePort()));
        echoPongUDP(udp);
      }
    }
  }

  static unsigned long lastPublishTime = 0;

  if (millis() - lastPublishTime >= publishInterval)
  {
    powerMonitor.readPower();
    float rmsCurrent = powerMonitor.getRmsCurrent();
    int rmsPower = powerMonitor.getRmsPower();

    Serial.print("Amps:");
    Serial.print(rmsCurrent);
    Serial.print(" Watts:");
    Serial.println(rmsPower);

    String payload = String(rmsPower);
    // Publish in following JSON format:
    /*
    {"value":[123],"timestamp":"N/A","sensor":"Current"}
    */
    String json = "{\"value\":[";
    json += payload;
    json += "],\"timestamp\":\"N/A\",\"sensor\":\"Current\"}";
    payload = json;
    mqttClient.publish(MQTT_TOPIC, 0, false, payload.c_str());
    lastPublishTime = millis();
  }
}