#!/usr/bin/env python3
"""posts.json -> 블로그 원고 메일 payload JSON.

posts.json 은 정책별 블로그 원고의 구조화 데이터다(schema/posts.schema.json).
이 스크립트가 필수 항목·2중 검토·공식 링크·금지어·검색 최적화 규칙(WRITING_GUIDE.md)을 검사한 뒤,
같은 구조에서 블로그 본문(HTML)과 마크다운을 만들어 한 통의 메일로 묶는다.

payload 형식은 benefit-radar 와 같다(첨부 attachments 는 선택):
  {"schema_version": "1.0", "messages": [{"to": [...], "cc": [...], "subject", "text", "html",
                                            "attachments": [{"filename", "content_type", "data_b64"}]}]}

표준 라이브러리만 사용한다. 본문·주소를 표준출력에 찍지 않는다.

사용법:
  PRIVACY_DENYLIST=... python3 render_posts.py --posts posts.json --to a@example.com --out payload.json \\
      [--public-base https://raw.githubusercontent.com/OWNER/REPO/refs/heads/BRANCH/public --thumb-dir public] [--test]
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import html
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
PERSONAS_PATH = HERE.parent / "personas.json"
CONFIG_PATH = HERE.parent / "blog_config.json"
KST = dt.timezone(dt.timedelta(hours=9))
WEEKDAYS = "월화수목금토일"

OFFICIAL_SUFFIXES = (".go.kr", ".or.kr", ".re.kr", ".ac.kr", "applyhome.co.kr", "korea.kr", "korea-pass.kr", "gov.kr")
BLOCKED_HOSTS = ("naver.com", "tistory.com", "brunch.co.kr", "daum.net", "kakao.com", "youtube.com",
                 "instagram.com", "facebook.com", "namu.wiki", "blogspot.com", "medium.com")

DISCLAIMER = ("※ 이 글에 나오는 인물은 이해를 돕기 위해 만든 가상 사례입니다. 자동 정리한 판정은 참고용이며, 실제 자격과 금액은 "
              "소득·가구·거주지에 따라 달라지니 신청 전에 반드시 공고 원문과 담당 기관에서 확인하세요. (정책 정보는 {date} 기준)")
FIT_MARK = {"yes": "✅", "partial": "❔"}
FIT_TEXT = {"yes": "해당될 가능성이 커요", "partial": "조건 확인이 필요해요"}


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


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def has_batchim(word: str) -> bool | None:
    """마지막 글자가 한글이고 받침이 있으면 True, 없으면 False, 한글이 아니면 None."""
    for ch in reversed(word.strip()):
        if "가" <= ch <= "힣":
            return (ord(ch) - 0xAC00) % 28 != 0
        if ch.isalnum():
            return None
    return None


# 받침 있을 때 / 없을 때 올바른 조사 쌍
_PARTICLE_PAIRS = [("은", "는"), ("이", "가"), ("을", "를"), ("과", "와")]


def particle_warnings(name: str, text: str) -> list[str]:
    """고유명사 바로 뒤 조사가 받침과 어긋나는지 검사(경고용)."""
    out = []
    b = has_batchim(name)
    if b is None or not name:
        return out
    for with_b, without_b in _PARTICLE_PAIRS:
        wrong, right = (without_b, with_b) if b else (with_b, without_b)
        if re.search(re.escape(name) + wrong + r"(?![가-힣])", text):
            out.append(f"조사 확인: '{name}{wrong}' → '{name}{right}'")
    if b is False and re.search(re.escape(name) + r"으로(?![가-힣])", text):
        out.append(f"조사 확인: '{name}으로' → '{name}로'")
    if b is True and re.search(re.escape(name) + r"로(?![가-힣])", text) and not name.rstrip().endswith("ㄹ"):
        last = [c for c in name if "가" <= c <= "힣"][-1]
        if (ord(last) - 0xAC00) % 28 != 8:  # ㄹ 받침은 '로'가 맞다
            out.append(f"조사 확인: '{name}로' → '{name}으로'")
    return out


def lint(post: dict, cfg: dict) -> list[str]:
    """맞춤법·표기 점검(경고). 메일 위 빨간 칸에 표시한다."""
    warn: list[str] = []
    texts = list(_walk_strings({k: v for k, v in post.items() if k not in ("verification", "sources", "apply_url", "notice_url", "id")}))
    blob = "\n".join(texts)
    for wrong, right in cfg.get("typos", {}).items():
        if wrong in blob:
            warn.append(f"맞춤법 확인: '{wrong}' → '{right}'")
    for m in re.finditer(r"([가-힣A-Za-z0-9㎡]{2,})\s+\1(?![가-힣A-Za-z0-9])", blob):
        warn.append(f"같은 단어 반복: '{m.group(1)}'")
        break
    if re.search(r"\s+[,.?!]", blob):
        warn.append("문장부호 앞 공백이 있어요")
    if re.search(r"\(\s*\)", blob):
        warn.append("빈 괄호가 있어요")
    warn += particle_warnings(post.get("search_name", ""), blob)
    # 중복 제거
    seen, out = set(), []
    for w in warn:
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out


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


def all_tags(post: dict, cfg: dict) -> list[str]:
    """고정 태그 + 이번 글의 태그(중복 제거, '#' 제거). 상한은 max_tags."""
    out, seen = [], set()
    for t in list(cfg.get("fixed_tags", [])) + list(post.get("hashtags", [])):
        t = str(t).lstrip("#").strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out


def validate(doc: dict, personas: dict, denylist: list[str], cfg: dict, today: dt.date) -> None:
    errors: list[str] = []
    if doc.get("schema_version") != "1.0":
        errors.append("schema_version must be '1.0'")
    posts = doc.get("posts")
    if not isinstance(posts, list):
        raise PostsError("posts must be a list")
    if len(posts) > cfg.get("max_posts_per_mail", 3):
        errors.append(f"too many posts (max {cfg.get('max_posts_per_mail', 3)} per mail)")
    seen: set[str] = set()
    titles: set[str] = set()
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
        for f in ("policy_name", "agency", "search_name", "title", "one_liner", "intro", "outro",
                  "target_short", "support_short", "method_short"):
            if not (isinstance(p.get(f), str) and p[f].strip()):
                errors.append(f"{w}: {f} required")
        # 제목·첫 문장: 정책 고유명사로 시작, 과장 표현 금지
        sn = (p.get("search_name") or "").strip()
        if sn:
            if not (p.get("title") or "").lstrip("[( ").startswith(sn.lstrip("[( ")):
                errors.append(f"{w}: title must start with search_name")
            if not (p.get("one_liner") or "").startswith(sn):
                errors.append(f"{w}: one_liner must start with search_name")
            if not (p.get("intro") or "").startswith(sn):
                errors.append(f"{w}: intro must start with search_name")
        if len(p.get("title") or "") > cfg.get("title_max_chars", 60):
            errors.append(f"{w}: title too long (>{cfg.get('title_max_chars', 60)} chars)")
        if (p.get("title") or "") in titles:
            errors.append(f"{w}: duplicate title")
        titles.add(p.get("title") or "")
        for phrase in cfg.get("banned_phrases", []):
            if phrase in "\n".join(_walk_strings({k: v for k, v in p.items() if k not in ("verification", "sources")})):
                errors.append(f"{w}: banned phrase '{phrase}'")
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
        for j, r in enumerate(p.get("related") or []):
            if not (isinstance(r, dict) and r.get("name") and r.get("line")):
                errors.append(f"{w}.related[{j}]: name and line required")
        if len(p.get("related") or []) > 6:
            errors.append(f"{w}: related has more than 6 items")
        if not (isinstance(p.get("hashtags"), list) and len(p["hashtags"]) >= 2):
            errors.append(f"{w}: hashtags needs at least 2 post-specific tags")
        elif len(all_tags(p, cfg)) > cfg.get("max_tags", 20):
            errors.append(f"{w}: more than {cfg.get('max_tags', 20)} tags in total")
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
        # 마감일: 당일 마감·지난 마감은 뺀다(읽는 사람이 쓸 시간이 없다)
        d = p.get("deadline") or {}
        if not (d.get("end") or d.get("text")):
            errors.append(f"{w}: deadline.end or deadline.text required")
        if d.get("end"):
            end = _parse_date(d["end"])
            if end is None:
                errors.append(f"{w}: deadline.end must be YYYY-MM-DD")
            elif end <= today:
                errors.append(f"{w}: deadline is today or already past (exclude this policy)")
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


def category_for(p: dict, cfg: dict) -> str:
    first = (p.get("personas") or [{}])[0].get("persona_id")
    return cfg.get("category_map", {}).get(first, cfg.get("category_default", "정책 소식"))


def thumb_url(p: dict, today: dt.date, public_base: str | None) -> str | None:
    if not public_base:
        return None
    return f"{public_base.rstrip('/')}/{today.isoformat()}/{p['id']}/01_thumb.png"


def summary_cells(p: dict, today: dt.date) -> list[tuple[str, str]]:
    d = p.get("deadline") or {}
    end = _parse_date(d.get("end"))
    when = (f"{end.month}/{end.day}까지 (D-{(end - today).days})" if end else (d.get("text") or "공고 확인"))
    return [("대상", p["target_short"]), ("지원 내용", p["support_short"]), ("마감", when), ("신청", p["method_short"])]


def blog_markdown(p: dict, personas: dict, today: dt.date, img: str | None = None) -> str:
    out = [f"# {p['title']}", ""]
    if img:
        out += [f"![{p['search_name']} 정리]({img})", ""]
    out += [p["one_liner"], "", p["intro"], "", f"**⏰ 신청 마감: {deadline_line(p, today)}**", ""]
    cells = summary_cells(p, today)
    out += ["| " + " | ".join(k for k, _ in cells) + " |", "|" + "---|" * len(cells),
            "| " + " | ".join(v for _, v in cells) + " |", "", "## 핵심 정리", ""]
    out += [f"- {x}" for x in p["summary_lines"]]
    out += ["", "## 누가 받을 수 있나요?", ""]
    for c in p["criteria"]:
        out += [f"▪ **{c['requirement']}**", "", c["detail"], ""]
    out += ["## 이런 분들은 이렇게 달라져요", "", "_가상 인물의 사례입니다. ✅는 해당될 가능성이 큰 경우, ❔는 조건 확인이 필요한 경우예요._", ""]
    for x in p["personas"]:
        out += [f"### {FIT_MARK[x['fit']]} {_persona_name(personas, x['persona_id'])} — {FIT_TEXT[x['fit']]}", "", x["story"], "",
                f"- 예상 혜택: {x['benefit_estimate']}", ""]
    out += ["## 좋은 점", ""] + [f"- {x}" for x in p["benefits"]]
    out += ["", "## 아쉬운 점·주의할 점", ""] + [f"- {x}" for x in p["drawbacks"]]
    out += ["", "## 신청 방법", ""] + [f"{i}. {x}" for i, x in enumerate(p["how_to_apply"], 1)]
    out += ["", f"- 신청하기: {p['apply_url']}", f"- 공고 원문: {p['notice_url']}"]
    if p.get("documents"):
        out += ["", "## 준비 서류", ""] + [f"- {x}" for x in p["documents"]]
    elif p.get("documents_note"):
        out += ["", "## 준비 서류", "", p["documents_note"]]
    if p.get("related"):
        out += ["", "## 함께 확인하면 좋은 정책", ""] + [f"- {r['name']} · {r['line']}" for r in p["related"]]
    out += ["", p["outro"], "", DISCLAIMER.format(date=today.isoformat()), "", "**출처**", ""]
    out += [f"- {s}" for s in p["sources"]]
    return "\n".join(out)


def blog_html(p: dict, personas: dict, today: dt.date, img: str | None, cfg: dict) -> str:
    h = [f"<h1>{e(p['title'])}</h1>"]
    if img:
        h.append(f'<p><img src="{e(img)}" width="600" alt="{e(p["search_name"])} 정리"></p>')
    h += [f"<p><strong>{e(p['one_liner'])}</strong></p>", f"<p>{e(p['intro'])}</p>",
          f"<p><strong>⏰ 신청 마감: {e(deadline_line(p, today))}</strong></p>"]
    cells = summary_cells(p, today)
    w = 100 // len(cells)
    h.append('<table width="100%" border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse">')
    h.append("<tr>" + "".join(f'<th width="{w}%">{e(k)}</th>' for k, _ in cells) + "</tr>")
    h.append("<tr>" + "".join(f'<td width="{w}%">{e(v)}</td>' for _, v in cells) + "</tr></table>")
    h += ["<h2>핵심 정리</h2><ul>"] + [f"<li>{e(x)}</li>" for x in p["summary_lines"]] + ["</ul>", "<h2>누가 받을 수 있나요?</h2>"]
    for c in p["criteria"]:
        h += [f"<p><strong>▪ {e(c['requirement'])}</strong><br>{e(c['detail'])}</p>"]
    h += ["<h2>이런 분들은 이렇게 달라져요</h2>",
          "<p><em>가상 인물의 사례입니다. ✅는 해당될 가능성이 큰 경우, ❔는 조건 확인이 필요한 경우예요.</em></p>"]
    for x in p["personas"]:
        h += [f"<h3>{FIT_MARK[x['fit']]} {e(_persona_name(personas, x['persona_id']))} — {e(FIT_TEXT[x['fit']])}</h3>",
              f"<p>{e(x['story'])}</p>", f"<ul><li>예상 혜택: {e(x['benefit_estimate'])}</li></ul>"]
    h += ["<h2>좋은 점</h2><ul>"] + [f"<li>{e(x)}</li>" for x in p["benefits"]] + ["</ul>"]
    h += ["<h2>아쉬운 점·주의할 점</h2><ul>"] + [f"<li>{e(x)}</li>" for x in p["drawbacks"]] + ["</ul>"]
    h += ["<h2>신청 방법</h2><ol>"] + [f"<li>{e(x)}</li>" for x in p["how_to_apply"]] + ["</ol>"]
    h += [f'<p>🔗 <a href="{e(p["apply_url"])}">신청 바로가기</a> · 📄 <a href="{e(p["notice_url"])}">공고 원문</a></p>']
    if p.get("documents"):
        h += ["<h2>준비 서류</h2><ul>"] + [f"<li>{e(x)}</li>" for x in p["documents"]] + ["</ul>"]
    elif p.get("documents_note"):
        h += ["<h2>준비 서류</h2>", f"<p>{e(p['documents_note'])}</p>"]
    if p.get("related"):
        h += ["<h2>함께 확인하면 좋은 정책</h2><ul>"] + [f"<li>{e(r['name'])} · {e(r['line'])}</li>" for r in p["related"]] + ["</ul>"]
    h += [f"<p>{e(p['outro'])}</p>", f"<p><small>{e(DISCLAIMER.format(date=today.isoformat()))}</small></p>",
          "<p><strong>출처</strong></p><ul>"]
    h += [f'<li><a href="{e(s)}">{e(s)}</a></li>' for s in p["sources"]]
    h += ["</ul>", f"<p>{e(' '.join('#' + t for t in all_tags(p, cfg)))}</p>"]
    return "\n".join(h)


# ---------------------------------------------------------------- email

def _sort_key(p: dict, today: dt.date):
    left = days_left(p, today)
    return (left is None or left < 0, left if left is not None else 0)


def subject_for(posts: list, today: dt.date, test: bool = False) -> str:
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
    return ("[시험] " if test else "") + s


def _guide_box_html(n: int, total: int, p: dict, slot: str, cfg: dict, warnings: list[str], has_thumb: bool) -> str:
    tags = ", ".join(all_tags(p, cfg))
    box = ['<div style="background:#fff8c5;border:1px solid #e0c200;border-radius:8px;padding:14px;margin:12px 0">',
           f"<p><strong>📋 발행 정보 (원고 {n}/{total})</strong></p>",
           f"<p>카테고리: <strong>{e(category_for(p, cfg))}</strong></p>",
           f"<p>제목: <strong>{e(p['title'])}</strong></p>",
           f"<p>태그(쉼표 목록, 태그 입력란에 붙여넣기): <br><code>{e(tags)}</code></p>",
           f"<p>예약 발행 시각: <strong>오늘 {e(slot)}</strong> (이미 지난 시각이면 다음 시각으로, 한 번에 몰아 올리지 마세요)</p>",
           "<p>사진: 본문을 통째로 복사하면 썸네일도 같이 들어갑니다. 빠지면 첨부한 PNG를 사진 버튼으로 올려 "
           "<strong>맨 위 첫 이미지</strong>로 두세요." + ("" if has_thumb else " (이번에는 썸네일을 만들지 못했어요)") + "</p>"]
    if warnings:
        box.append('<div style="background:#ffe3e3;border:1px solid #e03131;border-radius:6px;padding:10px;margin:8px 0">'
                   "<p><strong>🔴 검증 메모 — 확인 후 발행하세요</strong></p><ul>"
                   + "".join(f"<li>{e(w)}</li>" for w in warnings) + "</ul></div>")
    else:
        box.append("<p>검증 메모: 자동 점검에서 걸린 항목이 없어요.</p>")
    box.append("<p><strong>발행 전 점검표</strong></p><p>" + "<br>".join(f"☐ {e(c)}" for c in cfg["checklist"]) + "</p></div>")
    return "\n".join(box)


def render_html(posts: list, personas: dict, today: dt.date, cfg: dict, slots: dict, warns: dict, thumbs: dict) -> str:
    order = sorted(posts, key=lambda p: _sort_key(p, today))
    parts = ['<div style="font-family:-apple-system,\'Malgun Gothic\',sans-serif;max-width:760px;margin:0 auto;line-height:1.65;color:#222">',
             f"<h2>정책 블로그 원고 ({e(today.isoformat())})</h2>",
             "<p>각 원고의 노란 상자 아래 빨간 선부터가 붙여넣을 본문입니다. 본문을 선택해 복사하면 서식이 유지되고, 마크다운 원문은 맨 아래에 있어요.</p>",
             "<ol>"]
    for p in order:
        parts.append(f"<li><strong>{e(p['title'])}</strong> — {'신규' if p['kind'] == 'new' else '변경'} · ⏰ {e(deadline_line(p, today))}</li>")
    parts.append("</ol>")
    for n, p in enumerate(order, 1):
        img = thumbs.get(p["id"], {}).get("url")
        parts += [
            '<hr style="margin:28px 0">',
            f"<h3>원고 {n}/{len(order)} · {'신규 정책' if p['kind'] == 'new' else '변경된 정책'} · {e(p['policy_name'])} ({e(p['agency'])})</h3>",
            "<p style='color:#2a6b2a'>✔ 2중 검토 완료(작성 후 자체 검토 + 독립 검토)</p>",
            _guide_box_html(n, len(order), p, slots[p["id"]], cfg, warns[p["id"]], bool(thumbs.get(p["id"]))),
            '<hr style="border:0;border-top:3px solid #e03131;margin:14px 0">',
            "<p style='color:#e03131'><strong>↓ 여기서부터 끝까지 붙여넣을 본문</strong></p>",
            blog_html(p, personas, today, img, cfg),
            '<hr style="border:0;border-top:3px solid #e03131;margin:14px 0">',
            "<p><strong>마크다운 원문 (복사용)</strong></p>",
            f'<pre style="white-space:pre-wrap;background:#f6f6f6;padding:12px;border-radius:8px;font-size:13px">{e(blog_markdown(p, personas, today, img))}</pre>',
        ]
    parts += ['<hr style="margin:28px 0">',
              "<p style='color:#666;font-size:13px'>모든 원고는 공식 출처로 2회 검토했습니다. 게시 전 마감일과 링크를 한 번 더 확인하세요. "
              "이 메일에는 가상 인물만 등장하며 실제 개인정보가 들어 있지 않습니다.</p>", "</div>"]
    return "\n".join(parts)


def render_text(posts: list, personas: dict, today: dt.date, cfg: dict, slots: dict, warns: dict, thumbs: dict) -> str:
    order = sorted(posts, key=lambda p: _sort_key(p, today))
    out = [f"정책 블로그 원고 ({today.isoformat()})", ""]
    for p in order:
        out.append(f"- {p['title']} — {'신규' if p['kind'] == 'new' else '변경'} · 마감 {deadline_line(p, today)}")
    for n, p in enumerate(order, 1):
        out += ["", "=" * 60, f"원고 {n}/{len(order)} · {p['policy_name']} ({p['agency']})", "=" * 60, "",
                f"[발행 정보] 카테고리: {category_for(p, cfg)} / 예약: 오늘 {slots[p['id']]}",
                f"제목: {p['title']}", f"태그: {', '.join(all_tags(p, cfg))}"]
        if warns[p["id"]]:
            out += ["[검증 메모]"] + [f"  ! {w}" for w in warns[p["id"]]]
        out += ["[발행 전 점검표]"] + [f"  ☐ {c}" for c in cfg["checklist"]]
        out += ["", "↓ 아래부터 본문", "", blog_markdown(p, personas, today, thumbs.get(p["id"], {}).get("url")),
                "", " ".join("#" + t for t in all_tags(p, cfg))]
    out += ["", "모든 원고는 공식 출처로 2회 검토했습니다. 게시 전 마감일과 링크를 한 번 더 확인하세요."]
    return "\n".join(out)


def collect_thumbs(posts: list, today: dt.date, public_base: str | None, thumb_dir: Path | None) -> dict:
    """공개 주소(본문용)와 첨부(PNG 파일)를 모은다. 파일이 없으면 썸네일 없이 진행한다."""
    result = {}
    if not (public_base and thumb_dir):
        return result
    for p in posts:
        f = thumb_dir / today.isoformat() / p["id"] / "01_thumb.png"
        if f.is_file():
            result[p["id"]] = {"url": thumb_url(p, today, public_base), "path": f}
    return result


def build_payload(doc: dict, to: list[str], today: dt.date, cc: list[str] | None = None,
                  denylist: list[str] | None = None, public_base: str | None = None,
                  thumb_dir: Path | None = None, test: bool = False) -> dict:
    personas = load_personas()
    cfg = load_config()
    validate(doc, personas, denylist or [], cfg, today)
    posts = doc["posts"]
    if not posts:
        raise PostsError("no posts to send")
    if not to:
        raise PostsError("at least one --to recipient required")
    order = sorted(posts, key=lambda p: _sort_key(p, today))
    slot_list = cfg["publish_slots"]
    slots = {p["id"]: slot_list[i] for i, p in enumerate(order)}
    warns = {p["id"]: lint(p, cfg) for p in posts}
    thumbs = collect_thumbs(posts, today, public_base, thumb_dir)
    attachments = []
    for n, p in enumerate(order, 1):
        t = thumbs.get(p["id"])
        if t:
            attachments.append({"filename": f"{n:02d}_thumb_{p['id']}.png", "content_type": "image/png",
                                "data_b64": base64.b64encode(t["path"].read_bytes()).decode("ascii")})
    msg = {"to": to, "cc": cc or [], "subject": subject_for(posts, today, test),
           "text": render_text(posts, personas, today, cfg, slots, warns, thumbs),
           "html": render_html(posts, personas, today, cfg, slots, warns, thumbs),
           "from_name": "정책 블로그 원고"}
    if attachments:
        msg["attachments"] = attachments
    return {"schema_version": "1.0", "messages": [msg]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--posts", required=True, type=Path)
    ap.add_argument("--to", action="append", default=[])
    ap.add_argument("--cc", action="append", default=[])
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--today", help="기준일 YYYY-MM-DD (기본: 오늘, KST)")
    ap.add_argument("--public-base", help="썸네일 공개 주소 기준(…/public). 없으면 썸네일 없이 만든다")
    ap.add_argument("--thumb-dir", type=Path, help="썸네일 PNG 가 있는 로컬 public 폴더")
    ap.add_argument("--test", action="store_true", help="제목에 [시험]을 붙인다")
    ap.add_argument("--preview-html", type=Path)
    args = ap.parse_args(argv)
    today = dt.date.fromisoformat(args.today) if args.today else dt.datetime.now(KST).date()
    denylist = [t.strip() for t in os.environ.get("PRIVACY_DENYLIST", "").split(",") if t.strip()]
    doc = json.loads(args.posts.read_text(encoding="utf-8"))
    try:
        payload = build_payload(doc, args.to, today, args.cc, denylist, args.public_base, args.thumb_dir, args.test)
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
