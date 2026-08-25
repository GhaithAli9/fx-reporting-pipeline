import json

from extractors.positions import CURRENCIES, generate_positions, save_positions


def test_generate_positions_is_deterministic():
    assert generate_positions("2024-01-15") == generate_positions("2024-01-15")


def test_generate_positions_differs_by_date():
    assert generate_positions("2024-01-15") != generate_positions("2024-01-16")


def test_generate_positions_shape():
    positions = generate_positions("2024-01-15", num_positions=5)
    assert len(positions) == 5
    for p in positions:
        assert p["currency"] in CURRENCIES
        assert p["amount"] >= 1000
        assert p["business_date"] == "2024-01-15"


def test_save_positions_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    positions = generate_positions("2024-01-15", num_positions=3)

    save_positions(positions, "2024-01-15")
    save_positions(positions, "2024-01-15")  # run twice on purpose

    files = list(tmp_path.glob("data/raw/positions/date=2024-01-15/*.json"))
    assert len(files) == 1
    assert json.loads(files[0].read_text()) == positions
