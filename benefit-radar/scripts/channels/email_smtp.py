"""Gmail SMTP 이메일 채널.

환경변수: GMAIL_USER, GMAIL_APP_PASSWORD (Google 계정의 앱 비밀번호)
message["to"] 는 받는사람, message["cc"](선택)는 참조로 한 통에 담아 보낸다.
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


def build(message: dict, sender: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = formataddr((SENDER_NAME, sender))
    msg["To"] = ", ".join(message["to"])
    if message.get("cc"):
        msg["Cc"] = ", ".join(message["cc"])
    msg["Subject"] = message["subject"]
    msg["Message-ID"] = make_msgid(domain=sender.split("@")[-1])
    msg.set_content(message.get("text") or "")
    if message.get("html"):
        msg.add_alternative(message["html"], subtype="html")
    return msg


def send(message: dict, dry_run: bool = False) -> None:
    sender = os.environ.get("GMAIL_USER", "sender@example.com" if dry_run else "")
    password = os.environ.get("GMAIL_APP_PASSWORD", "")
    if not message.get("to"):
        raise ValueError("message has no recipients")
    mail = build(message, sender)
    if dry_run:
        return
    if not sender or not password:
        raise RuntimeError("GMAIL_USER / GMAIL_APP_PASSWORD not set")
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ssl.create_default_context()) as smtp:
        smtp.login(sender, password)
        smtp.send_message(mail)  # To + Cc 모두에게 전달
