# Pico Departure Board

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
    "station_code": "<your-station-code>",
    "station_name": "<your-station-name>"
}
```

A list of station codes can be found at https://en.wikipedia.org/wiki/UK_railway_stations


## Implementation notes

Train station names are difficult to display on the OLED screen, so we need to truncate them. The longest one I've found is "Rhoose Cardiff International Airport"* (34 characters). The OLED screen is 128 pixels wide, and the font is 8 pixels wide, so we can fit 16 characters per line.

Even so, font size 8 is quite large, so we can only fit 14 characters per line. To do: Investigate if we can use a smaller font for some items (e.g platform, status, etc)

* It's NOT Llanfairpwllgwyngyllgogerychwyrndrobwllllantysiliogogogoch, which is officially called "Llanfairpwll".

## Hardware

- Raspberry Pi Pico W
- Waveshare 1.3inch OLED HAT (128x64)

## Future ideas

- The OLED has two built in buttons, we could use these to cycle through different stations, or different views (departures, arrivals, etc.)
