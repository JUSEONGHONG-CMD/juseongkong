"""Gmail SMTP 이메일 채널.

환경변수: GMAIL_USER, GMAIL_APP_PASSWORD (Google 계정의 앱 비밀번호)
받는 사람이 서로의 주소를 보지 않도록 수신자별로 따로 보낸다.
개인정보(주소·제목·본문)는 절대 출력하지 않는다.
"""
from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465
SENDER_NAME = "지원제도 알리미"


def build(message: dict, sender: str, recipient: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = formataddr((SENDER_NAME, sender))
    msg["To"] = recipient
    msg["Subject"] = message["subject"]
    msg["Message-ID"] = make_msgid(domain=sender.split("@")[-1])
    msg.set_content(message.get("text") or "")
    if message.get("html"):
        msg.add_alternative(message["html"], subtype="html")
    return msg


def send(message: dict, dry_run: bool = False) -> None:
    sender = os.environ.get("GMAIL_USER", "sender@example.com" if dry_run else "")
    password = os.environ.get("GMAIL_APP_PASSWORD", "")
    recipients = message.get("to") or []
    if not recipients:
        raise ValueError("message has no recipients")
    mails = [build(message, sender, r) for r in recipients]
    if dry_run:
        return
    if not sender or not password:
        raise RuntimeError("GMAIL_USER / GMAIL_APP_PASSWORD not set")
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ssl.create_default_context()) as smtp:
        smtp.login(sender, password)
        for mail in mails:
            smtp.send_message(mail)
