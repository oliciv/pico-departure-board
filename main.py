import json
import network
import ntptime
import time
import ubinascii
import gc
from oled_lib import OLED_1inch3
from machine import Pin
import urequests 

VERSION = "0.0.1"

class PicoDepartureBoard:

    WIFI_MINIMUM_CONNECTION_ATTEMPTS = 5
    WIFI_MAXIMUM_CONNECTION_ATTEMPTS = 60
    DEPARTURE_REFRESH_SECONDS = 60

    def __init__(self):
        self.status_led = Pin("LED", Pin.OUT)
        self.status_led.value(True)

        self.oled = OLED_1inch3()

        self.oled.fill(self.oled.black)
        self.oled.show()

        # Load API credentials
        with open("api.json", "r") as api_json_fp:
            api_creds = json.load(api_json_fp)
            self.api_token = api_creds["api_token"]
            self.proxy_url = api_creds["proxy_url"]
            self.station_code = api_creds["station_code"].upper()
            self.station_name = api_creds["station_name"]

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
        while connection_attempt < self.WIFI_MAXIMUM_CONNECTION_ATTEMPTS:
            if connection_attempt > self.WIFI_MINIMUM_CONNECTION_ATTEMPTS and (wlan.status() < 0 or wlan.status() >= 3):
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
        self.oled.fill(self.oled.black) 

    def fetch_departures_demo(self):
        return {
            "trainServices": [
            {"std": "12:00", "etd": "On time", "destination": [{"locationName": "London Waterloo"}], "platform": "1"},
            {"std": "13:20", "etd": "DLY", "destination": [{"locationName": "Brighton"}], "platform": "285"},
            {"std": "14:40", "etd": "CNX", "destination": [{"locationName": "Rhoose Cardiff International Airport"}], "platform": "3"},
            {"std": "15:10", "etd": "On time", "destination": [{"locationName": "Glasgow Central"}], "platform": "4"},
            {"std": "16:30", "etd": "On time", "destination": [{"locationName": "Manchester Piccadilly"}], "platform": "5"},
        ]
        }

    def fetch_departures(self, num_rows=3):
        # return self.fetch_departures_demo()

        url = f"{self.proxy_url}/departures/{self.station_code}?accessToken={self.api_token}"
        print(f"Fetching: {url}")

        headers = {
            "Accept": "application/json"
        }

        response = urequests.get(url, headers=headers)

        gc.collect()

        if response.status_code != 200:
            print(f"API error: {response.status_code}")
            print(response.text)
            response.close()
            return None

        data = response.json()
        response.close()
        gc.collect()
        return data

    def _truncate_destination(self, dest, max_chars):
        # remove vowels and spaces from everything except the last char
        # (e.g. "London Waterloo" -> "Lndn Wtrlo" makes more sense than "Lndn Wtrl")
        # Uppercase vowels are assumed significant, e.g. "Aberystwyth" we'd not want to end up with "brstwyth"
        core, last = dest[:-1], dest[-1]
        core = ''.join(c for c in core if c not in 'aeiou ')

        # combine first
        dest = core + last

        # truncate while preserving last character if it's a vowel
        if len(dest) > max_chars:
            if last.lower() in 'aeiou':
                # keep last vowel, truncate core only
                dest = dest[:max_chars-1] + last
            else:
                # truncate normally
                dest = dest[:max_chars-1] + "."

        return dest

    def _get_current_time(self):
        # The pico has no real time clock so we'll need to fetch it from a NTP server
        # TODO: Timezone (BST/GMT) support
        ntptime.settime()
        t = time.localtime()
        return "{:02d}:{:02d}".format(t[3], t[4])

    def render_departures(self, services, offset=0):
        self.oled.fill(self.oled.black)

        if not services:
            self.oled.text("Welcome to", 1, 10, self.oled.white)
            self.oled.text(self._truncate_destination(self.station_name, 16), 1, 27, self.oled.white)
            self.oled.text(self._get_current_time(), 1, 44, self.oled.white)
            self.oled.show()
            return

        # Show up to 3 services, that's all we can fit!
        for i in range(3):
            idx = offset + i
            if idx >= len(services):
                break

            service = services[idx]
            std = service.get("std", "??:??")       # scheduled time of departure
            etd = service.get("etd", "")            # estimated: "On time", "Delayed", or "HH:MM"
            platform = service.get("platform", "")

            # Get destination name, truncate to fit
            dest = ""
            if service.get("destination"):
                dest = service["destination"][0].get("locationName", "")
            # Truncate destination: 5 chars time + space + dest + space + etd
            # At 8px per char, 128px = 16 chars max
            # Time takes 6 chars ("HH:MM "), status takes up 3 chars ("CNX", "DLY") - we'll just show the time if it's on time

            max_dest_chars = 16 - 6  # 10 chars for destination
            if len(dest) > max_dest_chars:
                dest = self._truncate_destination(dest, max_dest_chars)

            y = 5 + (i * 21)
            line_text = f"{std} {dest}"
            self.oled.text(line_text, 1, y, self.oled.white)

            if etd:
                self.oled.text(etd, 1, y + 8, self.oled.white)
            
            if platform:
                platform_str = f"Plat {platform}"
                self.oled.text(f"{platform_str}", 128 - len(f"{platform_str}") * 8, y + 8, self.oled.white)

        self.oled.show()

    def show_departure_board(self):
        print("Showing departure board")

        services = []
        offset = 0
        last_fetch = 0

        while True:
            # Refresh data periodically
            now = time.time()
            if now - last_fetch >= self.DEPARTURE_REFRESH_SECONDS:
                data = self.fetch_departures()
                if data and data.get("trainServices"):
                    services = data["trainServices"]
                    offset = 0
                    print(f"Got {len(services)} services")
                elif data:
                    services = []
                    print("No train services in response")
                else:
                    print("Failed to fetch data, retrying...")

                last_fetch = now
                self.render_departures(services, offset)

if __name__=='__main__':
    pdb = PicoDepartureBoard()
    pdb.show_boot_screen()
    pdb.connect_to_wifi()
    pdb.show_departure_board()
