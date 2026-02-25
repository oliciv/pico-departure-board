import network
import socket
import time


class CaptivePortal:

    def __init__(self, ssid, port=80, http_handler=None):
        """
        ssid: SSID to use for the access point
        port: port to listen on for HTTP requests
        http_handler: optional callback(method, path) -> str (HTML body).
                      If None, a default page is served.
        """
        self.ssid = ssid
        self.port = port
        self._http_handler = http_handler or self._default_http_handler

    def start(self, should_exit=None):
        """
        Start the captive portal. Blocks until should_exit() returns True.

        should_exit: callable returning True when the portal should stop.
                     If None, runs forever.

        Returns the AP IP address that was used.
        """
        # Deactivate station WiFi
        sta = network.WLAN(network.STA_IF)
        sta.active(False)

        # Start access point
        ap = network.WLAN(network.AP_IF)
        ap.active(True)
        ap.config(essid=self.ssid, security=0)

        for _ in range(20):
            if ap.active():
                break
            time.sleep_ms(250)

        ap_ip = ap.ifconfig()[0]
        print(f"AP started: {self.ssid} @ {ap_ip}")

        # DNS socket (UDP port 53) — replies to all queries with AP IP
        dns_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        dns_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        dns_sock.bind(("0.0.0.0", 53))
        dns_sock.setblocking(False)

        # HTTP socket (TCP)
        http_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        http_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        http_sock.bind(("0.0.0.0", self.port))
        http_sock.listen(1)
        http_sock.setblocking(False)

        try:
            while True:
                self._handle_dns(dns_sock, ap_ip)

                try:
                    client, _ = http_sock.accept()
                except OSError:
                    client = None
                if client:
                    self._serve_http(client)

                if should_exit and should_exit():
                    break

                time.sleep_ms(50)

        finally:
            dns_sock.close()
            http_sock.close()
            ap.active(False)

        return ap_ip

    def _handle_dns(self, dns_sock, ap_ip):
        try:
            data, addr = dns_sock.recvfrom(512)
        except OSError:
            return

        # Minimal DNS response pointing all queries to ap_ip
        response = data[:2] + b"\x81\x80"
        response += b"\x00\x01\x00\x01\x00\x00\x00\x00"
        # Copy the original question section
        pos = 12
        while pos < len(data) and data[pos] != 0:
            pos += data[pos] + 1
        pos += 1  # null terminator
        pos += 4  # QTYPE and QCLASS
        response += data[12:pos]
        # Answer: pointer to name, type A, class IN, TTL 60, 4-byte IP
        response += b"\xc0\x0c"
        response += b"\x00\x01\x00\x01"
        response += b"\x00\x00\x00\x3c"
        response += b"\x00\x04"
        response += bytes(int(b) for b in ap_ip.split("."))

        dns_sock.sendto(response, addr)

    @staticmethod
    def _default_http_handler(method, path, body):
        return "<html><body><h1>Setup</h1></body></html>"

    def _serve_http(self, client):
        try:
            client.settimeout(5)
            print("HTTP: reading request...")
            request = b""
            while b"\r\n\r\n" not in request:
                chunk = client.recv(512)
                if not chunk:
                    break
                request += chunk

            # Parse method and path from request line
            request_line = request.split(b"\r\n", 1)[0].decode()
            parts = request_line.split(" ")
            method = parts[0] if len(parts) >= 1 else "GET"
            path = parts[1] if len(parts) >= 2 else "/"
            print(f"HTTP: {method} {path}")

            # Read POST body if Content-Length header is present
            post_body = ""
            if method == "POST":
                headers_part = request.split(b"\r\n\r\n", 1)[0].decode()
                content_length = 0
                for line in headers_part.split("\r\n"):
                    if line.lower().startswith("content-length:"):
                        content_length = int(line.split(":", 1)[1].strip())
                        break
                print(f"HTTP: reading POST body ({content_length} bytes)")
                if content_length > 0:
                    # Some body bytes may already be in the buffer after headers
                    body_so_far = request.split(b"\r\n\r\n", 1)[1]
                    while len(body_so_far) < content_length:
                        chunk = client.recv(512)
                        if not chunk:
                            break
                        body_so_far += chunk
                    post_body = body_so_far[:content_length].decode()

            print("HTTP: calling handler...")
            body = self._http_handler(method, path, post_body)
            print(f"HTTP: handler returned {len(body)} bytes")

            header = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: text/html\r\n"
                f"Content-Length: {len(body)}\r\n"
                "Connection: close\r\n"
                "\r\n"
            )
            print("HTTP: sending headers...")
            client.sendall(header.encode())
            print("HTTP: sending body...")
            client.sendall(body.encode())
            print("HTTP: response sent")
        except Exception as e:
            print(f"HTTP error: {e}")
        finally:
            client.close()
