#!/usr/bin/env python3
"""posts.json -> 블로그 원고 메일 payload JSON.

posts.json 은 정책별 블로그 원고의 구조화 데이터다(schema/posts.schema.json).
이 스크립트가 필수 항목·2중 검토·공식 링크·금지어를 검사한 뒤, 같은 구조에서 블로그 본문(HTML)과
마크다운을 만들어 한 통의 메일로 묶는다.

payload 형식은 benefit-radar 와 같다:
  {"schema_version": "1.0", "messages": [{"to": [...], "cc": [...], "subject", "text", "html"}]}

표준 라이브러리만 사용한다. 본문·주소를 표준출력에 찍지 않는다.

사용법:
  PRIVACY_DENYLIST=... python3 render_posts.py --posts posts.json --to a@example.com --out payload.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
PERSONAS_PATH = HERE.parent / "personas.json"
KST = dt.timezone(dt.timedelta(hours=9))
WEEKDAYS = "월화수목금토일"

OFFICIAL_SUFFIXES = (".go.kr", ".or.kr", ".re.kr", ".ac.kr", "applyhome.co.kr", "korea.kr", "korea-pass.kr", "gov.kr")
BLOCKED_HOSTS = ("naver.com", "tistory.com", "brunch.co.kr", "daum.net", "kakao.com", "youtube.com",
                 "instagram.com", "facebook.com", "namu.wiki", "blogspot.com", "medium.com")

DISCLAIMER = ("※ 이 글에 나오는 인물은 이해를 돕기 위해 만든 가상 사례입니다. 실제 자격과 금액은 소득·가구·거주지에 따라 달라지니, "
              "신청 전에 반드시 공고 원문과 담당 기관에서 확인하세요. (정책 정보는 {date} 기준)")


class PostsError(ValueError):
    pass


# ---------------------------------------------------------------- helpers

def e(value) -> str:
    return html.escape("" if value is None else str(value))


def _parse_date(value):
    try:
        return dt.date.fromisoformat(value) if value else None
    except ValueError:
        return None


def fmt_date(d: dt.date) -> str:
    return f"{d.month}월 {d.day}일({WEEKDAYS[d.weekday()]})"


def deadline_line(post: dict, today: dt.date) -> str:
    d = post.get("deadline") or {}
    end = _parse_date(d.get("end"))
    start = _parse_date(d.get("start"))
    parts = []
    if start and end:
        parts.append(f"{fmt_date(start)} ~ {fmt_date(end)}")
    elif end:
        parts.append(f"{fmt_date(end)}까지")
    if d.get("text"):
        parts.append(d["text"])
    if end is not None and (end - today).days >= 0:
        parts.append(f"D-{(end - today).days}")
    return " · ".join(parts) if parts else "공고 확인 필요"


def days_left(post: dict, today: dt.date):
    end = _parse_date((post.get("deadline") or {}).get("end"))
    return None if end is None else (end - today).days


def _walk_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _walk_strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _walk_strings(v)


def load_personas() -> dict:
    data = json.loads(PERSONAS_PATH.read_text(encoding="utf-8"))
    return {p["id"]: p for p in data["personas"]}


# ---------------------------------------------------------------- validation

def _check_url(errors: list, where: str, url, official_only: bool = True) -> None:
    if not (isinstance(url, str) and url.startswith("https://")):
        errors.append(f"{where}: https URL required")
        return
    host = (urlparse(url).hostname or "").lower()
    if any(host == b or host.endswith("." + b) for b in BLOCKED_HOSTS):
        errors.append(f"{where}: non-official domain {host}")
    elif official_only and not any(host == s.lstrip(".") or host.endswith(s if s.startswith(".") else "." + s)
                                   for s in OFFICIAL_SUFFIXES):
        errors.append(f"{where}: domain not in official list ({host})")


def validate(doc: dict, personas: dict, denylist: list[str]) -> None:
    errors: list[str] = []
    if doc.get("schema_version") != "1.0":
        errors.append("schema_version must be '1.0'")
    posts = doc.get("posts")
    if not isinstance(posts, list):
        raise PostsError("posts must be a list")
    seen: set[str] = set()
    for i, p in enumerate(posts):
        w = f"posts[{i}]"
        pid = p.get("id")
        if not pid:
            errors.append(f"{w}: id required")
        elif pid in seen:
            errors.append(f"{w}: duplicate id {pid}")
        else:
            seen.add(pid)
        if p.get("kind") not in ("new", "update"):
            errors.append(f"{w}: kind must be new|update")
        for f in ("policy_name", "agency", "title", "intro", "outro"):
            if not (isinstance(p.get(f), str) and p[f].strip()):
                errors.append(f"{w}: {f} required")
        sl = p.get("summary_lines")
        if not (isinstance(sl, list) and 2 <= len(sl) <= 5 and all(isinstance(x, str) and x.strip() for x in sl)):
            errors.append(f"{w}: summary_lines needs 2-5 lines")
        for f in ("criteria", "benefits", "drawbacks", "how_to_apply", "sources"):
            v = p.get(f)
            if not (isinstance(v, list) and v):
                errors.append(f"{w}: {f} must have at least 1 item")
        for j, c in enumerate(p.get("criteria") or []):
            if not (isinstance(c, dict) and c.get("requirement") and c.get("detail")):
                errors.append(f"{w}.criteria[{j}]: requirement and detail required")
        if not (isinstance(p.get("hashtags"), list) and len(p["hashtags"]) >= 3):
            errors.append(f"{w}: hashtags needs at least 3")
        if not (isinstance(p.get("documents"), list) or p.get("documents_note")):
            errors.append(f"{w}: documents or documents_note required")
        # 대표 인물
        pp = p.get("personas")
        if not (isinstance(pp, list) and pp):
            errors.append(f"{w}: personas needs at least 1 entry")
            pp = []
        for j, x in enumerate(pp):
            if x.get("persona_id") not in personas:
                errors.append(f"{w}.personas[{j}]: unknown persona_id")
            if x.get("fit") not in ("yes", "partial"):
                errors.append(f"{w}.personas[{j}]: fit must be yes|partial")
            for f in ("story", "benefit_estimate"):
                if not (isinstance(x.get(f), str) and x[f].strip()):
                    errors.append(f"{w}.personas[{j}]: {f} required")
        # 마감일
        d = p.get("deadline") or {}
        if not (d.get("end") or d.get("text")):
            errors.append(f"{w}: deadline.end or deadline.text required")
        if d.get("end") and _parse_date(d["end"]) is None:
            errors.append(f"{w}: deadline.end must be YYYY-MM-DD")
        # 링크
        _check_url(errors, f"{w}.apply_url", p.get("apply_url"))
        _check_url(errors, f"{w}.notice_url", p.get("notice_url"))
        for j, s in enumerate(p.get("sources") or []):
            _check_url(errors, f"{w}.sources[{j}]", s, official_only=False)
        # 2중 검토
        v = p.get("verification") or {}
        for key in ("pass1", "pass2"):
            r = v.get(key) or {}
            if r.get("status") != "verified":
                errors.append(f"{w}: verification.{key}.status must be 'verified'")
            if not r.get("sources_checked"):
                errors.append(f"{w}: verification.{key}.sources_checked required")
    # 금지어(두 사람의 개인정보 등): 모든 문자열 검사, 값은 출력하지 않는다
    blob = "\n".join(_walk_strings(doc)).lower()
    for n, term in enumerate(denylist, 1):
        if term and term.lower() in blob:
            errors.append(f"denylisted term #{n} found in post text")
    if errors:
        raise PostsError("posts.json invalid:\n- " + "\n- ".join(errors[:40]))


# ---------------------------------------------------------------- blog body

def _persona_name(personas: dict, pid: str) -> str:
    return personas[pid]["display_name"]


def blog_markdown(p: dict, personas: dict, today: dt.date) -> str:
    out = [f"# {p['title']}", "", p["intro"], "", "## 한눈에 보기", ""]
    out += [f"- {x}" for x in p["summary_lines"]]
    out += ["", f"> ⏰ **신청 마감: {deadline_line(p, today)}**", "", "## 누가 받을 수 있나요?", "",
            "| 요건 | 내용 |", "|---|---|"]
    out += [f"| {c['requirement']} | {c['detail']} |" for c in p["criteria"]]
    out += ["", "## 이런 분들은 이렇게 달라져요", "", "_가상 인물의 사례입니다._", ""]
    for x in p["personas"]:
        tag = "" if x["fit"] == "yes" else " (조건 확인 필요)"
        out += [f"**{_persona_name(personas, x['persona_id'])}**{tag}", "", x["story"], "",
                f"- 예상 혜택: {x['benefit_estimate']}", ""]
    out += ["## 좋은 점", ""] + [f"- {x}" for x in p["benefits"]]
    out += ["", "## 아쉬운 점·주의할 점", ""] + [f"- {x}" for x in p["drawbacks"]]
    out += ["", "## 신청 방법", ""] + [f"{i}. {x}" for i, x in enumerate(p["how_to_apply"], 1)]
    out += ["", f"- 신청하기: {p['apply_url']}", f"- 공고 원문: {p['notice_url']}"]
    if p.get("documents"):
        out += ["", "## 준비 서류", ""] + [f"- {x}" for x in p["documents"]]
    elif p.get("documents_note"):
        out += ["", "## 준비 서류", "", p["documents_note"]]
    out += ["", p["outro"], "", DISCLAIMER.format(date=today.isoformat()), "", "**출처**", ""]
    out += [f"- {s}" for s in p["sources"]]
    out += ["", " ".join(h if h.startswith("#") else "#" + h for h in p["hashtags"])]
    return "\n".join(out)


def blog_html(p: dict, personas: dict, today: dt.date) -> str:
    h = [f"<h1>{e(p['title'])}</h1>", f"<p>{e(p['intro'])}</p>", "<h2>한눈에 보기</h2>", "<ul>"]
    h += [f"<li>{e(x)}</li>" for x in p["summary_lines"]]
    h += ["</ul>",
          f"<blockquote><p>⏰ <strong>신청 마감: {e(deadline_line(p, today))}</strong></p></blockquote>",
          "<h2>누가 받을 수 있나요?</h2>",
          '<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse"><tr><th>요건</th><th>내용</th></tr>']
    h += [f"<tr><td>{e(c['requirement'])}</td><td>{e(c['detail'])}</td></tr>" for c in p["criteria"]]
    h += ["</table>", "<h2>이런 분들은 이렇게 달라져요</h2>", "<p><em>가상 인물의 사례입니다.</em></p>"]
    for x in p["personas"]:
        tag = "" if x["fit"] == "yes" else " (조건 확인 필요)"
        h += [f"<h3>{e(_persona_name(personas, x['persona_id']))}{e(tag)}</h3>", f"<p>{e(x['story'])}</p>",
              f"<ul><li>예상 혜택: {e(x['benefit_estimate'])}</li></ul>"]
    h += ["<h2>좋은 점</h2><ul>"] + [f"<li>{e(x)}</li>" for x in p["benefits"]] + ["</ul>"]
    h += ["<h2>아쉬운 점·주의할 점</h2><ul>"] + [f"<li>{e(x)}</li>" for x in p["drawbacks"]] + ["</ul>"]
    h += ["<h2>신청 방법</h2><ol>"] + [f"<li>{e(x)}</li>" for x in p["how_to_apply"]] + ["</ol>"]
    h += [f'<p>🔗 <a href="{e(p["apply_url"])}">신청 바로가기</a> · 📄 <a href="{e(p["notice_url"])}">공고 원문</a></p>']
    if p.get("documents"):
        h += ["<h2>준비 서류</h2><ul>"] + [f"<li>{e(x)}</li>" for x in p["documents"]] + ["</ul>"]
    elif p.get("documents_note"):
        h += ["<h2>준비 서류</h2>", f"<p>{e(p['documents_note'])}</p>"]
    h += [f"<p>{e(p['outro'])}</p>", f"<p><small>{e(DISCLAIMER.format(date=today.isoformat()))}</small></p>",
          "<p><strong>출처</strong></p><ul>"]
    h += [f'<li><a href="{e(s)}">{e(s)}</a></li>' for s in p["sources"]]
    h += ["</ul>", f"<p>{e(' '.join(t if t.startswith('#') else '#' + t for t in p['hashtags']))}</p>"]
    return "\n".join(h)


# ---------------------------------------------------------------- email

def _sort_key(p: dict, today: dt.date):
    left = days_left(p, today)
    return (left is None or left < 0, left if left is not None else 0)


def subject_for(posts: list, today: dt.date) -> str:
    new = sum(1 for p in posts if p["kind"] == "new")
    upd = len(posts) - new
    bits = []
    if new:
        bits.append(f"신규 {new}건")
    if upd:
        bits.append(f"변경 {upd}건")
    s = f"[정책 블로그 원고] {' · '.join(bits)}"
    dated = [(days_left(p, today), p) for p in posts if days_left(p, today) is not None and days_left(p, today) >= 0]
    if dated:
        left, p = min(dated, key=lambda x: x[0])
        end = _parse_date(p["deadline"]["end"])
        s += f" - 가장 빠른 마감 {end.month}/{end.day}(D-{left})"
    return s


def render_html(posts: list, personas: dict, today: dt.date) -> str:
    order = sorted(posts, key=lambda p: _sort_key(p, today))
    parts = ['<div style="font-family:-apple-system,\'Malgun Gothic\',sans-serif;max-width:760px;margin:0 auto;line-height:1.65;color:#222">',
             f"<h2>정책 블로그 원고 ({e(today.isoformat())})</h2>",
             "<p>아래 원고를 블로그에 붙여 넣어 쓰세요. 본문은 선택해서 복사하면 서식이 유지되고, 마크다운 원문도 함께 있습니다.</p>",
             "<ol>"]
    for p in order:
        parts.append(f"<li><strong>{e(p['title'])}</strong> — {'신규' if p['kind'] == 'new' else '변경'} · ⏰ {e(deadline_line(p, today))}</li>")
    parts.append("</ol>")
    for n, p in enumerate(order, 1):
        parts += [
            '<hr style="margin:28px 0">',
            f"<h3>원고 {n}/{len(order)} · {'신규 정책' if p['kind'] == 'new' else '변경된 정책'} · {e(p['policy_name'])} ({e(p['agency'])})</h3>",
            "<p style='color:#2a6b2a'>✔ 2중 검토 완료(작성 후 자체 검토 + 독립 검토)</p>",
            "<p><strong>블로그 본문 (복사해서 붙여넣기)</strong></p>",
            '<div style="border:1px solid #ccc;border-radius:8px;padding:16px">',
            blog_html(p, personas, today), "</div>",
            "<p><strong>마크다운 원문 (복사용)</strong></p>",
            f'<pre style="white-space:pre-wrap;background:#f6f6f6;padding:12px;border-radius:8px;font-size:13px">{e(blog_markdown(p, personas, today))}</pre>',
        ]
    parts += ['<hr style="margin:28px 0">',
              "<p style='color:#666;font-size:13px'>모든 원고는 공식 출처로 2회 검토했습니다. 게시 전 마감일과 링크를 한 번 더 확인하세요. "
              "이 메일에는 가상 인물만 등장하며 실제 개인정보가 들어 있지 않습니다.</p>", "</div>"]
    return "\n".join(parts)


def render_text(posts: list, personas: dict, today: dt.date) -> str:
    order = sorted(posts, key=lambda p: _sort_key(p, today))
    out = [f"정책 블로그 원고 ({today.isoformat()})", ""]
    for p in order:
        out.append(f"- {p['title']} — {'신규' if p['kind'] == 'new' else '변경'} · 마감 {deadline_line(p, today)}")
    for n, p in enumerate(order, 1):
        out += ["", "=" * 60, f"원고 {n}/{len(order)} · {p['policy_name']} ({p['agency']})", "=" * 60, "",
                blog_markdown(p, personas, today)]
    out += ["", "모든 원고는 공식 출처로 2회 검토했습니다. 게시 전 마감일과 링크를 한 번 더 확인하세요."]
    return "\n".join(out)


def build_payload(doc: dict, to: list[str], today: dt.date, cc: list[str] | None = None,
                  denylist: list[str] | None = None) -> dict:
    personas = load_personas()
    validate(doc, personas, denylist or [])
    posts = doc["posts"]
    if not posts:
        raise PostsError("no posts to send")
    if not to:
        raise PostsError("at least one --to recipient required")
    return {"schema_version": "1.0", "messages": [{
        "to": to, "cc": cc or [], "subject": subject_for(posts, today),
        "text": render_text(posts, personas, today), "html": render_html(posts, personas, today)}]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--posts", required=True, type=Path)
    ap.add_argument("--to", action="append", default=[])
    ap.add_argument("--cc", action="append", default=[])
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--today", help="기준일 YYYY-MM-DD (기본: 오늘, KST)")
    ap.add_argument("--preview-html", type=Path)
    args = ap.parse_args(argv)
    today = dt.date.fromisoformat(args.today) if args.today else dt.datetime.now(KST).date()
    denylist = [t.strip() for t in os.environ.get("PRIVACY_DENYLIST", "").split(",") if t.strip()]
    doc = json.loads(args.posts.read_text(encoding="utf-8"))
    try:
        payload = build_payload(doc, args.to, today, args.cc, denylist)
    except PostsError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.preview_html:
        args.preview_html.write_text(payload["messages"][0]["html"], encoding="utf-8")
    print(f"payload written: {len(doc['posts'])} post(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
