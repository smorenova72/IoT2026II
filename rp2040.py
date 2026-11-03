from machine import Pin, SPI, time_pulse_us, ADC, idle
from lora_lib import LoRa
import time
import ujson
import ucryptolib
import ubinascii

AES_KEY = b"MiClaveSecreta16"

def pad(texto):
    pad_len = 16 - (len(texto) % 16)
    return texto + bytes([pad_len]) * pad_len

def unpad(texto):
    pad_len = texto[-1]
    if pad_len < 1 or pad_len > 16:
        raise ValueError("Padding inválido")
    return texto[:-pad_len]

def cifrar_mensaje(mensaje_str):
    cipher = ucryptolib.aes(AES_KEY, 1)
    cifrado_bytes = cipher.encrypt(pad(mensaje_str.encode('utf-8')))
    return ubinascii.hexlify(cifrado_bytes).decode('utf-8')

def descifrar_mensaje(mensaje_hex_str):
    try:
        cifrado_bytes = ubinascii.unhexlify(mensaje_hex_str)
        cipher = ucryptolib.aes(AES_KEY, 1)
        return unpad(cipher.decrypt(cifrado_bytes)).decode('utf-8')
    except Exception as e:
        print(f"Error descifrando: {e}")
        return None

trig = Pin(15, Pin.OUT)
echo = Pin(14, Pin.IN)
tds_sensor = ADC(Pin(26))

carga_tds = Pin(16, Pin.OUT)
carga_nivel = Pin(17, Pin.OUT)

def medir_distancia(temperatura_c=20.0):
    velocidad_cm_us = (331.3 + (0.6 * temperatura_c)) * 0.0001
    trig.low(); time.sleep_us(5)
    trig.high(); time.sleep_us(15); trig.low()
    duracion = time_pulse_us(echo, 1, 30000)
    if duracion > 0:
        return (duracion * velocidad_cm_us) / 2.0
    return -1

def calcular_tds(valor_adc):
    voltage = (valor_adc / 65535.0) * 3.3
    tds_value = (133.42 * (voltage ** 3) - 255.86 * (voltage ** 2) + 857.39 * voltage) * 0.5
    return max(0.0, tds_value)

def timestamp_ms():
    """'YYYY-MM-DD HH:MM:SS.mmm' (localtime no trae ms, se toman de time_ns)."""
    t = time.localtime()
    try:
        ms = (time.time_ns() // 1000000) % 1000
    except Exception:
        ms = time.ticks_ms() % 1000  # respaldo si time_ns no existe
    return f"{t[0]:04d}-{t[1]:02d}-{t[2]:02d} {t[3]:02d}:{t[4]:02d}:{t[5]:02d}.{ms:03d}"


SEND_INTERVAL_MS = 3000
TX_GUARD_MS = 200

rx_queue = []
rx_resume_at = None 
ultimo_envio_datos = time.ticks_add(time.ticks_ms(), -SEND_INTERVAL_MS)
datos_exitosos = 0

def al_recibir(dato):
    if len(rx_queue) < 8:
        rx_queue.append(dato)

def transmitir(payload_hex):
    """Envía y agenda la vuelta a RX sin bloquear."""
    global rx_resume_at
    lora.send(payload_hex)
    rx_resume_at = time.ticks_add(time.ticks_ms(), TX_GUARD_MS)

spi = SPI(1, baudrate=1000000, sck=Pin(10), mosi=Pin(11), miso=Pin(12))
lora = LoRa(spi, cs=13, reset=28, dio0=27, callback=al_recibir)
lora.set_bandwidth(250000)
lora.set_rx_mode()

print("--- INICIANDO SISTEMA RP2040 CIFRADO (TX/RX NO BLOQUEANTE) ---")

def procesar_rx():
    global datos_exitosos
    while rx_queue:
        dato_crudo = rx_queue.pop(0)
        try:
            if isinstance(dato_crudo, (bytes, bytearray)):
                texto_hex = dato_crudo.decode('utf-8')
            else:
                texto_hex = str(dato_crudo)

            texto_descifrado = descifrar_mensaje(texto_hex)
            if not texto_descifrado:
                continue

            msg = ujson.loads(texto_descifrado)
            print("Mensaje Descifrado:", msg)

            tipo = msg.get("tipo")
            if tipo == "ack":
                datos_exitosos += 1
                print(f"[*] Mensaje confirmado por ESP32. Exitosos: {datos_exitosos}")

            elif tipo == "comando":
                valor_tds = msg.get("tds", 0)
                valor_nivel = msg.get("nivel", 0)
                carga_tds.value(valor_tds)
                carga_nivel.value(valor_nivel)
                print(f"[!] Orden Ejecutada -> Pin TDS: {'3.3V' if valor_tds else '0V'} | Pin Nivel: {'3.3V' if valor_nivel else '0V'}")

        except Exception as e:
            print("Error procesando trama entrante:", e)

def enviar_datos():
    dist = medir_distancia()
    tds_ppm = calcular_tds(tds_sensor.read_u16())

    datos = f"{timestamp_ms()} {round(tds_ppm, 1)} {round(dist, 1) if dist >= 0 else None}"
    print("Transmitiendo (Original):", datos)

    payload_cifrado = cifrar_mensaje(datos)
    print("Transmitiendo (Cifrado HEX):", payload_cifrado)
    transmitir(payload_cifrado)

while True:
    ahora = time.ticks_ms()

    if rx_resume_at is not None and time.ticks_diff(ahora, rx_resume_at) >= 0:
        lora.set_rx_mode()
        rx_resume_at = None

    procesar_rx()

    if rx_resume_at is None and time.ticks_diff(ahora, ultimo_envio_datos) >= SEND_INTERVAL_MS:
        ultimo_envio_datos = ahora
        enviar_datos()

    idle()