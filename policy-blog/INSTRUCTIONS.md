# 정책 블로그 원고 실행 지침 (Routine 세션용)

새로 나왔거나 바뀐 정부·지자체 정책을 찾아, **대표 인물 4명(가상)**의 사례를 넣은 블로그 원고를 만들어 메일로 보낸다.
수신자·암호 등 **입력값은 Routine 프롬프트로만 전달**되며 이 문서와 저장소에는 없다.
발송·암호화·실패 알림은 `benefit-radar/` 의 파이프라인(GitHub Actions)을 그대로 쓴다.

**실행 요일과 대표 인물**: 화·목 오전. 한 번에 대표 인물 **2명씩** 맡는다 — 화요일은 청년 1인 가구·신혼부부, 목요일은 영유아 양육 가구·소득이 적은 시니어(`blog_config.json` 의 `focus_by_weekday`). 렌더러는 그날 인물 밖의 인물이 원고에 들어가면 거부한다(다른 요일에 수동으로 돌릴 때는 제한 없음).

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
- 한 번에 **최대 3건**(원고 단위). **원고는 정책 하나·인물 하나당 한 편**이다. 같은 정책이 그날 인물 2명 모두에 해당하면 인물마다 따로 쓴다(제목·첫 문장·사례·강조점이 달라야 하고, 같은 글을 복사하지 않는다). 그날 인물 2명 각각에 해당하는 정책이 있으면 **각자 최소 1편**을 먼저 채우고, 남는 자리는 마감이 가까운 정책 순으로 채운다.
- **인물별 탐색 렌즈**: 새 정책은 그날 인물의 관심 분야로 찾는다. 각 인물의 `personas.json` `search_lens` 에 키워드가 있다(예: 신혼부부는 신혼 대출·청약 특공·혼인 세제에 더해 **난임·가임력 검사·임신 사전건강관리·난임 시술비** 같은 임신 준비 지원). 렌즈에 나온 분야는 빠뜨리지 말고 확인한다.
- 새 정책이 없으면 원고를 만들지 않는다. 대신 `posts.json` 을 `{"schema_version":"1.0","posts":[],"scan":{"checked":[확인한 곳들],"note":"…"}}` 로 만들어 **그대로 발행한다**: 메일 맨 위에 "오늘은 새 정책이 없어요"가 나오고(확인한 대표 인물·확인한 곳·다음 점검일 포함), 사용자는 이 메일로 새 정책 유무를 바로 알 수 있다. 썸네일·이력 변화는 없다.
- 새 정책이 있으면 `scan.focus` 는 생략해도 된다(그날 요일의 인물로 자동). 메일 맨 위에 "🆕 새 정책이 있어요: 신규 N건"이 나온다.

### 3-2. 어디서 찾나
`benefit-radar/INSTRUCTIONS.md` 4-1장의 공식 출처 표와 같다(보조금24 `gov.kr`, 복지로 `bokjiro.go.kr`, 온통청년 `youthcenter.go.kr`, 주택도시기금 `nhuf.molit.go.kr`, 청약홈 `applyhome.co.kr`, 금융위 `fsc.go.kr`, 국세청 `nts.go.kr`, 고용24 `work24.go.kr`, 보건복지부·고용노동부·교육부·여성가족부 보도자료, 정책브리핑 등).
- 페이지는 `python3 benefit-radar/scripts/fetch.py text <URL>` 로 읽는다. 막힌 사이트(`korea.kr`, `korea-pass.kr`, `gov.kr` 루트, `mohw.go.kr`, `molit.go.kr` 루트 등)는 `WebSearch` 로 새 정책 소식을 찾되, **원고에 쓰는 사실은 반드시 접속되는 공식 페이지로 확인**한다. 확인이 안 되면 그 정책은 쓰지 않는다.
- 블로그·뉴스·카페는 정책을 발견하는 용도로만 쓴다. 근거(`sources`)와 신청·공고 링크는 공식 도메인만 쓴다.

---

## 4. 대표 인물 맞추기

