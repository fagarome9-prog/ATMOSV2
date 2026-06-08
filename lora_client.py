from machine import Pin, SPI
from Libraries.ulora import LoRa
import time

# ==========================================
# CONFIGURACIÓN LORA
# ==========================================

RFM95_RST = 9
RFM95_CS  = 10
RFM95_INT = 11

RF95_FREQ = 915.0
RF95_POW  = 15

CLIENT_ADDRESS = 1
SERVER_ADDRESS = 2

SPI_BUS = (1, 14, 15, 12)

# ==========================================
# VARIABLES
# ==========================================

paquete_pendiente = None

datos = {
    "T":  "--",
    "H":  "--",
    "VV": "--",
    "DV": "--",
    "UV": "--",
    "LL": "--"
}

# ==========================================
# CALLBACK — Se dispara automáticamente al recibir
# ==========================================

def al_recibir(message):
    global paquete_pendiente
    print(">>> PAQUETE LLEGÓ <<<")
    print(message)
    paquete_pendiente = message

# ==========================================
# INICIALIZAR LORA
# ==========================================

spi = SPI(
    1,
    baudrate=5000000,
    sck=Pin(14),
    mosi=Pin(15),
    miso=Pin(12)
)

lora = LoRa(
    SPI_BUS,
    RFM95_INT,
    CLIENT_ADDRESS,
    RFM95_CS,
    reset_pin=RFM95_RST,
    freq=RF95_FREQ,
    tx_power=RF95_POW,
    acks=False
)

lora.on_recv = al_recibir
lora.set_mode_rx()

print("LoRa inicializado")

# ==========================================
# ACTUALIZAR DATOS — No bloqueante
# Retorna True si llegaron datos nuevos
# Retorna False si no había nada pendiente
# ==========================================

def actualizar():
    global paquete_pendiente

    # Si no llegó nada por el callback, salir inmediatamente sin bloquear
    if not paquete_pendiente:
        return False

    # Hay paquete pendiente — procesar
    try:
        texto  = paquete_pendiente.message.decode("utf-8").strip()
        print("LoRa RX:", texto)

        partes = texto.split(",")
        for p in partes:
            clave, valor = p.split("=")
            datos[clave] = valor

    except Exception as e:
        print("Error parseando:", e)

    finally:
        paquete_pendiente = None  # Limpiar siempre, haya error o no

    lora.set_mode_rx()  # Volver a modo escucha tras procesar
    return True         # Indica que hubo datos nuevos

# ==========================================
# GETTERS
# ==========================================

def temperatura():
    return datos["T"]

def humedad():
    return datos["H"]

def velocidad_viento():
    return datos["VV"]

def direccion_viento():
    return datos["DV"]

def uv():
    return datos["UV"]

def lluvia():
    return datos["LL"]

def get_all():
    return datos