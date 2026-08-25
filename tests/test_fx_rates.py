import json
from unittest.mock import Mock, patch

import pytest
import requests

from extractors.fx_rates import fetch_fx_rates, save_fx_rates


def test_fetch_fx_rates_builds_correct_request():
    mock_response = Mock()
    mock_response.json.return_value = {
        "amount": 1.0,
        "base": "EUR",
        "date": "2024-01-15",
        "rates": {"USD": 1.0945},
    }
    with patch("extractors.fx_rates.requests.get", return_value=mock_response) as mock_get:
        fetch_fx_rates("2024-01-15", base="EUR", symbols=["USD"])

    mock_get.assert_called_once_with(
        "https://api.frankfurter.dev/v1/2024-01-15",
        params={"base": "EUR", "symbols": "USD"},
    )
    mock_response.raise_for_status.assert_called_once()


def test_fetch_fx_rates_renames_date_to_rate_date():
    mock_response = Mock()
    mock_response.json.return_value = {
        "amount": 1.0,
        "base": "EUR",
        "date": "2024-01-12",
        "rates": {"USD": 1.09},
    }
    with patch("extractors.fx_rates.requests.get", return_value=mock_response):
        result = fetch_fx_rates("2024-01-13", base="EUR", symbols=["USD"])

    assert result["rate_date"] == "2024-01-12"
    assert "date" not in result


def test_fetch_fx_rates_raises_on_http_error():
    mock_response = Mock()
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("500")
    with patch("extractors.fx_rates.requests.get", return_value=mock_response):
        with pytest.raises(requests.exceptions.HTTPError):
            fetch_fx_rates("2024-01-15")


def test_save_fx_rates_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data = {"amount": 1.0, "base": "EUR", "rates": {"USD": 1.09}, "rate_date": "2024-01-15"}

    save_fx_rates(data, "2024-01-15")
    save_fx_rates(data, "2024-01-15")  # run twice on purpose

    files = list(tmp_path.glob("data/raw/fx_rates/date=2024-01-15/*.json"))
    assert len(files) == 1
    assert json.loads(files[0].read_text()) == data
