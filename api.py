from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from typing import Optional
from datetime import datetime, date
import stats
import json
import os

app = FastAPI(title="Statistik API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def load_db_override():
    # Ensure stats.load_data reads from local database.json
    try:
        return json.load(open('database.json', 'r', encoding='utf-8'))
    except Exception:
        return []


@app.on_event("startup")
def startup_event():
    # wire stats.load_data to use the file-based loader
    stats.load_data = load_db_override


@app.get('/stats/day')
def stats_day(day: Optional[str] = None):
    """Return stats for a specific day. day=YYYY-MM-DD. If omitted, today is used."""
    try:
        if day:
            d = datetime.strptime(day, '%Y-%m-%d').date()
        else:
            d = date.today()
    except Exception:
        raise HTTPException(status_code=400, detail='Invalid date format, use YYYY-MM-DD')

    res = stats.daily_income(d)
    return {"date": d.isoformat(), "totals": res}


@app.get('/stats/top')
def stats_top(n: int = 10):
    """Return top N users by income."""
    res = stats.ranking_by_income(n)
    return {"top": res}


@app.get('/stats/total')
def stats_total():
    """Return overall totals across the entire database."""
    res = stats.total_all()
    return {"totals": res}


@app.get('/stats/info')
def stats_info():
    """Return small info about the DB: number of records and source channel (if present)."""
    try:
        db = json.load(open('database.json', 'r', encoding='utf-8'))
    except Exception:
        db = []
    source = None
    if db:
        # find first record with source
        for r in db:
            if r.get('source'):
                source = r.get('source')
                break
    return {"records": len(db), "source": source}


@app.get('/stats/range')
def stats_range(start: Optional[str] = None, end: Optional[str] = None):
    """Return per-day stats for a date range. Query params: start=YYYY-MM-DD, end=YYYY-MM-DD.

    If only start provided, end defaults to start. If neither provided, returns last 7 days.
    """
    from datetime import timedelta

    try:
        if start:
            d0 = datetime.strptime(start, '%Y-%m-%d').date()
        else:
            # default to 7 days ago
            d0 = date.today() - timedelta(days=6)

        if end:
            d1 = datetime.strptime(end, '%Y-%m-%d').date()
        else:
            d1 = d0
    except Exception:
        raise HTTPException(status_code=400, detail='Invalid date format, use YYYY-MM-DD')

    if d1 < d0:
        raise HTTPException(status_code=400, detail='end must be >= start')

    res = stats.income_by_days(d0, d1)
    return {"start": d0.isoformat(), "end": d1.isoformat(), "by_day": res}


@app.get('/stats/extremes')
def stats_extremes(start: Optional[str] = None, end: Optional[str] = None):
    """Return best and worst non-zero days and combined totals for range."""
    from datetime import timedelta

    try:
        if start:
            d0 = datetime.strptime(start, '%Y-%m-%d').date()
        else:
            d0 = date.today() - timedelta(days=6)

        if end:
            d1 = datetime.strptime(end, '%Y-%m-%d').date()
        else:
            d1 = d0
    except Exception:
        raise HTTPException(status_code=400, detail='Invalid date format, use YYYY-MM-DD')

    if d1 < d0:
        raise HTTPException(status_code=400, detail='end must be >= start')

    res = stats.extremes_by_days(d0, d1)
    return res


@app.get('/stats/reminders')
def stats_reminders(day: Optional[str] = None, last_n: int = 50, reminders: int = 1,
                    sleep_start: int = 0, sleep_end: int = 6, smoothing: bool = True, alpha: float = 0.8):
    """Return suggested reminders for all users for a specific day.

    Query params:
      - day=YYYY-MM-DD (defaults to today)
      - last_n: consider last N entries per user
      - reminders: reminders per day suggested when generating
      - sleep_start, sleep_end, smoothing, alpha: passed to generator
    """
    try:
        if day:
            target = datetime.strptime(day, '%Y-%m-%d').date()
        else:
            target = date.today()
    except Exception:
        raise HTTPException(status_code=400, detail='Invalid date format, use YYYY-MM-DD')

    # load DB directly
    try:
        db = json.load(open('database.json', 'r', encoding='utf-8'))
    except Exception:
        db = []

    # gather unique user_ids
    user_ids = sorted({r.get('user_id') for r in db if r.get('user_id') is not None})
    result = []
    for uid in user_ids:
        summary = stats.user_summary(uid)
        todo = stats.generate_reminders_from_summary(summary, days=1, last_n=last_n,
                                                     reminders_per_day=reminders,
                                                     sleep_start=sleep_start, sleep_end=sleep_end,
                                                     smoothing=smoothing, alpha=alpha)
        # filter reminders for the exact target date
        matched = [t for t in todo if t.get('date') == target.isoformat()]
        if matched:
            result.append({
                'user': summary.get('user'),
                'user_id': uid,
                'reminders': matched,
            })

    return {'date': target.isoformat(), 'count': len(result), 'result': result}


@app.get('/stats/user')
def stats_user(user_id: Optional[int] = None, last_n: int = 50, reminders: int = 1, days: int = 7,
               tz_offset: int = 0, sleep_start: int = 0, sleep_end: int = 6, smoothing: bool = True, alpha: float = 0.8):
    """Return user summary and suggestion TODOs for next `days` days.

    Query params:
      - user_id (int, required)
      - last_n (int) — consider last N entries (default 50)
      - reminders (int) — reminders per day (default 1)
      - days (int) — days ahead to suggest (default 7)
    """
    if user_id is None:
        raise HTTPException(status_code=400, detail='user_id required')

    summary = stats.user_summary(user_id)
    # generate reminders using new helper with advanced options
    todo = stats.generate_reminders_from_summary(summary, days=days, last_n=last_n,
                                                 reminders_per_day=reminders, tz_offset=tz_offset,
                                                 sleep_start=sleep_start, sleep_end=sleep_end,
                                                 smoothing=smoothing, alpha=alpha)
    return {'summary': summary, 'todo': todo}


@app.get('/')
def root():
    """Serve the frontend HTML file at the root."""
    frontend_path = os.path.join(os.getcwd(), 'frontend.html')
    if os.path.exists(frontend_path):
        return FileResponse(frontend_path, media_type='text/html')
    raise HTTPException(status_code=404, detail='frontend.html not found')


@app.get('/frontend.html')
def frontend_alias():
    return root()


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8001, log_level='info')
