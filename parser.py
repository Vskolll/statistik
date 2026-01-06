# parser.py

import re
import json
from datetime import datetime
from telethon.sync import TelegramClient
from config import API_ID, API_HASH, CHANNEL

client = TelegramClient('parser_session', API_ID, API_HASH)


def parse_message(text):
    """Парсит текст сообщения формата (пример в задаче) и возвращает dict с полями.

    Ожидаемые поля: user (username or display), user_id (int), account (str), duration (str),
    until (raw string), method (str), amount (int), currency (RUB/UAH), datetime (ISO '%Y-%m-%d %H:%M').
    """
    try:
        # remove simple markdown artifacts (bold/italic/code) and normalize spaces
        text = re.sub(r"[\*`_]", "", text)
        text = text.replace('\xa0', ' ')
        text = re.sub(r"\s+", " ", text).strip()

        # Пользователь: @username (ID: 1234567890)
        user_m = re.search(r"👤\s*Пользователь:\s*@?(?P<user>[^\s(]+)\s*\(ID:\s*(?P<id>\d+)\)", text)

        # Аккаунт: 006
        account_m = re.search(r"🧾\s*Аккаунт:\s*(?P<account>\d+)", text)

        # Длительность: night ч.
        duration_m = re.search(r"⏱️?\s*Длительность:\s*(?P<duration>.+?)\s*ч\.", text)

        # До: занят до 10:00 (04.01.2026)
        until_m = re.search(r"📅\s*До:\s*(?P<until>.+?)\s*\((?P<until_date>\d{2}\.\d{2}\.\d{4})\)", text)

        # Метод: pay_russia
        method_m = re.search(r"💳\s*Метод:\s*(?P<method>\S+)", text)

        # Сумма: 550 ₽  (symbol may be ₽ or ₴)
        amount_m = re.search(r"💰\s*Сумма:\s*(?P<amount>[0-9]+(?:[.,][0-9]+)?)\s*(?P<sym>[₽₴$€])", text)

        # Время: 03.01.2026 23:48
        dt_m = re.search(r"🕓\s*Время:\s*(?P<dt>\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2})", text)

        if not any([user_m, account_m, duration_m, until_m, method_m, amount_m, dt_m]):
            print("❌ Не найдено ожидаемых полей в сообщении")
            return None

        user = user_m.group('user') if user_m else "без username"
        user_id = int(user_m.group('id')) if user_m else None
        account = account_m.group('account') if account_m else ""
        duration = duration_m.group('duration').strip() if duration_m else ""
        until_raw = until_m.group('until').strip() if until_m else ""
        method = method_m.group('method') if method_m else ""

        # Normalize amount and currency
        if amount_m:
            amount_str = amount_m.group('amount').replace(',', '.')
            try:
                amount = int(float(amount_str))
            except ValueError:
                amount = 0
            sym = amount_m.group('sym')
            currency = 'UAH' if sym == '₴' else 'RUB'
        else:
            amount = 0
            currency = 'RUB'

        dt_str = dt_m.group('dt') if dt_m else None
        dt_iso = None
        if dt_str:
            dt_iso = datetime.strptime(dt_str, "%d.%m.%Y %H:%M").strftime("%Y-%m-%d %H:%M")

        return {
            "user": user,
            "user_id": user_id,
            "account": account,
            "duration": duration,
            "until": until_raw,
            "method": method,
            "amount": amount,
            "currency": currency,
            "datetime": dt_iso,
        }

    except Exception as e:
        print("❌ Ошибка при парсинге:", e)
        return None


def load_db(path="database.json"):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []
    except Exception as e:
        print("⚠️ Ошибка при чтении базы:", e)
        return []


def save_db(records, path="database.json"):
    # Sort by datetime ascending (None values go to end)
    def key_fn(x):
        try:
            return datetime.strptime(x.get("datetime", "1970-01-01 00:00"), "%Y-%m-%d %H:%M")
        except Exception:
            return datetime(1970, 1, 1)

    records_sorted = sorted(records, key=key_fn)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records_sorted, f, ensure_ascii=False, indent=2)


def is_duplicate(existing, new):
    # Простая проверка дубликата по комбинации user_id, account, datetime и amount
    for e in existing:
        # if message_id present, use it as strongest indicator
        if new.get("message_id") and e.get("message_id") == new.get("message_id"):
            return True
        if e.get("user_id") == new.get("user_id") and e.get("account") == new.get("account") and e.get("datetime") == new.get("datetime") and e.get("amount") == new.get("amount"):
            return True
    return False


