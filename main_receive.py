import machine
from machine import Pin
import network
import time
import urequests
import ujson
import lora_client

#------------------------------------
#   LED ONBOARD
#------------------------------------
led = Pin("LED", machine.Pin.OUT)
def blink(times=1, ms=150):
    for i in range(times):
        led.value(1)
        time.sleep_ms(ms)
        led.value(0)
        time.sleep_ms(ms)

#------------------------------------
#   WIFI CONNECTION
#------------------------------------
wifi_ssid = 'FRANCKROM' # Replace with WiFi SSID
wifi_password = '12345678' # Replace with WiFi password
server_ip = '192.168.1.100' # Replace with your server IP and port
server_port = 80 # Replace with your server port if different
endpoint_reads = '/data' # Replace with your server endpoint
BASE_URL = f'http://{server_ip}:{server_port}{endpoint_reads}' # Full URL for the POST request


def connect_wifi(ssid, password):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        print('[WIFI] Pi Pico W is already connected to:', wlan.ifconfig())
        return wlan
    print('[WIFI] Connecting to WiFi network:', ssid)
    wlan.connect(ssid, password)
    intentos = 0
    while not wlan.isconnected():
        if intentos >= 10:
            print('[WIFI] Failed to connect after 10 attempts. Restarting...')
            machine.reset()
        print(".", end="")
        led.toggle()
        time.sleep(1)
        intentos += 1
    
    led.on()
    ip, mascara, gateway, dns = wlan.ifconfig()
    print(f"[WIFI] Connected! IP: {ip}, Mask: {mascara}, Gateway: {gateway}, DNS: {dns}\n")
    return wlan
#------------------------------------
#   LORA INTERFACE
#------------------------------------
def esperar_primer_paquete(timeout_ms=5000):
    print("[LORA] Waiting for first packet...")
    inicio = time.ticks_ms()
    while not lora_client.actualizar():
        if time.ticks_diff(time.ticks_ms(), inicio) > timeout_ms:
            print("[LORA] No initial packet received, continuing anyway...")
            return False
        time.sleep_ms(20)
    print("[LORA] First packet received:", lora_client.get_all())
    return True

def actualizar():
    return lora_client.actualizar()

def get_datos():
    return lora_client.get_all()

#------------------------------------
#   BATERY LEVEL READING
#------------------------------------
def _leer_bateria():
    adc     = machine.ADC(3)         # GP29 / VSYS en Pico W
    raw     = adc.read_u16()
    voltaje = raw * (3.3 * 3) / 65535
    return round(voltaje, 3)

#------------------------------------
#   PAYLOAD
#------------------------------------
def construir_payload():
    datos = lora_client.get_all()
    return {
        "battery_level" : _leer_bateria(),
        "wind_speed_kmh": float(datos["VV"]) if datos["VV"] != "--" else 0.0,
        "rainfall"      : float(datos["LL"]) if datos["LL"] != "--" else 0.0,
        "uv_index"      : int(datos["UV"])   if datos["UV"] != "--" else 0,
        "temperature_c" : float(datos["T"])  if datos["T"]  != "--" else 0.0,
        "humidity"      : float(datos["H"])  if datos["H"]  != "--" else 0.0,
    }

#------------------------------------
#   HTTP POST
#------------------------------------
def enviar_lectura():
    payload = construir_payload()
    headers = {"Content-Type": "application/json"}
    body    = ujson.dumps(payload)

    print(f"[HTTP] POST -> {BASE_URL}")
    print(f"[HTTP] Body: {body}")

    try:
        resp = urequests.post(BASE_URL, data=body, headers=headers)
        print(f"[HTTP] Status: {resp.status_code} | Response: {resp.text}")
        resp.close()
        blink(2)          # 2 parpadeos = exito
    except Exception as e:
        print(f"[HTTP] ERROR: {e}")
        blink(5, ms=80)   # 5 parpadeos rapidos = fallo

#------------------------------------
#   MAIN FUNCTIONS
#------------------------------------

def main():
    # 1. Conectar WiFi
    wlan = wifi.connect()
    if wlan is None:
        print('[FATAL] Could not connect to WiFi. Restarting...')
        time.sleep(5)
        machine.reset()
 
    # 2. Esperar primer paquete LoRa
    lora.esperar_primer_paquete(timeout_ms=5000)
 
    # 3. Loop principal
    while True:
        if not wlan.isconnected():
            print('[WIFI] Connection lost. Reconnecting...')
            wlan = wifi.connect()
            if wlan is None:
                print('[FATAL] Could not reconnect. Restarting...')
                time.sleep(5)
                machine.reset()
 
        if lora.actualizar():
            print("[LORA] New data:", lora.get_datos())
            lora.enviar_lectura()
 
        time.sleep_ms(10)
 
if __name__ == "__main__":
    main()