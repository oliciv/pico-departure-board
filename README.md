# Pico Departure Board

## Overview

This is a departure board for a train station, running on a Raspberry Pi Pico W with a Waveshare 1.3inch OLED HAT. There are many bigger departure boards in the world, this was a fun challenge to fit on a tiny screen. It's not perfect, but it works!

## Initial Setup

### WiFi Credentials

Create a `wifi.json` file with the following format:

```json
{
    "ssid": "<your-ssid>",
    "password": "<your-password>"
}
```

### API Credentials

Sign up at https://realtime.nationalrail.co.uk/OpenLDBWSRegistration/

Create a `api.json` file with the following format:

```json
{
    "api_token": "<your-api-token>",
    "proxy_url": "<your-proxy-url>",
    "station_code": "<your-station-code>",
    "station_name": "<your-station-name>"
}
```

A list of station codes can be found at https://en.wikipedia.org/wiki/UK_railway_stations

The National Rail API is SOAP, which is not ideal on the Pico for reasons of memory and sanity. So we'll fetch results through a [Huxley2](https://github.com/jpsingleton/Huxley2) proxy. This can run in Docker, Azure or there is a public instance available.


## Implementation notes

Train station names are difficult to display on the OLED screen, so we need to truncate them. The longest one I've found is "Rhoose Cardiff International Airport"* (34 characters). The OLED screen is 128 pixels wide, and the font is 8 pixels wide, so we can fit 16 characters per line.

Even so, font size 8 is quite large, so we can only fit 14 characters per line. To do: Investigate if we can use a smaller font for some items (e.g platform, status, etc)

* It's NOT Llanfairpwllgwyngyllgogerychwyrndrobwllllantysiliogogogoch, which is officially called "Llanfairpwll".

## Hardware

- Raspberry Pi Pico W
- Waveshare 1.3inch OLED HAT (128x64)

## Future ideas

- It'll need a 3d printed case
- It could be battery powered and portable or even wearable
- Need to find a way to display calling stations
- Limit to a specific platform, or destination(s)
- Better error handling!

## License

This project is licensed under the terms of the GNU General Public License v3.0. It includes code from the following sources:

- [Waveshare Pico_code](https://github.com/waveshare/Pico_code/blob/main/Python/Pico-OLED-1.3/Pico-OLED-1.3(spi).py) - GPL-3.0
