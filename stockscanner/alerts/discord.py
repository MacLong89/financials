from __future__ import annotations

import os

import requests


def send_discord_message(body: str, *, webhook_url: str | None = None) -> None:
    url = webhook_url or os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not url:
        raise ValueError("DISCORD_WEBHOOK_URL is not set")

    # Discord content limit is 2000 chars; truncate safely
    content = body if len(body) <= 1900 else body[:1900] + "\n… (truncated)"
    response = requests.post(url, json={"content": f"```\n{content}\n```"}, timeout=30)
    response.raise_for_status()
