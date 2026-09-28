#!/usr/bin/env python3
"""report.json(schema/report.schema.json) -> 발송용 payload JSON.

payload 형식: {"schema_version": "1.0", "messages": [{"to": [...], "subject": str, "text": str, "html": str}]}

표준 라이브러리만 사용한다. 개인정보가 담긴 내용을 표준출력에 찍지 않는다.

사용법:
  python3 render_email.py --report report.json --to a@example.com --to b@example.com --out payload.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import sys
from pathlib import Path

CLOSING_SOON_DAYS = 14
KST = dt.timezone(dt.timedelta(hours=9))

STATUS_LABEL = {
    "eligible": "✅ 신청 가능",
    "after_marriage_registration": "🗓️ 혼인신고 후 가능",
}
VERIFIED_LABEL = {
    "fetched": "링크 확인됨",
    "search_result": "검색 결과로 확인",
    "unverified": "링크 미확인",
}


class ReportError(ValueError):
    pass


# ---------------------------------------------------------------- validation

def _is_url(value) -> bool:
    return isinstance(value, str) and value.startswith(("https://", "http://"))


def validate(report: dict) -> None:
    """리포트 필수 규칙을 검사한다. 위반 시 ReportError (메시지에 개인정보 없음)."""
    errors: list[str] = []
    if report.get("schema_version") != "1.0":
        errors.append("schema_version must be '1.0'")
    if not report.get("member_labels"):
        errors.append("member_labels is required")
    programs = report.get("programs")
    if not isinstance(programs, list):
        errors.append("programs must be a list")
        programs = []
    seen: set[str] = set()
    for i, p in enumerate(programs):
        where = f"programs[{i}]"
        pid = p.get("id")
        if not pid:
            errors.append(f"{where}: id required")
        elif pid in seen:
            errors.append(f"{where}: duplicate id")
        seen.add(pid)
        for key in ("name", "agency", "summary"):
            if not p.get(key):
                errors.append(f"{where}: {key} required")
        if p.get("status") not in STATUS_LABEL:
            errors.append(f"{where}: status must be eligible|after_marriage_registration")
        if not p.get("criteria"):
            errors.append(f"{where}: criteria (요건 대조표) required")
        for c in p.get("criteria") or []:
            if c.get("met") not in ("yes", "after_marriage_registration"):
                errors.append(f"{where}: 불충족 요건이 있는 제도는 리포트에 넣을 수 없음")
                break
        if not p.get("benefits"):
            errors.append(f"{where}: benefits(이득) 최소 1개 필요")
        if not p.get("drawbacks"):
            errors.append(f"{where}: drawbacks(손해·주의점) 최소 1개 필요")
        if not _is_url((p.get("apply") or {}).get("url")):
            errors.append(f"{where}: apply.url(바로 신청하기) 필요")
        if not _is_url(p.get("notice_url")):
            errors.append(f"{where}: notice_url(공고 원문) 필요")
        if not p.get("documents") and not p.get("documents_note"):
            errors.append(f"{where}: documents 또는 documents_note 필요")
        if not p.get("required_info"):
            errors.append(f"{where}: required_info(필요 정보) 필요")
    if errors:
        raise ReportError("report validation failed:\n  - " + "\n  - ".join(errors))


# ---------------------------------------------------------------- helpers

def e(value) -> str:
    return html.escape("" if value is None else str(value))


def _parse_date(value):
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


def days_left(program: dict, today: dt.date):
    end = _parse_date((program.get("deadline") or {}).get("end"))
    return None if end is None else (end - today).days


def deadline_text(program: dict, today: dt.date) -> str:
    d = program.get("deadline") or {}
    parts = []
    if d.get("start") or d.get("end"):
        parts.append(f"{d.get('start') or ''} ~ {d.get('end') or ''}".strip())
    if d.get("text"):
        parts.append(d["text"])
    left = days_left(program, today)
    if left is not None and left >= 0:
        parts.append(f"D-{left}")
    return " / ".join(parts) if parts else "공고 확인 필요"


WEEKDAYS = "월화수목금토일"


def fmt_date(d: dt.date) -> str:
    return f"{d.isoformat()}({WEEKDAYS[d.weekday()]})"


def deadline_info(program: dict, today: dt.date) -> dict:
    """마감 강조 표시용 정보: label(표시 문구), dday, level(urgent|soon|normal|open|closed)."""
    d = program.get("deadline") or {}
    end = _parse_date(d.get("end"))
    note = d.get("text")
    if end is None:
        return {"label": note or "상시 (마감일 없음)", "dday": None, "level": "open", "end": None}
    left = (end - today).days
    if left < 0:
        return {"label": f"{fmt_date(end)} 마감됨", "dday": None, "level": "closed", "end": end}
    level = "urgent" if left <= 7 else "soon" if left <= 30 else "normal"
    dday = "D-DAY" if left == 0 else f"D-{left}"
    label = fmt_date(end) + (f" · {note}" if note else "")
    return {"label": label, "dday": dday, "level": level, "end": end}


DEADLINE_STYLE = {
    "urgent": ("#fee2e2", "#b91c1c", "#dc2626"),
    "soon": ("#ffedd5", "#9a3412", "#ea580c"),
    "normal": ("#dbeafe", "#1e3a8a", "#2563eb"),
    "open": ("#f3f4f6", "#374151", "#9ca3af"),
    "closed": ("#f3f4f6", "#6b7280", "#9ca3af"),
}


def _deadline_banner_html(p: dict, today: dt.date) -> str:
    info = deadline_info(p, today)
    bg, fg, border = DEADLINE_STYLE[info["level"]]
    dday = (f'<span style="background:{border};color:#fff;border-radius:6px;padding:2px 10px;margin-left:8px;'
            f'font-size:16px">{e(info["dday"])}</span>') if info["dday"] else ""
    start = (p.get("deadline") or {}).get("start")
    start_html = f'<div style="font-size:12px;margin-top:2px">접수 시작: {e(start)}</div>' if start else ""
    return (f'<div style="background:{bg};color:{fg};border-left:6px solid {border};border-radius:8px;'
            f'padding:10px 12px;margin:8px 0 10px">'
            f'<div style="font-size:12px;font-weight:700;letter-spacing:.5px">📅 신청 마감</div>'
            f'<div style="font-size:19px;font-weight:800;margin-top:2px">{e(info["label"])}{dday}</div>'
            f'{start_html}</div>')


def _deadline_sort_key(p: dict):
    end = _parse_date((p.get("deadline") or {}).get("end"))
    return (end is None, end or dt.date.max, p.get("name", ""))


def _deadline_overview_html(programs: list, today: dt.date) -> str:
    if not programs:
        return ""
    rows = []
    for p in sorted(programs, key=_deadline_sort_key):
        info = deadline_info(p, today)
        if info["level"] == "closed":
            continue
        _, fg, border = DEADLINE_STYLE[info["level"]]
        dday = f'<b style="color:{border}">{e(info["dday"])}</b>' if info["dday"] else '<span style="color:#6b7280">상시</span>'
        rows.append(
            f"<tr><td style='padding:6px 8px;border-bottom:1px solid #f3f4f6'>{_link(p['apply']['url'], p['name'])}</td>"
            f"<td style='padding:6px 8px;border-bottom:1px solid #f3f4f6;color:{fg};font-weight:700'>{e(info['label'])}</td>"
            f"<td style='padding:6px 8px;border-bottom:1px solid #f3f4f6;white-space:nowrap'>{dday}</td></tr>"
        )
    if not rows:
        return ""
    return (f'<div style="{H2}">📅 신청 마감 일정 한눈에</div><div style="{CARD}">'
            '<table style="border-collapse:collapse;width:100%;font-size:14px">'
            '<tr style="background:#f9fafb"><th style="text-align:left;padding:6px 8px">제도</th>'
            '<th style="text-align:left;padding:6px 8px">마감일</th><th style="text-align:left;padding:6px 8px">남은 기간</th></tr>'
            + "".join(rows) + "</table></div>")


def _link(url, label) -> str:
    if not _is_url(url):
        return e(label)
    return f'<a href="{e(url)}" style="color:#1a56db">{e(label)}</a>'


def _doc_line_html(doc: dict) -> str:
    bits = [f"<b>{e(doc.get('name'))}</b>"]
    issuer = doc.get("issuer")
    if issuer:
        bits.append(f"발급처: {_link(doc.get('url'), issuer)}")
    if doc.get("online") is not None:
        bits.append("온라인 발급 가능" if doc["online"] else "방문 발급")
    if doc.get("validity"):
        bits.append(f"유효기간: {e(doc['validity'])}")
    if doc.get("who"):
        bits.append(f"발급 대상: {e(', '.join(doc['who']))}")
    return "☐ " + " · ".join(bits)


def _doc_line_text(doc: dict) -> str:
    bits = [doc.get("name", "")]
    if doc.get("issuer"):
        bits.append(f"발급처 {doc['issuer']}" + (f" ({doc['url']})" if doc.get("url") else ""))
    if doc.get("online") is not None:
        bits.append("온라인 발급 가능" if doc["online"] else "방문 발급")
    if doc.get("validity"):
        bits.append(f"유효기간 {doc['validity']}")
    if doc.get("who"):
        bits.append(f"발급 대상 {', '.join(doc['who'])}")
    return "[ ] " + " · ".join(bits)


# ---------------------------------------------------------------- html

CARD = "border:1px solid #e5e7eb;border-radius:10px;padding:16px;margin:14px 0;background:#ffffff"
H2 = "font-size:18px;margin:28px 0 8px;color:#111827"
MUTED = "color:#6b7280;font-size:13px"


def _program_html(p: dict, today: dt.date) -> str:
    apply = p.get("apply") or {}
    rows = "".join(
        f"<tr><td style='padding:4px 8px;border-bottom:1px solid #f3f4f6'>{e(c.get('requirement'))}</td>"
        f"<td style='padding:4px 8px;border-bottom:1px solid #f3f4f6'>{e(c.get('household_value'))}</td>"
        f"<td style='padding:4px 8px;border-bottom:1px solid #f3f4f6'>{'충족' if c.get('met') == 'yes' else '혼인신고 후 충족'}"
        f"{(' — ' + e(c['note'])) if c.get('note') else ''}</td></tr>"
        for c in p.get("criteria", [])
    )
    docs = "".join(f"<li style='list-style:none'>{_doc_line_html(d)}</li>" for d in p.get("documents") or [])
    if not docs and p.get("documents_note"):
        docs = f"<li style='list-style:none'>{e(p['documents_note'])}</li>"
    info = "".join(f"<li style='list-style:none'>☐ {e(x)}</li>" for x in p.get("required_info") or [])
    benefits = "".join(f"<li>{e(x)}</li>" for x in p["benefits"])
    drawbacks = "".join(f"<li>{e(x)}</li>" for x in p["drawbacks"])
    method = apply.get("method")
    offline = apply.get("offline_place")
    verified = VERIFIED_LABEL.get(apply.get("verified") or "", "")
    badges = [STATUS_LABEL[p["status"]]]
    if p.get("is_new"):
        badges.append("🆕 신규")
    if p.get("change_note"):
        badges.append("🔄 변경")
    return f"""
