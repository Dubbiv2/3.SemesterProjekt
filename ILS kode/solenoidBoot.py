import network, socket
from machine import Pin
from time import sleep
import ujson

wifi_navn = "SkoleProjekt"
wifi_kode = "InternetSkoleprojekt1234!"

solenoid = Pin(18, Pin.OUT)
solenoid.value(0)

port = 5005

def wifi_forbindelse():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(wifi_navn, wifi_kode)
        while not wlan.isconnected():
            sleep(0.2)
    return wlan

wlan = wifi_forbindelse()
ip = wlan.ifconfig()[0]
print("Modtager ip", ip)

addr = socket.getaddrinfo("0.0.0.0", port) [0][-1]
s = socket.socket()
s.bind(addr)
s.listen(1)

while True:
    cl, remote_addr = s.accept()
    print("Forbindelse fra:", remote_addr)
    
    try:
        data = cl.recv(256)
        
        try:
            msg = ujson.loads(data)
            alarm = msg.get("alarm", False)
            reason = msg.get("reason", None)
            
            if alarm:
                solenoid.value(1)    
            else:
                solenoid.value(0)
                
        except Exception as e:
            print("Kunne ikke parse JSON:", e)
            
    except Exception as e:
        print("Fejl:", e)
        
    finally:
        cl.close()