`policy-blog/personas.json` 의 인물(청년 1인 가구, 신혼부부, 영유아 양육 가구, 소득이 적은 시니어)을 읽고, 정책 요건을 인물의 조건과 **항목별로** 대조한다.

- 모든 핵심 요건을 충족하면 `fit: "yes"`, 한두 가지가 인물 설정만으로 확정되지 않으면 `fit: "partial"` 로 하고 `story` 에 무엇을 확인해야 하는지 쓴다.
- **원고마다 대표 인물은 정확히 1명**이다(`personas` 길이 1). 그날 인물 중 해당하지 않는 인물의 원고는 쓰지 않는다(억지로 채우지 않는다). 원고는 그 인물의 관점으로 제목·첫 문장·강조점을 정한다.
- `benefit_estimate` 는 계산 가정(기간, 금리, 소득 구간 등)을 같이 적는다. 인물에 없는 숫자를 지어내지 않는다.
- 소득 기준은 **조사 시점 연도의 공식 수치**(기준중위소득 등)를 확인해 계산하고, 계산식을 `story` 나 `criteria.detail` 에 짧게 남긴다.

---

## 5. 원고 쓰기 (`$WORK/posts.json`)

**검색 노출 규칙은 `policy-blog/WRITING_GUIDE.md` 를 따른다**(제목·첫 문장·한 줄 요약·태그·표 규칙; 렌더러가 상당 부분을 검사한다).
형식은 `policy-blog/schema/posts.schema.json`, 예시는 `policy-blog/examples/sample-posts.json`(가짜 데이터). 본문 구조(한눈에 보기 → 요건 표 → 인물 사례 → 좋은 점/아쉬운 점 → 신청 방법 → 서류 → 마무리 → 면책·출처·해시태그)는 렌더러가 만든다. 모델은 구조화된 필드를 채운다.

새 필드(모두 필수): `search_name`(정책의 짧은 고유명사), `one_liner`(정책 이름으로 시작하는 한 줄 요약: 대상·금액·마감 포함), `target_short`·`support_short`·`method_short`(요약표 칸, 각 20자 안팎). 선택: `related`(다루지 못한 관련 정책 이름 + 속성 한 줄, 최대 6), `thumb_action`(썸네일 행동 문장, 판정이 불확실하면 "확인해 보세요").

글쓰기 규칙:
- 어투는 친근한 정보 전달체(~해요). 과장·낚시 제목(“무조건”, “난리 났다”)과 광고성 표현 금지.
- **좋은 점과 아쉬운 점을 모두** 쓴다(“특별히 없음” 금지: 중복수혜 제한, 의무 유지기간, 환수, 소득 증가 시 불이익, 신청 시간 등).
- **마감일을 공고 원문에서 반드시 찾아** `deadline.end` 에 넣는다. 상시·예산 소진이면 `text` 에 그대로 쓴다.
- 공식 문서의 문장을 그대로 길게 옮기지 않고 요약한다. 금액·비율·날짜는 공식 수치 그대로.
- **제목은 `search_name` 으로 시작**하고, 그다음 검색 속성(자격·지원금·마감일·신청 방법), 날짜는 맨 뒤 괄호(예: “청년 월세 특별지원 신청 자격·지원금·마감일 총정리 (10/14)”). `one_liner` 와 `intro` 도 정책 이름으로 시작한다. 글마다 제목이 달라야 하고 과장 표현은 금지.
- **강조**: 독자가 놓치면 안 되는 숫자·날짜·핵심 요건은 `**이렇게**` 감싼다. 메일 본문에서 굵은 글씨 + 노란 음영으로 바뀐다(한 섹션에 2~3곳 이하, 문장 전체를 감싸지 않는다). `title`·`search_name` 에는 쓰지 않는다. 마감 칸(큰 글씨 + 음영), 한 줄 요약(큰 글씨), 표 왼쪽 칸(음영)은 렌더러가 자동으로 강조한다.
- `hashtags` 는 이번 글의 정책 이름·주제·월 태그 2~14개(고정 태그 6개는 자동 추가, 합계 20개 이하). 무관한 인기 키워드는 넣지 않는다.
- **마감이 오늘이거나 이미 지난 정책은 쓰지 않는다**(렌더러가 거부).
- `documents` 가 공고에 없으면 `documents_note` 에 “공고에 서류 미기재 — 문의처: …”.
- `apply_url`, `notice_url` 은 공식 도메인만. 발행 전 `python3 benefit-radar/scripts/fetch.py check <URL...>` 로 열린다는 것을 확인한다(접속 불가 사이트는 WebSearch 결과에서 공식 도메인 URL임을 확인).
- 정책 id 는 `<기관>-<제도>[-지역]-<인물코드>` kebab-case. **인물코드**는 `young`(사회초년생 청년) / `newlywed`(신혼부부) / `parenting`(영유아 양육 가구) / `senior`(시니어)이고, 렌더러가 id 끝과 대표 인물이 맞는지 검사한다.

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