<div style="{CARD}">
  <div style="{MUTED}">{e(' · '.join(badges))} · {e(p.get('agency'))}{(' · ' + e(p['region_scope'])) if p.get('region_scope') else ''}</div>
  <div style="font-size:17px;font-weight:700;margin:4px 0 6px">{e(p['name'])}</div>
  {_deadline_banner_html(p, today)}
  <div>{e(p['summary'])}</div>
  {f"<div style='margin-top:6px;color:#b45309'>변경 사항: {e(p['change_note'])}</div>" if p.get('change_note') else ''}
  <div style="margin-top:12px"><b>왜 우리에게 해당되나요?</b></div>
  <table style="border-collapse:collapse;width:100%;font-size:13px;margin-top:4px">
    <tr style="background:#f9fafb"><th style="text-align:left;padding:4px 8px">요건</th><th style="text-align:left;padding:4px 8px">우리 조건</th><th style="text-align:left;padding:4px 8px">판정</th></tr>
    {rows}
  </table>
  <div style="margin-top:12px"><b>👍 신청하면 이득</b><ul style="margin:4px 0">{benefits}</ul></div>
  <div><b>👎 손해·주의점</b><ul style="margin:4px 0">{drawbacks}</ul></div>
  <div style="margin-top:8px"><b>📑 필요 서류</b><ul style="margin:4px 0;padding-left:4px">{docs}</ul></div>
  <div><b>🧾 필요 정보</b><ul style="margin:4px 0;padding-left:4px">{info}</ul>
  {f"<div style='{MUTED}'>인증: {e(p['auth_required'])}</div>" if p.get('auth_required') else ''}</div>
  <div style="margin-top:12px">
    <a href="{e(apply['url'])}" style="display:inline-block;background:#1a56db;color:#fff;padding:8px 14px;border-radius:6px;text-decoration:none;margin-right:6px">🔗 바로 신청하기</a>
    <a href="{e(p['notice_url'])}" style="display:inline-block;border:1px solid #1a56db;color:#1a56db;padding:7px 13px;border-radius:6px;text-decoration:none">📄 공고 원문</a>
  </div>
  <div style="{MUTED};margin-top:6px">{e(' · '.join(x for x in [method, ('방문처: ' + offline) if offline else None, verified, ('문의: ' + p['contact']) if p.get('contact') else None] if x))}</div>
