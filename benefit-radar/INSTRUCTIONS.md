# Benefit Radar 실행 지침 (Routine 세션용)

이 문서는 예약 작업(Routine)이 매주 실행될 때 Claude가 따르는 절차다.
가구 프로필·수신자·암호 등 **개인 입력값은 Routine 프롬프트로만 전달**되며, 이 문서와 저장소에는 없다.

---

## 0. 🔒 개인정보 절대 규칙 (모든 단계보다 우선)

이 저장소는 **공개(public)** 저장소다. 아래 규칙을 하나라도 어길 상황이면 작업을 멈추고 발행하지 않는다.

1. 프로필 값·이름·이메일·생년·소득·자산·주소·직장·결혼 일정을 **평문으로 저장소에 쓰지 않는다.** 파일, 파일명, 커밋 메시지, 브랜치명, 코드 주석, 로그 모두 해당.
2. 평문 작업 파일(report.json, payload, state)은 **저장소 밖 임시 폴더**(`mktemp -d`)에서만 만든다. 저장소에는 `seal.sh`로 암호화한 `.enc`만 올린다.
3. 웹 검색어·WebFetch URL에 이름, 이메일, 정확한 소득 금액, 상세 주소(동·번지), 생년월일을 넣지 않는다. 일반 조건으로만 검색한다.
   - 좋은 예: `서울 마포구 신혼부부 전세자금 이자 지원 2026`, `청년 월세 지원 소득 기준 중위소득 60%`
   - 나쁜 예: 실명, `연봉 4,200만원 29세 ○○동`
4. 결과는 이메일(암호화 → GitHub Actions 발송)로만 보낸다. GitHub 이슈·PR·코멘트·공개 Artifact·카카오톡 등 다른 곳에 결과나 프로필을 올리지 않는다.
5. 커밋 전 반드시 `PRIVACY_DENYLIST=... benefit-radar/scripts/check_privacy.sh` 를 통과해야 한다. 실패하면 커밋하지 않는다.
6. 세션 마지막 요약에도 프로필 값·수신자 주소를 적지 않는다(건수와 성공 여부만).

---

## 1. 입력 (Routine 프롬프트에 포함됨)

| 이름 | 내용 |
|---|---|
| `PROFILE` | `schema/profile.schema.json` 형식의 YAML |
| `RECIPIENTS` | 쉼표로 구분한 수신 이메일 |
| `REPORT_PASSPHRASE` | 암호화 키 (GitHub Secret 과 동일) |
| `PRIVACY_DENYLIST` | 쉼표로 구분한 금지어(실명, 실제 이메일, 상세 주소 등) |
| `BRANCH` | 발행할 브랜치 |

Bash에서 쓸 때는 `export` 로 환경변수에 넣고, 명령줄에 값을 반복해서 늘어놓지 않는다.

---

## 2. 준비

```bash
cd <저장소 루트>
git fetch origin "$BRANCH" && git checkout "$BRANCH" && git pull --ff-only origin "$BRANCH"
WORK="$(mktemp -d)"; chmod 700 "$WORK"          # 평문 작업 폴더(저장소 밖)
benefit-radar/scripts/unseal.sh benefit-radar/state/state.json.enc "$WORK/state.json" 2>/dev/null \
  && python3 benefit-radar/scripts/state.py known --state "$WORK/state.json"   # 이미 알린 제도 확인
```
state 파일이 없으면 첫 실행이다(모두 신규).

---

## 3. 연봉(소득) 재입력 판정

정부·지자체 제도는 대부분 **직전연도 확정 소득**(원천징수영수증, 소득금액증명원, 건강보험료)으로 자격을 본다.
`household.income_refresh_month`(기본 4월)부터 새 연도 소득이 공식 기준이 된다고 본다.

```
기준연도 = (오늘.월 >= income_refresh_month) ? 오늘.연도 - 1 : 오늘.연도 - 2
재입력 필요 = 어떤 구성원이라도 income.base_year 가 비었거나 기준연도보다 작음
별도 알림 메일 = 재입력 필요 AND state.income_notice_sent_for_year != 기준연도
```

