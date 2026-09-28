#!/usr/bin/env python3
"""복호화된 payload JSON을 알림 채널로 발송한다.

사용법: python3 deliver.py payload.json [--channel email] [--dry-run] [--mask]

--mask 는 GitHub Actions 로그에서 수신자 주소를 가리도록 ::add-mask:: 명령을 먼저 출력한다.
그 외에는 개인정보(주소·제목·본문)를 절대 출력하지 않고 건수만 남긴다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from channels import CHANNELS  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("payload", type=Path)
    ap.add_argument("--channel", default="email", choices=sorted(CHANNELS))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--mask", action="store_true")
    args = ap.parse_args(argv)

    payload = json.loads(args.payload.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "1.0" or not isinstance(payload.get("messages"), list):
        print("invalid payload format", file=sys.stderr)
        return 2
    messages = payload["messages"]
    if args.mask:
        for m in messages:
            for addr in (m.get("to") or []) + (m.get("cc") or []):
                print(f"::add-mask::{addr}")
    channel = CHANNELS[args.channel]
    failed = 0
    for i, m in enumerate(messages, 1):
        try:
            channel.send(m, dry_run=args.dry_run)
            print(f"message {i}/{len(messages)}: {'built (dry-run)' if args.dry_run else 'sent'} to {len(m.get('to') or [])} + cc {len(m.get('cc') or [])} recipient(s)")
        except Exception as exc:  # 예외 메시지에 주소가 섞일 수 있어 타입만 출력
            failed += 1
            print(f"message {i}/{len(messages)}: FAILED ({type(exc).__name__})", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
