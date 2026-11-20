import json
from datetime import date, timedelta
from pathlib import Path

import anthropic
import yfinance as yf

from common import PORTFOLIO, FAST_MODEL, send_telegram, get_text

STATE_FILE = Path("alert_state.json")
HISTORY_FILE = Path("history.json")

client = anthropic.Anthropic()

SYSTEM = """You explain big one-day stock moves to a complete beginner investor.
Rules:
- Plain English, 2-3 short sentences, no jargon.
- Use ONLY the headlines provided. Never invent facts or numbers.
- If the headlines don't clearly explain the move, say the cause isn't clear.
- Never claim a headline definitely caused the move.
- Never tell the user to buy or sell. Remind them that big one-day moves happen and
  a move alone is not a reason to act."""


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def recent_headlines(ticker, days=2):
    if not HISTORY_FILE.exists():
        return []
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    history = json.loads(HISTORY_FILE.read_text())
    items = [h for h in history if h["ticker"] == ticker and h["date"] >= cutoff]
    items.sort(key=lambda h: -h["importance"])
    return [h["title"] for h in items[:8]]


def explain(stock, pct, headlines):
    if not headlines:
        return (
            "I don't have any recent headlines saved for this stock, so I can't tell "
            "what's behind the move. Big one-day moves happen and a move alone is not "
            "a reason to act."
        )
    prompt = (
        f"{stock['name']} ({stock['ticker']}) moved {pct:+.1f}% versus yesterday's close.\n"
        f"Background: {stock['why']}\n\nRecent headlines:\n"
        + "\n".join(f"- {t}" for t in headlines)
    )
    resp = client.messages.create(
        model=FAST_MODEL,
        max_tokens=1500,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    return get_text(resp)


def main():
    state = load_state()

    for stock in PORTFOLIO:
        try:
            closes = yf.Ticker(stock["price_symbol"]).history(period="5d")["Close"].dropna()
            if len(closes) < 2:
                continue
            last, prev = float(closes.iloc[-1]), float(closes.iloc[-2])
            bar_date = closes.index[-1].date().isoformat()
            pct = (last / prev - 1) * 100

            level = int(abs(pct) // stock["alert_pct"])
            done = state.get(stock["ticker"], {})
            already = done.get("level", 0) if done.get("date") == bar_date else 0

            if level >= 1 and level > already:
                arrow = "📈" if pct > 0 else "📉"
                try:
                    why = explain(stock, pct, recent_headlines(stock["ticker"]))
                except Exception as e:
                    print(f"Explanation failed: {e}")
                    why = "Couldn't generate an explanation this time."
                send_telegram(
                    f"{arrow} BIG MOVE: {stock['ticker']} is {pct:+.1f}% vs yesterday's close\n"
                    f"Now ${last:.2f} (was ${prev:.2f})\n\n{why}"
                )
                state[stock["ticker"]] = {"date": bar_date, "level": level}
        except Exception as e:
            print(f"Problem with {stock['ticker']}: {e}")

    STATE_FILE.write_text(json.dumps(state))


if __name__ == "__main__":
    main()
