import network
import time
import json
import ucryptolib
import ubinascii
from machine import Pin, SPI
from umqtt.simple import MQTTClient
from lora_lib import LoRa

WIFI_SSID = "IoT"
WIFI_PASS = "EIJabcd1234"

MQTT_BROKER    = "192.168.0.115"
MQTT_PORT      = 8883
MQTT_CLIENT_ID = "esp32smv"

PUB_TOPIC = b"sensor/data/out"
SUB_TOPIC = b"sensor/data/in"

MQTT_USER     = 'bug'
MQTT_PASSWORD = '777'

AES_KEY = b"MiClaveSecreta16"

def pad(data):
    pad_len = 16 - (len(data) % 16)
    return data + bytes([pad_len]) * pad_len

def unpad(data):
    pad_len = data[-1]
    if pad_len < 1 or pad_len > 16:
        raise ValueError("Invalid padding")
    return data[:-pad_len]

def encrypt_message(msg_str):
    cipher = ucryptolib.aes(AES_KEY, 1)
    encrypted = cipher.encrypt(pad(msg_str.encode('utf-8')))
    return ubinascii.hexlify(encrypted).decode('utf-8')

def decrypt_message(hex_str):
    try:
        if isinstance(hex_str, (bytes, bytearray)):
            hex_str = hex_str.decode('utf-8')
        encrypted = ubinascii.unhexlify(hex_str.strip())
        cipher = ucryptolib.aes(AES_KEY, 1)
        return unpad(cipher.decrypt(encrypted)).decode('utf-8')
    except Exception as e:
        print("Error de descifrado:", e)
        return None

MAX_MUESTRAS = 20
historial_tds = []
historial_depth = []

cmd_tds = 0
cmd_depth = 0

UMBRAL_TDS_MAX = 5.0
UMBRAL_DEPTH_MAX = 300.0

def enviar_comando_lora():
    """Envía el estado actual de las cargas cifrado vía LoRa al RP2040."""
    global cmd_tds, cmd_depth
    payload = json.dumps({
        "tipo": "comando",
        "tds_load": cmd_tds,
        "depth_load": cmd_depth
    })
    
    time.sleep_ms(100)
    enc_payload = encrypt_message(payload)
    lora.send(enc_payload)
    lora.set_rx_mode()
    print(f"[LoRa TX -> RP2040] Orden enviada al RP2040: TDS={cmd_tds}, Nivel={cmd_depth}")

def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("Conectando a Wi-Fi...")
        wlan.connect(WIFI_SSID, WIFI_PASS)
        while not wlan.isconnected():
            time.sleep(0.5)
    print("Wi-Fi conectado IP:", wlan.ifconfig()[0])

def on_message_received(topic, msg):
    """Procesa comandos remotos entrantes desde el servidor MQTT y actualiza de inmediato."""
    global cmd_tds, cmd_depth
    try:
        if isinstance(msg, bytes):
            msg_str = msg.decode('utf-8').strip()
        else:
            msg_str = str(msg).strip()

        print(f"\n[MQTT SERVIDOR] Comando recibido: {msg_str}")

        if msg_str == "tds/load/on":
            cmd_tds = 1
        elif msg_str == "tds/load/off":
            cmd_tds = 0
        elif msg_str in ("nivel/load/on", "nivel/load/on"):
            cmd_depth = 1
        elif msg_str in ("nivel/load/off", "nivel/load/off"):
            cmd_depth = 0
        elif msg_str.startswith("{"):
            data = json.loads(msg_str)
            if "tds_load" in data:
                cmd_tds = int(data["tds_load"])
            if "depth_load" in data:
                cmd_depth = int(data["depth_load"])
        else:
            print("Formato MQTT no reconocido.")
            return

        enviar_comando_lora()

    except Exception as e:
        print("Error procesando mensaje MQTT:", e)

def lora_receive(msg):
    """Procesa los paquetes de sensores y solo toma/envía decisiones al llegar a 20 muestras."""
    global cmd_tds, cmd_depth, historial_tds, historial_depth
    try:
        plain = decrypt_message(msg)
        if plain is None:
            return

        date, _time, tds_str, depth_str = plain.split()
        tds_val = float(tds_str)
        depth_val = float(depth_str)

        historial_tds.append(tds_val)
        historial_depth.append(depth_val)
        num_muestras = len(historial_tds)

        print(f"\n[LoRa RX <- RP2040] Lectura {num_muestras}/{MAX_MUESTRAS} -> TDS: {tds_val} ppm | Nivel: {depth_val} cm")

        if num_muestras >= MAX_MUESTRAS:
            prom_tds = sum(historial_tds) / MAX_MUESTRAS
            prom_depth = sum(historial_depth) / MAX_MUESTRAS

            print(f"\n--- ¡20 MUESTRAS ALCANZADAS! PROCESANDO PROMEDIOS ---")
            print(f"Promedio TDS: {prom_tds:.2f} ppm | Promedio Nivel: {prom_depth:.2f} cm")

            # TOMA DE DECISIÓN LOCAL
            cmd_tds = 1 if prom_tds <= UMBRAL_TDS_MAX else 0
            cmd_depth = 1 if prom_depth <= UMBRAL_DEPTH_MAX else 0

            data_mqtt = {
                "read_time": f"{date} {_time}",
                "avg_tds_ppm": round(prom_tds, 2),
                "avg_depth_cm": round(prom_depth, 2),
                "samples": MAX_MUESTRAS,
                "tds_load": cmd_tds,
                "depth_load": cmd_depth,
                "status": "bloque_20_procesado"
            }
            client.publish(PUB_TOPIC, json.dumps(data_mqtt))

            enviar_comando_lora()

            historial_tds.clear()
            historial_depth.clear()

        else:
            data_instant = {
                "read_time": f"{date} {_time}",
                "tds_ppm": tds_val,
                "depth_cm": depth_val,
                "sample_num": num_muestras,
                "tds_load": cmd_tds,
                "depth_load": cmd_depth
            }
            client.publish(PUB_TOPIC, json.dumps(data_instant))

            enviar_comando_lora()

    except Exception as e:
        print("Error en recepción/procesamiento LoRa:", e)

connect_wifi()

with open("ca.crt", "r") as f:
    ca_cert = f.read()

client = MQTTClient(
    client_id=MQTT_CLIENT_ID,
    server=MQTT_BROKER,
    port=MQTT_PORT,
    user=MQTT_USER,
    password=MQTT_PASSWORD,
    keepalive=60,
    ssl=True,
    ssl_params={"server_hostname": "localhost"}
)

client.set_callback(on_message_received)

print("Conectando a Mosquitto Broker...")
client.connect()
print("Conectado a MQTT.")

client.subscribe(SUB_TOPIC)
print(f"Suscrito a: {SUB_TOPIC.decode()}")

spi = SPI(2, baudrate=1000000, sck=Pin(14), mosi=Pin(13), miso=Pin(12))
lora = LoRa(spi, cs=17, reset=5, dio0=6, callback=lora_receive)
lora.set_bandwidth(250000)
lora.set_rx_mode()
print("LoRa listo y escuchando...")

try:
    while True:
        client.check_msg()
        time.sleep(0.1)

except Exception as e:
    print("Error en bucle principal:", e)
finally:
    client.disconnect()
    print("Desconectado de MQTT.")
