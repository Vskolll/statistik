# stats.py

import json
from datetime import datetime, date, timedelta
from config import USD_RUB, USD_UAH


def load_data(path="database.json"):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_dt(s: str):
    return datetime.strptime(s, "%Y-%m-%d %H:%M")


def convert_to_usd(amount: float, currency: str) -> float:
    if currency == "RUB":
        return amount / USD_RUB
    elif currency == "UAH":
        return amount / USD_UAH
    return amount


def convert_to_rub(amount: float, currency: str) -> float:
    if currency == "RUB":
        return amount
    elif currency == "UAH":
        # UAH -> USD -> RUB: amount / USD_UAH * USD_RUB
        return amount / USD_UAH * USD_RUB
    return amount


def get_stats(start: datetime, end: datetime):
    """Возвращает суммарный доход в рублях, гривнах и в долларах (≈) за период."""
    data = load_data()
    total_rub = 0
    total_uah = 0

    for entry in data:
        if not entry.get("datetime"):
            continue
        dt = parse_dt(entry["datetime"])
        # treat `end` as exclusive (start <= dt < end)
        if start <= dt < end:
            if entry["currency"] == "RUB":
                total_rub += entry["amount"]
            elif entry["currency"] == "UAH":
                total_uah += entry["amount"]

    total_usd = round(total_rub / USD_RUB + total_uah / USD_UAH, 2)

    return {
        "rub": total_rub,
        "uah": total_uah,
        "usd": total_usd,
    }


def total_all():
    """Возвращает суммарный доход по всей базе (без фильтра по дате).

    Результат: {rub: int, uah: int, usd: float}
    """
    data = load_data()
    total_rub = 0
    total_uah = 0
    for entry in data:
        if entry.get("currency") == "RUB":
            total_rub += entry.get("amount", 0)
        elif entry.get("currency") == "UAH":
            total_uah += entry.get("amount", 0)

    total_usd = round(total_rub / USD_RUB + total_uah / USD_UAH, 2)
    return {"rub": total_rub, "uah": total_uah, "usd": total_usd}


def daily_income(target_date: date):
    """Возвращает доход за указанный день по валютам и в USD эквиваленте."""
    start = datetime.combine(target_date, datetime.min.time())
    end = start + timedelta(days=1)
    s = get_stats(start, end)
    return s


def income_by_days(start_date: date, end_date: date):
    """Возвращает словарь date->stats для каждого дня в диапазоне [start_date, end_date]."""
    result = {}
    cur = start_date
    while cur <= end_date:
        result[cur.isoformat()] = daily_income(cur)
        cur = cur + timedelta(days=1)
    return result


def extremes_by_days(start_date: date, end_date: date):
    """Return the best and worst day (by rub-equivalent) in given inclusive range.

    Excludes days with zero total (rub + uah == 0). Returns dict:
    {"best": {"date": iso, "rub": r, "uah": u, "rub_eq": x, "usd": y},
     "worst": {...},
     "combined": {"rub": rsum, "uah": usum, "usd": dsum}}
    If no non-zero days found, returns {"best": None, "worst": None, "combined": {rub:0,uah:0,usd:0}}
    """
    days = income_by_days(start_date, end_date)
    best = None
    worst = None
    for iso, stats_day in days.items():
        r = stats_day.get('rub', 0) or 0
        u = stats_day.get('uah', 0) or 0
        # rub equivalent
        rub_eq = r + convert_to_rub(u, 'UAH')
        if (r == 0 and u == 0):
            continue
        rec = {"date": iso, "rub": r, "uah": u, "rub_eq": round(rub_eq, 2), "usd": round(convert_to_usd(rub_eq, 'RUB'), 2)}
        if best is None or rec['rub_eq'] > best['rub_eq']:
            best = rec
        if worst is None or rec['rub_eq'] < worst['rub_eq']:
            worst = rec

    if not best:
        return {"best": None, "worst": None, "combined": {"rub": 0, "uah": 0, "usd": 0}}

    combined_rub = best['rub'] + worst['rub']
    combined_uah = best['uah'] + worst['uah']
    combined_rub_eq = best['rub_eq'] + worst['rub_eq']
    combined_usd = round(convert_to_usd(combined_rub_eq, 'RUB'), 2)
    return {"best": best, "worst": worst, "combined": {"rub": combined_rub, "uah": combined_uah, "usd": combined_usd}}


