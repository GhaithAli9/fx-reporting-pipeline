import requests

BASE_URL = "https://api.frankfurter.dev/v1"


def fetch_fx_rates(date: str, base: str = "USD", symbols: list[str] | None = None) -> dict:
    """Fetch FX rates for a given date (YYYY-MM-DD) from the Frankfurter API."""
    params = {"base": base}
    if symbols:
        params["symbols"] = ",".join(symbols)

    response = requests.get(f"{BASE_URL}/{date}", params=params)

    response.raise_for_status()
    return response.json()


if __name__ == "__main__":
    weekday = fetch_fx_rates("2024-01-15", symbols=["EUR", "GBP"])
    print("weekday:", weekday)

    weekend = fetch_fx_rates("2024-01-13", symbols=["EUR"])
    print("weekend:", weekend)