async def fetch_and_save(limit=None):
    """Fetch messages from the channel and save parsed records.

    By default fetches all messages (limit=None). If limit is set, will fetch up to that many.
    """
    parsed_results = []
    async with client:
        print(f"📡 Чтение из канала: {CHANNEL}")
        # when limit is None, Telethon will iterate entire history
        async for msg in client.iter_messages(CHANNEL, limit=limit):
            # prefer message text
            text = getattr(msg, 'text', None) or getattr(msg, 'message', None) or ''
            if not text:
                continue

            if "📊" in text and "аренда" in text.lower():
                parsed = parse_message(text)
                # if parser couldn't extract datetime from text, use message date
                if parsed is None:
                    # attempt looser parsing on raw text
                    parsed = parse_message(text)

                if parsed:
                    # if datetime missing, use Telegram message date
                    if not parsed.get('datetime') and getattr(msg, 'date', None):
                        try:
                            parsed['datetime'] = msg.date.strftime('%Y-%m-%d %H:%M')
                        except Exception:
                            parsed['datetime'] = None

                    # include message id for deduplication
                    try:
                        parsed['message_id'] = int(getattr(msg, 'id', 0)) if getattr(msg, 'id', None) is not None else None
                    except Exception:
                        parsed['message_id'] = None

                    # Помечаем источник (канал), чтобы на фронтенде было видно, откуда запись
                    parsed["source"] = CHANNEL
                    parsed_results.append(parsed)

    if not parsed_results:
        print("ℹ️ Нет новых записей для сохранения")
        return

    existing = load_db()
    added = 0
    for r in parsed_results:
        if not is_duplicate(existing, r):
            existing.append(r)
            added += 1

    if added:
        save_db(existing)
        print(f"💾 Добавлено {added} новых записей в database.json")
    else:
        print("ℹ️ Новых уникальных записей не найдено")


async def repair_db(path="database.json"):
    """Repair existing records in database.json by fetching original messages when message_id is available

    For each record with obvious markdown artifacts or missing fields, fetch the message by id
    from the configured channel and re-parse it. Also clean simple markdown from string fields.
    """
    def clean_text(s):
        if not isinstance(s, str):
            return s
        s = re.sub(r"[\*`_]", "", s)
        s = s.replace('\xa0', ' ')
        return s.strip()

    db = load_db(path)
    changed = 0
    async with client:
        for i, rec in enumerate(db):
            needs_fix = False
            # crude heuristics: markdown chars present or missing user/account or amount==0
            for k in ["user", "account", "duration", "until", "method"]:
                v = rec.get(k)
                if isinstance(v, str) and any(ch in v for ch in ['*', '`', '_']):
                    needs_fix = True
            if not rec.get('user_id') or rec.get('amount') in (0, None):
                needs_fix = True

            if not needs_fix:
                continue

            msg_id = rec.get('message_id')
            if msg_id:
                try:
                    msg = await client.get_messages(CHANNEL, ids=msg_id)
                except Exception as e:
                    print('⚠️ Не удалось получить сообщение', msg_id, e)
                    msg = None

                if msg and getattr(msg, 'text', None):
                    parsed = parse_message(msg.text)
                    if parsed:
                        # take parsed values, but keep source and message_id
                        parsed['source'] = rec.get('source') or CHANNEL
                        parsed['message_id'] = msg_id
                        db[i] = parsed
                        changed += 1
                        continue

            # fallback: clean textual fields in place
            for k in ['user', 'account', 'duration', 'until', 'method']:
                if k in rec:
                    rec[k] = clean_text(rec[k])

            # if datetime missing but message_id present, try fill from msg.date if available
            if not rec.get('datetime') and msg_id:
                try:
                    msg = await client.get_messages(CHANNEL, ids=msg_id)
                    if msg and getattr(msg, 'date', None):
                        rec['datetime'] = msg.date.strftime('%Y-%m-%d %H:%M')
                        changed += 1
                except Exception:
                    pass

    if changed:
        save_db(db, path)
        print(f"✅ Исправлено записей: {changed}")
    else:
        print("ℹ️ Нет записей, требующих исправления")


if __name__ == "__main__":
    import asyncio
    async def loop_forever(poll_interval=10, limit=100):
        """Continuously fetch new messages every `poll_interval` seconds.

        - limit: how many recent messages to fetch each iteration (keeps fetch bounded)
        - poll_interval: seconds between runs
        """
        while True:
            try:
                await fetch_and_save(limit=limit)
            except Exception as e:
                print('⚠️ Ошибка при fetch_and_save в цикле:', e)
            await asyncio.sleep(poll_interval)

    # Run the polling loop. This keeps the parser live and updates database.json every 10s.
    try:
        asyncio.run(loop_forever(poll_interval=10, limit=100))
    except KeyboardInterrupt:
        print('\n🛑 Остановлено пользователем')
