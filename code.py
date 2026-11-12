from os import getenv
from analogio import AnalogIn

import adafruit_ads7830.ads7830 as ADC
from adafruit_ads7830.analog_in import AnalogIn as I2CAnalogIn

import alarm
import alarm.pin
import board
import digitalio
import math
# import neopixel
import pwmio
import time

import ipaddress
import socketpool
import wifi
from wiz_socket import WizSocket

WIZ_IP_1 = "192.168.1.226"
WIZ_IP_2 = "192.168.1.81"
WIZ_IP_3 = "192.168.1.76"

WIZ_PORT = 38899
WINDOW = 10

# The ADC on the ESP32-S2 maxes out at ~2.5v so we need a ref to the max value
# the ADC will return. It ends up being ~53k/65k.
# A better approach is to use a dedicated IC like the ADS7830 8-Channel 8-Bit ADC,
# or maybe use a voltage divider to drop the input voltage from 3.3v -> 2.5v so we
# can use the feather's reading directly.
ADC_MAX = 52944 # measured max
ADC_MIN = 575   # measured min
ESP32_S2_REF_VOLTAGE = 3.3
#  ADC is 8 bit but CircuitPython bitshifts everything to 16 bit for max compatibility
ADS7830_MAX = 255 << 8 # 65280

# Uncomment if using the Adafruit Feather ESP32-S2 TFT w/ display
# We need to flip the display, it is mounted upside down in the case.
# board.DISPLAY.rotation = 180 

# Get WiFi details, ensure these are set up in settings.toml
# Not using the CIRCUITPY_WIFI_* names so CircuitPython doesn't auto-connect with
# DHCP before code.py runs. We connect ourselves below with a static IP.
ssid = getenv("WIFI_SSID")
password = getenv("WIFI_PASSWORD")

if None in [ssid, password]:
    raise RuntimeError(
        "WiFi settings are kept in settings.toml, please add them there.",
        "The settings file must contain 'WIFI_SSID', 'WIFI_PASSWORD'"
    )

# Setup local controls and LEDs before starting Wi-Fi.
# pixel = neopixel.NeoPixel(board.NEOPIXEL, 1, brightness=0.2)

wake_pin = board.D38
light_mode_pin = board.TX
dimmer_pin = board.A1

slide_pot_r_pin = board.A2
slide_pot_g_pin = board.A3
slide_pot_b_pin = board.A4

# Channels on the ADS7830 (0-7), not Feather pins
SLIDE_POT_R_CHANNEL = 2
SLIDE_POT_G_CHANNEL = 3
SLIDE_POT_B_CHANNEL = 4
DIMMER_THUMBWHEEL_CHANNEL = 5

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

# Mode pins are connected to ground so we pull UP by default so 
# when they are activated they read 0v. Wiring to ground just makes
# the PCB routing easier.
light_mode_input = digitalio.DigitalInOut(light_mode_pin)
light_mode_input.direction = digitalio.Direction.INPUT
light_mode_input.pull = digitalio.Pull.UP

using_feather_adc = True

try:
# Initialize ADS7830
    i2c = board.I2C()
    adc = ADC.ADS7830(i2c)

    analog_r = I2CAnalogIn(adc, SLIDE_POT_R_CHANNEL)
    analog_g = I2CAnalogIn(adc, SLIDE_POT_G_CHANNEL)
    analog_b = I2CAnalogIn(adc, SLIDE_POT_B_CHANNEL)
    analog_dimmer = I2CAnalogIn(adc, DIMMER_THUMBWHEEL_CHANNEL)

    using_feather_adc = False
except:
    analog_r = AnalogIn(slide_pot_r_pin)
    analog_g = AnalogIn(slide_pot_g_pin)
    analog_b = AnalogIn(slide_pot_b_pin)
    analog_dimmer = AnalogIn(dimmer_pin)


def get_adc_ratio(pin, normalize_adc_readings):
    # invert because when the pot is fully to the right, it has maximum resistance
    # so we need to map lowest voltage to highest value
    value = ADC_MAX - pin.value
    if normalize_adc_readings:
        return max((min(value, ADC_MAX) - ADC_MIN) / (ADC_MAX - ADC_MIN), 0)
    else:
        return value / 65280


def apply_leds(r, g, b, d_r, d_g, d_b, dimming=100):
    scale = dimming / 100
    led_r.duty_cycle = 65535 - int((r / 255) * 65535 * scale)
    led_g.duty_cycle = 65535 - int((g / 255) * 65535 * 0.1 * scale)
    led_b.duty_cycle = 65535 - int((b / 255) * 65535 * 0.2 * scale)
    apply_diff_leds(d_r, d_g, d_b, dimming)

def apply_diff_leds(r, g, b, dimming=100):
    scale = dimming / 100
    diff_r.duty_cycle = 65535 - int((r / 255) * 65535 * scale)
    diff_g.duty_cycle = 65535 - int((g / 255) * 65535 * scale)
    diff_b.duty_cycle = 65535 - int((b / 255) * 65535 * scale)

def kelvin_to_rgb(kelvin):
    # Tanner Helland's blackbody approximation, good from ~1000K to 40000K
    temp = kelvin / 100

    if temp <= 66:
        r = 255
        g = 99.4708025861 * math.log(temp) - 161.1195681661
    else:
        r = 329.698727446 * ((temp - 60) ** -0.1332047592)
        g = 288.1221695283 * ((temp - 60) ** -0.0755148492)

    if temp >= 66:
        b = 255
    elif temp <= 19:
        b = 0
    else:
        b = 138.5177312231 * math.log(temp - 10) - 305.0447927307

    return tuple(int(max(0, min(255, c))) for c in (r, g, b))

