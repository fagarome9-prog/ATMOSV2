import machine
import time
from machine import ADC, Pin, I2C
from ulora import LoRa
from machine import SPI

# ============================================================================
#  MAPA DEFINITIVO DE ASIGNACIÓN DE PINES (ESTACIÓN METEOROLÓGICA + LORA)
# ============================================================================
# [RESERVADO LORA]   GP12 -> SPI1 MISO
# [RESERVADO LORA]   GP13 -> SPI1 CS / NSS
# [RESERVADO LORA]   GP14 -> SPI1 SCK
# [RESERVADO LORA]   GP15 -> SPI1 MOSI
# [RESERVADO LORA]   GP20 -> IRQ / INT (Interrupción de Radio)
# [RESERVADO LORA]   GP21 -> RESET LoRa
# [RESERVADO LORA]   GP22 -> Uso especial / Reservado por usuario
#
# [SENSORES I2C]     GP4  -> I2C0 SDA (AM2315 y LTR390)
#                    GP5  -> I2C0 SCL (AM2315 y LTR390)
#
# [SENSORES DIRECTO] GP26 -> ADC0 Veleta de Viento
#                    GP16 -> Anemómetro (¡Movido aquí para evitar conflicto con GP15!)
#                    GP17 -> Pluviómetro
# ============================================================================

# --- 1. CONFIGURACIÓN DE PARÁMETROS LORA ---

spi = SPI(
    1,
    baudrate=5000000,
    sck=Pin(14),
    mosi=Pin(15),
    miso=Pin(12)
)

print("SPI creado correctamente")



RFM95_RST = 21
RFM95_SPIBUS = (1, 14, 15, 12) 
RFM95_CS = 13 
RFM95_INT = 20
RF95_FREQ = 915.0
RF95_POW = 15
CLIENT_ADDRESS = 1
SERVER_ADDRESS = 2

print("CS =", RFM95_CS)
print("RST =", RFM95_RST)
print("INT =", RFM95_INT)

# --- 2. CONFIGURACIÓN DE PINES DE SENSORES ---
vane_adc = ADC(26)  
wind_pin = Pin(16, Pin.IN, Pin.PULL_UP)  # Cambiado a GP16 de forma segura
rain_pin = Pin(17, Pin.IN, Pin.PULL_UP)  

# Inicializar bus I2C0 para AM2315 y LTR390
i2c = I2C(0, sda=Pin(4), scl=Pin(5), freq=100000)

AM2315_ADDR = 0x5C
LTR390_ADDR = 0x53

# Registros del LTR390
LTR390_MAIN_CTRL = 0x00
LTR390_MEAS_RATE = 0x04
LTR390_GAIN = 0x05

# --- 3. VARIABLES GLOBALES DE CONTEO E INTERRUPCIONES ---
paquete_pendiente = None

pulse_count = 0
last_wind_time = 0

rain_tips = 0
last_rain_time = 0
total_rain_mm = 0.0

# Última telemetría almacenada
ultima_temp = -999.0
ultima_hum = -999.0
ultima_uv = -999.0
ultima_luz = -999
ultima_vel_viento = 0.0
ultima_dir_viento = 0.0
ultima_lluvia = 0.0

# Valores ADC para calibración de la Veleta
VANE_ADC_VALUES = {
    0: 50294,       # N (33K)
    22.5: 25983,    # NNE (6.57K)
    45: 29526,      # NE (8.2K)
    67.5: 5361,     # ENE (891 ohms)
    90: 5957,       # E (1K)
    112.5: 4217,    # ESE (688 ohms)
    135: 11817,     # SE (2.2K)
    157.5: 8098,    # SSE (1.41K)
    180: 18386,     # S (3.9K)
    202.5: 15658,   # SSW (3.14K)
    225: 40329,     # SW (16K)
    247.5: 38361,   # WSW (14.12K)
    270: 60493,     # W (120K)
    292.5: 52960,   # WNW (42.12K)
    315: 56788,     # NW (64.9K)
    337.5: 44983    # NNW (21.88K)
}