def user_summary(user_id):
    """Return all entries for a user and computed summary: counts by hour and weekday, common hours.

    Result:
    {"user": name, "user_id": id, "entries": [ {datetime, account, amount, currency, source}... ],
     "by_hour": {hour: count}, "by_weekday": {0:count..6:count}, "common_hours": [hour,...] }
    """
    data = load_data()
    entries = []
    name = None
    for e in data:
        if e.get('user_id') == user_id:
            if not name:
                name = e.get('user')
            if e.get('datetime'):
                entries.append({
                    'datetime': e.get('datetime'),
                    'account': e.get('account'),
                    'amount': e.get('amount'),
                    'currency': e.get('currency'),
                    'source': e.get('source'),
                })

    # compute stats
    from collections import Counter
    hours = Counter()
    weekdays = Counter()
    from datetime import datetime
    for ent in entries:
        try:
            dt = datetime.strptime(ent['datetime'], '%Y-%m-%d %H:%M')
            hours[dt.hour] += 1
            weekdays[dt.weekday()] += 1
        except Exception:
            continue

    # most common hours (top 3)
    common_hours = [h for h,c in hours.most_common(3)]

    return {
        'user': name or 'без username',
        'user_id': user_id,
        'entries': sorted(entries, key=lambda x: x['datetime']),
        'by_hour': dict(hours),
        'by_weekday': dict(weekdays),
        'common_hours': common_hours,
    }


def generate_reminders_from_summary(summary, days=7, last_n=None, reminders_per_day=1,
                                    tz_offset=0, sleep_start=0, sleep_end=6, smoothing=True, alpha=0.8):
    """Generate reminder suggestions based on user summary.

    - summary: result of user_summary(user_id)
    - days: number of future days to generate reminders for
    - last_n: consider only the last N entries (None -> all)
    - reminders_per_day: how many reminders per day to suggest

    Returns list of {date, time, note}
    """
    from datetime import date, timedelta, datetime
    from collections import Counter, defaultdict

    entries = summary.get('entries', [])
    if last_n and len(entries) > last_n:
        entries = entries[-last_n:]

    if not entries:
        return []

    # Build global hour frequencies and weekday->hour frequencies
    global_hours = Counter()
    weekday_hours = defaultdict(Counter)
    for e in entries:
        try:
            dt = datetime.strptime(e['datetime'], '%Y-%m-%d %H:%M')
        except Exception:
            continue
        # apply timezone offset (hours) to align times to target timezone
        try:
            if tz_offset:
                dt = dt + timedelta(hours=int(tz_offset))
        except Exception:
            pass
        h = dt.hour
        wd = dt.weekday()
        global_hours[h] += 1
        weekday_hours[wd][h] += 1

    # Prepare sorted lists
    # Prepare weighted order; apply smoothing (flatten peaks) via exponent alpha
    if smoothing and global_hours:
        # compute weights
        weights = {h: (cnt ** alpha) for h, cnt in global_hours.items()}
        # sort by weight desc
        global_order = sorted(weights.keys(), key=lambda hh: weights[hh], reverse=True)
    else:
        global_order = [h for h,_ in global_hours.most_common()]

    today = date.today()
    todo = []
    # For each future day, choose reminders_per_day hours
    for i in range(days):
        d = today + timedelta(days=i)
        wd = d.weekday()
        chosen = []
        # first try weekday-specific popular hours
        week_counter = weekday_hours.get(wd, Counter())
        if smoothing and week_counter:
            week_weights = {h: (cnt ** alpha) for h, cnt in week_counter.items()}
            week_hours = sorted(week_weights.keys(), key=lambda hh: week_weights[hh], reverse=True)
        else:
            week_hours = [h for h,_ in week_counter.most_common()]
        # merge: try week_hours first, then global_order
        candidates = week_hours + [h for h in global_order if h not in week_hours]
        for h in candidates:
            if len(chosen) >= reminders_per_day:
                break
            # exclude sleep hours
            if sleep_start <= sleep_end:
                if sleep_start <= h < sleep_end:
                    continue
            else:
                # wrap-around (e.g., sleep_start=22 sleep_end=6)
                if h >= sleep_start or h < sleep_end:
                    continue
            if h not in chosen:
                # avoid choosing adjacent hours for spread
                too_close = any(abs(h - c) <= 1 for c in chosen)
                if not too_close:
                    chosen.append(h)

        # if still not enough, fill with next best non-sleep hours
        for h in range(24):
            if len(chosen) >= reminders_per_day:
                break
            if h in chosen:
                continue
            if sleep_start <= sleep_end:
                if sleep_start <= h < sleep_end:
                    continue
            else:
                if h >= sleep_start or h < sleep_end:
                    continue
            chosen.append(h)

        for h in chosen:
            todo.append({'date': d.isoformat(), 'time': f"{h:02d}:00", 'note': f"Напомнить {summary.get('user')} взять аренду"})

    return todo


