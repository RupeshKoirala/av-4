# Flask Market Data API

This project exposes a small collection of REST endpoints that fetch company
profile data, real-time market quotes, historical pricing, and derived
analytics.  The implementation relies on [Yahoo Finance](https://finance.yahoo.com)
through the [`yfinance`](https://github.com/ranaroussi/yfinance) Python
package.

## Requirements

* Python 3.10+
* The packages listed in `requirements.txt`

Install the dependencies with:

```bash
pip install -r requirements.txt
```

## Running the server

The application can be started with the built-in development server:

```bash
python app.py --host 0.0.0.0 --port 5000 --debug
```

## Endpoints

All endpoints return JSON responses.

### `GET /api/company-info/<symbol>`

Returns company profile information such as the business summary, industry,
sector, web site, and key officers for the provided stock ticker symbol.

### `GET /api/stock-data/<symbol>`

Returns recent market pricing information for the given symbol, including the
latest price, daily range, volume, market capitalisation, and 52-week range.

### `POST /api/historical-data`

Accepts a JSON payload with `symbol`, `start_date`, `end_date`, and an optional
`interval`.  Returns OHLCV candles for the specified window.

```json
{
  "symbol": "AAPL",
  "start_date": "2023-01-01",
  "end_date": "2023-01-31",
  "interval": "1d"
}
```

### `POST /api/analytical-insights`

Accepts the same payload shape as the historical data endpoint.  In addition to
the raw price history the endpoint returns aggregate analytics, such as the
average closing price, the highest/lowest close, price volatility, and total
return for the requested period.

## Error handling

If the upstream Yahoo Finance service is unreachable the API responds with a
`502 Bad Gateway` error.  Validation issues result in a `400 Bad Request`
response with a message describing the problem.
