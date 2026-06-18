# Third-party travel data integrations

This project keeps external travel data providers optional. A missing, slow, or
failed provider must not block AI itinerary generation, especially on the Render
free tier memory and timeout limits.

## Weather: QWeather / 和风天气

Status: feasible.

QWeather provides city weather forecast APIs such as `/v7/weather/{days}` for
3-day and longer daily forecasts. Tour Pass currently calls the 3-day forecast
endpoint through `tools/weather_api.py`.

Supported environment variables, checked in this order:

- `QWEATHER_KEY`
- `QWEATHER_API_KEY`
- `HEFENG_WEATHER_KEY`

Only one key is required. `HEFENG_WEATHER_KEY` is supported so the existing
和风天气 API key can be added without renaming if that is already how it is
stored in Render.

Current behavior:

- If no key is configured, WeatherAgent skips real weather and keeps using the
  existing planning flow.
- If QWeather fails or a city has no local LocationID mapping, the request is
  logged and returns an empty forecast instead of failing the whole trip plan.
- `tools.weather_api.get_config_status()` exposes non-secret configuration
  status for future admin diagnostics.

Reference:

- QWeather Weather Daily Forecast: https://dev.qweather.com/en/docs/api/weather/weather-daily-forecast/

## Hotel realtime prices

Status: feasible, but usually requires an authorized supplier account.

Realtime hotel prices are not reliable as a plain public scrape. Practical
options are supplier or affiliate APIs such as Booking.com Demand API or
Amadeus Hotel APIs, both of which require credentials and provider-specific
terms. Tour Pass therefore uses a small adapter boundary instead of binding the
main planning pipeline to one vendor.

Supported environment variables:

- `HOTEL_PRICE_PROVIDER`: provider name, for example `booking`, `amadeus`, or
  `custom`.
- `HOTEL_PRICE_ENDPOINT`: HTTPS endpoint for the adapter service.
- `HOTEL_PRICE_API_KEY`: adapter service API key.

If the hotel price provider is not configured, HotelAgent keeps using local
hotel data. If the provider request fails, HotelAgent logs the failure and falls
back to local prices.

Reference:

- Booking.com Demand API: https://developers.booking.com/demand/docs/open-api/demand-api
- Amadeus Hotel APIs: https://developers.amadeus.com/self-service/category/hotels

## Hotel price adapter contract

Tour Pass sends a single POST request to `HOTEL_PRICE_ENDPOINT`.

Request:

```json
{
  "city": "北京",
  "hotels": [
    {
      "id": "hotel_id",
      "name": "酒店名称",
      "area": "商圈或区域"
    }
  ],
  "check_in": "2026-07-01",
  "check_out": "2026-07-03"
}
```

Required request header:

```text
Authorization: Bearer ${HOTEL_PRICE_API_KEY}
Content-Type: application/json
```

Response:

```json
{
  "prices": [
    {
      "hotel_id": "hotel_id",
      "hotel_name": "酒店名称",
      "price_per_night": 588,
      "currency": "CNY",
      "provider": "booking"
    }
  ]
}
```

Matching rules:

- Prefer `hotel_id` when both sides provide it.
- Fall back to exact `hotel_name` matching.
- `price_per_night` is interpreted as the nightly price in `currency`.
- Unknown or zero prices are ignored when building `price_range`.

## Future adapter implementation notes

Recommended path:

1. Keep vendor credentials inside the adapter service or Render environment,
   never in frontend code.
2. Normalize every vendor response into the adapter response above.
3. Cache price responses by city, hotel list, check-in, and check-out to avoid
   slowing down multi-agent planning.
4. Keep provider failures non-fatal so the itinerary still renders with local
   hotel recommendations.

Tour-AI-inspired future work such as 小红书帖子导入 can reuse the same pattern:
parse external content into a small normalized structure first, then pass that
structure into the existing AI planning pipeline.