</div>"""


def _income_banner_html(report: dict) -> str:
    ir = report.get("income_refresh") or {}
    if not ir.get("required"):
        return ""
    labels = "·".join(report.get("member_labels", []))
    return f"""
<div style="border:2px solid #dc2626;background:#fef2f2;border-radius:10px;padding:14px;margin:12px 0">
  <div style="font-weight:700;color:#b91c1c">⚠️ 연봉 재입력 필요: {e(labels)} 모두 {e(ir.get('target_year'))}년 확정 연봉을 새로 알려주세요</div>
  <div style="margin-top:6px;font-size:14px">현재 판정은 {e(ir.get('profile_year') or '이전')}년 소득 기준(갱신 전)입니다. {INCOME_HOWTO_HTML}</div>
</div>"""


INCOME_HOWTO_HTML = (
    "확인 방법: 회사 <b>근로소득 원천징수영수증</b>의 총급여, "
    '<a href="https://www.hometax.go.kr">홈택스</a> 또는 '
    '<a href="https://www.gov.kr">정부24</a>의 <b>소득금액증명원</b>, '
    '<a href="https://www.nhis.or.kr">국민건강보험공단</a> <b>보험료 납부확인서</b>. '
    "갱신 방법: Claude Code 세션에서 “연봉 갱신: 본인 ○○원, 배우자 ○○원 (○○년 귀속)”이라고 말하면 "
    "예약 작업(Routine)의 프로필이 교체됩니다."
)
INCOME_HOWTO_TEXT = (
    "확인 방법: 근로소득 원천징수영수증 총급여, 홈택스(https://www.hometax.go.kr) 또는 "
    "정부24(https://www.gov.kr) 소득금액증명원, 국민건강보험공단(https://www.nhis.or.kr) 보험료 납부확인서.\n"
    "갱신 방법: Claude Code 세션에서 \"연봉 갱신: 본인 ○○원, 배우자 ○○원 (○○년 귀속)\"이라고 말하면 "
    "예약 작업(Routine)의 프로필이 교체됩니다."
)


def render_html(report: dict, today: dt.date) -> str:
    programs = report.get("programs", [])
    new_eligible = [p for p in programs if p["status"] == "eligible" and (p.get("is_new") or p.get("change_note"))]
    closing = [p for p in programs if (d := days_left(p, today)) is not None and 0 <= d <= CLOSING_SOON_DAYS]
    after_reg = [p for p in programs if p["status"] == "after_marriage_registration"]
    shown = {id(p) for p in new_eligible}
    other_eligible = [p for p in programs if p["status"] == "eligible" and id(p) not in shown]

    out = [
        '<div style="font-family:-apple-system,BlinkMacSystemFont,\'Apple SD Gothic Neo\',\'Malgun Gothic\',sans-serif;'
        'max-width:720px;margin:0 auto;color:#111827;line-height:1.55;background:#f9fafb;padding:16px">',
        f'<div style="font-size:22px;font-weight:800">맞춤 지원제도 주간 리포트</div>',
        f'<div style="{MUTED}">{e(today.isoformat())} 기준 · 대상: {e(" · ".join(report.get("member_labels", [])))}</div>',
        _income_banner_html(report),
    ]

    out.append(_deadline_overview_html(programs, today))

    common = report.get("common_documents") or []
    if common:
        out.append(f'<div style="{H2}">📂 이번 주 한 번에 떼두면 좋은 서류</div><div style="{CARD}"><ul style="margin:0;padding-left:4px">')
        out += [f"<li style='list-style:none'>{_doc_line_html(d)}</li>" for d in common]
        out.append("</ul></div>")

    out.append(f'<div style="{H2}">✅ 이번 주 새로 찾은 신청 가능 제도 ({len(new_eligible)}건)</div>')
    if new_eligible:
        out += [_program_html(p, today) for p in new_eligible]
    else:
        out.append(f'<div style="{CARD}">이번 주에 새로 찾은 신청 가능 제도는 없습니다.</div>')

    if closing:
        out.append(f'<div style="{H2}">⏰ 마감 임박 ({CLOSING_SOON_DAYS}일 이내)</div><div style="{CARD}"><ul style="margin:0">')
        out += [
            f"<li>{e(p['name'])} — {e(deadline_text(p, today))} · {_link(p['apply']['url'], '바로 신청하기')}</li>"
            for p in closing
        ]
        out.append("</ul></div>")

    if other_eligible:
        out.append(f'<div style="{H2}">📌 계속 신청 가능한 제도</div>')
        out += [_program_html(p, today) for p in other_eligible]

    if after_reg:
        out.append(f'<div style="{H2}">🗓️ 혼인신고 후 가능</div>')
        out += [_program_html(p, today) for p in after_reg]

    notes = report.get("notes") or []
    if notes:
        out.append(f'<div style="{H2}">📝 참고 메모</div><div style="{CARD}"><ul style="margin:0">')
        out += [f"<li>{e(n)}</li>" for n in notes]
        out.append("</ul></div>")

    cumulative = report.get("cumulative") or []
    if cumulative:
        out.append(f'<div style="{H2}">📚 지금까지 알린 제도 ({len(cumulative)}건)</div><div style="{CARD}"><ul style="margin:0">')
        out += [
            f"<li>{STATUS_LABEL.get(c.get('status'), '')} {_link(c.get('apply_url'), c['name'])}"
            f"{(' — ' + e(c['deadline_text'])) if c.get('deadline_text') else ''}</li>"
            for c in cumulative
        ]
        out.append("</ul></div>")

    more = report.get("needs_more_info") or []
    if more:
        out.append(f'<div style="{H2}">➕ 정보를 추가하면 더 찾아드릴 수 있어요</div><div style="{CARD}"><ul style="margin:0">')
        out += [
            f"<li><b>{e(m['field'])}</b>: {e(m['reason'])}"
            f"{(' (' + str(m['unlocks_count']) + '건 추가 판정 가능)') if m.get('unlocks_count') else ''}</li>"
            for m in more
        ]
        out.append("</ul></div>")

    limits = report.get("search_limitations") or []
    if limits:
        out.append(f'<div style="{MUTED};margin-top:16px">이번 조사의 한계: {e(" / ".join(limits))}</div>')

    out.append(
        f'<div style="{MUTED};margin-top:20px">이 메일은 Benefit Radar가 공식 공고를 바탕으로 자동 작성했습니다. '
        "최종 자격은 반드시 공고 원문과 담당 기관에서 확인하세요.</div></div>"
    )
    return "\n".join(x for x in out if x)


# ---------------------------------------------------------------- text

def _program_text(p: dict, today: dt.date) -> str:
    lines = [
        f"■ {p['name']} ({STATUS_LABEL[p['status']]}{', 신규' if p.get('is_new') else ''}) - {p.get('agency', '')}",
        f"  {p['summary']}",
    ]
    if p.get("change_note"):
        lines.append(f"  변경 사항: {p['change_note']}")
    info = deadline_info(p, today)
    lines.insert(1, f"  ★ 신청 마감: {info['label']}" + (f" ({info['dday']})" if info["dday"] else "") + " ★")
    lines.append("  왜 해당되나요?")
    lines += [
        f"   - {c['requirement']} → {c['household_value']} ({'충족' if c['met'] == 'yes' else '혼인신고 후 충족'})"
        for c in p["criteria"]
    ]
    lines.append("  이득:")
    lines += [f"   + {x}" for x in p["benefits"]]
    lines.append("  손해·주의점:")
    lines += [f"   - {x}" for x in p["drawbacks"]]
    lines.append("  필요 서류:")
    lines += [f"   {_doc_line_text(d)}" for d in p.get("documents") or []]
    if not p.get("documents") and p.get("documents_note"):
        lines.append(f"   {p['documents_note']}")
    lines.append("  필요 정보:")
    lines += [f"   [ ] {x}" for x in p["required_info"]]
    if p.get("auth_required"):
        lines.append(f"  인증: {p['auth_required']}")
    lines.append(f"  바로 신청하기: {p['apply']['url']}")
    lines.append(f"  공고 원문: {p['notice_url']}")
    if p.get("contact"):
        lines.append(f"  문의: {p['contact']}")
    return "\n".join(lines)


def render_text(report: dict, today: dt.date) -> str:
    programs = report.get("programs", [])
    out = [f"맞춤 지원제도 주간 리포트 ({today.isoformat()})", ""]
    ir = report.get("income_refresh") or {}
    if ir.get("required"):
        out += [
            f"⚠️ 연봉 재입력 필요: {'·'.join(report.get('member_labels', []))} 모두 {ir.get('target_year')}년 확정 연봉을 새로 알려주세요.",
            INCOME_HOWTO_TEXT,
            "",
        ]
    if programs:
        out.append("[신청 마감 일정]")
        for p in sorted(programs, key=_deadline_sort_key):
            info = deadline_info(p, today)
            if info["level"] != "closed":
                out.append(f"- {p['name']}: {info['label']}" + (f" ({info['dday']})" if info["dday"] else ""))
        out.append("")
    common = report.get("common_documents") or []
    if common:
        out.append("[이번 주 한 번에 떼두면 좋은 서류]")
        out += [_doc_line_text(d) for d in common]
        out.append("")
    if not programs:
        out.append("이번 주에 새로 찾은 신청 가능 제도는 없습니다.")
    for p in programs:
        out += [_program_text(p, today), ""]
    for m in report.get("needs_more_info") or []:
        out.append(f"+ 정보 추가 요청: {m['field']} - {m['reason']}")
    out += ["", "최종 자격은 반드시 공고 원문과 담당 기관에서 확인하세요."]
    return "\n".join(out)


# ---------------------------------------------------------------- payload

def subject_for(report: dict, today: dt.date) -> str:
    programs = report.get("programs", [])
    new_count = sum(1 for p in programs if p.get("is_new"))
    closing = sum(1 for p in programs if (d := days_left(p, today)) is not None and 0 <= d <= CLOSING_SOON_DAYS)
    parts = [f"신규 {new_count}건"]
    if closing:
        parts.append(f"마감임박 {closing}건")
    upcoming = sorted(
        (i for i in (deadline_info(p, today) for p in programs) if i["dday"]), key=lambda i: i["end"]
    )
    if upcoming:
        parts.append(f"가장 빠른 마감 {upcoming[0]['end'].month}/{upcoming[0]['end'].day}({upcoming[0]['dday']})")
    if (report.get("income_refresh") or {}).get("required"):
        parts.append("연봉 재입력 필요")
    return f"[지원제도 알리미] {today.isoformat()} 주간 리포트 - " + ", ".join(parts)


def income_notice_message(report: dict, to: list[str], today: dt.date) -> dict:
    ir = report["income_refresh"]
    labels = "·".join(report.get("member_labels", []))
    year = ir.get("target_year")
    text = (
        f"{labels} 모두 {year}년 확정 연봉(세전 총급여)을 새로 알려주세요.\n"
        f"대부분의 정부·지자체 제도는 직전연도 확정 소득으로 자격을 판정하기 때문에, "
        f"갱신 전까지는 {ir.get('profile_year') or '이전'}년 소득 기준으로 판정됩니다.\n\n"
        + INCOME_HOWTO_TEXT
    )
    body = (
        '<div style="font-family:-apple-system,\'Apple SD Gothic Neo\',\'Malgun Gothic\',sans-serif;max-width:640px;line-height:1.6">'
        f"<h2 style='color:#b91c1c'>⚠️ {e(year)}년 연봉을 새로 입력해 주세요</h2>"
        f"<p>{e(labels)} 모두 {e(year)}년 확정 연봉(세전 총급여)을 새로 알려주세요. "
        f"대부분의 정부·지자체 제도는 직전연도 확정 소득으로 자격을 판정하기 때문에, 갱신 전까지는 "
        f"{e(ir.get('profile_year') or '이전')}년 소득 기준으로 판정됩니다.</p><p>{INCOME_HOWTO_HTML}</p></div>"
    )
    return {"to": to, "subject": f"[지원제도 알리미] {year}년 연봉 재입력 요청", "text": text, "html": body}


def build_payload(report: dict, to: list[str], today: dt.date) -> dict:
    validate(report)
    if not to:
        raise ReportError("at least one --to recipient is required")
    messages = [
        {
            "to": to,
            "subject": subject_for(report, today),
            "text": render_text(report, today),
            "html": render_html(report, today),
        }
    ]
    ir = report.get("income_refresh") or {}
    if ir.get("required") and ir.get("send_separate_notice"):
        messages.append(income_notice_message(report, to, today))
    return {"schema_version": "1.0", "messages": messages}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", required=True, type=Path)
    ap.add_argument("--to", action="append", default=[], help="수신자(여러 번 지정)")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--today", help="기준일 YYYY-MM-DD (기본: 오늘, KST)")
    ap.add_argument("--preview-html", type=Path, help="HTML 미리보기 파일도 저장(로컬 확인용, 커밋 금지)")
    args = ap.parse_args(argv)

    today = dt.date.fromisoformat(args.today) if args.today else dt.datetime.now(KST).date()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    try:
        payload = build_payload(report, args.to, today)
    except ReportError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.preview_html:
        args.preview_html.write_text(payload["messages"][0]["html"], encoding="utf-8")
    print(f"payload written: {len(payload['messages'])} message(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
