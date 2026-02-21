import json
import network
import time
from oled_lib import OLED_1inch3
from machine import Pin

VERSION = "0.0.1"

class PicoDepartureBoard:
    def __init__(self):
        self.status_led = Pin("LED", Pin.OUT)
        self.status_led.value(True)

        self.oled = OLED_1inch3()

        self.oled.fill(self.oled.black)
        self.oled.show()

    def show_boot_screen(self):
        # Dimensions: 128 x 64, so 127, 63 are the max values
        
        self.oled.text("PDB", 5, 5, self.oled.white)
        self.oled.text(VERSION, 128 - 5 - len(VERSION) * 8, 64 - 10, self.oled.white)

        # top
        self.oled.line(40, 22, 87, 22, self.oled.white)
        # self.oled.line(40, 21, 87, 21, self.oled.white)
        self.oled.line(75, 22, 60, 12, self.oled.white)

        # connecting line
        self.oled.line(75, 22, 55, 38, self.oled.white)

        # bottom
        self.oled.line(40, 38, 87, 38, self.oled.white)
        # self.oled.line(40, 39, 87, 39, self.oled.white)
        self.oled.line(55, 38, 70, 48, self.oled.white)

        self.oled.show()

        time.sleep(3)

        self.oled.fill(self.oled.black)
        self.oled.show()

    def connect_to_wifi(self):
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

            self.oled.fill(self.oled.black)
            self.oled.text("Connecting to",1,10,self.oled.white)
            self.oled.text(ssid,1,27,self.oled.white)
            self.oled.text(f"Attempt {connection_attempt}",1,44,self.oled.white)
            self.oled.show()
            self.status_led.toggle()

            time.sleep(1)
        
        self.oled.fill(self.oled.black)

        if wlan.status() < 0:
            self.oled.text("WiFi Error",1,10,self.oled.white)
            self.oled.text(f"Attempt {connection_attempt}",1,27,self.oled.white)
            self.oled.text(f"Status: {wlan.status()}",1,44,self.oled.white)
            self.oled.show()
            raise Exception("Connection failed")

        self.oled.text("Pico Depature",1,10,self.oled.white)
        self.oled.text(f"Board v{VERSION}",1,27,self.oled.white)
        self.oled.text(wlan.ifconfig()[0],1,44,self.oled.white)
        self.oled.show()
        
        time.sleep(5)
        self.oled.fill(0x0000) 

    def show_departure_board(self):
        print("Showing departure board")

if __name__=='__main__':
    pdb = PicoDepartureBoard()
    pdb.show_boot_screen()
    pdb.connect_to_wifi()
    pdb.show_departure_board()