WARMTH_MIN_K = 2200
WARMTH_MAX_K = 6200
WARMTH_STEP_K = 50

def get_warmth_kelvin():
    # Map the red pot to the bulbs' color temp range, snapped to steps
    # so ADC jitter doesn't trigger a resend every loop
    kelvin = WARMTH_MIN_K + get_adc_ratio(analog_r, normalize_adc_readings=using_feather_adc) * (WARMTH_MAX_K - WARMTH_MIN_K)
    return int(round(kelvin / WARMTH_STEP_K) * WARMTH_STEP_K)

# WiZ bulbs accept dimming from 10-100%
DIMMING_MIN = 10
DIMMING_MAX = 100
DIMMING_STEP = 5

def get_dimming():
    # Snapped to steps for the same ADC jitter reason as get_warmth_kelvin
    dimming = DIMMING_MIN + (1- get_adc_ratio(analog_dimmer, normalize_adc_readings=using_feather_adc)) * (DIMMING_MAX - DIMMING_MIN)
    return int(round(dimming / DIMMING_STEP) * DIMMING_STEP)

def get_mode():
    # Pulled up, so the switch reads False when it's closed to ground
    return "rgb" if light_mode_input.value else "warmth"

def get_rgb():
    r = int(get_adc_ratio(analog_r, normalize_adc_readings=using_feather_adc) * 255)
    g = int(get_adc_ratio(analog_g, normalize_adc_readings=using_feather_adc) * 255)
    b = int(get_adc_ratio(analog_b, normalize_adc_readings=using_feather_adc) * 255)
    return r, g, b

def show_rgb_leds(r, g, b, dimming):
    apply_leds(r, g, b, r, g, b, dimming)

def show_warmth_leds(kelvin, dimming):
    d_r, d_g, d_b = kelvin_to_rgb(kelvin)
    apply_leds(0, 0, 0, d_r, d_g, d_b, dimming)

# Light the box up for the current mode before Wi-Fi so it isn't dark while connecting.
# The bulbs get updated on the first pass of the main loop once we're connected.
if get_mode() == "rgb":
    show_rgb_leds(*get_rgb(), get_dimming())
else:
    show_warmth_leds(get_warmth_kelvin(), get_dimming())

last_r = last_g = last_b = None
last_kelvin = None
last_dimming = None
last_mode = None

print("\nConnecting to WiFi")

#  connect to your SSID
try:
    wifi.radio.set_ipv4_address(
        ipv4=ipaddress.IPv4Address("192.168.1.50"),
        netmask=ipaddress.IPv4Address("255.255.255.0"),
        gateway=ipaddress.IPv4Address("192.168.1.1"),
        ipv4_dns=ipaddress.IPv4Address("192.168.1.1"),
    )
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
print(f"My IP address is {wifi.radio.ipv4_address}")

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

def set_rgb(r, g, b, dimming):
    msg = f'{{"id":1,"method":"setPilot","params":{{"r":{r},"g":{g},"b":{b},"dimming":{dimming}}}}}'
    print(f"set light to r:{r} g:{g} b:{b} dimming:{dimming}%")
    wiz_1.send(msg)
    wiz_2.send(msg)
    wiz_3.send(msg)

def set_warmth(kelvin_temp, dimming):
    msg = f'{{"id":1,"method":"setPilot","params":{{"temp":{kelvin_temp},"dimming":{dimming}}}}}'
    print(f"set warmth to {kelvin_temp} Kelvin dimming:{dimming}%")
    wiz_1.send(msg)
    wiz_2.send(msg)
    wiz_3.send(msg)

def run_warmth_mode():
    global last_kelvin, last_dimming
    kelvin = get_warmth_kelvin()
    dimming = get_dimming()

    if kelvin != last_kelvin or dimming != last_dimming:
        set_warmth(kelvin, dimming)
        last_kelvin, last_dimming = kelvin, dimming

        show_warmth_leds(kelvin, dimming)

def run_rgb_mode():
    global last_r, last_g, last_b, last_dimming
    #ceil to prevent changing decimal values
    # print(dir(analog_r))
    # print("analog_r.value: ", analog_r.value)
    # print("analog_r.reference_voltage: ", analog_r.reference_voltage)
    r, g, b = get_rgb()
    dimming = get_dimming()

    if r != last_r or g != last_g or b != last_b or dimming != last_dimming:
        set_rgb(r, g, b, dimming)
        last_r, last_g, last_b = r, g, b
        last_dimming = dimming
        print(f"analog_r:{analog_r.value} analog_g:{analog_g.value} analog_b:{analog_b.value}")
        print(f"r:{r} g:{g} b:{b}")
        print(f"\n")

        show_rgb_leds(r, g, b, dimming)

        print(f"led_r:{led_r.duty_cycle} led_g:{led_g.duty_cycle} led_b:{led_b.duty_cycle}")

while True:
    if wake_input.value:
        enter_deep_sleep()

    mode = get_mode()
    if mode != last_mode:
        print(f"light mode switch: {mode} (TX={light_mode_input.value})")
        last_mode = mode
        # Forget what was last sent so the new mode pushes its state immediately
        last_r = last_g = last_b = None
        last_kelvin = None
        last_dimming = None

    if mode == "rgb":
        run_rgb_mode()
    else:
        run_warmth_mode()
    
    time.sleep(.1)
