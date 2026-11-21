import json
import re
import hashlib
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote

import feedparser
import anthropic

from common import PORTFOLIO, FAST_MODEL, send_telegram, get_text

MIN_IMPORTANCE = 4   # nothing scores 4, so no individual alerts; everything is still saved to history.json
MAX_PER_STOCK = 8
SEEN_FILE = Path("seen.json")
HISTORY_FILE = Path("history.json")

client = anthropic.Anthropic()

SYSTEM = """You are a friendly assistant for a complete beginner investor.
You read news headlines about stocks they own and explain them simply.
Rules:
- Use plain English, no jargon. If you must use a term, explain it in a few words.
- Base your explanation ONLY on the headline. Never invent numbers or facts.
- If the headline is vague, say so honestly.
- Never tell the user to buy or sell. Explain what happened and why it might matter.
- Keep each message to 2-3 short sentences.

Importance scale:
3 = Important: could meaningfully affect the company's value or the user's thesis
    (earnings results, big lawsuits or regulation, acquisitions, CEO changes,
    major product or contract news, big unexpected events).
2 = Worth knowing: relevant but not dramatic (analyst opinions, smaller deals,
    industry trends that touch the company).
1 = Minor or noise: routine price-move articles, listicles, opinion pieces,
    repeated or unrelated stories."""


def load_seen():
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return set()


def save_seen(seen):
    SEEN_FILE.write_text(json.dumps(sorted(seen)[-3000:]))


def load_history():
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text())
    return []


def save_history(history):
    cutoff = (date.today() - timedelta(days=90)).isoformat()
    history = [h for h in history if h["date"] >= cutoff]
    HISTORY_FILE.write_text(json.dumps(history, indent=1))


def make_id(title):
    return hashlib.md5(title.lower().strip().encode()).hexdigest()


def fetch_news(stock):
    q = quote(f'{stock["query"]} when:1d')
    url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
    feed = feedparser.parse(url)
    return [
        {"id": make_id(e.title), "title": e.title, "link": e.link}
        for e in feed.entries
    ]


def analyze(stock, items):
    lines = "\n".join(f"{i}. {it['title']}" for i, it in enumerate(items))
    prompt = f"""Stock: {stock['name']} ({stock['ticker']})
Background: {stock['why']}

Headlines:
{lines}

Return ONLY a JSON list with one object per headline, like:
[{{"id": 0, "importance": 2, "message": "Plain-English explanation here."}}]"""
    resp = client.messages.create(
        model=FAST_MODEL,
        max_tokens=4000,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    text = re.sub(r"```(?:json)?", "", get_text(resp)).strip()
    return json.loads(text)


def main():
    seen = load_seen()
    history = load_history()
    emoji = {3: "🔴", 2: "🟡", 1: "🟢"}
    failed_stocks = []

    for stock in PORTFOLIO:
        try:
            new = [it for it in fetch_news(stock) if it["id"] not in seen]
            new = new[:MAX_PER_STOCK]
            if not new:
                continue

            results = analyze(stock, new)
            for r in results:
                item = new[r["id"]]
                level = int(r["importance"])
                history.append({
                    "date": date.today().isoformat(),
                    "ticker": stock["ticker"],
                    "importance": level,
                    "message": r["message"],
                    "title": item["title"],
                    "link": item["link"],
                })
                if level >= MIN_IMPORTANCE:
                    send_telegram(
                        f"{emoji[level]} {stock['ticker']} | Importance {level}/3\n\n"
                        f"{r['message']}\n\n"
                        f"Headline: {item['title']}\n{item['link']}"
                    )
            seen.update(it["id"] for it in new)
        except Exception as e:
            print(f"Problem with {stock['ticker']}: {e}")
            failed_stocks.append(stock["ticker"])

    save_seen(seen)
    save_history(history)
    if failed_stocks:
        raise RuntimeError(
            f"News monitor failed for: {', '.join(failed_stocks)}"
        )


if __name__ == "__main__":
    main()
