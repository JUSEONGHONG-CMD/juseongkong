# 결혼 준비 도구 모음

## 🎯 Benefit Radar — 맞춤 정부지원제도 알리미

가구(예: 결혼 준비 중인 커플)의 조건을 미리 입력해 두면, Claude가 **매주 월요일 아침** 정부·지자체 지원제도를 조사해
**자격 요건을 모두 충족하는 제도만** 골라 이메일로 보내줍니다.

메일에 담기는 내용(제도별):
- ✅ 신청 가능 / 🗓️ 혼인신고 후 가능 판정과 **요건 ↔ 우리 조건 대조표**
- 👍 신청하면 이득 / 👎 손해·주의점 (각 최소 1개)
- 📑 필요 서류(발급처 링크·유효기간·누가 떼는지), 🧾 필요 정보, 인증 수단
- 🔗 바로 신청하기 / 📄 공고 원문 (공식 사이트 링크만)
- ⏰ 마감 임박, 📂 한 번에 떼두면 좋은 공통 서류, ➕ 추가 정보 요청
- ⚠️ 매년 소득 기준이 바뀌는 달(기본 4월)부터 **연봉 재입력 요청**

### 일정·검증·실패 알림

- **발송 시각**: 매주 월요일 06:43에 조사를 시작해 **오전 7시 반 전후**에 메일이 도착합니다.
- **2중 검토**: 메일에 넣기 전에 모든 제도를 공식 출처로 두 번 확인합니다.
  1차는 작성 직후 자체 대조, 2차는 작성 과정을 모르는 독립 검토자(서브에이전트)가 처음부터 다시 확인합니다.
  두 검토를 모두 통과한 제도만 발송되고, 기록이 없으면 `render_email.py`가 발행을 거부합니다.
- **실패 알림**: 메일 발송 단계가 실패하면 즉시, 오전 9시까지 이번 주 리포트가 만들어지지 않았으면 9시에
  보내는 Gmail 계정으로 알림 메일이 옵니다(`benefit-watchdog` 워크플로, 개인정보 없음).

### 동작 구조

```
[Claude 예약 작업(Routine) · 매주 월 06:43 KST]
  비공개 프로필 → 웹 조사 → 자격 판정 → report.json → 2중 검토
  → 이메일 payload 렌더링 → AES-256 암호화 → outbox/*.enc 커밋·푸시
[GitHub Actions: send-benefit-report]
  복호화 → Gmail SMTP로 발송 (로그에는 성공/실패만)
```

### 🔒 개인정보 보호

이 저장소는 공개 저장소입니다. **개인정보는 평문으로 저장소에 절대 올라가지 않습니다.**
- 프로필·수신자·암호는 계정 비공개 영역인 **Claude Routine 설정**에만 있습니다.
- 저장소에는 암호문(`*.enc`)만 올라가고, 커밋 전 `check_privacy.sh`가 이름·이메일·전화번호 등을 검사합니다.
- Actions 로그에는 수신자·제목·본문이 출력되지 않습니다(수신자는 마스킹).
- 웹 검색어에는 이름·정확한 금액·상세 주소를 넣지 않습니다.

자세한 규칙은 [`benefit-radar/INSTRUCTIONS.md`](benefit-radar/INSTRUCTIONS.md) 0장을 보세요.

### 설정 방법

1. **Gmail 앱 비밀번호 만들기** — 보내는 Gmail 계정에 2단계 인증을 켜고, Google 계정 → 보안 → 앱 비밀번호에서 16자리 비밀번호를 만듭니다.
2. **GitHub Secrets 등록** — 저장소 Settings → Secrets and variables → Actions → New repository secret
   | 이름 | 값 |
   |---|---|
   | `GMAIL_USER` | 보내는 Gmail 주소 |
   | `GMAIL_APP_PASSWORD` | 1번의 앱 비밀번호 |
   | `REPORT_PASSPHRASE` | Claude가 알려주는 암호화 키 |
   | `ALERT_CC` (선택) | 실패 알림을 참조로 함께 받을 주소(쉼표 구분) |
3. **프로필 입력** — [`profile.example.yaml`](benefit-radar/profile.example.yaml) 항목을 Claude와의 대화로 알려주면 Routine 설정에만 저장합니다(파일로 커밋하지 않음).
4. 회사 메일이 외부 발신 메일을 스팸 처리할 수 있으니, 첫 메일이 오면 발신 주소를 안전한 발신자로 등록하세요.

### 프로필 바꾸기
Claude Code 세션에서 “연봉 갱신: 본인 ○○원, 배우자 ○○원 (○○년 귀속)”, “주소 바뀜: …”처럼 말하면 Routine 설정의 프로필만 교체합니다.

### 파일 구성

| 경로 | 역할 |
|---|---|
| `benefit-radar/INSTRUCTIONS.md` | Routine이 매주 따르는 조사·판정·발행 절차 |
| `benefit-radar/schema/profile.schema.json` | 가구 프로필 스키마(버전 관리) |
| `benefit-radar/schema/report.schema.json` | 채널 무관 결과 스키마(이메일·향후 앱 공용) |
| `benefit-radar/scripts/render_email.py` | report → 이메일 payload (필수 항목 검증 포함) |
| `benefit-radar/scripts/state.py` | 알림 이력(신규/변경 감지, 누적 목록) |
| `benefit-radar/scripts/publish.sh` | 이력 병합 → 렌더링 → 암호화 파이프라인 |
| `benefit-radar/scripts/seal.sh` / `unseal.sh` | AES-256 암호화/복호화 (키 환경변수 지정 가능) |
| `benefit-radar/scripts/deliver.py`, `channels/` | 알림 채널 어댑터(현재 이메일) |
| `benefit-radar/scripts/check_privacy.sh` | 커밋 전 개인정보 유출 검사 |
| `benefit-radar/scripts/fetch.py` | 공식 사이트 본문 읽기·링크 확인(재시도 포함) |
| `.github/workflows/send-benefit-report.yml` | 복호화 후 메일 발송(실패 시 알림) |
| `.github/workflows/benefit-watchdog.yml` | 월 09:00 KST 리포트 누락 확인·알림 |
| `benefit-radar/scripts/alert.py` | 운영 알림 메일(개인정보 없음) |
| `docs/ROADMAP.md` | 다른 사용자용 앱 확장 계획 |

