#!/usr/bin/env python3
"""알림 이력(state.json) 관리. state.json 은 복호화된 상태로만 다루고 저장소에는 암호문만 올린다.

state 형식:
{
  "schema_version": "1.0",
  "notified": {
    "<program id>": {"name", "status", "first_notified", "last_notified",
                      "deadline_end", "deadline_text", "apply_url", "fingerprint"}
  },
  "income_notice_sent_for_year": 2026 | null
}

사용법:
  state.py init  --state state.json
  state.py known --state state.json              # 알린 제도 id·이름·마감 목록(판정 시 중복 확인용)
  state.py drop  --state state.json --id <program id> [--id ...]   # 더 이상 해당되지 않는 제도를 이력·누적 목록에서 제거
  state.py merge --state state.json --report report.json [--today YYYY-MM-DD]
      → report.programs 의 is_new 를 이력 기준으로 보정하고, report.cumulative 를 채우고,
        state 를 갱신한다(두 파일 모두 덮어씀).
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
    return {"schema_version": "1.0", "notified": {}, "income_notice_sent_for_year": None}


def fingerprint(p: dict) -> str:
    """제도 핵심 조건이 바뀌었는지 감지하기 위한 해시(개인 판정값 제외)."""
    key = {
        "status": p.get("status"),
        "deadline": p.get("deadline"),
        "apply": (p.get("apply") or {}).get("url"),
        "requirements": sorted(c.get("requirement", "") for c in p.get("criteria", [])),
    }
    return hashlib.sha256(json.dumps(key, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else empty_state()


def save(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def merge(state: dict, report: dict, today: dt.date) -> tuple[dict, dict]:
    notified = state.setdefault("notified", {})
    for p in report.get("programs", []):
        prev = notified.get(p["id"])
        fp = fingerprint(p)
        p["is_new"] = prev is None
        if prev and prev.get("fingerprint") != fp and not p.get("change_note"):
            p["change_note"] = "지난 알림 이후 신청 기간·조건·신청 경로 중 일부가 바뀌었습니다. 공고 원문을 확인하세요."
        d = p.get("deadline") or {}
        notified[p["id"]] = {
            "name": p["name"],
            "status": p["status"],
            "first_notified": (prev or {}).get("first_notified") or today.isoformat(),
            "last_notified": today.isoformat(),
            "deadline_end": d.get("end"),
            "deadline_text": d.get("text"),
            "apply_url": (p.get("apply") or {}).get("url"),
            "fingerprint": fp,
        }

    cumulative = []
    for pid, n in sorted(notified.items(), key=lambda kv: kv[1].get("first_notified") or ""):
        end = n.get("deadline_end")
        if end:
            try:
                if dt.date.fromisoformat(end) < today:
                    continue  # 마감 지난 제도는 누적 목록에서 제외
            except ValueError:
                pass
        text = " / ".join(x for x in [f"~{end}" if end else None, n.get("deadline_text")] if x) or None
        cumulative.append({
            "id": pid,
            "name": n["name"],
            "status": n.get("status"),
            "deadline_text": text,
            "apply_url": n.get("apply_url"),
            "first_notified": n.get("first_notified"),
        })
    report["cumulative"] = cumulative

    ir = report.get("income_refresh") or {}
    if ir.get("required") and ir.get("send_separate_notice"):
        state["income_notice_sent_for_year"] = ir.get("target_year")
    return state, report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["init", "known", "drop", "merge"])
    ap.add_argument("--id", action="append", default=[], help="drop 대상 program id")
    ap.add_argument("--state", required=True, type=Path)
    ap.add_argument("--report", type=Path)
    ap.add_argument("--today")
    args = ap.parse_args(argv)
    today = dt.date.fromisoformat(args.today) if args.today else dt.datetime.now(KST).date()

    if args.cmd == "init":
        if args.state.exists():
            print("state already exists", file=sys.stderr)
            return 1
        save(args.state, empty_state())
        return 0
    state = load(args.state)
    if args.cmd == "known":
        for pid, n in state.get("notified", {}).items():
            print(f"{pid}\t{n.get('name')}\t{n.get('status')}\t{n.get('deadline_end') or n.get('deadline_text') or ''}")
        print(f"# income_notice_sent_for_year={state.get('income_notice_sent_for_year')}")
        return 0
    if args.cmd == "drop":
        notified = state.get("notified", {})
        removed = [i for i in args.id if notified.pop(i, None) is not None]
        save(args.state, state)
        print(f"dropped {len(removed)} of {len(args.id)} program(s)")
        return 0
    if not args.report:
        print("--report required", file=sys.stderr)
        return 2
    report = json.loads(args.report.read_text(encoding="utf-8"))
    state, report = merge(state, report, today)
    save(args.state, state)
    save(args.report, report)
    print(f"merged: {len(report.get('programs', []))} program(s), cumulative {len(report['cumulative'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
