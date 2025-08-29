# parser.py

import re
import json
from datetime import datetime
from telethon.sync import TelegramClient
from config import API_ID, API_HASH, CHANNEL

client = TelegramClient('parser_session', API_ID, API_HASH)

def parse_message(text):
    try:
        user = re.search(r"👤 Пользователь: @(.*?) \(ID: `(\d+)`\)", text)
        account = re.search(r"🧾 Аккаунт: \*\*(\d+)\*\*", text)
        duration = re.search(r"⏱ Длительность: \*\*(.+?) ч\.\*\*", text)
        until = re.search(r"📅 До: \*\*занят до (.+?) \(", text)
        method = re.search(r"💳 Метод: `(.*?)`", text)
        amount = re.search(r"💰 Сумма: \*\*(\d+)\s?[₽₴]\*\*", text)
        currency = 'UAH' if '₴' in text else 'RUB'
        dt = re.search(r"🕓 Время: __([0-9.:\s]+)__", text)

        if not all([user, account, duration, until, method, amount, dt]):
            print("❌ Не удалось найти все данные")
            return None

        return {
            "user": user.group(1),
            "user_id": int(user.group(2)),
            "account": account.group(1),
            "duration": duration.group(1),
            "until": until.group(1),
            "method": method.group(1),
            "amount": int(amount.group(1)),
            "currency": currency,
            "datetime": datetime.strptime(dt.group(1), "%d.%m.%Y %H:%M").strftime("%Y-%m-%d %H:%M")
        }

    except Exception as e:
        print("❌ Ошибка при парсинге:", e)
        return None

async def fetch_and_save():
    results = []
    async with client:
        print(f"📡 Чтение из канала: {CHANNEL}")
        async for msg in client.iter_messages(CHANNEL, limit=500):
            if msg.text:
                print("👉 Сообщение:")
                print(msg.text)
                print("=" * 50)

                if "📊" in msg.text and "аренда" in msg.text.lower():
                    print("✅ Найдено подходящее сообщение")
                    parsed = parse_message(msg.text)
                    if parsed:
                        print("✅ Успешно распарсено")
                        results.append(parsed)
                    else:
                        print("❌ Ошибка при парсинге")
                else:
                    print("⛔ Пропущено (не содержит ключевых слов)")

    print(f"💾 Сохраняем {len(results)} записей в database.json...")
    with open("database.json", "w", encoding="utf-8") as f:
        json.dump(results[::-1], f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    import asyncio
    asyncio.run(fetch_and_save())
