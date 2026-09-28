#!/usr/bin/env python3
"""운영 알림(리포트 실패 등)을 보내는 Gmail 계정 자신에게 보낸다.

사용법: alert.py --subject "제목" --body "본문" [--link URL] [--dry-run]

개인정보는 넣지 않는다(실패 사실과 GitHub Actions 링크만). 받는사람은 GMAIL_USER,
참조는 환경변수 ALERT_CC(쉼표 구분, 선택 — GitHub Secret 으로 넣는다).
"""
from __future__ import annotations

import argparse
import html
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from channels import CHANNELS  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--subject", required=True)
    ap.add_argument("--body", required=True)
    ap.add_argument("--link")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    to = os.environ.get("GMAIL_USER") or ("owner@example.com" if args.dry_run else "")
    if not to:
        print("GMAIL_USER not set", file=sys.stderr)
        return 2
    text = args.body + (f"\n\n자세히 보기: {args.link}" if args.link else "")
    body_html = "<br>".join(html.escape(line) for line in args.body.splitlines())
    link_html = f'<p><a href="{html.escape(args.link)}">GitHub Actions 실행 기록 보기</a></p>' if args.link else ""
    message = {
        "to": [to],
        "cc": [a.strip() for a in os.environ.get("ALERT_CC", "").split(",") if a.strip()],
        "subject": f"[지원제도 알리미] {args.subject}",
        "text": text,
        "html": f'<div style="font-family:sans-serif;line-height:1.6"><p>{body_html}</p>{link_html}</div>',
    }
    try:
        CHANNELS["email"].send(message, dry_run=args.dry_run)
    except Exception as exc:  # 주소가 섞일 수 있어 타입만 출력
        print(f"alert: FAILED ({type(exc).__name__})", file=sys.stderr)
        return 1
    print("alert: built (dry-run)" if args.dry_run else "alert: sent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
