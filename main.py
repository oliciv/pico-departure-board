import json
import network
import ntptime
import time
import gc
from oled_lib import OLED_1inch3
from machine import Pin
import urequests

VERSION = "0.0.1"


class PicoDepartureBoard:

    WIFI_MINIMUM_CONNECTION_ATTEMPTS = 0
    WIFI_MAXIMUM_CONNECTION_ATTEMPTS = 60
    DEPARTURE_REFRESH_SECONDS = 60
    API_TIMEOUT_SECONDS = 10

    # Sync time at 02:00 UTC daily (after 01:00 BST changeover and hopefully less
    # noticable/jarring if time has drifted slightly)
    TIME_SYNC_HOUR_UTC = 2

    def __init__(self):
        self.status_led = Pin("LED", Pin.OUT)
        self.status_led.value(True)

        self.oled = OLED_1inch3()

        self.oled.fill(self.oled.black)
        self.oled.show()

        # Load API credentials
        api_creds = self._load_json_config(
            "api.json", ["api_token", "proxy_url", "station_code", "station_name"]
        )
        self.api_token = api_creds["api_token"]
        self.proxy_url = api_creds["proxy_url"]
        self.station_code = api_creds["station_code"].upper()
        self.station_name = api_creds["station_name"]

        self.show_clock = True

    def _load_json_config(self, filename, required_keys):
        try:
            with open(filename, "r") as f:
                data = json.load(f)
        except OSError:
            self._show_message("Missing file", filename)
            raise
        except ValueError:
            self._show_message("Invalid JSON", filename)
            raise

        for key in required_keys:
            if key not in data:
                self._show_message("Missing key", f"'{key}'", f"in {filename}")
                raise KeyError(f"Missing '{key}' in {filename}")

        return data

    def _show_message(self, line1, line2=None, line3=None):
        self.oled.fill(self.oled.black)
        self.oled.text(line1, 1, 10, self.oled.white)
        if line2:
            self.oled.text(line2, 1, 27, self.oled.white)
        if line3:
            self.oled.text(line3, 1, 44, self.oled.white)
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
        wifi_creds = self._load_json_config("wifi.json", ["ssid", "password"])
        ssid = wifi_creds["ssid"]
        password = wifi_creds["password"]
        print("WiFi creds:", wifi_creds)

        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        wlan.connect(ssid, password)

        connection_attempt = 0
        while connection_attempt < self.WIFI_MAXIMUM_CONNECTION_ATTEMPTS:
            if connection_attempt > self.WIFI_MINIMUM_CONNECTION_ATTEMPTS and (
                wlan.status() < 0 or wlan.status() >= 3
            ):
                break
            connection_attempt += 1

            self._show_message("Connecting to", ssid, f"Attempt {connection_attempt}")
            self.status_led.toggle()

            time.sleep(1)

        if wlan.status() < 0:
            self._show_message(
                "WiFi Error",
                f"Attempt {connection_attempt}",
                f"Status: {wlan.status()}",
            )
            raise Exception("Connection failed")

        self.sync_time()

        self._show_message("Pico Departure", f"Board v{VERSION}", wlan.ifconfig()[0])

        time.sleep(5)
        self.oled.fill(self.oled.black)

    def fetch_departures_demo(self):
        return {
            "trainServices": [
                {
                    "std": "12:00",
                    "etd": "On time",
                    "destination": [{"locationName": "London Waterloo"}],
                    "platform": "1",
                },
                {
                    "std": "13:20",
                    "etd": "DLY",
                    "destination": [{"locationName": "Brighton"}],
                    "platform": "285",
                },
                {
                    "std": "14:40",
                    "etd": "CNX",
                    "destination": [
                        {"locationName": "Rhoose Cardiff International Airport"}
                    ],
                    "platform": "3",
                },
                {
                    "std": "15:10",
                    "etd": "On time",
                    "destination": [{"locationName": "Glasgow Central"}],
                    "platform": "4",
                },
                {
                    "std": "16:30",
                    "etd": "On time",
                    "destination": [{"locationName": "Manchester Piccadilly"}],
                    "platform": "5",
                },
            ]
        }

    def fetch_departures(self, num_rows=3):
        # return self.fetch_departures_demo()

        url = (
            f"{self.proxy_url}/departures/{self.station_code}"
            f"?accessToken={self.api_token}"
        )
        print(f"Fetching: {url}")

        headers = {"Accept": "application/json"}

        try:
            response = urequests.get(
                url, headers=headers, timeout=self.API_TIMEOUT_SECONDS
            )
            if response.status_code != 200:
                raise Exception(f"API error: {response.status_code}")
        except Exception as e:
            print(f"API error: {e}")
            self._show_message("API Error", "Status", str(e))
            time.sleep(5)
            return None
        gc.collect()
        data = response.json()
        response.close()
        gc.collect()
        return data

    def _truncate_destination(self, dest, max_chars):
        # remove vowels and spaces from everything except the last char
        # (e.g. "London Waterloo" -> "Lndn Wtrlo" makes more sense than "Lndn Wtrl")
        # Uppercase vowels are assumed significant, e.g. "Aberystwyth" we'd not want to
        # end up with "brstwyth"
        core, last = dest[:-1], dest[-1]
        core = "".join(c for c in core if c not in "aeiou ")

        # combine first
        dest = core + last

        # truncate while preserving last character if it's a vowel
        if len(dest) > max_chars:
            if last.lower() in "aeiou":
                # keep last vowel, truncate core only
                dest = dest[: max_chars - 1] + last
            else:
                # truncate normally
                dest = dest[: max_chars - 1] + "."

        return dest

    def _last_sunday_of_month(self, year, month):
        """
        Return day of month of the last Sunday in a given month
        """
        # Find last day of the month
        if month == 12:
            next_month = 1
            next_year = year + 1
        else:
            next_month = month + 1
            next_year = year
        # Last day = day before the 1st of next month
        t = time.mktime((next_year, next_month, 1, 0, 0, 0, 0, 0))
        t -= 24 * 60 * 60  # subtract one day
        last_day_info = time.localtime(t)
        last_day = last_day_info[2]

        # Back up to Sunday (MicroPython: 0=Mon, 6=Sun)
        days_since_sunday = (last_day_info[6] + 1) % 7
        return last_day - days_since_sunday

    def sync_time(self):
        """
        Sync clock via NTP and determine whether we're in BST.
        BST starts at 01:00 UTC on the last Sunday of March
        and ends at 01:00 UTC on the last Sunday of October.
        """
        try:
            ntptime.settime()
        except Exception as e:
            # Not the end of the world, we'll try again tomorrow!
            print(f"NTP sync failed: {e}")

        year = time.localtime()[0]
        bst_start = time.mktime(
            (year, 3, self._last_sunday_of_month(year, 3), 1, 0, 0, 0, 0)
        )
        bst_end = time.mktime(
            (year, 10, self._last_sunday_of_month(year, 10), 1, 0, 0, 0, 0)
        )
        now = time.time()
        self.is_bst = bst_start <= now < bst_end
        self._last_sync_date = time.localtime()[:3]  # (year, month, day)
        print(f"Time synced, BST status: {self.is_bst}")

    def _get_current_time(self, include_seconds=False):
        t = time.localtime()
        hour = t[3]
        if self.is_bst:
            # BST is UTC+1, so add 1 hour (and wrap around if necessary for midnight)
            hour = (hour + 1) % 24

        if include_seconds:
            return "{:02d}:{:02d}:{:02d}".format(hour, t[4], t[5])
        else:
            return "{:02d}:{:02d}".format(hour, t[4])

    def _format_etd(self, etd, std):
        # estimated: "On time", "Delayed", "+MM mins", or "HH:MM"
        if etd not in (std, "On time") and all(":" in t for t in (etd, std)):
            # convert HH:MM to minutes to display minutes delayed
            std_h, std_m = map(int, std.split(":"))
            etd_h, etd_m = map(int, etd.split(":"))

            std_total = std_h * 60 + std_m
            etd_total = etd_h * 60 + etd_m

            diff = etd_total - std_total
            # Handle midnight wraparound (e.g. scheduled 23:50, estimated 00:05)
            if diff < 0:
                diff += 24 * 60
            if diff == 0:
                return "On time"
            return f"+{diff} mins"
        return etd

    def render_departures(self, services, offset=0):
        self.oled.fill(self.oled.black)

        if not services:
            self.oled.text("Welcome to", 1, 10, self.oled.white)
            self.oled.text(
                self._truncate_destination(self.station_name, 16),
                1,
                27,
                self.oled.white,
            )
            self.oled.text(self._get_current_time(), 1, 44, self.oled.white)
            self.oled.show()
            return

        num_rows = 2 if self.show_clock else 3
        row_spacing = 20 if self.show_clock else 21

        for i in range(num_rows):
            idx = offset + i
            if idx >= len(services):
                break

            service = services[idx]
            std = service.get("std", "??:??")  # scheduled time of departure

            etd = self._format_etd(service.get("etd", ""), std)

            platform = service.get("platform", "")

            # Get destination name, truncate to fit
            dest = ""
            if service.get("destination"):
                dest = service["destination"][0].get("locationName", "")
            # At 8px per char, 128px = 16 chars max
            # Time takes 6 chars ("HH:MM" plus a space)

            max_dest_chars = 16 - 6  # 10 chars for destination
            if len(dest) > max_dest_chars:
                dest = self._truncate_destination(dest, max_dest_chars)

            y = 2 + (i * row_spacing)
            line_text = f"{std} {dest}"
            self.oled.text(line_text, 1, y, self.oled.white)

            if etd:
                self.oled.text(etd, 1, y + 10, self.oled.white)

            if platform:
                platform_str = f"Plat {platform}"
                self.oled.text(
                    f"{platform_str}",
                    128 - len(f"{platform_str}") * 8,
                    y + 10,
                    self.oled.white,
                )

        if self.show_clock:
            # Separator line
            self.oled.hline(0, 44, 128, self.oled.white)

            # Centered clock at the bottom
            current_time = self._get_current_time(include_seconds=True)
            time_width = len(current_time) * 8
            time_x = (128 - time_width) // 2
            self.oled.text(current_time, time_x, 50, self.oled.white)

        self.oled.show()

    def show_departure_board(self):
        print("Showing departure board")

        services = []
        offset = 0
        last_fetch = 0

        buttons = {
            "clock": Pin(15, Pin.IN, Pin.PULL_UP),
            "scroll": Pin(17, Pin.IN, Pin.PULL_UP),
        }

        # Default state is pulled up, so 1 = not pressed
        prev_state = {name: 1 for name in buttons}

        while True:
            now = time.time()

            # Daily NTP sync and BST recalculation at 02:00 UTC
            t = time.localtime(now)
            if t[3] == self.TIME_SYNC_HOUR_UTC and t[:3] != self._last_sync_date:
                self.sync_time()

            # Refresh data periodically
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

            elif self.show_clock and now - last_fetch >= 1:
                # We can refresh just the clock more often while it's visible,
                # as this includes seconds, we'll need to update it every second
                self.render_departures(services, offset)

            # Read all buttons and detect change in state (pressed)
            pressed = {}
            for name, pin in buttons.items():
                cur = pin.value()
                pressed[name] = cur == 0 and prev_state[name] == 1
                prev_state[name] = cur

            if pressed["clock"]:
                self.show_clock = not self.show_clock
                self.render_departures(services, offset)

            if pressed["scroll"]:
                offset += 1
                if offset >= len(services):
                    offset = 0
                self.render_departures(services, offset)


if __name__ == "__main__":
    pdb = PicoDepartureBoard()
    pdb.show_boot_screen()
    pdb.connect_to_wifi()
    pdb.show_departure_board()
