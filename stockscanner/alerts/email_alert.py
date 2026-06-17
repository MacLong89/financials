from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def send_email_message(subject: str, body: str) -> None:
    host = _env("SMTP_HOST")
    port = int(_env("SMTP_PORT", "587"))
    user = _env("SMTP_USER")
    password = _env("SMTP_PASSWORD")
    from_addr = _env("SMTP_FROM", user)
    to_raw = _env("SMTP_TO")

    if not host or not user or not password or not to_raw:
        raise ValueError(
            "Email alerts require SMTP_HOST, SMTP_USER, SMTP_PASSWORD, and SMTP_TO"
        )

    recipients = [addr.strip() for addr in to_raw.split(",") if addr.strip()]
    if not recipients:
        raise ValueError("SMTP_TO must contain at least one recipient")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(recipients)
    msg.set_content(body)

    use_tls = _env("SMTP_USE_TLS", "true").lower() in {"1", "true", "yes"}
    context = ssl.create_default_context()

    with smtplib.SMTP(host, port, timeout=30) as server:
        if use_tls:
            server.starttls(context=context)
        server.login(user, password)
        server.send_message(msg)