- `report.income_refresh = {required, target_year: 기준연도, profile_year: 프로필의 가장 오래된 base_year, send_separate_notice}`
- 재입력 필요해도 조사는 계속하고, 소득 요건이 걸린 판정의 `note`에 "갱신 전 {profile_year}년 소득 기준"이라고 적는다.
- 매년 조사할 때 소득금액증명원·건강보험 정산 반영 시점을 공식 출처로 한 번 더 확인하고, 기본 달과 다르면 세션 요약에 "income_refresh_month 조정 필요"라고 남긴다(값은 적지 않음).

---

## 4. 조사

### 4-1. 조사 범위
프로필의 나이·거주지·혼인 상태·주거 계획·관심 분야에 맞춰 아래를 **매주 전부 훑는다.**

| 분야 | 주요 공식 출처 |
|---|---|
| 통합 검색 | 보조금24/정부24 `gov.kr`, 복지로 `bokjiro.go.kr` |
| 청년 | 온통청년 `youthcenter.go.kr`, 거주 시·도 청년포털 |
| 주거·대출 | 주택도시기금 `nhuf.molit.go.kr`(버팀목·디딤돌·신혼·신생아 특례), 마이홈 `myhome.go.kr`, 한국주택금융공사 `hf.go.kr`, LH `lh.or.kr`, SH/GH 등 지방공사 |
| 청약 | 청약홈 `applyhome.co.kr` (신혼부부·생애최초·청년 특공 요건) |
| 금융·저축 | 서민금융진흥원 `kinfa.or.kr`(청년도약계좌 등), 금융위원회 `fsc.go.kr` |
| 세금 | 국세청 `nts.go.kr`, 홈택스 `hometax.go.kr` (결혼 세액공제, 혼인 증여재산공제, 월세 세액공제, 연말정산) |
| 고용 | 고용24 `work24.go.kr`, 중소기업 재직자 제도(중소벤처기업부 `mss.go.kr`) |
| 결혼·출산 | 보건복지부 `mohw.go.kr`, 저출산고령사회위원회, 지자체 결혼·임신 준비 지원(예비부부 건강검진 등) |
| 지자체 | 거주 시·도 / 시·군·구 누리집 공지·고시공고, 희망 신혼집 지역 지자체 |

- 새 제도뿐 아니라 **이미 알린 제도의 변경(기간 연장, 요건 완화, 마감)**도 확인한다.
- 올해·다음 해 **제도 개편 발표**(예산안, 세법개정안)는 확정 전이면 `notes`에 "발표 단계"로만 적는다.
- **페이지 읽기**: `WebFetch` 도구는 환경 허용 목록과 별개로 막힐 수 있으므로 기본은 세션 네트워크를 쓰는
  `python3 benefit-radar/scripts/fetch.py text <URL>` 로 공고 본문을 읽는다(재시도 포함). 안 되면 `WebFetch`, 그래도 안 되면
  `WebSearch` 결과(제목·스니펫·URL)로 판단하고, 접속 실패 도메인을 `search_limitations`에 적는다.
- 일부 정부 사이트(`gov.kr`, `myhome.go.kr` 등)는 해외 접속을 끊는 경우가 있다. 같은 제도를 다른 공식 기관 페이지
  (주관 부처, 복지로, 온통청년, 지자체)에서 확인한다.

### 4-2. 자격 판정 (핵심)
각 후보 제도마다 공식 공고에서 요건을 항목별로 뽑아 프로필과 하나씩 대조한다.

