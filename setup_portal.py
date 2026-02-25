import gc
import json

from captive_portal import CaptivePortal


class SetupPortal:

    def __init__(self, ssid, port=80, config_files=None):
        self.ssid = ssid
        self.port = port
        self._config_files = config_files or ["wifi.json", "api.json"]
        self._saved = False

    def start(self, should_exit=lambda: False):
        portal = CaptivePortal(
            ssid=self.ssid,
            port=self.port,
            http_handler=self._http_handler,
        )
        portal.start(should_exit=lambda: self._saved or should_exit())
        return self._saved

    def _http_handler(self, method, path, body):
        gc.collect()

        if method == "POST" and path == "/":
            fields = {}
            if body:
                for pair in body.split("&"):
                    if "=" not in pair:
                        continue
                    key, value = pair.split("=", 1)
                    key = _url_decode(key)
                    value = _url_decode(value)
                    fields[key] = value

            file_data = {}
            for field_name, value in fields.items():
                if ":" not in field_name:
                    continue
                filename, key = field_name.split(":", 1)
                if filename not in file_data:
                    file_data[filename] = {}
                file_data[filename][key] = value

            for filename, data in file_data.items():
                existing = _read_config_file(filename)
                for key, value in data.items():
                    if key in existing and isinstance(existing[key], bool):
                        data[key] = value == "true"
                    elif "password" in key and value == "":
                        data[key] = existing.get(key, "")
                existing.update(data)
                with open(filename, "w") as f:
                    json.dump(existing, f)

            self._saved = True
            gc.collect()
            return _render_template("setup_success.html")

        form_fields = ""
        for filename in self._config_files:
            data = _read_config_file(filename)
            heading = " ".join(
                w[0].upper() + w[1:] for w in filename.replace(".json", "").split("_")
            )
            form_fields += f"<h2>{heading}</h2>"
            for key, value in data.items():
                field_name = f"{filename}:{key}"
                label = " ".join(w[0].upper() + w[1:] for w in key.split("_"))
                if isinstance(value, bool):
                    true_sel = " selected" if value else ""
                    false_sel = "" if value else " selected"
                    form_fields += (
                        f"<label>{label}</label>"
                        f"<select name='{field_name}'>"
                        f"<option value='true'{true_sel}>True</option>"
                        f"<option value='false'{false_sel}>False</option>"
                        f"</select>"
                    )
                elif "password" in key:
                    form_fields += (
                        f"<label>{label}</label>"
                        f"<input type='password' name='{field_name}' "
                        f"placeholder='{'Set' if value else 'Not set'}'>"
                    )
                else:
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

        return _render_template("setup_form.html", {"{{FORM_FIELDS}}": form_fields})


def _url_decode(s):
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


def _read_config_file(filename):
    try:
        with open(filename, "r") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _render_template(filename, replacements=None):
    with open(filename, "r") as f:
        html = f.read()
    if replacements:
        for key, value in replacements.items():
            html = html.replace(key, value)
    return html
