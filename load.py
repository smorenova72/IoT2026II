import tkinter as tk
import paho.mqtt.client as mqtt
import ssl

BROKER   = "192.168.0.115"
PORT     = 8883
USER     = "bug"
PASSWORD = "777"
PUB_TOPIC    = "sensor/data/in"
CA_CERT  = "ca.crt"
SKIP_HOSTNAME_CHECK = True

state = {
    "tds": False,
    "level": False
}

def update_tds():
    state["tds"] = not state["tds"]
    tds_button.config(relief="sunken" if state["tds"] == True else "raised", bg="green" if state["tds"] == True else "red")
    client.publish(PUB_TOPIC, "tds/load/on" if state["tds"] == True else "tds/load/off")


def update_level():
    state["level"] = not state["level"]
    level_button.config(relief="sunken" if state["level"] == True else "raised", bg="green" if state["level"] == True else "red")
    client.publish(PUB_TOPIC, "nivel/load/on" if state["level"] == True else "nivel/load/off")

def on_connect(_c, _u, _f, _r):
    print("Connected")

def on_disconnect(_c, _u, _f, _r):
    print("Disconnected")

client = mqtt.Client(client_id="control_panel")
client.username_pw_set(USER, PASSWORD)
client.tls_set(ca_certs=CA_CERT)
client.tls_insecure_set(SKIP_HOSTNAME_CHECK)
client.on_connect = on_connect
client.on_disconnect = on_disconnect

window = tk.Tk()
window.title("Sistema de Monitoreo de Pescera")

title = tk.Label(text="Panel de Control | Sistema de Monitoreo de Pescera", wraplength=200)
title.pack(padx=16, pady=8)

frame = tk.Frame(window, width=150, height=100)
frame.pack(pady=8)

tds_label = tk.Label(frame, text="Carga TDS: ")
tds_label.grid(column=0, row=1)

tds_button = tk.Button(frame, width=2, command=update_tds, bg="red")
tds_button.grid(column=1, row=1)

level_label = tk.Label(frame, text="Carga nivel: ")
level_label.grid(column=0, row=2)

level_button = tk.Button(frame, width=2, command=update_level, bg="red")
level_button.grid(column=1, row=2)

client.connect_async(BROKER, PORT, keepalive=60)
client.loop_start()
window.mainloop()