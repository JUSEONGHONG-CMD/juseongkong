# 정책 블로그 원고 실행 지침 (Routine 세션용)

새로 나왔거나 바뀐 정부·지자체 정책을 찾아, **대표 인물 4명(가상)**의 사례를 넣은 블로그 원고를 만들어 메일로 보낸다.
수신자·암호 등 **입력값은 Routine 프롬프트로만 전달**되며 이 문서와 저장소에는 없다.
발송·암호화·실패 알림은 `benefit-radar/` 의 파이프라인(GitHub Actions)을 그대로 쓴다.

---

## 0. 🔒 개인정보 규칙 (모든 단계보다 우선)

이 저장소는 공개 저장소다.

1. 이 프로그램은 **특정인의 프로필을 읽지 않는다.** 원고에는 `personas.json` 의 가상 인물만 나온다.
   실제 사용자(수신자 포함)의 이름·소득·거주지·직장·가족 사정을 원고나 검색어에 쓰지 않는다.
2. 수신자 주소·암호·금지어 목록은 저장소 파일, 커밋 메시지, 로그, 세션 요약에 쓰지 않는다.
3. 평문 작업 파일(`posts.json`, payload, state)은 **저장소 밖 임시 폴더**(`mktemp -d`)에서만 만든다. 저장소에는 `.enc` 만 올린다.
4. 렌더러는 `PRIVACY_DENYLIST` 의 금지어가 원고에 있으면 발행을 거부한다. 커밋 전 `benefit-radar/scripts/check_privacy.sh` 도 반드시 통과해야 한다.
5. 웹 검색어에는 일반 조건만 넣는다(예: `2026년 청년 월세 지원 신청`).

---

## 1. 입력 (Routine 프롬프트에 포함됨)

| 이름 | 내용 |
|---|---|
| `RECIPIENTS` | 받는사람 이메일(쉼표 구분) |
| `CC` | 참조 이메일(선택) |
| `REPORT_PASSPHRASE` | 암호화 키 (GitHub Secret 과 동일) |
| `PRIVACY_DENYLIST` | 쉼표로 구분한 금지어 |
| `BRANCH` | 발행할 브랜치 |

Bash에서 쓸 때는 `export` 로 환경변수에 넣고, 명령줄에 값을 반복해서 늘어놓지 않는다.

---

## 2. 준비

```bash
cd <저장소 루트>
git fetch origin "$BRANCH" && git checkout "$BRANCH" && git pull --ff-only origin "$BRANCH"
WORK="$(mktemp -d)"; chmod 700 "$WORK"
benefit-radar/scripts/unseal.sh benefit-radar/state/blog-state.json.enc "$WORK/state.json" 2>/dev/null \
  && python3 policy-blog/scripts/blog_state.py known --state "$WORK/state.json"     # 이미 쓴 정책
```
이력 파일이 없으면 첫 실행이다(모두 신규).

---

## 3. 새 정책 찾기

### 3-1. 무엇이 "새 정책"인가
- 최근 약 **3주 안**에 발표·시행되었거나 **신청이 시작·변경**된 전국 단위 정책(지원금, 대출, 세제, 청약, 육아·보육, 노인, 교통, 청년 지원 등)
- 이미 쓴 정책이라도 **신청 기간·요건·금액·신청 경로가 바뀌면** 변경 원고(`update`)로 쓴다. 이력(`known`)과 비교한다.
- 확정되지 않은 **예산안·세법개정안은 쓰지 않는다**(국회 확정 후 시행 단계가 되면 쓴다).
- 한 번에 **최대 3건**. 대표 인물 4명 중 한 명이라도 실제로 해당될 가능성이 큰 정책, 마감이 가까운 정책을 먼저 고른다.
- 새 정책이 없으면 원고를 만들지 않고 7장 요약만 남긴다(메일·커밋 없음).

### 3-2. 어디서 찾나
`benefit-radar/INSTRUCTIONS.md` 4-1장의 공식 출처 표와 같다(보조금24 `gov.kr`, 복지로 `bokjiro.go.kr`, 온통청년 `youthcenter.go.kr`, 주택도시기금 `nhuf.molit.go.kr`, 청약홈 `applyhome.co.kr`, 금융위 `fsc.go.kr`, 국세청 `nts.go.kr`, 고용24 `work24.go.kr`, 보건복지부·고용노동부·교육부·여성가족부 보도자료, 정책브리핑 등).
- 페이지는 `python3 benefit-radar/scripts/fetch.py text <URL>` 로 읽는다. 막힌 사이트(`korea.kr`, `korea-pass.kr`, `gov.kr` 루트, `mohw.go.kr`, `molit.go.kr` 루트 등)는 `WebSearch` 로 새 정책 소식을 찾되, **원고에 쓰는 사실은 반드시 접속되는 공식 페이지로 확인**한다. 확인이 안 되면 그 정책은 쓰지 않는다.
- 블로그·뉴스·카페는 정책을 발견하는 용도로만 쓴다. 근거(`sources`)와 신청·공고 링크는 공식 도메인만 쓴다.

---

## 4. 대표 인물 맞추기

`policy-blog/personas.json` 의 인물(청년 1인 가구, 신혼부부, 영유아 양육 가구, 소득이 적은 시니어)을 읽고, 정책 요건을 인물의 조건과 **항목별로** 대조한다.

