#!/usr/bin/env python3
"""posts.json -> 정책별 대표 이미지(썸네일) PNG.

1080x1080. 큰 글씨 = 정책 고유명사 + 행동 문장, 위 띠 = 누구를 위한 글인지(대표 인물 종류),
아래 띠 = 지원 내용 + 마감(D-n). 목록에서 잘려도 보이게 핵심 글자는 가운데, 좌우 여백 8%.
실존 건물 사진·로고·얼굴은 쓰지 않는다. 한글 글꼴이 없으면 만들지 않는다(네모로 깨진 이미지보다 낫다).

저장 위치: <out-dir>/<날짜>/<정책 id>/01_thumb.png  (주소에는 한글을 쓰지 않는다)

사용법: python3 make_thumb.py --posts posts.json --out-dir public [--today YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
KST = dt.timezone(dt.timedelta(hours=9))
SIZE = 1080
MARGIN = int(SIZE * 0.08)
FONT_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/nanumgothic/NanumGothic-Bold.ttf"
FONT_CACHE = Path.home() / ".cache" / "policy-blog" / "NanumGothic-Bold.ttf"
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
]
COLORS = {"young_single": "#1F4FBF", "newlywed": "#C2255C", "parenting": "#D9480F", "senior": "#2B8A3E"}
DEFAULT_COLOR = "#364FC7"


def ensure_pillow():
    try:
        from PIL import Image, ImageDraw, ImageFont  # noqa: F401
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "--user", "-q", "pillow"], check=False)
    try:
        from PIL import Image, ImageDraw, ImageFont
        return Image, ImageDraw, ImageFont
    except ImportError:
        return None


def ensure_font() -> Path | None:
    for c in FONT_CANDIDATES:
        if Path(c).is_file():
            return Path(c)
    if FONT_CACHE.is_file() and FONT_CACHE.stat().st_size > 100_000:
        return FONT_CACHE
    try:
        FONT_CACHE.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(FONT_URL, timeout=30) as r:
            FONT_CACHE.write_bytes(r.read())
        return FONT_CACHE if FONT_CACHE.stat().st_size > 100_000 else None
    except Exception:
        return None


def wrap(draw, text, font, max_w):
    """띄어쓰기 단위로 줄바꿈. 한 단어가 너무 길면 그대로 둔다(자르지 않음)."""
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def fit(draw, text, font_path, ImageFont, max_w, max_lines, start, floor):
    size = start
    while size >= floor:
        font = ImageFont.truetype(str(font_path), size)
        lines = wrap(draw, text, font, max_w)
        if len(lines) <= max_lines and all(draw.textlength(l, font=font) <= max_w for l in lines):
            return font, lines
        size -= 4
    font = ImageFont.truetype(str(font_path), floor)
    lines = wrap(draw, text, font, max_w)[:max_lines]  # 띄어쓰기 단위로 앞쪽만 남김
    return font, lines


def draw_centered(draw, lines, font, y, fill, gap=1.25):
    for line in lines:
        w = draw.textlength(line, font=font)
        draw.text(((SIZE - w) / 2, y), line, font=font, fill=fill)
        y += int(font.size * gap)
    return y


def make(post: dict, personas: dict, today: dt.date, path: Path, font_path: Path, mods) -> None:
    Image, ImageDraw, ImageFont = mods
    first = (post.get("personas") or [{}])[0].get("persona_id")
    img = Image.new("RGB", (SIZE, SIZE), COLORS.get(first, DEFAULT_COLOR))
    d = ImageDraw.Draw(img)
    max_w = SIZE - 2 * MARGIN
    # 위 띠: 누구를 위한 글인지
    labels = " · ".join(personas[x["persona_id"]]["label"] for x in post["personas"] if x["persona_id"] in personas)
    d.rectangle([0, 0, SIZE, 150], fill="#00000040" if False else "#0B1B3F")
    f, lines = fit(d, labels, font_path, ImageFont, max_w, 1, 48, 30)
    draw_centered(d, lines, f, 150 // 2 - f.size // 2 - 4, "#FFFFFF")
    # 가운데: 고유명사 + 행동 문장
    f1, l1 = fit(d, post["search_name"], font_path, ImageFont, max_w, 3, 124, 56)
    action = post.get("thumb_action") or "누가 받을 수 있는지 정리했어요"
    f2, l2 = fit(d, action, font_path, ImageFont, max_w, 2, 58, 36)
    h1 = len(l1) * int(f1.size * 1.25)
    h2 = len(l2) * int(f2.size * 1.25)
    top = 150 + (SIZE - 150 - 210 - (h1 + 40 + h2)) // 2
    y = draw_centered(d, l1, f1, top, "#FFFFFF")
    draw_centered(d, l2, f2, y + 40, "#FFE066")
    # 아래 띠: 지원 내용 + 마감
    end = None
    try:
        end = dt.date.fromisoformat((post.get("deadline") or {}).get("end"))
    except (TypeError, ValueError):
        pass
    tail = f"D-{(end - today).days}" if end and (end - today).days >= 0 else ((post.get("deadline") or {}).get("text") or "")
    band = post["support_short"] + (f"  ·  {tail}" if tail else "")
    d.rectangle([0, SIZE - 210, SIZE, SIZE], fill="#0B1B3F")
    f3, l3 = fit(d, band, font_path, ImageFont, max_w, 2, 54, 34)
    draw_centered(d, l3, f3, SIZE - 210 + (210 - len(l3) * int(f3.size * 1.25)) // 2, "#FFFFFF")
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG", optimize=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--posts", required=True, type=Path)
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--today")
    args = ap.parse_args(argv)
    today = dt.date.fromisoformat(args.today) if args.today else dt.datetime.now(KST).date()
    doc = json.loads(args.posts.read_text(encoding="utf-8"))
    personas = {p["id"]: p for p in json.loads((HERE.parent / "personas.json").read_text(encoding="utf-8"))["personas"]}
    mods = ensure_pillow()
    font = ensure_font()
    if not mods or not font:
        print("make_thumb: Pillow 또는 한글 글꼴이 없어 썸네일을 만들지 않습니다(원고는 썸네일 없이 발송됩니다)", file=sys.stderr)
        return 0
    n = 0
    for post in doc["posts"]:
        make(post, personas, today, args.out_dir / today.isoformat() / post["id"] / "01_thumb.png", font, mods)
        n += 1
    print(f"thumbnails written: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