# ============================================================================
#  RUTINAS DE INTERRUPCIÓN (ISR)
# ============================================================================
def al_recibir(message):
    global paquete_pendiente
    paquete_pendiente = message

def count_wind_pulse(pin):
    global pulse_count, last_wind_time
    current_time = time.ticks_ms()
    if time.ticks_diff(current_time, last_wind_time) > 15:
        pulse_count += 1
        last_wind_time = current_time

def count_rain_tip(pin):
    global rain_tips, last_rain_time
    current_time = time.ticks_ms()
    if time.ticks_diff(current_time, last_rain_time) > 50:
        rain_tips += 1
        last_rain_time = current_time

# ============================================================================
#  FUNCIONES DE LECTURA DE SENSORES
# ============================================================================
def configurar_ltr390():
    try:
        i2c.writeto_mem(LTR390_ADDR, LTR390_MEAS_RATE, b'\x00') # 20-bit, 400ms
        i2c.writeto_mem(LTR390_ADDR, LTR390_GAIN, b'\x04')      # Ganancia 18x
        print("LTR390 configurado con Ganancia 18x y Resolución 20-bit.")
    except Exception as e:
        print("Error al configurar LTR390:", e)

def get_wind_direction():
    lecturas = []
    for _ in range(10):
        lecturas.append(vane_adc.read_u16())
        time.sleep_ms(2)
    promedio_adc = sum(lecturas) / len(lecturas)
    angulo_mas_cercano = min(VANE_ADC_VALUES.keys(), key=lambda k: abs(VANE_ADC_VALUES[k] - promedio_adc))
    return angulo_mas_cercano, promedio_adc

def leer_am2315():
    try:
        try: i2c.writeto(AM2315_ADDR, b'\x00')
        except: pass
        time.sleep_ms(2)
        i2c.writeto(AM2315_ADDR, b'\x03\x00\x04')
        time.sleep_ms(10)
        data = i2c.readfrom(AM2315_ADDR, 8)
        
        if len(data) == 8:
            humedad = ((data[2] << 8) | data[3]) / 10.0
            temp_raw = (data[4] << 8) | data[5]
            if temp_raw & 0x8000:
                temp_raw = -(temp_raw & 0x7FFF)
            temperatura = temp_raw / 10.0
            return temperatura, humedad
        return None, None
    except:
        return None, None

def leer_ltr390():
    try:
        i2c.writeto_mem(LTR390_ADDR, LTR390_MAIN_CTRL, b'\x02') # ALS Mode
        time.sleep_ms(450) 
        data_als = i2c.readfrom_mem(LTR390_ADDR, 0x0D, 3)
        als_raw = data_als[0] | (data_als[1] << 8) | (data_als[2] << 16)
        
        i2c.writeto_mem(LTR390_ADDR, LTR390_MAIN_CTRL, b'\x0A') # UVS Mode
        time.sleep_ms(450) 
        data_uvs = i2c.readfrom_mem(LTR390_ADDR, 0x10, 3)
        uvs_raw = data_uvs[0] | (data_uvs[1] << 8) | (data_uvs[2] << 16)
        
        i2c.writeto_mem(LTR390_ADDR, LTR390_MAIN_CTRL, b'\x00') # Standby
        uvi = uvs_raw / 10937.0 
        return als_raw, uvs_raw, uvi
    except:
        return None, None, None

# ============================================================================
#  INICIALIZACIÓN DEL SISTEMA
# ============================================================================
print("--- Inicializando Estación Meteorológica con Enlace LoRa ---")

# Inicializar Radio LoRa sin modificar parámetros originales
lora = LoRa(RFM95_SPIBUS, RFM95_INT, SERVER_ADDRESS, RFM95_CS,
            reset_pin=RFM95_RST, freq=RF95_FREQ, tx_power=RF95_POW, acks=True)
lora.on_recv = al_recibir
lora.set_mode_rx()
print("Servidor LoRa inicializado en 915 MHz.")

# Inicializar Sensores I2C
configurar_ltr390()

# Configurar Interrupciones de Hardware de los sensores mecánicos
wind_pin.irq(trigger=Pin.IRQ_FALLING, handler=count_wind_pulse)
rain_pin.irq(trigger=Pin.IRQ_FALLING, handler=count_rain_tip)