- 모든 핵심 요건을 충족하면 `fit: "yes"`, 한두 가지가 인물 설정만으로 확정되지 않으면 `fit: "partial"` 로 하고 `story` 에 무엇을 확인해야 하는지 쓴다.
- 해당하지 않는 인물은 **넣지 않는다**(억지로 4명을 채우지 않는다). 최소 1명.
- `benefit_estimate` 는 계산 가정(기간, 금리, 소득 구간 등)을 같이 적는다. 인물에 없는 숫자를 지어내지 않는다.
- 소득 기준은 **조사 시점 연도의 공식 수치**(기준중위소득 등)를 확인해 계산하고, 계산식을 `story` 나 `criteria.detail` 에 짧게 남긴다.

---

## 5. 원고 쓰기 (`$WORK/posts.json`)

형식은 `policy-blog/schema/posts.schema.json`, 예시는 `policy-blog/examples/sample-posts.json`(가짜 데이터). 본문 구조(한눈에 보기 → 요건 표 → 인물 사례 → 좋은 점/아쉬운 점 → 신청 방법 → 서류 → 마무리 → 면책·출처·해시태그)는 렌더러가 만든다. 모델은 구조화된 필드를 채운다.

글쓰기 규칙:
- 어투는 친근한 정보 전달체(~해요). 과장·낚시 제목(“무조건”, “난리 났다”)과 광고성 표현 금지.
- **좋은 점과 아쉬운 점을 모두** 쓴다(“특별히 없음” 금지: 중복수혜 제한, 의무 유지기간, 환수, 소득 증가 시 불이익, 신청 시간 등).
- **마감일을 공고 원문에서 반드시 찾아** `deadline.end` 에 넣는다. 상시·예산 소진이면 `text` 에 그대로 쓴다.
- 공식 문서의 문장을 그대로 길게 옮기지 않고 요약한다. 금액·비율·날짜는 공식 수치 그대로.
- 제목은 정책 이름과 대상이 드러나게(예: “월세 사는 청년이라면: 청년 월세 특별지원 총정리”).
- `documents` 가 공고에 없으면 `documents_note` 에 “공고에 서류 미기재 — 문의처: …”.
- `apply_url`, `notice_url` 은 공식 도메인만. 발행 전 `python3 benefit-radar/scripts/fetch.py check <URL...>` 로 열린다는 것을 확인한다(접속 불가 사이트는 WebSearch 결과에서 공식 도메인 URL임을 확인).
- 정책 id 는 `<기관>-<제도>[-지역]` kebab-case, 같은 정책은 항상 같은 id.

---

## 6. 2중 검토 (발행 전 필수)

원고는 공개되는 글이므로 **두 번, 서로 독립적으로** 공식 출처와 대조한다.

### 1차 — 작성자 자체 검증
정책마다 공고 원문을 `fetch.py text` 로 **다시 열어** 요건, 마감일, 금액과 계산, 서류, 신청 방법, 링크, 인물 사례의 결론(요건 대조가 논리적으로 맞는지)을 한 줄씩 대조한다. 고친 내용은 `verification.pass1 = {status: "verified", sources_checked: [...], fixes: [...]}`.

### 2차 — 독립 검토자(서브에이전트)
`Agent` 도구로 **general-purpose 서브에이전트**를 새로 띄워 작성 과정은 알려주지 않고 원고의 사실 주장만 준다(정책 요건, 마감, 금액, 서류, 링크, 인물 사례 계산).
지시: “각 사실 주장을 공식 출처(`*.go.kr`, 공공기관, 법령)로 처음부터 다시 확인하고 항목마다 `확인됨 / 틀림(올바른 내용+근거 URL) / 확인 불가` 로 답하라. 검색어에 개인정보를 넣지 마라. 페이지 읽기는 `python3 benefit-radar/scripts/fetch.py text <URL>` 을 먼저 써라. 블로그·뉴스 단독 근거는 ‘확인됨’으로 치지 마라.”
- 모두 `확인됨` → `pass2 = {status: "verified", sources_checked: [...], issues: []}`
- `틀림` → 고친 뒤 **고친 문장만** 새 서브에이전트로 다시 검토. 통과하면 `issues` 에 고친 내용을 남기고 `verified`
- `확인 불가` → 그 문장을 근거 있는 표현으로 바꾸거나 지우고, 정책 자체가 확인 불가면 이번에는 **쓰지 않는다**

렌더러는 `pass1`·`pass2` 가 `verified` 가 아니면 발행을 거부한다.

---

## 7. 발행

```bash
export REPORT_PASSPHRASE RECIPIENTS CC PRIVACY_DENYLIST
policy-blog/scripts/publish_posts.sh "$WORK/posts.json"     # 종료 코드 3 = 새 원고 없음(커밋·메일 없음)
git add benefit-radar/outbox benefit-radar/state
printf 'chore(policy-blog): posts %s\n' "$(TZ=Asia/Seoul date +%F)" > "$WORK/msg"
COMMIT_MSG_FILE="$WORK/msg" benefit-radar/scripts/check_privacy.sh
git commit -F "$WORK/msg"
git push -u origin "$BRANCH"      # 네트워크 오류 시 2s·4s·8s·16s 간격으로 최대 4회 재시도
rm -rf "$WORK"
```
- 커밋 메시지는 위 형식 그대로.
- push 되면 `send-benefit-report` 워크플로가 복호화해 메일을 보낸다. 가능하면 워크플로 결과(성공/실패)만 확인한다.
- 같은 정책을 같은 내용으로 다시 쓰지 않는다(이력 비교는 `publish_posts.sh` 가 한다).

---

## 8. 세션 요약 (개인정보 없이)
```
이번 회차: 신규 N건 / 변경 N건 / 새 정책 없음
조사 한계: (막힌 도메인 등)
메일 발송 워크플로: 성공/실패/해당 없음
```
