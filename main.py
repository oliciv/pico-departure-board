import json
import network
import ntptime
import time
import gc
import rp2
from oled_lib import OLED_1inch3
from machine import Pin, unique_id
import urequests
from machine import reset
from captive_portal import CaptivePortal

VERSION = "0.0.1"


class PicoDepartureBoard:

    WIFI_MINIMUM_CONNECTION_ATTEMPTS = 0
    WIFI_MAXIMUM_CONNECTION_ATTEMPTS = 60
    DEPARTURE_REFRESH_SECONDS = 60
    DELAY_PLATFORM_DISPLAY_MS = 10000
    CALLING_AT_PAUSE_MS = 1000
    CALLING_AT_SCROLL_MS = 100
    API_TIMEOUT_SECONDS = 10
    ROTATE_SCREEN = False
    DARWIN_ENDPOINT = "https://lite.realtime.nationalrail.co.uk/OpenLDBWS/ldb12.asmx"
    SETUP_SSID = f"PDBSetup-{unique_id().hex()[-4:]}"
    SETUP_PORT = 80

    # Sync time at 02:00 UTC daily (after 01:00 BST changeover and hopefully less
    # noticable/jarring in the middle of the night if time has drifted slightly
    # and needs to be corrected)
    TIME_SYNC_HOUR_UTC = 2

    def __init__(self):
        self.status_led = Pin("LED", Pin.OUT)
        self.status_led.value(True)

        self.oled = OLED_1inch3(rotate=self.ROTATE_SCREEN)

        self.oled.fill(self.oled.black)
        self.oled.show()

        # Load API credentials
        api_creds = self._load_json_config(
            "api.json", ["api_token", "station_code", "station_name"]
        )
        self.api_token = api_creds["api_token"]
        self.station_code = api_creds["station_code"].upper()
        self.station_name = api_creds["station_name"]

        self.show_clock = True

        self.buttons = {
            "clock": Pin(15, Pin.IN, Pin.PULL_UP),
            "scroll": Pin(17, Pin.IN, Pin.PULL_UP),
        }

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

    def _build_departures_request(self, num_rows=3):
        return (
            '<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"'
            ' xmlns:typ="http://thalesgroup.com/RTTI/2013-11-28/Token/types"'
            ' xmlns:ldb="http://thalesgroup.com/RTTI/2021-11-01/ldb/">'
            "<soap:Header><typ:AccessToken>"
            "<typ:TokenValue>{}</typ:TokenValue>"
            "</typ:AccessToken></soap:Header>"
            "<soap:Body><ldb:GetDepartureBoardRequest>"
            "<ldb:numRows>{}</ldb:numRows>"
            "<ldb:crs>{}</ldb:crs>"
            "</ldb:GetDepartureBoardRequest></soap:Body>"
            "</soap:Envelope>"
        ).format(self.api_token, num_rows, self.station_code)

    def _build_service_request(self, service_id):
        return (
            '<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"'
            ' xmlns:typ="http://thalesgroup.com/RTTI/2013-11-28/Token/types"'
            ' xmlns:ldb="http://thalesgroup.com/RTTI/2021-11-01/ldb/">'
            "<soap:Header><typ:AccessToken>"
            "<typ:TokenValue>{}</typ:TokenValue>"
            "</typ:AccessToken></soap:Header>"
            "<soap:Body><ldb:GetServiceDetailsRequest>"
            "<ldb:serviceID>{}</ldb:serviceID>"
            "</ldb:GetServiceDetailsRequest></soap:Body>"
            "</soap:Envelope>"
        ).format(self.api_token, service_id)

    def _find_tag_value(self, xml, tag, start=0):
        # Find <prefix:tag> or <tag> and extract content up to closing tag
        # Search for :tag> first (namespaced), then <tag> (unnamespaced)
        needle = ":" + tag + ">"
        pos = xml.find(needle, start)
        if pos < 0:
            needle = "<" + tag + ">"
            pos = xml.find(needle, start)
            if pos < 0:
                return None, start
        val_start = pos + len(needle)
        # Find closing tag - look for </...tag>
        end = xml.find(tag + ">", val_start)
        if end < 0:
            return None, start
        # Walk back to find the </  or </:
        val_end = end
        while (
            val_end > val_start and xml[val_end - 1] != "<" and xml[val_end - 1] != ":"
        ):
            val_end -= 1
        if val_end <= val_start:
            return None, start
        # val_end - 1 is either < or :, we want everything before that
        if xml[val_end - 1] == ":":
            # </prefix:tag> - go back one more to find <
            val_end -= 1
            while val_end > val_start and xml[val_end - 1] != "<":
                val_end -= 1
        # val_end - 1 should be '<' now (the '<' of the closing tag)
        value = xml[val_start : val_end - 1]
        # Unescape XML entities
        if "&" in value:
            value = value.replace("&amp;", "&")
            value = value.replace("&lt;", "<")
            value = value.replace("&gt;", ">")
            value = value.replace("&apos;", "'")
            value = value.replace("&quot;", '"')
        after = end + len(tag) + 1
        return value, after

    def _find_all_blocks(self, xml, tag):
        pos = 0
        while True:
            # Find opening tag with namespace prefix or without
            needle = ":" + tag + ">"
            start = xml.find(needle, pos)
            if start < 0:
                needle = "<" + tag + ">"
                start = xml.find(needle, pos)
                if start < 0:
                    break
            block_start = start + len(needle)
            # Find closing tag
            close_needle = tag + ">"
            end = xml.find(close_needle, block_start)
            # Walk backwards to find </ for the closing tag
            scan = end - 1
            while scan >= block_start and xml[scan] != "<":
                scan -= 1
            if scan < block_start:
                break
            yield xml[block_start:scan]
            pos = end + len(close_needle)

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

    def fetch_departures(self, num_rows=3):
        print("Fetching departures from National Rail API")
        body = self._build_departures_request(num_rows)
        headers = {"Content-Type": "application/soap+xml; charset=utf-8"}

        try:
            response = urequests.post(
                self.DARWIN_ENDPOINT,
                data=body,
                headers=headers,
                timeout=self.API_TIMEOUT_SECONDS,
            )
            if response.status_code != 200:
                raise Exception(f"API error: {response.status_code}")
        except Exception as e:
            print(f"API error: {e}")
            self._show_message("API Error", "Status", str(e))
            time.sleep(5)
            return None

        gc.collect()
        xml = response.text
        response.close()
        gc.collect()

        services = []
        for block in self._find_all_blocks(xml, "service"):
            std, _ = self._find_tag_value(block, "std")
            etd, _ = self._find_tag_value(block, "etd")
            platform, _ = self._find_tag_value(block, "platform")
            service_id, _ = self._find_tag_value(block, "serviceID")

            # Destination name is nested inside a destination > location block
            dest_name = None
            for dest_block in self._find_all_blocks(block, "destination"):
                dest_name, _ = self._find_tag_value(dest_block, "locationName")
                if not dest_name:
                    dest_name, _ = self._find_tag_value(dest_block, "name")
                break

            service = {
                "std": std or "??:??",
                "etd": etd or "",
                "serviceID": service_id or "",
                "destination": [{"locationName": dest_name or ""}],
            }
            if platform:
                service["platform"] = platform
            services.append(service)

        if services:
            return {"trainServices": services}
        return {"trainServices": None}

    def fetch_calling_points(self, service_id):
        print(f"Fetching calling points for {service_id}")
        body = self._build_service_request(service_id)
        headers = {"Content-Type": "application/soap+xml; charset=utf-8"}

        try:
            response = urequests.post(
                self.DARWIN_ENDPOINT,
                data=body,
                headers=headers,
                timeout=self.API_TIMEOUT_SECONDS,
            )
            if response.status_code != 200:
                return []
        except Exception as e:
            print(f"Calling points fetch failed: {e}")
            return []

        gc.collect()
        xml = response.text
        response.close()
        gc.collect()

        # Find the subsequentCallingPoints section
        points = []
        for scp_block in self._find_all_blocks(xml, "subsequentCallingPoints"):
            for cp_block in self._find_all_blocks(scp_block, "callingPoint"):
                name, _ = self._find_tag_value(cp_block, "locationName")
                if name:
                    points.append(name)
            break  # only first subsequentCallingPoints list
        return points

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

    def render_welcome_screen(self):
        self.oled.text("Welcome to", 1, 10, self.oled.white)
        self.oled.text(
            self._truncate_destination(self.station_name, 16),
            1,
            27,
            self.oled.white,
        )
        self.oled.text(self._get_current_time(), 1, 44, self.oled.white)
        self.oled.show()

        # If we have no services, it's likely the middle of the night, a day of
        # engineering works, a particularly quiet station - or some other situation
        # where it's unlikely that a train will suddenly sneak up on us, so we can
        # afford to sleep for 5 minutes and check again to see if the situation has
        # changed. We still update the clock each minute on the minute so it doesn't
        # look frozen.

        # Initially, sleep until the next minute passes to keep the clock accurate
        current_seconds = time.localtime()[5]
        sleep_time = 60 - current_seconds

        for _ in range(5):
            time.sleep(sleep_time)
            sleep_time = 60  # from now on, sleep for 60 subsequent seconds
            self.oled.fill_rect(1, 44, 128, 8, self.oled.black)
            self.oled.text(self._get_current_time(), 1, 44, self.oled.white)
            self.oled.show()

    def render_departures(self, services, offset=0, calling_at_text=None):
        self.oled.fill(self.oled.black)

        if not services:
            self.render_welcome_screen()
            return

        num_rows = 2 if self.show_clock else 3
        row_spacing = 20 if self.show_clock else 21

        for current_row in range(num_rows):
            idx = offset + current_row
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

            y = 2 + (current_row * row_spacing)
            line_text = f"{std} {dest}"
            self.oled.text(line_text, 1, y, self.oled.white)

            # Second line: for top service, alternate between etd/platform
            # and scrolling calling points
            if current_row == 0 and calling_at_text is not None:
                self.oled.text(calling_at_text[:16], 1, y + 10, self.oled.white)
            else:
                if etd:
                    self.oled.text(etd, 1, y + 10, self.oled.white)

                if platform:
                    platform_str = f"Plat {platform}"
                    self.oled.text(
                        platform_str,
                        128 - len(platform_str) * 8,
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

    def update_calling_points(self, services, offset):
        if not services or offset >= len(services):
            # If there are no services to display, there can't be any calling points
            self._current_top_service_id = None
            self._calling_at_str = ""
            return
        service_id = services[offset].get("serviceID", "")
        if service_id and service_id != self._current_top_service_id:
            points = self.fetch_calling_points(service_id)
            self._current_top_service_id = service_id
            self._calling_at_str = "Calling at: " + ", ".join(points) if points else ""
            if len(points) == 1:
                self._calling_at_str = f"{self._calling_at_str} Only"
            self._calling_at_phase = "info"
            self._calling_at_scroll_offset = 0
            self._calling_at_phase_start = time.ticks_ms()
            print(f"Calling at: {self._calling_at_str}")

    def advance_calling_at(self):
        """
        Advance the calling-at animation state. Returns True if
        display needs updating.
        """
        if not self._calling_at_str:
            return False

        time_ms_now = time.ticks_ms()
        elapsed = time.ticks_diff(time_ms_now, self._calling_at_phase_start)

        if (
            self._calling_at_phase == "info"
            and elapsed >= self.DELAY_PLATFORM_DISPLAY_MS
        ):
            self._calling_at_phase = "scroll"
            self._calling_at_scroll_offset = 0
            self._calling_at_phase_start = time_ms_now
            return True
        elif self._calling_at_phase == "scroll" and elapsed >= (
            self.CALLING_AT_PAUSE_MS
            if self._calling_at_scroll_offset == 0
            else self.CALLING_AT_SCROLL_MS
        ):
            self._calling_at_scroll_offset += 1
            self._calling_at_phase_start = time_ms_now
            # Once the text has scrolled off screen, switch back to delay/platform info
            if self._calling_at_scroll_offset >= len(self._calling_at_str):
                self._calling_at_phase = "info"
                self._calling_at_scroll_offset = 0
            return True

        return False

    def get_calling_at_text(self):
        if not self._calling_at_str or self._calling_at_phase == "info":
            return None
        # Show a 16-char window scrolling left through the string
        return self._calling_at_str[self._calling_at_scroll_offset :][:16]

    def _url_decode(self, s):
        result = s.replace("+", " ")
        parts = result.split("%")
        decoded = parts[0]
        for part in parts[1:]:
            if len(part) >= 2:
                try:
                    decoded += chr(int(part[:2], 16)) + part[2:]
                except ValueError:
                    decoded += "%" + part
            else:
                decoded += "%" + part
        return decoded

    def _read_config_file(self, filename):
        try:
            with open(filename, "r") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _render_template(self, filename, replacements=None):
        with open(filename, "r") as f:
            html = f.read()
        if replacements:
            for key, value in replacements.items():
                html = html.replace(key, value)
        return html

    def _setup_http_handler(self, method, path, body):
        gc.collect()
        config_files = ["wifi.json", "api.json"]

        if method == "POST" and path == "/":
            # Parse URL-encoded form body
            fields = {}
            if body:
                for pair in body.split("&"):
                    if "=" not in pair:
                        continue
                    key, value = pair.split("=", 1)
                    key = self._url_decode(key)
                    value = self._url_decode(value)
                    fields[key] = value

            # Group by filename prefix and write back
            file_data = {}
            for field_name, value in fields.items():
                if ":" not in field_name:
                    continue
                filename, key = field_name.split(":", 1)
                if filename not in file_data:
                    file_data[filename] = {}
                file_data[filename][key] = value

            for filename, data in file_data.items():
                with open(filename, "w") as f:
                    json.dump(data, f)

            self._setup_saved = True
            gc.collect()
            return self._render_template("setup_success.html")

        # GET: render the config form
        form_fields = ""
        for filename in config_files:
            data = self._read_config_file(filename)
            heading = " ".join(
                w[0].upper() + w[1:] for w in filename.replace(".json", "").split("_")
            )
            form_fields += f"<h2>{heading}</h2>"
            for key, value in data.items():
                field_name = f"{filename}:{key}"
                label = " ".join(w[0].upper() + w[1:] for w in key.split("_"))
                escaped_value = (
                    str(value)
                    .replace("&", "&amp;")
                    .replace('"', "&quot;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )
                form_fields += (
                    f"<label>{label}</label>"
                    f"<input type='text' name='{field_name}' value=\"{escaped_value}\">"
                )

        return self._render_template(
            "setup_form.html", {"{{FORM_FIELDS}}": form_fields}
        )

    def start_setup_mode(self):
        self._show_message("Entering", "setup mode...")

        gc.collect()
        self._setup_saved = False
        portal = CaptivePortal(
            ssid=self.SETUP_SSID,
            port=self.SETUP_PORT,
            http_handler=self._setup_http_handler,
        )

        self._show_message("Setup:Connect to", self.SETUP_SSID, "http://pdb.setup")
        portal.start(
            should_exit=lambda: self._setup_saved
            or any(pin.value() == 0 for pin in self.buttons.values())
        )

        self._show_message("Setup complete", "Restarting...")
        time.sleep(3)
        reset()

    def show_departure_board(self):
        print("Showing departure board")

        services = []
        offset = 0
        last_fetch = 0

        # Calling points state
        self._current_top_service_id = None
        self._calling_at_str = ""
        self._calling_at_phase = (
            "info"  # "info" (delay/platform) or "scroll" (calling points)
        )
        self._calling_at_scroll_offset = 0
        self._calling_at_phase_start = time.ticks_ms()
        last_render = time.ticks_ms()

        # Default state is pulled up, so 1 = not pressed
        prev_state = {name: 1 for name in self.buttons}

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
                self.update_calling_points(services, offset)
                self.render_departures(services, offset, self.get_calling_at_text())

            else:
                needs_render = self.advance_calling_at()

                # Re-render for clock seconds
                time_ms_now = time.ticks_ms()
                if (
                    self.show_clock
                    and time.ticks_diff(time_ms_now, last_render) >= 1000
                ):
                    needs_render = True

                if needs_render:
                    self.render_departures(services, offset, self.get_calling_at_text())
                    last_render = time_ms_now

            # Read all buttons and detect change in state (pressed)
            pressed = {}
            for name, pin in self.buttons.items():
                cur = pin.value()
                pressed[name] = cur == 0 and prev_state[name] == 1
                prev_state[name] = cur

            if pressed["clock"]:
                self.show_clock = not self.show_clock
                self.render_departures(services, offset, self.get_calling_at_text())

            if pressed["scroll"]:
                offset += 1
                if offset >= len(services):
                    offset = 0
                self.update_calling_points(services, offset)
                self.render_departures(services, offset, self.get_calling_at_text())

            # Both buttons held simultaneously -> enter setup mode
            if (
                self.buttons["clock"].value() == 0
                and self.buttons["scroll"].value() == 0
            ):
                self.start_setup_mode()

            # Sleep to prevent the CPU from constantly spinning in a tight loop
            time.sleep_ms(50)


if __name__ == "__main__":
    pdb = PicoDepartureBoard()
    pdb.show_boot_screen()
    pdb.connect_to_wifi()
    pdb.show_departure_board()
