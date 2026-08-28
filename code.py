from os import getenv
from analogio import AnalogIn

import alarm
import alarm.pin
import board
import digitalio
import time
import neopixel
import pwmio

import wifi
import socketpool
from wiz_socket import WizSocket

WIZ_IP_1 = "192.168.1.226"
WIZ_IP_2 = "192.168.1.81"
WIZ_IP_3 = "192.168.1.76"

WIZ_PORT = 38899
WINDOW = 10

ADC_MAX = 52944 # Feather ESP32-S2
ADC_MIN = 575
ESP32_S2_REF_VOLTAGE = 3.3

# flip display, it is mounted upside down in the case
# board.DISPLAY.rotation = 180

# Get WiFi details, ensure these are set up in settings.toml
ssid = getenv("CIRCUITPY_WIFI_SSID")
password = getenv("CIRCUITPY_WIFI_PASSWORD")

if None in [ssid, password]:
    raise RuntimeError(
        "WiFi settings are kept in settings.toml, "
        "please add them there. The settings file must contain "
        "'CIRCUITPY_WIFI_SSID', 'CIRCUITPY_WIFI_PASSWORD', "
        "at a minimum."
    )

# Setup local controls and LEDs before starting Wi-Fi.
pixel = neopixel.NeoPixel(board.NEOPIXEL, 1, brightness=0.2)

wake_pin = board.D13

analog_r = AnalogIn(board.A2)
analog_g = AnalogIn(board.A3)
analog_b = AnalogIn(board.A4)

# Duty cycles are inverted because the LEDs are common anode, so 0 is fully on and 65535 is fully off
led_r = pwmio.PWMOut(board.D5, frequency=5000, duty_cycle=0)
led_g = pwmio.PWMOut(board.D9, frequency=5000, duty_cycle=0)
led_b = pwmio.PWMOut(board.D6, frequency=5000, duty_cycle=0)

diff_r = pwmio.PWMOut(board.D12, frequency=5000, duty_cycle=0)
diff_g = pwmio.PWMOut(board.D11, frequency=5000, duty_cycle=0)
diff_b = pwmio.PWMOut(board.D10, frequency=5000, duty_cycle=0)

wake_input = digitalio.DigitalInOut(wake_pin)
wake_input.direction = digitalio.Direction.INPUT
wake_input.pull = digitalio.Pull.DOWN

def get_adc_ratio(pin):
    # invert because when the pot is fully to the right, it has maximum resistance
    value = ADC_MAX - pin.value
    return max((min(value, ADC_MAX) - ADC_MIN) / (ADC_MAX - ADC_MIN), 0)

def apply_leds(r, g, b):
    led_r.duty_cycle = 65535 - int((r / 255) * 65535)
    led_g.duty_cycle = 65535 - int((g / 255) * 65535 * 0.1)
    led_b.duty_cycle = 65535 - int((b / 255) * 65535 * 0.2)
    diff_r.duty_cycle = 65535 - int((r / 255) * 65535)
    diff_g.duty_cycle = 65535 - int((g / 255) * 65535)
    diff_b.duty_cycle = 65535 - int((b / 255) * 65535)

r = int(get_adc_ratio(analog_r) * 255)
g = int(get_adc_ratio(analog_g) * 255)
b = int(get_adc_ratio(analog_b) * 255)
apply_leds(r, g, b)
last_r, last_g, last_b = r, g, b

print("\nConnecting to WiFi")

#  connect to your SSID
try:
    wifi.radio.connect(ssid, password)
except TypeError:
    print("Could not find WiFi info. Check your settings.toml file!")
    raise

print("Connected to WiFi")

pool = socketpool.SocketPool(wifi.radio)
wiz_1 = WizSocket(pool, WIZ_IP_1, WIZ_PORT)
wiz_2 = WizSocket(pool, WIZ_IP_2, WIZ_PORT)
wiz_3 = WizSocket(pool, WIZ_IP_3, WIZ_PORT)

#  prints MAC address to REPL
print("My MAC addr:", [hex(i) for i in wifi.radio.mac_address])

#  prints IP address to REPL
print(f"My IP address is {wifi.radio.ipv4_address}")

#### end WiFi test

def enter_deep_sleep():
    print("entering deep sleep")
    wake_input.deinit()

    # D13 needs an external pulldown so releasing 3.3V makes it low and wakes the board.
    wake_alarm = alarm.pin.PinAlarm(pin=wake_pin, value=False, pull=False)
    alarm.exit_and_deep_sleep_until_alarms(wake_alarm)

def battery_color(percent):
    if percent <= 25:
        return (255, 0, 0)      # red
    elif percent <= 50:
        return (255, 80, 0)     # orange
    else:
        return (0, 255, 0)      # green

def set_light(r, g, b):
    msg = f'{{"id":1,"method":"setPilot","params":{{"r":{r},"g":{g},"b":{b},"dimming":100}}}}'
    print(f"set light to r:{r} g:{g} b:{b}")
    wiz_1.send(msg)
    wiz_2.send(msg)
    wiz_3.send(msg)


while True:
    if wake_input.value:
        enter_deep_sleep()

    #ceil to prevent changing decimal values
    # print(dir(analog_r))
    # print("analog_r.value: ", analog_r.value)
    # print("analog_r.reference_voltage: ", analog_r.reference_voltage)
    r = int(get_adc_ratio(analog_r) * 255)
    g = int(get_adc_ratio(analog_g) * 255)
    b = int(get_adc_ratio(analog_b) * 255)

    if r != last_r or g != last_g or b != last_b:
        set_light(r, g, b)
        last_r, last_g, last_b = r, g, b
        print(f"analog_r:{analog_r.value} analog_g:{analog_g.value} analog_b:{analog_b.value}")
        print(f"r:{r} g:{g} b:{b}")
        print(f"\n")

        apply_leds(r, g, b)

        print(f"led_r:{led_r.duty_cycle} led_g:{led_g.duty_cycle} led_b:{led_b.duty_cycle}")
    time.sleep(.1)