썸네일은 공개 주소(저장소 `public/`)로 본문에 들어가므로 **이미지를 먼저 push 하고, 그다음 메일 파일(outbox)을 push** 한다.

```bash
export REPORT_PASSPHRASE RECIPIENTS CC PRIVACY_DENYLIST
policy-blog/scripts/publish_posts.sh "$WORK/posts.json"     # 새 원고가 없으면 "새 정책 없음" 알림 메일 파일이 만들어진다
# (형식 확인용 시험 발송: TEST_MODE=1 로 실행하면 제목에 [시험]이 붙고 이력이 남지 않는다)

# 1) 썸네일 먼저(새 정책이 없는 날은 public/ 이 비어 있어 이 단계가 필요 없다)
printf 'chore(policy-blog): thumbnails %s\n' "$(TZ=Asia/Seoul date +%F)" > "$WORK/msg1"
git add public
COMMIT_MSG_FILE="$WORK/msg1" benefit-radar/scripts/check_privacy.sh && git commit -F "$WORK/msg1" || true   # 썸네일이 없으면 커밋할 것 없음
git push -u origin "$BRANCH"
python3 benefit-radar/scripts/fetch.py check "<썸네일 공개 주소 하나>"   # ok/200 이면 메일을 보낸다(수 초 걸릴 수 있음, 재시도)

# 2) 메일 파일
printf 'chore(policy-blog): posts %s\n' "$(TZ=Asia/Seoul date +%F)" > "$WORK/msg"
git add benefit-radar/outbox benefit-radar/state
COMMIT_MSG_FILE="$WORK/msg" benefit-radar/scripts/check_privacy.sh
git commit -F "$WORK/msg"
git push -u origin "$BRANCH"      # 네트워크 오류 시 2s·4s·8s·16s 간격으로 최대 4회 재시도
rm -rf "$WORK"
```
- 커밋 메시지는 위 형식 그대로. `public/` 에는 정책 id·날짜 이름의 PNG 만 올라간다(개인정보 없음).
- push 되면 `send-benefit-report` 워크플로가 복호화해 메일을 보낸다. 가능하면 워크플로 결과(성공/실패)만 확인한다.
- 같은 정책을 같은 내용으로 다시 쓰지 않는다(이력 비교는 `publish_posts.sh` 가 한다).

---

## 8. 사용자가 검색어 통계를 알려 줄 때
블로그 통계의 유입 검색어를 받으면 `WRITING_GUIDE.md` 11장 순서대로 "고유명사 + 속성" 의 속성 단어를 모아, 이후 원고의 `one_liner`·`summary_lines`·`thumb_action`·`hashtags` 에 반영한다(저장소에는 검색어 원문을 쓰지 않고 규칙만 고친다). 유입이 0인 글은 제목에 정책 이름이 앞에 있는지부터 본다.

---

## 9. 세션 요약 (개인정보 없이)
```
이번 회차(요일·대표 인물 2명): 신규 N건 / 변경 N건 / 새 정책 없음(알림 메일 발송)
조사 한계: (막힌 도메인 등)
메일 발송 워크플로: 성공/실패/해당 없음
```