### 로컬 테스트 (가짜 데이터)

```bash
W=$(mktemp -d); cp benefit-radar/examples/sample-report.json $W/report.json
python3 benefit-radar/scripts/render_email.py --report $W/report.json --to a@example.com \
  --out $W/payload.json --preview-html $W/preview.html
python3 benefit-radar/scripts/deliver.py $W/payload.json --dry-run
```

## ✍️ Policy Blog — 정책 블로그 원고 메일

새로 나왔거나 바뀐 정부·지자체 정책을 찾아, **대표 인물 4명(가상: 청년 1인 가구 / 신혼부부 / 영유아 양육 가구 / 소득이 적은 시니어)**의 사례를 넣은 블로그 원고를 메일로 보내는 프로그램입니다.

- **화·목 오전**에 새 정책·변경 정책을 확인합니다. 화요일은 청년·신혼부부, 목요일은 영유아 양육 가구·시니어 **2명씩** 맡습니다. 한 번에 최대 3건.
- **원고는 대표 인물 한 명당 한 편**이고, 그 안에 그 인물에게 해당하는 정책을 **같은 형식의 칸(최대 5개)으로 나란히 나열**합니다(한 정책만 크게 다루지 않음). 신혼부부는 청약·대출뿐 아니라 난임·가임력 검사 같은 임신 준비 지원도 함께 찾습니다.
- 메일 맨 위에 **"🆕 새 정책이 있어요"** 또는 **"오늘은 새 정책이 없어요"** 가 항상 표시됩니다(없는 날에도 확인한 곳과 다음 점검일을 알리는 짧은 메일이 옵니다).
- 원고마다 요약표, 요건, 인물별 사례(예상 혜택에 계산 가정 표기), 좋은 점·아쉬운 점, 신청 방법·링크, 서류, **마감일**, 출처, 해시태그를 넣습니다. 메일에는 노란 발행 정보 상자(카테고리·제목·태그 쉼표 목록·예약 시각·검증 메모·발행 전 점검표), 붙여넣을 블로그 본문, 마크다운 원문, 썸네일 PNG 첨부가 들어 있습니다. 자동 게시는 하지 않습니다.
- 검색 노출 규칙(`policy-blog/WRITING_GUIDE.md`)을 코드로 검사합니다: 제목·첫 문장이 정책 이름으로 시작, 과장 표현 금지, 태그 20개 이하, 당일 마감 제외, 맞춤법·조사 점검, 1080×1080 썸네일(공개 주소로 본문에 삽입, 메일보다 먼저 push).
- 공개되는 글이라 Benefit Radar 와 같은 **2중 검토**(작성자 자체 검토 + 독립 서브에이전트)를 거치고, 렌더러가 검토 미통과·비공식 링크·금지어를 거부합니다.
- 이 프로그램은 특정인의 프로필을 읽지 않으며, 원고에는 `policy-blog/personas.json` 의 가상 인물만 나옵니다. 발송은 Benefit Radar 의 암호화·GitHub Actions 파이프라인을 그대로 씁니다.

| 파일 | 역할 |
|---|---|
| `policy-blog/INSTRUCTIONS.md` | Routine 이 따르는 절차 |
| `policy-blog/WRITING_GUIDE.md` | 블로그 조회수 규칙(근거 수준 표시) |
| `policy-blog/blog_config.json` | 고정 태그·카테고리·예약 시각·금지 표현·점검표 |
| `policy-blog/personas.json` | 대표 인물 4명(가상) |
| `policy-blog/schema/posts.schema.json` | 원고 데이터 형식 |
| `policy-blog/scripts/render_posts.py` | 검증 + 블로그 본문(HTML·마크다운) + 메일 payload |
| `policy-blog/scripts/make_thumb.py` | 원고별 썸네일 PNG(`public/` 에 저장) |
| `policy-blog/scripts/blog_state.py` | 이미 쓴 정책 이력(중복·변경 감지) |
| `policy-blog/scripts/publish_posts.sh` | 이력 병합 → 렌더링 → 암호화 저장 |
| `policy-blog/examples/sample-posts.json` | 가짜 예시 데이터 |

```bash
W=$(mktemp -d); cp policy-blog/examples/sample-posts.json $W/posts.json
python3 policy-blog/scripts/make_thumb.py --posts $W/posts.json --out-dir $W/public
python3 policy-blog/scripts/render_posts.py --posts $W/posts.json --to a@example.com \
  --out $W/payload.json --preview-html $W/preview.html --thumb-dir $W/public \
  --public-base https://raw.githubusercontent.com/OWNER/REPO/refs/heads/BRANCH/public --test
python3 benefit-radar/scripts/deliver.py $W/payload.json --dry-run
```

---

© All rights reserved. 이 저장소의 코드와 문서는 저작권자의 허락 없이 복제·배포·상업적으로 이용할 수 없습니다.