# Tiempos de control para el bucle no bloqueante
last_tick = time.ticks_ms()
INTERVALO_MEDICION = 3000  # Envío/Muestreo de datos cada 3 segundos

print("Sistema operativo de forma concurrente. Esperando eventos...")
print("-" * 60)

# ============================================================================
#  BUCLE PRINCIPAL (COOPERATIVO / NO BLOQUEANTE)
# ============================================================================
while True:

    # --- PRIORIDAD 1: Procesamiento asíncrono de paquetes LoRa entrantes ---
    if paquete_pendiente:

        try:
            mensaje = paquete_pendiente.message.decode("utf-8").strip()

            print("\n>>> [LoRa] Paquete Recibido <<<")
            print("Mensaje:", mensaje)

            nodo_origen = paquete_pendiente.header_from

            if mensaje == "REQ":

                print("REQ RECIBIDO")

                respuesta = (
                    "T={:.1f},"
                    "H={:.1f},"
                    "VV={:.2f},"
                    "DV={:.1f},"
                    "UV={:.2f},"
                    "LL={:.2f}"
                ).format(
                    ultima_temp,
                    ultima_hum,
                    ultima_vel_viento,
                    ultima_dir_viento,
                    ultima_uv,
                    ultima_lluvia
                )

                print("Enviando:")
                print(respuesta)

                lora.send_to_wait(
                    respuesta,
                    nodo_origen
                )

                lora.wait_packet_sent()

                print("Respuesta enviada")

                lora.set_mode_rx()

            else:
                print("Comando desconocido:", mensaje)

        except Exception as e:
            print("Error LoRa:", e)

        paquete_pendiente = None

    # --- PRIORIDAD 2: Muestreo periódico de la estación meteorológica ---
    current_time = time.ticks_ms()
    if time.ticks_diff(current_time, last_tick) >= INTERVALO_MEDICION:

        
        # 1. Leer Anemómetro y Veleta
        angulo_viento, adc_crudo = get_wind_direction()
        hz = pulse_count / (INTERVALO_MEDICION / 1000)
        wind_speed_kmh = hz * 2.4011
        
        # 2. Leer Pluviómetro
        rain_mm = rain_tips * 0.2794
        total_rain_mm += rain_mm
        
        # 3. Leer Sensores I2C
        temp, hum = leer_am2315()
        als, uvs, uvi = leer_ltr390()

         # Guardar última telemetría para responder por LoRa
        ultima_temp = temp if temp is not None else -999.0
        ultima_hum = hum if hum is not None else -999.0

        ultima_uv = uvi if uvi is not None else -999.0
        ultima_luz = als if als is not None else -999

        ultima_vel_viento = wind_speed_kmh
        ultima_dir_viento = angulo_viento
        ultima_lluvia = rain_mm
        
        # 4. Desplegar Telemetría en Consola
        print(f"\n=== TELEMETRÍA LOCAL ({INTERVALO_MEDICION//1000}s) ===")
        print(f"Viento: {wind_speed_kmh:.2f} km/h | Dirección: {angulo_viento}° (ADC: {adc_crudo:.0f})")
        print(f"Lluvia: {rain_mm:.4f} mm ciclo / {total_rain_mm:.4f} mm acumulado")
        
        if temp is not None:
            print(f"Termo-Higrómetro (AM2315) -> Temp: {temp:.1f} °C | Hum: {hum:.1f} %")
        else:
            print("Termo-Higrómetro (AM2315) -> Error de comunicación")
            
        if als is not None:
            print(f"Radiación (LTR390)        -> Luz: {als} lx | UV Raw: {uvs} | Índice UV: {uvi:.2f}")
        else:
            print("Radiación (LTR390)        -> Error de comunicación")
        print("=" * 40)
        
        # Limpieza de acumuladores rápidos para el próximo ciclo
        pulse_count = 0  
        rain_tips = 0    
        last_tick = current_time
        
    # Pausa mínima de control para ceder tiempo de CPU a hilos internos de MicroPython
    time.sleep_ms(10)