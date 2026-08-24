import random
import os
import json

CURRENCIES = ["USD", "GBP", "JPY", "CHF"]


def generate_positions(date: str, num_positions: int = 15) -> list[dict]:
    """Deterministically generate synthetic positions for a given business date."""
    random.seed(date)

    positions = []
    for i in range(num_positions):
        position = {
            "position_id": f"POS{i:04d}",
            "currency": random.choice(CURRENCIES),
            "amount": round(random.uniform(1000, 500000), 2),
            "business_date": date,
        }
        positions.append(position)

    return positions


def save_positions(data: list, date: str) -> None:
    """Idempotently save positions to a date-partitioned raw file."""
    path = f"data/raw/positions/date={date}/"
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, "positions.json"), "w") as f:
        json.dump(data, f)


if __name__ == "__main__":
    positions = generate_positions("2024-01-15")
    save_positions(positions, "2024-01-15")
    print(f"generated {len(positions)} positions:")
    for p in positions[:3]:
        print(" ", p)
    print("  ...")
