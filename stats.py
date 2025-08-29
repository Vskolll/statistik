# stats.py

import json
from datetime import datetime
from config import USD_RUB, USD_UAH

def load_data():
    with open("database.json", "r", encoding="utf-8") as f:
        return json.load(f)

def get_stats(start: datetime, end: datetime):
    data = load_data()
    total_rub = 0
    total_uah = 0

    for entry in data:
        dt = datetime.strptime(entry["datetime"], "%Y-%m-%d %H:%M")
        if start <= dt <= end:
            if entry["currency"] == "RUB":
                total_rub += entry["amount"]
            elif entry["currency"] == "UAH":
                total_uah += entry["amount"]

    total_usd = round(total_rub / USD_RUB + total_uah / USD_UAH, 2)

    return {
        "rub": total_rub,
        "uah": total_uah,
        "usd": total_usd
    }

# Тест: Статистика за сегодня
if __name__ == "__main__":
    from datetime import date, timedelta

    today = datetime.combine(date.today(), datetime.min.time())
    tomorrow = today + timedelta(days=1)

    result = get_stats(today, tomorrow)
    print(f"Сегодня заработано: {result['rub']}₽, {result['uah']}₴, ≈ {result['usd']}$")
