# peace-humanize

AI가 쓴 한글 글을 사람이 쓴 것처럼 고쳐 주는 Claude 스킬이에요. 카드뉴스랑 마케팅 블로그 글을 다듬으려고 만들었습니다.

규칙은 두 갈래예요.

- **하우스 룰**: 사람 카드뉴스 120세트와 AI 블로그 120세트를 비교해서 둘을 실제로 가르는 것만 남겼어요. 금지어, 쉼표 비율, 종결어미 배분, 요체 리듬 같은 것들이요.
- **AI 티 룰북**: [im-not-ai](https://github.com/epoko77-ai/im-not-ai)에서 가져온 룰북입니다. 번역투나 AI 특유의 관용구를 잡아요.

둘이 부딪히면 하우스 룰이 이기는 거죠. 고친 뒤에는 측정 스크립트로 전후를 숫자로 비교하고요.

## 설치

### Claude Code · Codex · Cursor 등 (추천)

```bash
npx skills add peacemaintenancemaster/peace-humanize
```

### 직접 복사

```bash
git clone https://github.com/peacemaintenancemaster/peace-humanize.git
```

`skills/peace-humanize` 폴더를 아래 위치에 넣으면 끝이에요.

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

## 측정 스크립트만 따로 쓰기

파이썬 3만 있으면 됩니다. 외부 패키지는 없어요.

```bash
python skills/peace-humanize/scripts/house_check.py 글.txt
```

```bash
python skills/peace-humanize/scripts/house_check.py 고친글.txt --base 원문.txt
```

항목마다 PASS/FAIL이 나옵니다. 위반이 두 종류 이상이면 "고친다"로 판정해요. `--base`를 주면 변경률과 숫자 누락까지 봅니다.

종결어미 분류는 휴리스틱이라 가끔 틀려요. 이상한 결과가 나오면 이슈로 알려주세요.

## 구성

```
skills/peace-humanize/
├── SKILL.md                    작업 순서와 철칙
├── references/
│   ├── house-rules.md          하우스 룰 (우선)
│   └── quick-rules.md          im-not-ai AI 티 룰북
└── scripts/
    └── house_check.py          하우스 룰 측정기
```

## 규칙 고치기

하우스 룰은 `references/house-rules.md`에 있어요. 고친 뒤 스크립트 기준도 바꿔야 하면 `house_check.py` 위쪽의 `BANNED_WORDS`, `LIMITED_WORDS`, `BANNED_PHRASES`, `HUMAN_MARKERS`를 같이 수정하세요.

## 라이선스

MIT. `references/quick-rules.md`와 SKILL.md 일부는 [epoko77-ai/im-not-ai](https://github.com/epoko77-ai/im-not-ai)(MIT)에서 가져왔습니다.
