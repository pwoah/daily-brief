#!/usr/bin/env python3
"""Email today's Daily Brief to yourself. Standard library only, no AI.

Runs after build.py (which writes brief.json). Needs two GitHub secrets:
  GMAIL_ADDRESS       your Gmail address (the brief is sent from and to it)
  GMAIL_APP_PASSWORD  a Google App Password, not your normal password
If either is missing it prints a note and exits without failing the workflow.
"""
import html
import json
import os
import smtplib
import re
import ssl
import sys
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).parent
SITE = "https://pwoah.github.io/daily-brief/"


def render(data):
    e = html.escape
    parts = [
        '<div style="font-family:Georgia,serif;max-width:640px;margin:auto;color:#222">',
        f'<h1 style="font-size:22px;margin:0 0 4px">Daily Brief</h1>',
        f'<p style="color:#777;margin:0 0 20px;font-size:13px">{e(data["built"])} · '
        f'<a href="{SITE}" style="color:#777">open the page</a></p>',
    ]
    for s in data["sections"]:
        parts.append(f'<h2 style="font-size:16px;border-bottom:1px solid #ddd;padding-bottom:4px;margin:24px 0 8px">{e(s["name"])}</h2>')
        for i in s["items"]:
            lock = " 🔒" if i.get("paywall") else ""
            parts.append(
                '<p style="margin:0 0 12px;line-height:1.4">'
                f'<a href="{e(i["url"])}" style="color:#1a4d8f;font-weight:bold;text-decoration:none">{e(i["title"])}</a>{lock}<br>'
                f'<span style="color:#888;font-size:12px">{e(i["source"])} · {e(i["time"])}</span>'
                + (f'<br><span style="font-size:14px">{e(i["teaser"])}</span>' if i.get("teaser") else "")
                + "</p>"
            )
    parts.append("</div>")
    return "".join(parts)


def plain(data):
    lines = [f"Daily Brief · {data['built']}", SITE, ""]
    for s in data["sections"]:
        lines += [s["name"].upper(), ""]
        for i in s["items"]:
            lines += [f"- {i['title']} ({i['source']})", f"  {i['url']}"]
        lines.append("")
    return "\n".join(lines)


def main():
    # strip every kind of space (Google shows the app password in groups, sometimes with non-breaking spaces) and stray quotes
    address = re.sub(r"\s", "", os.environ.get("GMAIL_ADDRESS", "")).strip("\"'")
    password = re.sub(r"\s", "", os.environ.get("GMAIL_APP_PASSWORD", "")).strip("\"'")
    if not address or not password:
        print("GMAIL_ADDRESS or GMAIL_APP_PASSWORD secret not set; skipping email.")
        return
    data = json.loads((ROOT / "brief.json").read_text(encoding="utf-8"))
    msg = EmailMessage()
    msg["Subject"] = f"Daily Brief · {data['built'].split(' · ')[0]}"
    msg["From"] = address
    msg["To"] = address
    msg.set_content(plain(data))
    msg.add_alternative(render(data), subtype="html")
    # safe diagnostics: shapes only, never the values
    print(f"address: {len(address)} chars, ends with @gmail.com: {address.lower().endswith('@gmail.com')}, ascii: {address.isascii()}")
    print(f"app password: {len(password)} chars, letters only: {password.isalpha()}, all lowercase: {password.islower()}, ascii: {password.isascii()}")
    last = None
    for attempt in ("ssl", "starttls"):
        try:
            if attempt == "ssl":
                smtp = smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=30)
            else:
                smtp = smtplib.SMTP("smtp.gmail.com", 587, timeout=30)
                smtp.starttls(context=ssl.create_default_context())
            with smtp:
                smtp.ehlo()
                print("server offers:", smtp.esmtp_features.get("auth", "?"))
                code, resp = smtp.docmd("AUTH", "LOGIN")
                print("AUTH LOGIN ->", code)
                code, resp = smtp.docmd(smtplib.base64.b64encode(address.encode()).decode())
                print("username step ->", code)
                code, resp = smtp.docmd(smtplib.base64.b64encode(password.encode()).decode())
                print("password step ->", code, resp.decode(errors="replace")[:120])
                if code != 235:
                    raise smtplib.SMTPAuthenticationError(code, resp)
                smtp.send_message(msg)
            print(f"Emailed the brief ({attempt}).")
            return
        except smtplib.SMTPAuthenticationError as exc:
            sys.exit(f"Gmail rejected the login: {exc.smtp_code}. Check that GMAIL_ADDRESS is your full Gmail address and GMAIL_APP_PASSWORD is a fresh App Password.")
        except Exception as exc:
            last = exc
            print(f"{attempt} attempt failed: {exc.__class__.__name__}: {exc}")
    sys.exit(f"Could not send the email: {last}")


if __name__ == "__main__":
    main()
