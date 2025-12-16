import network, socket, ujson, _thread
import urequests
import uasyncio as asyncio
from machine import Pin, PWM, UART
from time import sleep, ticks_ms, ticks_diff, time
import MPU6050

WIFI_NAVN = "Navn på nettet"
WIFI_KODE = "Kode til nettet"

solenoide_ip = "172.19.101.61"
solenoide_port = 5005

hjemmeside = "www.url.tld/api/update"
patient = 196 #Test

led_pin = 26
buz_pin = 25
pb_pin = 4
vibmot_pin = 27
UART_PORT = 2
UART_BAUD = 9600

led = Pin(led_pin, Pin.OUT)
buzzer = PWM(Pin(buz_pin))
buzzer.freq(3000)
buzzer.duty(0)
pb = Pin(pb_pin, Pin.IN, Pin.PULL_UP)
vib = PWM(Pin(vibmot_pin))
vib.freq(175)
vib.duty(0)
MPU6050 = MPU6050.MPU6050()
gps_uart = UART(UART_PORT, UART_BAUD)

fald = 0.5
fald_threshold = 2.0
fald_tid_ms = 2000

UNIT = 0.2
sos = [1, 1, 1, 3, 3, 3, 1, 1, 1]
sos_index = 0
sos_tid = ticks_ms()

alarm_igang = False
fald_tid = None

alarm_grund = "Stop"
lat = None
lon = None
gps = False


solenoid_ok = False
web_ok = False

lock = _thread.allocate_lock()

venter_solenoid = False
venter_web = False
gps_request = False

wlan = None
wifi_lock = _thread.allocate_lock()

def wifi_forbind():
    global wlan
    with wifi_lock:
        if wlan is None:
            wlan = network.WLAN(network.STA_IF)
            wlan.active(True)

        if not wlan.isconnected():
            wlan.connect(WIFI_NAVN, WIFI_KODE)
            while not wlan.isconnected():
                sleep(0.2)

        return True
    
def venter_send(solenoid = False, web = False, gps = False):
    global venter_solenoid, venter_web, gps_request
    with lock:
        if solenoid:
            venter_solenoid = True
        if web:
            venter_web = True
        if gps:
            gps_request = True


def _nmea_to_deg(field, hemi):
    if not field:
        return None
    raw_data = float(field)
    grader = int(raw_data / 100)
    minutter = raw_data - grader * 100
    val = grader + minutter / 60
    return -val if hemi in ("S", "W") else val


def gps_fast(timeout_ms=10000):
    start = ticks_ms()
    buf = b""

    while ticks_diff(ticks_ms(), start) < timeout_ms:
        if gps_uart.any():
            tegn = gps_uart.read(1)
            if not tegn: 
                continue

            if tegn == b'\n':
                try:
                    line = buf.decode().strip()
                except:
                    buf = b""
                    continue
                buf = b""

                if line.startswith("$GPRMC") or line.startswith("$GNRMC"):
                    parts = line.split(",")
                    if len(parts) > 6 and parts[2] == "A":
                        return (
                            _nmea_to_deg(parts[3], parts[4]),
                            _nmea_to_deg(parts[5], parts[6])
                        )

                if line.startswith("$GPGGA") or line.startswith("$GNGGA"):
                    parts = line.split(",")
                    if len(parts) > 6 and parts[6] in ("1", "2"):
                        return (
                            _nmea_to_deg(parts[2], parts[3]),
                            _nmea_to_deg(parts[4], parts[5])
                        )
            else:
                buf += tegn

    return None

def gps_thread():
    global lat, lon, gps, gps_request

    while True:
        do_gps = False
        with lock:
            do_gps = gps_request

        if do_gps:
            pos = gps_fast(timeout_ms=10000)
            with lock:
                gps_request = False

            if pos:
                lat_ny, lon_ny = pos
                with lock:
                    lat = lat_ny
                    lon = lon_ny
                    gps = True
            else:
                with lock:
                    gps = False
            
            venter_send(web=True)

        sleep(0.05)


def send_til_solenoid(alarm_on, grund):
    addr = socket.getaddrinfo(solenoide_ip, solenoide_port)[0][-1]
    s = socket.socket()
    s.settimeout(1)
    try:
        s.connect(addr)
        door_state = "OPEN" if alarm_on else "LOCKED"
        payload = ujson.dumps({"alarm": bool(alarm_on), "reason": grund, "door_state": door_state})
        s.send(payload.encode())
    finally:
        try:
            s.close()
        except:
            pass