- 요건 예: 나이(만 나이, 기준일), 소득(기준중위소득 %·연소득 상한·부부합산 여부), 가구 구성, 거주지·거주기간, 무주택(세대 전원), 자산(부동산·자동차·총자산), 고용형태·회사 규모, 청약통장 가입기간·납입횟수, 혼인 기간(혼인신고일 기준 N년 이내), 중복수혜 제한, 신청 시점 조건
- 판정:
  - **모든 요건 충족** → `status: eligible` → 리포트에 포함
  - **혼인신고(또는 결혼) 후에 충족**되는 경우 → `status: after_marriage_registration`, 해당 요건 `met: after_marriage_registration`
  - **하나라도 불충족** → **리포트에서 제외** (이름도 적지 않는다)
  - **정보 부족으로 판정 불가** → 제도는 제외하고, `needs_more_info`에 "어떤 정보를 주면 몇 건을 더 판정할 수 있는지"만 적는다
- 기준중위소득·소득 상한은 **조사 시점 연도의 공식 수치**를 확인해서 쓴다(매년 1월 갱신). 계산식은 `criteria[].note`에 짧게 남긴다.
- 커플 제도는 부부합산 소득·자산, 개인 제도는 각 구성원 기준. 구성원별로 따로 해당되면 `criteria`에 누구 기준인지 적는다.
- 확신이 없으면 포함하지 않는다. 추측으로 채우지 않는다.
- **주민등록지와 실거주지가 다르면** 둘 다 대조한다. "거주" 요건이 있는 제도는 주민등록과 실거주를 모두 충족해야 포함한다.
  실거주와 다른 곳에 주소를 두거나 옮기라는 권유(위장전입)는 절대 하지 않는다. 실거주지로 전입하면 생기는 유불리는 `notes`에 적는다.
- 이전에 알렸지만 조건 변화로 더 이상 해당되지 않는 제도는 `state.py drop --id <id>`로 이력에서 빼고, 이유를 `notes`에 한 줄로 적는다.

### 4-3. 제도별 필수 항목 (하나라도 없으면 리포트에 넣지 않는다)
`render_email.py`가 아래 규칙을 검사하고, 어기면 발행이 실패한다.

1. **요건 대조표** `criteria` — 요건 ↔ 우리 조건 ↔ 판정
2. **👍 이득** `benefits` 최소 1개 — 가능하면 금액 환산 (예: "연 이자 약 ○○만 원 절감(대출 1억·금리차 1.5%p 가정)")
3. **👎 손해·주의점** `drawbacks` 최소 1개 — "특별히 없음" 금지. 중복수혜 제한, 의무 유지·거주 기간, 중도해지 불이익, 청약 특공 기회 소진, 혼인신고 시점 제약, 소득 증가 시 환수, 대출 한도 영향(DSR), 신청 소요 시간·방문 필요 등 **우리 상황에서 실제로 따져야 할 것**
4. **🔗 바로 신청하기** `apply.url` — 실제 신청 페이지. 은행 창구 신청이면 취급 은행 안내 페이지. 방문 신청이면 `apply.method`·`apply.offline_place`에 어디서인지
5. **📄 공고 원문** `notice_url`
6. **📑 필요 서류** `documents` — 서류명, 발급처와 발급 링크, 온라인 발급 여부, 유효기간, 누가 떼는지(`who`: 구성원 label). 공고에 없으면 `documents_note`에 "공고에 서류 미기재 — 문의처: …"
7. **📅 신청 마감일** `deadline` — 공고 원문에서 **마감일을 반드시 찾아** `deadline.end`(YYYY-MM-DD)에 넣는다. 메일에서 가장 크게 강조된다(D-day, 7일 이내 빨강·30일 이내 주황).
   접수 시작일이 있으면 `deadline.start`. 상시·예산 소진 시 마감·"혼인신고일부터 1년 이내"처럼 날짜가 없으면 `end: null`로 두고 `deadline.text`에 그대로 적는다.
   연말정산처럼 회사 일정에 따르는 제도는 `text`에 "○○년 1월 회사 연말정산 기간(회사 공지 확인)"처럼 실제로 챙겨야 할 시점을 적는다.
8. **🧾 필요 정보** `required_info` — 신청서에 입력할 정보(계좌, 회사 정보, 임대차계약 내용, 청약통장 번호 등). 인증 수단은 `auth_required`

