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
