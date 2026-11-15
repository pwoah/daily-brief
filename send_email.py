#!/usr/bin/env python3
"""Email today's Daily Brief to yourself, with a private Inbox section. Standard library only, no AI.

Runs after build.py (which writes brief.json). Needs two GitHub secrets:
  GMAIL_ADDRESS       your Gmail address (the brief is sent from and to it)
  GMAIL_APP_PASSWORD  a Google App Password (16 lowercase letters), not your normal password
The Inbox section lists mail that reached your inbox in the last 24 hours. It only ever goes
in this email, never on the public web page. Reading is read-only: nothing is marked as read.
If either secret is missing it prints a note and exits without failing the workflow.
"""
import base64
import html
import imaplib
import json
import os
import re
import smtplib
import ssl
import sys
from datetime import datetime, timedelta, timezone
from email import message_from_bytes, policy
from email.message import EmailMessage
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).parent
SITE = "https://pwoah.github.io/daily-brief/"
TZ = ZoneInfo("America/Vancouver")
MAX_MAIL = 25


def clean(text, limit=160):
    text = re.sub(r"<style[\s\S]*?</style>|<script[\s\S]*?</script>", " ", text or "", flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    text = re.sub(r"[͏​-‏﻿\xa0\s]+", " ", text).strip()
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


def snippet(msg):
    part = msg.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    try:
        return clean(part.get_content())
    except Exception:
        return ""


def fetch_inbox(address, password):
    """Mail in INBOX from the last 24 hours, newest first. Read-only (BODY.PEEK)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    since = (cutoff - timedelta(days=1)).strftime("%d-%b-%Y")
    items = []
    with imaplib.IMAP4_SSL("imap.gmail.com", 993, ssl_context=ssl.create_default_context(), timeout=30) as imap:
        imap.login(address, password)
        imap.select("INBOX", readonly=True)
        _, data = imap.uid("search", None, f"SINCE {since}")
        uids = data[0].split()[-80:]
        for uid in reversed(uids):
            _, resp = imap.uid("fetch", uid, "(X-GM-MSGID BODY.PEEK[])")
            raw = next((r for r in resp if isinstance(r, tuple)), None)
            if not raw:
                continue
            m = re.search(rb"X-GM-MSGID (\d+)", raw[0])
            msg = message_from_bytes(raw[1], policy=policy.default)
            try:
                when = parsedate_to_datetime(msg["Date"])
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
            except Exception:
                continue
            if when < cutoff:
                continue
            subject = clean(str(msg["Subject"] or "(no subject)"), 140)
            if subject.startswith("Daily Brief ·"):
                continue  # don't list yesterday's brief
            name, addr = (getaddresses([str(msg["From"] or "")]) or [("", "")])[0]
            items.append({
                "from": clean(name or addr, 60),
                "subject": subject,
                "snippet": snippet(msg),
                "time": when.astimezone(TZ).strftime("%a %-I:%M %p"),
                "url": f"https://mail.google.com/mail/u/0/#all/{int(m.group(1)):x}" if m else "https://mail.google.com/mail/u/0/#inbox",
            })
            if len(items) >= MAX_MAIL:
                break
    return items


def render(data, inbox, inbox_error):
    e = html.escape
    out = [
        '<div style="font-family:Georgia,serif;max-width:640px;margin:auto;color:#222">',
        '<h1 style="font-size:22px;margin:0 0 4px">Daily Brief</h1>',
        f'<p style="color:#777;margin:0 0 20px;font-size:13px">{e(data["built"])} · <a href="{SITE}" style="color:#777">open the news page</a></p>',
    ]
    head = "📬 Inbox" + (f" · {len(inbox)} new in the last 24 hours" if inbox else "")
    out.append(f'<h2 style="font-size:16px;border-bottom:1px solid #ddd;padding-bottom:4px;margin:24px 0 8px">{e(head)}</h2>')
    if inbox_error:
        out.append(f'<p style="color:#a33;font-size:14px">Couldn\'t check your inbox today ({e(inbox_error)}).</p>')
    elif not inbox:
        out.append('<p style="color:#777;font-size:14px">Nothing new. Inbox zero. 🎉</p>')
    for m in inbox:
        out.append(
            '<p style="margin:0 0 12px;line-height:1.4">'
            f'<b>{e(m["from"])}</b> <span style="color:#888;font-size:12px">· {e(m["time"])}</span><br>'
            f'<a href="{e(m["url"])}" style="color:#1a4d8f;text-decoration:none">{e(m["subject"])}</a>'
            + (f'<br><span style="font-size:13px;color:#555">{e(m["snippet"])}</span>' if m["snippet"] else "")
            + "</p>"
        )
    for s in data["sections"]:
        out.append(f'<h2 style="font-size:16px;border-bottom:1px solid #ddd;padding-bottom:4px;margin:24px 0 8px">{e(s["name"])}</h2>')
        for i in s["items"]:
            lock = " 🔒" if i.get("paywall") else ""
            out.append(
                '<p style="margin:0 0 12px;line-height:1.4">'
                f'<a href="{e(i["url"])}" style="color:#1a4d8f;font-weight:bold;text-decoration:none">{e(i["title"])}</a>{lock}<br>'
                f'<span style="color:#888;font-size:12px">{e(i["source"])} · {e(i["time"])}</span>'
                + (f'<br><span style="font-size:14px">{e(i["teaser"])}</span>' if i.get("teaser") else "")
                + "</p>"
            )
    out.append("</div>")
    return "".join(out)


def plain(data, inbox, inbox_error):
    lines = [f"Daily Brief · {data['built']}", SITE, "", "INBOX", ""]
    if inbox_error:
        lines.append(f"Couldn't check your inbox today ({inbox_error}).")
    elif not inbox:
        lines.append("Nothing new.")
    for m in inbox:
        lines += [f"- {m['from']}: {m['subject']} ({m['time']})"]
    lines.append("")
    for s in data["sections"]:
        lines += [s["name"].upper(), ""]
        for i in s["items"]:
            lines += [f"- {i['title']} ({i['source']})", f"  {i['url']}"]
        lines.append("")
    return "\n".join(lines)


def smtp_send(address, password, msg):
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=30) as smtp:
        smtp.ehlo()
        # AUTH LOGIN step by step: Gmail answers a bad password with a clear 535 this way
        code, resp = smtp.docmd("AUTH", "LOGIN")
        if code == 334:
            code, resp = smtp.docmd(base64.b64encode(address.encode()).decode())
        if code == 334:
            code, resp = smtp.docmd(base64.b64encode(password.encode()).decode())
        if code != 235:
            print(f"app password shape: {len(password)} chars, lowercase letters only: {password.isalpha() and password.islower()}")
            sys.exit(f"Gmail rejected the login ({code}). GMAIL_APP_PASSWORD must be a Google App Password.")
        smtp.send_message(msg)


def main():
    # strip every kind of space (Google shows the app password in groups) and stray quotes
    address = re.sub(r"\s", "", os.environ.get("GMAIL_ADDRESS", "")).strip("\"'")
    password = re.sub(r"\s", "", os.environ.get("GMAIL_APP_PASSWORD", "")).strip("\"'")
    if not address or not password:
        print("GMAIL_ADDRESS or GMAIL_APP_PASSWORD secret not set; skipping email.")
        return
    data = json.loads((ROOT / "brief.json").read_text(encoding="utf-8"))
    inbox, inbox_error = [], None
    try:
        inbox = fetch_inbox(address, password)
    except Exception as exc:  # a mail-reading problem must never stop the news email
        inbox_error = exc.__class__.__name__
        print(f"Inbox check failed: {exc.__class__.__name__}: {exc}")
    msg = EmailMessage()
    msg["Subject"] = f"Daily Brief · {data['built'].split(' · ')[0]}" + (f" · 📬 {len(inbox)}" if inbox else "")
    msg["From"] = address
    msg["To"] = address
    msg.set_content(plain(data, inbox, inbox_error))
    msg.add_alternative(render(data, inbox, inbox_error), subtype="html")
    smtp_send(address, password, msg)
    print(f"Emailed the brief with {len(inbox)} inbox items.")


if __name__ == "__main__":
    main()
