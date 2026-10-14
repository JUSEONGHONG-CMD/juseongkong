#!/usr/bin/env python3
"""이미 원고를 쓴 정책 이력(blog-state.json). 복호화된 상태로만 다루고 저장소에는 암호문만 올린다.

state 형식:
{"schema_version": "1.0", "written": {"<policy id>": {"title", "first_written", "last_written", "fingerprint"}}}

사용법:
  blog_state.py init  --state s.json
  blog_state.py known --state s.json                       # 이미 쓴 정책 id·제목·작성일
  blog_state.py merge --state s.json --posts posts.json [--today YYYY-MM-DD]
      → 이력에 있고 핵심 내용이 그대로인 원고는 posts 에서 뺀다(중복 방지).
        이력에 있는데 핵심 내용이 바뀌었으면 kind 를 'update' 로, 없으면 'new' 로 맞춘다.
        남은 원고 수를 'remaining=N' 으로 출력한다. 이력은 남은 원고 기준으로 갱신한다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

KST = dt.timezone(dt.timedelta(hours=9))


def empty_state() -> dict:
    return {"schema_version": "1.0", "written": {}}


def fingerprint(p: dict) -> str:
    key = {
        "deadline": p.get("deadline"),
        "apply": p.get("apply_url"),
        "criteria": sorted(c.get("requirement", "") + "|" + c.get("detail", "") for c in p.get("criteria", [])),
        "benefits": sorted(p.get("benefits", [])),
    }
    return hashlib.sha256(json.dumps(key, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else empty_state()


def merge(state: dict, doc: dict, today: dt.date) -> dict:
    written = state.setdefault("written", {})
    kept = []
    for p in doc.get("posts", []):
        prev = written.get(p["id"])
        fp = fingerprint(p)
        if prev and prev.get("fingerprint") == fp:
            continue  # 같은 내용으로 이미 썼음
        p["kind"] = "update" if prev else "new"
        written[p["id"]] = {
            "title": p.get("title"),
            "first_written": (prev or {}).get("first_written") or today.isoformat(),
            "last_written": today.isoformat(),
            "fingerprint": fp,
        }
        kept.append(p)
    doc["posts"] = kept
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("init", "known", "merge"):
        sp = sub.add_parser(name)
        sp.add_argument("--state", required=True, type=Path)
        if name == "merge":
            sp.add_argument("--posts", required=True, type=Path)
            sp.add_argument("--today")
    args = ap.parse_args(argv)

    if args.cmd == "init":
        args.state.write_text(json.dumps(empty_state(), ensure_ascii=False, indent=2), encoding="utf-8")
        return 0
    state = load(args.state)
    if args.cmd == "known":
        for pid, w in sorted(state.get("written", {}).items(), key=lambda kv: kv[1].get("first_written") or ""):
            print(f"{pid}\t{w.get('title')}\t{w.get('first_written')}")
        print(f"# total={len(state.get('written', {}))}")
        return 0
    today = dt.date.fromisoformat(args.today) if args.today else dt.datetime.now(KST).date()
    doc = json.loads(args.posts.read_text(encoding="utf-8"))
    doc = merge(state, doc, today)
    args.posts.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    args.state.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"remaining={len(doc['posts'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