링크 규칙:
- 공식 도메인만: `*.go.kr`, 공공기관 `*.or.kr`, 지자체, 취급 금융기관, `applyhome.co.kr` 등. 블로그·뉴스·카페 링크는 쓰지 않는다.
- 발행 전 모든 신청·공고 링크를 `python3 benefit-radar/scripts/fetch.py check <URL...>` 로 확인한다.
  `ok`/`redirect`이고 `fetch.py text`로 연 내용이 해당 제도 페이지가 맞으면 `apply.verified: fetched`.
  접속이 끊기는 사이트면 WebSearch 결과에서 공식 도메인 URL로 확인됐을 때만 `search_result`. 둘 다 아니면 그 제도는 제외한다.

공통 서류: 여러 제도에 쓰이는 서류(주민등록등본, 가족관계증명서, 소득금액증명원, 건강보험 자격득실확인서, 원천징수영수증 등)는 `common_documents`에 모으고 `used_by`에 제도 id를 적는다.

`notes`: 혼인신고 시점에 따른 유불리(예: 신혼부부 특공·대출의 혼인 기간 요건, 부부합산 소득 전환 시 탈락 가능성)처럼 판단에 도움 되는 메모.

### 4-4. 제도 id
사용자와 무관한 안정적인 kebab-case: `<기관>-<제도>[-<지역>]` (예: `hug-beotimmok-newlywed`, `seoul-youth-monthly-rent`). 같은 제도는 매주 같은 id를 쓴다(이력·변경 감지 기준).

---

## 5. report.json 작성
`$WORK/report.json`에 `schema/report.schema.json` 형식으로 쓴다. 예시는 `examples/sample-report.json`(가짜 데이터).
- `member_labels`: 프로필 `members[].label` 그대로
- `programs`: 이번 주 판정을 통과한 **모든** 제도(신규 + 계속 유효한 기존 제도). `is_new`·`cumulative`는 `state.py merge`가 채운다.
- 해당 제도가 0건이어도 리포트는 발행한다("이번 주 새 제도 없음" 메일).

---

## 6. 발행

```bash
export REPORT_PASSPHRASE RECIPIENTS PRIVACY_DENYLIST
benefit-radar/scripts/publish.sh "$WORK/report.json"        # outbox/<날짜>.json.enc, state/state.json.enc 생성
git add benefit-radar/outbox benefit-radar/state
printf 'chore(benefit-radar): weekly report %s\n' "$(TZ=Asia/Seoul date +%F)" > "$WORK/msg"
COMMIT_MSG_FILE="$WORK/msg" benefit-radar/scripts/check_privacy.sh    # 실패 시 중단
git commit -F "$WORK/msg"
git push -u origin "$BRANCH"     # 네트워크 오류 시 2s·4s·8s·16s 간격으로 최대 4회 재시도
rm -rf "$WORK"
```

- 커밋 메시지는 위 형식 그대로. 이름·건수 외 내용 금지.
- push 되면 GitHub Actions `send-benefit-report` 워크플로가 복호화해 메일을 보낸다.
- 가능하면 GitHub 도구로 워크플로 실행 결과(성공/실패)만 확인한다. 실패 로그에도 개인정보가 없어야 정상이다.

---

## 7. 세션 요약 (개인정보 없이)
```
이번 주 발행: 신규 N건 / 유지 N건 / 혼인신고 후 N건, 연봉 재입력 알림: 예/아니오
조사 한계: (막힌 도메인 등)
메일 발송 워크플로: 성공/실패/확인 불가
```

---

## 8. 사용자가 프로필 갱신을 요청할 때 ("연봉 갱신: …", "주소 바뀜: …")
1. `list_triggers`로 이 Routine을 찾고 `get_trigger`로 현재 프롬프트를 읽는다.
2. 프롬프트 안 `PROFILE` 블록의 해당 값만 바꾸고(연봉이면 `income.annual_gross_krw`와 `income.base_year` 함께), 나머지는 그대로 둔 채 `update_trigger`의 `prompt`로 교체한다.
3. 저장소에는 아무것도 커밋하지 않는다. 사용자에게 "갱신 완료"만 알린다.
