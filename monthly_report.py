import json
from datetime import date, timedelta
from pathlib import Path

import anthropic
import yfinance as yf

from common import (
    PORTFOLIO,
    BENCHMARK_NAME,
    BENCHMARK_SYMBOL,
    REPORT_MODEL,
    send_telegram,
    get_text,
)

HISTORY_FILE = Path("history.json")
DAYS = 30
MAX_ITEMS_PER_STOCK = 40

client = anthropic.Anthropic()

SYSTEM = """You write a monthly stock report for a complete beginner investor.
Rules:
- Plain English, no jargon. Briefly explain any term you must use.
- Use ONLY the notes and price facts provided. Never invent or calculate your own
  numbers, prices, or events. Quote price figures exactly as given.
- Connect news to price moves only when the notes clearly support it. Otherwise say
  the cause isn't clear from the headlines. Do not claim news caused a price move.
- Never tell the user to buy or sell. Describe what happened and what to keep an eye on.
- If little happened for a stock, say so. A quiet month is normal and fine.
- Plain text only: no markdown symbols like ** or #. Use the emoji and short paragraphs.
- Be honest that this is based on news headlines, so it may miss details."""


def price_change(symbol):
    try:
        closes = yf.Ticker(symbol).history(period="1mo")["Close"].dropna()
        if len(closes) < 2:
            return None
        start, end = float(closes.iloc[0]), float(closes.iloc[-1])
        return {
            "start_date": closes.index[0].date(),
            "end": end,
            "pct": (end / start - 1) * 100,
            "low": float(closes.min()),
            "high": float(closes.max()),
        }
    except Exception as e:
        print(f"Price lookup failed for {symbol}: {e}")
        return None


def build_price_lines():
    lines, any_ok = [], False
    bench = price_change(BENCHMARK_SYMBOL)
    for stock in PORTFOLIO:
        p = price_change(stock["price_symbol"])
        if not p:
            lines.append(f"{stock['ticker']}: price data unavailable")
            continue
        any_ok = True
        line = (
            f"{stock['ticker']}: ${p['end']:.2f}, {p['pct']:+.1f}% since "
            f"{p['start_date']:%d %b}. Month range: ${p['low']:.2f} to ${p['high']:.2f}."
        )
        if bench:
            diff = p["pct"] - bench["pct"]
            word = "ahead of" if diff >= 0 else "behind"
            line += f" That is {abs(diff):.1f} points {word} the market."
        lines.append(line)
    if bench:
        lines.append(f"{BENCHMARK_NAME}: {bench['pct']:+.1f}% over the same period.")
    return lines, any_ok


def main():
    price_lines, have_prices = build_price_lines()

    if not HISTORY_FILE.exists():
        send_telegram("Monthly report: no news history saved yet, so nothing to summarise.")
        return

    history = json.loads(HISTORY_FILE.read_text())
    cutoff = (date.today() - timedelta(days=DAYS)).isoformat()
    recent = [h for h in history if h["date"] >= cutoff]
    if not recent:
        send_telegram("Monthly report: no news was recorded in the last 30 days.")
        return

    if have_prices:
        send_telegram(
            "💰 PRICE SNAPSHOT (US dollars, last ~month)\n\n"
            + "\n\n".join(price_lines)
        )

    notes = []
    for ticker in sorted({h["ticker"] for h in recent}):
        items = [h for h in recent if h["ticker"] == ticker]
        items.sort(key=lambda h: (-h["importance"], h["date"]))
        notes.append(f"=== {ticker}: {len(items)} headlines this month ===")
        for h in items[:MAX_ITEMS_PER_STOCK]:
            notes.append(f"[{h['date']}] importance {h['importance']}/3: {h['message']}")

    price_block = (
        "\n".join(price_lines)
        if have_prices
        else "Price data was unavailable this month. Do not mention prices."
    )

    prompt = f"""Here are my notes on news about the stocks I own over the last {DAYS} days
(today is {date.today().isoformat()}).

PRICE FACTS (already calculated, quote exactly):
{price_block}

NEWS NOTES:
{chr(10).join(notes)}

Write my monthly report with this structure:
1. A 2-3 sentence overview of the month across all my stocks, including how they did
   compared with the overall market if price facts are available.
2. For each stock: an emoji header with the ticker, one line on how the price moved
   (if available), the 2-4 most important news items (most important first), and one
   thing worth watching next month.
3. A short closing note reminding me this is based on headlines and is not financial advice."""

    resp = client.messages.create(
        model=REPORT_MODEL,
        max_tokens=8000,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    send_telegram("📊 MONTHLY REPORT\n\n" + get_text(resp))


if __name__ == "__main__":
    main()
