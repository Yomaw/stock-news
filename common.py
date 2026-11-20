import os
import requests

FAST_MODEL = "claude-haiku-5-5"
REPORT_MODEL = "claude-sonnet-5-5"

PORTFOLIO = [
    {
        "ticker": "NVDA",
        "name": "NVIDIA",
        "query": '"NVIDIA" stock',
        "price_symbol": "NVDA",
        "alert_pct": 5,
        "why": "Leading maker of AI chips. Sensitive to AI demand, chip export rules, and competition.",
    },
    {
        "ticker": "SPCX",
        "name": "SpaceX",
        "query": '"SpaceX" stock OR SPCX',
        "price_symbol": "SPCX",
        "alert_pct": 8,
        "why": "Newly public rocket and satellite company (Starlink). Recent IPO, so prices can swing a lot.",
    },
    {
        "ticker": "BRK",
        "name": "Berkshire Hathaway",
        "query": '"Berkshire Hathaway" stock',
        "price_symbol": "BRK-B",
        "alert_pct": 3,
        "why": "Warren Buffett's conglomerate: insurance, railroads, energy, and a large stock portfolio. Usually slow-moving.",
    },
]

BENCHMARK_NAME = "S&P 500 (the overall US market)"
BENCHMARK_SYMBOL = "^GSPC"

TG_TOKEN = os.environ["TELEGRAM_TOKEN"]
TG_CHAT = os.environ["TELEGRAM_CHAT_ID"]


def send_telegram(text):
    """Send a Telegram message, splitting long text (Telegram's limit is 4096 chars)."""
    chunks, current = [], ""
    for para in text.split("\n\n"):
        if len(current) + len(para) + 2 > 3800:
            chunks.append(current)
            current = ""
        current += para + "\n\n"
    chunks.append(current)
    for chunk in chunks:
        if chunk.strip():
            requests.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={
                    "chat_id": TG_CHAT,
                    "text": chunk.strip(),
                    "disable_web_page_preview": True,
                },
                timeout=30,
            ).raise_for_status()
