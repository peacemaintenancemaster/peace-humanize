# peace-humanize

AI가 쓴 한글 글을 사람이 쓴 것처럼 고쳐 주는 Claude 스킬이에요. 카드뉴스랑 마케팅 블로그 글을 다듬으려고 만들었습니다.

규칙은 세 갈래예요.

- **하우스 룰**: 사람 카드뉴스 120세트와 AI 블로그 120세트를 비교해서 둘을 실제로 가르는 것만 남겼어요. 금지어, 쉼표 비율, 종결어미 배분, 요체 리듬 같은 것들이요.
- **연구 보강**: KatFish(ACL 2025) 같은 한국어 AI 글 연구에서 수치로 확인된 규칙을 더했고요. 쉼표 습관이 대표적입니다. 출처는 `research-notes.md`에 있어요.
- **AI 티 룰북**: [im-not-ai](https://github.com/epoko77-ai/im-not-ai)에서 가져온 룰북입니다. 번역투나 AI 특유의 관용구를 잡아요.

서로 부딪히면 하우스 룰이 이기는 거죠. 고친 뒤에는 측정 스크립트로 전후를 숫자로 비교하고요.

## 설치

### Claude Code · Codex · Cursor 등 (추천)

```bash
npx skills add peacemaintenancemaster/peace-humanize
```

### 직접 복사

```bash
git clone https://github.com/peacemaintenancemaster/peace-humanize.git
```

`skills/peace-humanize` 폴더를 아래 위치에 넣으면 끝입니다.

- 모든 프로젝트에서 쓰기: `~/.claude/skills/peace-humanize`
- 특정 프로젝트에서만: `<프로젝트>/.claude/skills/peace-humanize`

### claude.ai (웹·앱 채팅)

`skills/peace-humanize` 폴더를 zip으로 묶어서 설정 → 기능 → 스킬에서 업로드하세요.

## 쓰는 법

글을 붙여넣고 이렇게 말하면 됩니다.

- "이거 AI 티 없애줘" → 윤문
- "이 글 AI 같아?" → 점검만 (고치지 않음)
- "이 재료로 카드뉴스 문구 사람처럼 써줘" → 새로 쓰기

Claude Code라면 `/peace-humanize 글...`로 직접 불러도 돼요.

### 구어체 정도 고르기 (0~100)

윤문이나 새로 쓰기를 시작하면 Claude가 구어체 정도를 묻습니다. Claude Code에서는 선택 카드가 뜹니다. 원문 톤에 가장 가까운 값이 추천으로 맨 위에 와요.

| 구어체 정도 | 이런 글 | 문체 |
|---|---|---|
| 0 | 공문·보도자료·보고서 | 해라체나 합쇼체로 통일, 요체·감탄 없음 |
| 30 | 칼럼·리포트·격식 뉴스레터 | 합쇼체 중심, 질문 한두 개 |
| 50 | 블로그·카드뉴스 | 합니다체와 요체를 섞은 실측 리듬 |
| 70 | 인스타 캡션·캐주얼 뉴스레터 | 요체 중심, ~거든요·~잖아요, 축약형 |
| 100 | 반말 SNS | 반말, 감탄·도치, 존댓말 섞지 않음 |

카드에 없는 숫자(예: 85)나 "원문 유지"는 Other에 적으면 돼요. 처음부터 "구어체 70으로 바꿔줘"처럼 말하면 묻지 않고 바로 작업하죠.

## 측정 스크립트만 따로 쓰기

파이썬 3만 있으면 됩니다. 외부 패키지는 없어요.

```bash
python skills/peace-humanize/scripts/house_check.py 글.txt
```

```bash
python skills/peace-humanize/scripts/house_check.py 고친글.txt --base 원문.txt --level 70
```

항목마다 PASS/FAIL이 나옵니다. 위반이 두 종류 이상이면 "고친다"로 판정해요. `--base`를 주면 변경률과 숫자 누락까지 봅니다. `--level`을 주면 그 구어체 정도 조건으로 재고요.

종결어미 분류는 휴리스틱이라 가끔 틀리는데요. 이상한 결과가 나오면 이슈로 알려주세요.

## 구성

```
skills/peace-humanize/
├── SKILL.md                    작업 순서와 철칙
├── references/
│   ├── house-rules.md          하우스 룰 (우선)
│   ├── register-levels.md      구어체 정도 0~100 레벨 조건
│   ├── research-notes.md       한국어 연구로 더한 규칙과 출처
│   └── quick-rules.md          im-not-ai AI 티 룰북
└── scripts/
    └── house_check.py          하우스 룰 측정기
```

## 규칙 고치기

하우스 룰은 `references/house-rules.md`에 있어요. 고친 뒤 스크립트 기준도 바꿔야 하면 `house_check.py` 위쪽의 `BANNED_WORDS`, `LIMITED_WORDS`, `BANNED_PHRASES`, `HUMAN_MARKERS`를 같이 수정하세요.

## 라이선스

MIT. `references/quick-rules.md`와 SKILL.md 일부는 [epoko77-ai/im-not-ai](https://github.com/epoko77-ai/im-not-ai)(MIT)에서 가져왔습니다.
