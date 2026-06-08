import urequests
import ujson
from machine import Pin
import network, time

# --- conectar wifi primero ---
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect('FRANCKROM', '12345678')
while not wlan.isconnected():
    time.sleep(1)
print("WiFi OK:", wlan.ifconfig()[0])

# --- payload de prueba ---
payload = {
    "battery_level" : 3.85,
    "wind_speed_kmh": 12.5,
    "rainfall"      : 0.0,
    "uv_index"      : 3,
    "temperature_c" : 25.4,
    "humidity"      : 60.0,
}

headers = {"Content-Type": "application/json"}
body    = ujson.dumps(payload)

resp = urequests.post("https://httpbin.org/post", data=body, headers=headers)
print("Status:", resp.status_code)
print("Response:", resp.text)
resp.close()