def ranking_by_income(top_n: int = 10):
    """Возвращает топ пользователей по сумме в RUB-эквиваленте.

    Результат: список словарей: {user, user_id, total_rub, total_usd, count}
    """
    data = load_data()
    users = {}

    for e in data:
        uid = e.get("user_id")
        name = e.get("user") or "без username"
        amt = e.get("amount", 0) or 0
        cur = e.get("currency", "RUB")

        # keep raw sums by currency; compute rub-equivalent for sorting
        key = (uid, name)
        if key not in users:
            users[key] = {
                "user": name,
                "user_id": uid,
                "total_rub_raw": 0.0,
                "total_uah_raw": 0.0,
                "total_rub_eq": 0.0,
                "count": 0,
            }

        if cur == "RUB":
            users[key]["total_rub_raw"] += amt
        elif cur == "UAH":
            users[key]["total_uah_raw"] += amt

        # rub-equivalent used for sorting
        users[key]["total_rub_eq"] += convert_to_rub(amt, cur)
        users[key]["count"] += 1

    arr = list(users.values())
    arr.sort(key=lambda x: x["total_rub_eq"], reverse=True)
    # Round totals for neatness and provide a USD-equivalent computed with server config
    for a in arr:
        a["total_rub_raw"] = round(a["total_rub_raw"], 2)
        a["total_uah_raw"] = round(a["total_uah_raw"], 2)
        a["total_rub_eq"] = round(a["total_rub_eq"], 2)
        # USD-equivalent (server-side) provided for convenience
        a["total_usd_eq"] = round(a["total_rub_eq"] / USD_RUB, 2)

    return arr[:top_n]


def ranking_by_count(top_n: int = 10):
    data = load_data()
    users = {}
    for e in data:
        uid = e.get("user_id")
        name = e.get("user") or "без username"
        key = (uid, name)
        users.setdefault(key, 0)
        users[key] += 1

    arr = [{"user": k[1], "user_id": k[0], "count": v} for k, v in users.items()]
    arr.sort(key=lambda x: x["count"], reverse=True)
    return arr[:top_n]


if __name__ == "__main__":
    # Пример использования: статистика за сегодня и топ-10 пользователей
    today = datetime.combine(date.today(), datetime.min.time())
    tomorrow = today + timedelta(days=1)

    res = get_stats(today, tomorrow)
    print(f"Сегодня: {res['rub']} ₽, {res['uah']} ₴, ≈ {res['usd']} $")

    print("\nТоп пользователей по доходу:")
    for i, u in enumerate(ranking_by_income(10), 1):
        print(f"{i}. {u['user']} ({u['user_id']}): {u['total_rub']} ₽ ≈ {u['total_usd']}$, count={u['count']}")
