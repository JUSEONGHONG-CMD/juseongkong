#!/usr/bin/env python3
"""공식 사이트 페이지 읽기·링크 확인 (세션 네트워크 사용, curl 기반).

WebFetch 도구가 막혀 있어도 환경의 허용 도메인(Custom network access)으로 접속할 수 있다.
일부 정부 사이트는 해외 접속을 느리게 받거나 끊으므로 재시도한다.

사용법:
  fetch.py check URL [URL ...]     # URL별 상태: ok / redirect / fail (+HTTP 코드)
  fetch.py text URL [--max 20000]  # 페이지 본문을 텍스트로 추출해 출력

개인정보가 담긴 URL(쿼리에 이름·주소 등)은 절대 넣지 않는다.
"""
from __future__ import annotations

import argparse
import html
import re
import subprocess
import sys
import time

RETRIES = 3
TIMEOUT = 25
UA = "Mozilla/5.0 (compatible; BenefitRadar/1.0)"


def curl(url: str, body: bool) -> tuple[int, str, str]:
    """(http_code, final_url, body_text). 실패 시 code=0."""
    last = (0, url, "")
    for attempt in range(RETRIES):
        cmd = ["curl", "-sS", "-L", "--max-redirs", "5", "--max-time", str(TIMEOUT), "-A", UA,
               "-w", "\n__BR__%{http_code} %{url_effective}"]
        if not body:
            cmd += ["-o", "/dev/null"]
        cmd.append(url)
        proc = subprocess.run(cmd, capture_output=True)
        out = proc.stdout.decode("utf-8", errors="replace")
        marker = out.rfind("\n__BR__")
        if marker != -1:
            code_s, _, final = out[marker + 7:].partition(" ")
            code = int(code_s) if code_s.isdigit() else 0
            last = (code, final.strip() or url, out[:marker] if body else "")
            if 200 <= code < 400:
                return last
        time.sleep(2 * (attempt + 1))
    return last


def html_to_text(doc: str) -> str:
    doc = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", doc)
    doc = re.sub(r"(?i)<br\s*/?>|</(p|div|li|tr|h[1-6]|table|ul|ol)>", "\n", doc)
    doc = re.sub(r"(?i)<a\s[^>]*href=[\"']([^\"']+)[\"'][^>]*>", r" [link:\1] ", doc)
    doc = re.sub(r"<[^>]+>", " ", doc)
    doc = html.unescape(doc)
    doc = re.sub(r"[ \t\r\f\v]+", " ", doc)
    doc = re.sub(r"\n\s*\n+", "\n", doc)
    return doc.strip()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("urls", nargs="+")
    t = sub.add_parser("text")
    t.add_argument("url")
    t.add_argument("--max", type=int, default=20000)
    args = ap.parse_args(argv)

    if args.cmd == "check":
        bad = 0
        for u in args.urls:
            code, final, _ = curl(u, body=False)
            status = "ok" if 200 <= code < 300 else "redirect" if 300 <= code < 400 else "fail"
            bad += status == "fail"
            print(f"{status}\t{code}\t{u}" + (f"\t-> {final}" if final != u else ""))
        return 1 if bad else 0

    code, final, body = curl(args.url, body=True)
    if not (200 <= code < 400):
        print(f"fetch failed ({code}): {args.url}", file=sys.stderr)
        return 1
    print(f"# {final} ({code})")
    print(html_to_text(body)[: args.max])
    return 0


if __name__ == "__main__":
    sys.exit(main())
