"""Flask application that exposes endpoints for fetching stock market data.

The endpoints are inspired by the project brief provided in the repository.

This module can be executed directly or used via a WSGI server.  It relies on
`yfinance` for fetching market data, which in turn queries Yahoo Finance.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException
import yfinance as yf


app = Flask(__name__)


class ClientError(ValueError):
    """Exception raised when the client provides invalid input."""


@dataclass
class HistoricalRequest:
    """Represents the payload for historical data queries."""

    symbol: str
    start_date: datetime
    end_date: datetime
    interval: str = "1d"

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "HistoricalRequest":
        """Validate and build an instance from a JSON payload.

        Raises:
            ClientError: if mandatory fields are missing or malformed.
        """

        if not isinstance(payload, dict):
            raise ClientError("JSON body must be an object")

        try:
            symbol = payload["symbol"].strip().upper()
        except KeyError as exc:  # pragma: no cover - defensive programming
            raise ClientError("'symbol' field is required") from exc
        except AttributeError as exc:
            raise ClientError("'symbol' must be a string") from exc

        if not symbol:
            raise ClientError("'symbol' cannot be empty")

        if "start_date" not in payload:
            raise ClientError("'start_date' field is required")
        start_date = _parse_date(payload.get("start_date"))

        if "end_date" not in payload:
            raise ClientError("'end_date' field is required")
        end_date = _parse_date(payload.get("end_date"))

        if start_date > end_date:
            raise ClientError("'start_date' must not be after 'end_date'")

        interval = payload.get("interval", "1d")
        if not isinstance(interval, str):
            raise ClientError("'interval' must be a string if provided")
        interval = interval.strip() or "1d"

        return cls(symbol=symbol, start_date=start_date, end_date=end_date, interval=interval)


def _parse_date(value: Any) -> datetime:
    """Parse a date from a YYYY-MM-DD string."""

    if not isinstance(value, str):
        raise ClientError("Dates must be provided as YYYY-MM-DD strings")

    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ClientError("Dates must follow the YYYY-MM-DD format") from exc


@app.errorhandler(ClientError)
def _handle_client_error(exc: ClientError):
    """Return a JSON response for client-side validation errors."""

    response = {"error": str(exc)}
    return jsonify(response), 400


@app.errorhandler(Exception)
def _handle_uncaught_error(exc: Exception):
    """Return a JSON response for unexpected server errors."""

    if isinstance(exc, HTTPException):  # pragma: no cover - rely on Werkzeug's handler
        return exc

    response = {"error": "An unexpected error occurred", "details": str(exc)}
    return jsonify(response), 500


@app.get("/api/company-info/<symbol>")
def company_information(symbol: str):
    """Return company profile information using Yahoo Finance data."""

    data = _safe_fetch(lambda: yf.Ticker(symbol).info)
    if data is None:
        return _upstream_error_response()

    if not data:
        raise ClientError(f"No company information found for symbol '{symbol.upper()}'")

    payload = {
        "symbol": symbol.upper(),
        "name": data.get("longName") or data.get("shortName"),
        "summary": data.get("longBusinessSummary"),
        "industry": data.get("industry"),
        "sector": data.get("sector"),
        "website": data.get("website"),
        "officers": _format_officers(data.get("companyOfficers", [])),
    }
    return jsonify(payload)


@app.get("/api/stock-data/<symbol>")
def stock_market_data(symbol: str):
    """Return real-time market data for the specified symbol."""

    ticker = yf.Ticker(symbol)
    fast_info = _safe_fetch(lambda: ticker.fast_info)
    if fast_info is None:
        return _upstream_error_response()

    if not fast_info:
        raise ClientError(f"No market data found for symbol '{symbol.upper()}'")

    payload = {
        "symbol": symbol.upper(),
        "currency": fast_info.get("currency"),
        "last_price": fast_info.get("last_price"),
        "previous_close": fast_info.get("previous_close"),
        "open": fast_info.get("open"),
        "day_high": fast_info.get("day_high"),
        "day_low": fast_info.get("day_low"),
        "volume": fast_info.get("volume"),
        "market_cap": fast_info.get("market_cap"),
        "fifty_two_week_high": fast_info.get("year_high"),
        "fifty_two_week_low": fast_info.get("year_low"),
    }
    return jsonify(payload)


@app.post("/api/historical-data")
def historical_market_data():
    """Return historical market data for the provided symbol and date range."""

    payload = request.get_json(silent=True)
    historical_request = HistoricalRequest.from_payload(payload)

    data = _safe_fetch(
        lambda: yf.download(
            tickers=historical_request.symbol,
            start=historical_request.start_date,
            end=historical_request.end_date + timedelta(days=1),
            interval=historical_request.interval,
            auto_adjust=False,
            progress=False,
        )
    )
    if data is None:
        return _upstream_error_response()

    if data.empty:
        raise ClientError("No historical data found for the specified parameters")

    results = [
        {
            "date": index.strftime("%Y-%m-%d"),
            "open": float(row.Open),
            "high": float(row.High),
            "low": float(row.Low),
            "close": float(row.Close),
            "adj_close": float(row["Adj Close"]),
            "volume": int(row.Volume),
        }
        for index, row in data.iterrows()
    ]

    return jsonify({"symbol": historical_request.symbol, "interval": historical_request.interval, "data": results})


@app.post("/api/analytical-insights")
def analytical_insights():
    """Return analytical insights derived from historical data."""

    payload = request.get_json(silent=True)
    historical_request = HistoricalRequest.from_payload(payload)

    data = _safe_fetch(
        lambda: yf.download(
            tickers=historical_request.symbol,
            start=historical_request.start_date,
            end=historical_request.end_date + timedelta(days=1),
            interval=historical_request.interval,
            auto_adjust=True,
            progress=False,
        )
    )
    if data is None:
        return _upstream_error_response()

    if data.empty:
        raise ClientError("No analytical data found for the specified parameters")

    closing_prices = data["Close"]
    insights = {
        "symbol": historical_request.symbol,
        "interval": historical_request.interval,
        "start_date": historical_request.start_date.strftime("%Y-%m-%d"),
        "end_date": historical_request.end_date.strftime("%Y-%m-%d"),
        "average_close": float(closing_prices.mean()),
        "highest_close": float(closing_prices.max()),
        "lowest_close": float(closing_prices.min()),
        "closing_price_volatility": float(closing_prices.std()),
        "total_return": float(_compute_total_return(closing_prices)),
    }
    return jsonify(insights)


def _compute_total_return(series):
    """Compute the total return for a series of closing prices."""

    first = series.iloc[0]
    last = series.iloc[-1]
    return (last - first) / first if first else 0.0


def _format_officers(officers: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return a list of simplified officer information."""

    formatted = []
    for officer in officers or []:
        try:
            formatted.append(
                {
                    "name": officer.get("name"),
                    "title": officer.get("title"),
                    "age": officer.get("age"),
                    "year_born": officer.get("yearBorn"),
                }
            )
        except AttributeError:  # pragma: no cover - guard against unexpected types
            continue
    return formatted


def _safe_fetch(callback):
    """Safely execute a callback that queries an external API.

    Returns ``None`` when the request fails for network or upstream reasons.
    """

    try:
        return callback()
    except Exception:  # pragma: no cover - network related failures
        return None


def _upstream_error_response():
    """Return a consistent response when upstream data fetch fails."""

    return jsonify({"error": "Failed to retrieve data from upstream provider"}), 502


if __name__ == "__main__":
    from argparse import ArgumentParser

    parser = ArgumentParser(description="Run the Flask development server.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", default=5000, type=int)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    app.run(host=args.host, port=args.port, debug=args.debug)
