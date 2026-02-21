import json
import network
import time
from oled_lib import OLED_1inch3
from machine import Pin

VERSION = "0.0.1"

if __name__=='__main__':

    status_led = Pin("LED", Pin.OUT)
    status_led.value(True)

    OLED = OLED_1inch3()

    OLED.fill(OLED.black)
    OLED.show()

    # Dimensions: 128 x 64, so 127, 63 are the max values
    
    OLED.text("PDB", 5, 5, OLED.white)
    OLED.text(VERSION, 128 - 5 - len(VERSION) * 8, 64 - 10, OLED.white)

    # top
    OLED.line(40, 22, 87, 22, OLED.white)
    # OLED.line(40, 21, 87, 21, OLED.white)
    OLED.line(75, 22, 60, 12, OLED.white)

    # connecting line
    OLED.line(75, 22, 55, 38, OLED.white)

    # bottom
    OLED.line(40, 38, 87, 38, OLED.white)
    # OLED.line(40, 39, 87, 39, OLED.white)
    OLED.line(55, 38, 70, 48, OLED.white)

    OLED.show()

    time.sleep(3)

    OLED.fill(OLED.black)
    OLED.show()

    with open("wifi.json", "r") as wifi_json_fp:
        wifi_creds = json.load(wifi_json_fp)
        ssid = wifi_creds["ssid"]
        password = wifi_creds["password"]
        print("WiFi creds:", wifi_creds)

    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(ssid, password)

    connection_attempt = 0
    max_attempts = 60
    while connection_attempt < max_attempts:
        if connection_attempt > 5 and (wlan.status() < 0 or wlan.status() >= 3):
            break
        connection_attempt += 1

        OLED.fill(OLED.black)
        OLED.text("Connecting to",1,10,OLED.white)
        OLED.text(ssid,1,27,OLED.white)
        OLED.text(f"Attempt {connection_attempt}",1,44,OLED.white)
        OLED.show()
        status_led.toggle()

        time.sleep(1)
    
    OLED.fill(OLED.black)

    if wlan.status() < 0:
        OLED.text("WiFi Error",1,10,OLED.white)
        OLED.text(f"Attempt {connection_attempt}",1,27,OLED.white)
        OLED.text(f"Status: {wlan.status()}",1,44,OLED.white)
        OLED.show()
        raise Exception("Connection failed")

    OLED.text("Pico Depature",1,10,OLED.white)
    OLED.text(f"Board v{VERSION}",1,27,OLED.white)
    OLED.text(wlan.ifconfig()[0],1,44,OLED.white)  
    OLED.show()
    
    time.sleep(5)
    OLED.fill(0x0000) 
    keyA = Pin(15,Pin.IN,Pin.PULL_UP)
    keyB = Pin(17,Pin.IN,Pin.PULL_UP)
    while(1):
        if keyA.value() == 0:
            if OLED.rotate == 0:
                OLED.fill_rect(0,0,128,20,OLED.white)
            else:
                OLED.fill_rect(0,44,128,20,OLED.white)
            print("A")
        else :
            if OLED.rotate == 0:
                OLED.fill_rect(0,0,128,20,OLED.black)
            else:
                OLED.fill_rect(0,44,128,20,OLED.black)
            
            
        if(keyB.value() == 0):
            if OLED.rotate == 0:
                OLED.fill_rect(0,44,128,20,OLED.white)
            else:
                OLED.fill_rect(0,0,128,20,OLED.white)
            print("B")
        else :
            if OLED.rotate == 0:
                OLED.fill_rect(0,44,128,20,OLED.black)
            else:
                OLED.fill_rect(0,0,128,20,OLED.black)
        OLED.fill_rect(0,22,128,20,OLED.white)
        OLED.text("press the button",0,28,OLED.black)
            
        OLED.show()
    
    
    time.sleep(1)
    OLED.fill(0xFFFF)
