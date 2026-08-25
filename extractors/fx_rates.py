import requests
import os
import json

BASE_URL = "https://api.frankfurter.dev/v1"


def fetch_fx_rates(date: str, base: str = "EUR", symbols: list[str] | None = None) -> dict:
    """Fetch FX rates for a given date (YYYY-MM-DD) from the Frankfurter API."""
    params = {"base": base}
    if symbols:
        params["symbols"] = ",".join(symbols)

    response = requests.get(f"{BASE_URL}/{date}", params=params)

    response.raise_for_status()
    data = response.json()
    data["rate_date"] = data.pop("date")
    return data

def save_fx_rates(data: dict, date: str) -> None:
    path = f"data/raw/fx_rates/date={date}/"
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, "rates.json"), "w") as f:
        json.dump(data, f)


POSITION_CURRENCIES = ["USD", "GBP", "JPY", "CHF"]

if __name__ == "__main__":
    weekday = fetch_fx_rates("2024-01-15", symbols=POSITION_CURRENCIES)
    save_fx_rates(weekday, "2024-01-15")
    print("weekday saved:", weekday)

    weekend = fetch_fx_rates("2024-01-13", symbols=POSITION_CURRENCIES)
    save_fx_rates(weekend, "2024-01-13")
    print("weekend saved:", weekend)