def send_til_web(payload):
    r  = urequests.post(
        hjemmeside,
        data = ujson.dumps(payload),
        headers = {"Content-Type": "application/json"}
    )
    r.close()

def web_payload():
    with lock:
        _alarm = bool(alarm_igang)
        _reason = alarm_grund
        _gps_ok = bool(gps)
        _lat = lat
        _lon = lon
        _sol_ok = bool(solenoid_ok)

    return {
        "patient_id": patient,
        "alarm": _alarm,
        "reason": _reason,
        "door_state": "OPEN" if _alarm else "LOCKED",
        "gps_ok": _gps_ok,
        "lat": _lat,
        "lon": _lon,
        "solenoid_ok": _sol_ok,
        "sent_to_web": True,
    }


def net_thread():
    global solenoid_ok, web_ok, venter_solenoid, venter_web

    while True:
        try:
            if wlan is None or (not wlan.isconnected()):
                wifi_forbind()
        except Exception as e:
            print("wifi fejl", e)
            sleep(0.5)
            continue

        with lock:
            do_sol = venter_solenoid
            do_web = venter_web
        
        if do_sol:
            try:
                reason = alarm_grund if alarm_igang else "STOP"
                send_til_solenoid(alarm_igang, reason)
                solenoid_ok = True
                with lock:
                    venter_solenoid = False
            
            except Exception as e:
                print("Solenoid fejl:", e)
                solenoid_ok = False


        if do_web:
            try:
                payload = web_payload()
                send_til_web(payload)
                web_ok = True
                with lock:
                    venter_web = False

            except Exception as e:
                print("web fejl:", e)
                web_ok = False

        sleep(0.05)

_thread.start_new_thread(net_thread, ())
_thread.start_new_thread(gps_thread, ())

def start_alarm(reason = "ukendt"):
    global alarm_igang, sos_index, sos_tid, alarm_grund, web_ok

    with lock:
        alarm_igang = True
        alarm_grund = reason

    web_ok = False
    sos_index = 0
    sos_tid = ticks_ms()

    led.on()
    buzzer.duty(512)
    vib.duty(400)

    venter_send(solenoid=True, gps=True)
    print("Alarm:", reason)

def stop_alarm():
    global web_ok

    with lock:
        global alarm_igang, alarm_grund
        alarm_igang = False
        alarm_grund = "STOP"

    web_ok = False

    led.off()
    buzzer.duty(0)
    vib.duty(0)

    venter_send(solenoid=True, web=True)

async def update_sos():
    global sos_index, sos_tid
    led_state = 0

    while True:
        if not alarm_igang:
            led_state = 0
            await asyncio.sleep_ms(50)
            continue

        nu = ticks_ms()
        duration_ms = int(UNIT * 1000 * sos[sos_index])

        if ticks_diff(nu, sos_tid) >= duration_ms:
            if led_state == 0:
                led.on()
                buzzer.duty(512)
                vib.duty(400)
                led_state = 1
            else:
                led.off()
                buzzer.duty(0)
                vib.duty(0)
                led_state = 0
                sos_index = (sos_index + 1) % len(sos)
            sos_tid = nu

        await asyncio.sleep_ms(10)


async def knappen():
    while True:
        if pb.value() == 0:
            if alarm_igang:
                stop_alarm()
            else:
                start_alarm("Manuel")
            await asyncio.sleep_ms(300)
        await asyncio.sleep_ms(10)

async def fald_func():
    global fald_tid
    fald_tid = None

    while True:
        if not alarm_igang:
            total_accel = MPU6050.read_accel_abs(g = True)
            nu = ticks_ms()

            if total_accel < fald:
                fald_tid = nu
            elif fald_tid is not None:
                if total_accel > fald_threshold and ticks_diff(nu, fald_tid) < fald_tid_ms:
                    start_alarm("Fald registeret")
                    fald_tid = None
                elif ticks_diff(nu, fald_tid) > fald_tid_ms:
                    fald_tid = None

        await asyncio.sleep_ms(10)

async def main():
    asyncio.create_task(update_sos())
    asyncio.create_task(knappen())
    asyncio.create_task(fald_func())

    while True:
        await asyncio.sleep_ms(500)

asyncio.run(main())
