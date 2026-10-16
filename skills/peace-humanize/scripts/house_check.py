#!/usr/bin/env python3
"""peace-humanize 자체 규칙 측정기. 표준 라이브러리만 쓴다.

사용:
  python house_check.py 글.txt
  python house_check.py 고친글.txt --base 원문.txt
  python house_check.py 고친글.txt --base 원문.txt --level 70
  python house_check.py - < 글.txt          (stdin)
  python house_check.py 글.txt --json       (기계용 출력)

--level N  구어체 정도 목표(0=단정한 합쇼체 … 100=친근한 요체, 모두 존댓말). 주면 레벨별 종결 조건과
           목표 구어체 정도(±15)를 함께 본다. 안 주면 자체 규칙(50 기준)으로 잰다.

종결어미 분류, 구어체 정도 추정, 쉼표 탐지는 휴리스틱이라 오탐이 있을 수 있다.
"""
import argparse
import difflib
import json
import re
import statistics
import sys
from collections import Counter

# ── 자체 규칙 어휘 ────────────────────────────────────────────
BANNED_WORDS = ["핵심", "다만", "단순히"]  # 0회. '및'은 단어 경계로 따로 센다
LIMITED_WORDS = ["결국", "확인", "중요"]  # 1회까지

BANNED_PHRASES = {
    "정리·결산": [r"결론적으로", r"요약하면", r"정리하자면", r"요컨대"],
    "의의 과장": [r"시사하는 바", r"주목할 만", r"매우 중요"],
    "꾸밈말": [r"흥미롭게도", r"놀랍게도", r"진정한", r"심오한"],
    "개념어": [r"패러다임", r"메커니즘", r"여정", r"중추적"],
    "상투구": [r"역할을\s*(?:한다|합니다|해요|하고|하며|했다|했습니다)",
             r"살펴보겠(?:습니다|다|어요)", r"마무리하며",
             r"(?:이)?라고\s*할\s*수\s*있(?:다|습니다|어요|죠)"],
    "기본값 이름": [r"(?<![가-힣])(?:민수|지수|철수|영희)(?=씨|는|가|이|를|의|에게|도|와|랑|\s|$|[.,!?])"],
}

HUMAN_MARKERS = [r"거죠", r"거예요", r"겁니다", r"는데요", r"죠", r"잖아요",
                 r"요즘", r"사실", r"그런데", r"이런"]

# ── 공개 연구로 더한 규칙 (references/research-notes.md) ──────────
CONNECTIVE_COMMA = re.compile(r"[가-힣](?:고|며|지만|면서|아서|어서|해서|니라|는데|다가),")
CONJ_COMMA = re.compile(
    r"(?:^|[.!?…]\s+)(그리고|그러나|그런데|하지만|그러므로|따라서|또한|즉|특히|게다가|그래서|근데|물론|아무튼),",
    re.M)
ADVERBIAL_COMMA = re.compile(r"[가-힣](?:에서는|에서|에게|으로는|으로|에는|와 함께|과 함께),")
EMPHASIS_LINKERS = ["특히", "무엇보다", "예를 들어", "또한"]  # 각 2회까지
OBJECT_HONORIFIC = re.compile(
    r"(?:품절|매진|재고|가격|사이즈|출시|배송|결제|할인|주문|사은품|이벤트|포장)\s*"
    r"(?:이십니다|이세요|되십니다|되세요|이셨|되셨)"
    r"|(?:커피|음료|메뉴|주문하신\s*[가-힣]+)\s*(?:가|이)?\s*나오셨")
SOFT_PHRASES = {
    "serves-as 직역": r"(?:로서|으로서)?\s*기능(?:한다|합니다|해요|하고|하며)",
    "지시형 도입": r"상상해\s*(?:보세요|봐)",
}
# 자체 규칙 9장: 한자어를 피하려고 끌어온 어색한 고유어
NATIVE_STRONG = re.compile(
    r"알맹이|걷어내|걷어낸|덜어내|덜어낸|털어내|짚어\s*(?:보|봤|볼)|결이\s*다르|빚어내|빚어낸"
    r"|담아내|담아낸|풀어내|풀어낸|녹여내|녹여낸|엮어내|엮어낸")
NATIVE_CONTEXT = {
    "설치": r"깔(?:려요|립니다|리면|면|아\s*주|았|고\s)",
    "표시·출력": r"찍(?:혀요|힙니다|힌다|혀\s*나)",
    "실행": r"돌려\s*(?:보|봐)|돌리면|돌려요|돌립니다",
    "검사·확인": r"봐\s*(?:줘요|줍니다|드려요|드립니다)",
    "가능": r"(?<=[가-힣])(?<![아어여해워와써봐줘가서려내타파떠껴쳐켜펴져돼])도\s*(?:돼요|됩니다)",
    "작성": r"써\s*(?:줘요|줍니다|주고)",
    "구분": r"가르는|가른다|갈라요",
    "수정": r"손보(?:고|는|면|세요|기)|손봐|손봤",
}
# 자체 규칙 12장: 트렌드로 여는 문장과 반전 공식
TREND_HOOK = re.compile(
    r"요즘\s*.{0,20}(?:없는|안\s*[가-힣]{1,3}는)\s*.{0,15}(?:찾기|보기)(?:가|는)?\s*(?:더\s*)?(?:힘|어렵)"
    r"|바야흐로|의\s*시대(?:가|입니다|예요|다)")
TURN_WORDS = re.compile(r"(?<![가-힣])(?:하지만|그러나|오히려)(?![가-힣])")
NOMINALIZATION = re.compile(r"[가-힣]{2,}(?:적(?=인|으로|이다|\s)|화(?=하|되|를|가|의|에|\s))")
TRIPLE_LIST = re.compile(
    r"[가-힣A-Za-z0-9]+(?:,\s*|·)[가-힣A-Za-z0-9]+(?:,\s*|·|,?\s*그리고\s+|\s*및\s*)[가-힣A-Za-z0-9]+")
COLLOQUIAL = re.compile(r"(?<![가-힣])(?:근데|좀|그냥|진짜|되게|완전|막|이건|그건|저건|이게|그게|뭐)(?![가-힣])")

JOSA = sorted(["은", "는", "이", "가", "을", "를", "의", "에", "에서", "으로", "로", "도", "만",
               "와", "과", "에게", "께", "부터", "까지", "처럼", "보다", "이나", "나", "랑", "이랑",
               "에는", "에서는", "으로는", "이라", "라"], key=len, reverse=True)
STOPWORDS = {"그리고", "하지만", "그런데", "이런", "그런", "저런", "우리", "저희", "지금", "정말",
             "너무", "많이", "이것", "그것", "여기", "거기", "때문", "있습니다", "합니다", "있어요",
             "해요", "있다", "한다", "했다", "없다", "같은", "이렇게", "그렇게", "어떻게", "모든",
             "가장", "다른", "이번", "오늘", "사실", "요즘", "진짜", "그냥"}

# ── 종결 유형 ───────────────────────────────────────────────
FORMAL = {"현재형 ~한다", "과거형 ~었다", "평서 ~다(이다·있다 등)", "명사형"}
HAPNIDA = {"~합니다"}  # 합쇼체 묶음 이름. 세부 유형은 HAPNIDA_SUB
HAPNIDA_SUB = {"~했습니다(과거)", "~합니다(현재)", "~입니다", "~습니까"}
YO = {"~어요", "~예요", "~는데요", "~고요", "~죠", "기타 요체", "요체 질문"}
BANMAL = {"반말 ~어", "반말 ~지", "반말 ~거든·~잖아", "반말 ~더라·~네", "반말 ~는데", "감탄·반말 질문"}
NON_POLITE = (FORMAL - {"명사형"}) | BANMAL  # 해라체·반말. 명사형 항목은 세지 않는다

# 구어체 정도는 존댓말 안에서만 잰다: 합쇼체 0, ~어요류 80, ~는데요·~죠류 100
SCORE = {"~합니다": 0, "~어요": 80, "~예요": 80, "~고요": 80,
         "~는데요": 100, "~죠": 100, "기타 요체": 100, "요체 질문": 80}

# 기준점별 조건. 기준점 사이 숫자는 가장 가까운 기준점 조건을 쓴다.
# sub=True면 합쇼체를 과거·현재·~입니다·~습니까로 나눠서 종결 배분을 잰다.
LEVELS = {
    0: dict(sub=True, max_top=0.5, min_types=2, run3=False, present_max=None, markers_min=0,
            share_rules=[("요체(질문 제외)", YO - {"요체 질문"}, "max", 0.10)]),
    50: dict(max_top=0.4, min_types=3, run3=True, present_max=3, markers_min=1,
             share_rules=[], eoyo_mono=True),
    100: dict(max_top=0.4, min_types=4, run3=True, present_max=None, markers_min=2,
              share_rules=[("요체", YO, "min", 0.7), ("합쇼체", HAPNIDA, "max", 0.2)]),
}


def group_ending(e):
    return "~합니다" if e in HAPNIDA_SUB else e


def read(path):
    if path == "-":
        return sys.stdin.buffer.read().decode("utf-8", errors="replace")
    with open(path, encoding="utf-8-sig") as f:
        return f.read()


def clean(text):
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    out, in_code = [], False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("```"):
            in_code = not in_code
            continue
        if in_code or not s or s.startswith("|"):
            continue
        s = re.sub(r"^#{1,6}\s*", "", s)
        s = re.sub(r"^(?:[-*+>]|\d+[.)])\s+", "", s)
        s = s.replace("**", "").replace("__", "")
        out.append(s)
    return "\n".join(out)


def sentences(text):
    result = []
    for line in text.split("\n"):
        line = re.sub(r"(\d)\.(\d)", "\\1\u2027\\2", line)  # 소수점 보호
        # 문장부호 뒤에 공백이나 줄 끝이 올 때만 자른다(.com, .md, "?"라고 같은 경우 보호)
        for m in re.finditer(r".+?(?:[.!?…]+[\"'”’)\]]*(?=\s|$)|$)", line):
            s = m.group(0).strip().replace("\u2027", ".")
            if re.search(r"[가-힣]", s):
                result.append(s)
    return result


def jong(ch):
    c = ord(ch) - 0xAC00
    return c % 28 if 0 <= c < 11172 else -1


def ending(s):
    tail = s.rstrip().rstrip("\"'”’)]")
    asks = tail.endswith(("?", "!"))
    t = re.sub(r"[\s\"'”’“‘)\]…~.!?,·]+$", "", s)
    if not t:
        return "명사형·기타"
    if t.endswith("니까"):
        return "~습니까"
    if t.endswith("입니다"):
        return "~입니다"
    if t.endswith("니다"):
        if t.endswith("습니다") and len(t) >= 4 and jong(t[-4]) == 20 and t[-4] not in "있겠":
            return "~했습니다(과거)"
        return "~합니다(현재)"
    if asks and t.endswith(("까요", "나요", "가요")):
        return "요체 질문"
    if t.endswith("데요"):
        return "~는데요"
    if t.endswith("고요"):
        return "~고요"
    if t.endswith(("죠", "지요")):
        return "~죠"
    if t.endswith(("예요", "에요")):
        return "~예요"
    if t.endswith(("네요", "거든요", "잖아요", "군요", "나요", "까요", "래요", "대요", "더라고요")):
        return "기타 요체"
    if t.endswith("요"):
        return "~어요"
    if asks:
        return "감탄·반말 질문"
    if t.endswith(("거든", "잖아")):
        return "반말 ~거든·~잖아"
    if t.endswith(("더라", "네", "구나", "군")):
        return "반말 ~더라·~네"
    if t.endswith("는데"):
        return "반말 ~는데"
    if t.endswith(("냐", "니", "래", "대")):
        return "감탄·반말 질문"
    if t.endswith("다") and len(t) >= 2:
        j = jong(t[-2])
        if j == 4:
            return "현재형 ~한다"
        if j == 20 and t[-2] not in "있겠":  # 있다·하겠다는 과거가 아니다
            return "과거형 ~었다"
        return "평서 ~다(이다·있다 등)"
    if t.endswith(("음", "함", "임", "됨", "기")):
        return "명사형"
    if t.endswith("지"):
        return "반말 ~지"
    if t.endswith(("어", "아", "야", "해", "게", "걸", "자", "고")):
        return "반말 ~어"
    return "명사형·기타"


SOUND_ALIAS = {"아요": "어요", "워요": "어요", "와요": "어요", "해요": "어요", "여요": "어요",
               "에요": "예요", "니까": "니다"}


def end_sound(s):
    """문장 끝 두 음절(소리 단위). 문장부호·따옴표는 뗀다."""
    t = re.sub(r"[^가-힣]+$", "", s)
    tail = t[-2:] if len(t) >= 2 else t
    return SOUND_ALIAS.get(tail, tail) or None


def count(pattern, text):
    return len(re.findall(pattern, text))


def estimate_level(endings, text, n):
    """존댓말 문장만 점수를 매긴다. 존댓말이 절반 미만이면 'non-polite'를 돌려준다."""
    polite = [SCORE[e] for e in endings if e in SCORE]
    rude = [e for e in endings if e in NON_POLITE]
    if not polite and not rude:
        return None
    if len(polite) < (len(polite) + len(rude)) / 2:
        return "non-polite"
    base = statistics.mean(polite)
    bump = min(10, 20 * len(COLLOQUIAL.findall(text)) / n)
    return round(min(100, base + bump))


def nearest_level(n):
    return min(LEVELS, key=lambda k: abs(k - n))


LINKERS = re.compile(r"^(?:그래서|그러니|그러니까|그런데|하지만|그러나|또|게다가|왜냐하면|예를 들어|이|그|이런|그런|이렇게|그렇게|이때|그때|이건|그건)(?![가-힣])")
VERBISH = re.compile(r"(?:는|고|서|면|며|게|도록|니다|요|다|던|면서|지만|니까|려고|어|아|해|았|었|겠|ㄴ)$")
REASON_END = re.compile(r"(?:니까요|거든요|때문입니다|때문이에요|때문이다|니까)[.!?]?$")


def content_stems(sentence):
    out = set()
    for w in re.findall(r"[가-힣]{2,}", sentence):
        for j in JOSA:
            if w.endswith(j) and len(w) - len(j) >= 2:
                w = w[: -len(j)]
                break
        if w in STOPWORDS or VERBISH.search(w):  # 용언은 빼고 명사 위주로 비교한다
            continue
        out.add(w[:2])  # 어미 변화를 흡수하려고 앞 두 글자로 비교한다
    return out


def topic_jumps(text):
    """앞 문장과 겹치는 말도, 잇는 말도 없이 화제가 바뀌는 문장."""
    jumps = []
    for line in text.split("\n"):
        ls = sentences(line)
        for a, b in zip(ls, ls[1:]):
            if content_stems(a) & content_stems(b):
                continue
            if LINKERS.search(b) or REASON_END.search(b.strip()):
                continue
            jumps.append(b)
    return jumps


def repeated_words(text):
    stems = Counter()
    for w in re.findall(r"[가-힣]{2,}", text):
        for j in JOSA:
            if w.endswith(j) and len(w) - len(j) >= 2:
                w = w[: -len(j)]
                break
        if w not in STOPWORDS:
            stems[w] += 1
    return {w: c for w, c in stems.most_common(5) if c >= 5}


def analyze(raw, level=None, editing=False):
    text = clean(raw)
    sents = sentences(text)
    n = len(sents) or 1
    raw_endings = [ending(s) for s in sents]
    endings = [group_ending(e) for e in raw_endings]
    dist = Counter(endings)
    share = lambda types: sum(dist[t] for t in types) / n
    checks = []  # (항목, 통과여부, 값, 기준)
    warnings = []

    rule_level = nearest_level(level) if level is not None else 50
    cfg = LEVELS[rule_level]

    # 자체 규칙 2·3장
    banned = {w: text.count(w) for w in BANNED_WORDS}
    banned["및"] = count(r"(?<![가-힣])및(?![가-힣])", text)
    hit = {w: c for w, c in banned.items() if c}
    checks.append(("금지 단어(핵심·다만·및·단순히)", not hit, hit or 0, "0회"))

    limited = {w: text.count(w) for w in LIMITED_WORDS}
    over = {w: c for w, c in limited.items() if c > 1}
    checks.append(("제한 단어(결국·확인·중요)", not over, over or limited, "각 1회까지"))

    phrases = {}
    for group, pats in BANNED_PHRASES.items():
        for p in pats:
            for m in re.finditer(p, text):
                phrases.setdefault(group, []).append(m.group(0))
    checks.append(("AI 단골 표현", not phrases, phrases or 0, "0회"))

    # 쉼표 (자체 규칙 1장 + KatFish)
    comma_sents = sum(1 for s in sents if "," in s)
    ratio = comma_sents / n
    checks.append(("쉼표 있는 문장 비율", ratio <= 0.3, f"{ratio:.0%} ({comma_sents}/{len(sents)})", "30% 이하"))
    conj_spans = [m.span(1) for m in CONJ_COMMA.finditer(text)]
    cc = [m for m in CONNECTIVE_COMMA.finditer(text)
          if not any(a <= m.start() < b for a, b in conj_spans)]
    checks.append(("연결어미 뒤 쉼표(추정)", not cc, len(cc), "0회"))
    conj = CONJ_COMMA.findall(text)
    checks.append(("문두 접속부사 뒤 쉼표", not conj, Counter(conj) and dict(Counter(conj)) or 0, "0회"))

    # 어색한 고유어 (자체 규칙 9장)
    strong = NATIVE_STRONG.findall(text)
    checks.append(("어색한 고유어", not strong, strong or 0, "0회 (알맹이·걷어내다·짚어 보다 등)"))
    for hanja, pat in NATIVE_CONTEXT.items():
        found = [m.group(0) for m in re.finditer(pat, text)]
        if found:
            warnings.append(f"고유어 의심 → '{hanja}' 같은 한자어 검토: " + " / ".join(found[:3]))

    # 사물 존칭 (레벨 무관)
    hon = [m.group(0) for m in OBJECT_HONORIFIC.finditer(text)]
    checks.append(("사물 존칭", not hon, hon or 0, "0회"))

    # 종결어미 (자체 규칙 7장 / register-levels.md)
    pool = raw_endings if cfg.get("sub") else endings
    counted = [e for e in pool if e != "명사형·기타"] or pool
    cdist = Counter(counted)
    cn = len(counted) or 1
    short = len(counted) < 6  # 짧은 글에 비율 규칙을 걸면 문장마다 어미를 돌려 쓰게 된다
    if short:
        warnings.append("다섯 문장 이하라 종결 비율 규칙은 재지 않았다(끝소리 규칙만 적용)")
    top_type, top_n = cdist.most_common(1)[0] if cdist else ("-", 0)
    top_ratio = top_n / cn
    if not short:
        checks.append(("최다 종결 비율", top_ratio <= cfg["max_top"], f"{top_type} {top_ratio:.0%}",
                   f"{cfg['max_top']:.0%} 이하"))

    run, worst, worst_type = 1, 1, counted[0] if counted else "-"
    for a, b in zip(counted, counted[1:]):
        run = run + 1 if a == b else 1
        if run > worst:
            worst, worst_type = run, b
    if short:
        pass
    elif cfg["run3"]:
        checks.append(("같은 종결 최장 연속", worst < 3, f"{worst}문장 ({worst_type})", "3연속 금지"))
    elif worst >= 4:
        warnings.append(f"같은 종결이 {worst}문장 연속({worst_type})")

    if not short:
        checks.append(("종결 유형 수", len(cdist) >= cfg["min_types"], len(cdist), f"{cfg['min_types']}가지 이상"))

    # 끝소리 반복: 짧은 문장이 같은 끝 두 음절로 이어지면 같은 소리가 빠르게 반복된다
    #   (~했습니다·~합니다·~입니다는 유형이 달라도 모두 "니다")
    run_t = worst_t = 0
    prev = worst_tail = None
    for sn, e in zip(sents, endings):
        tail = end_sound(sn) if e != "명사형·기타" and len(sn) < 40 else None
        run_t = run_t + 1 if tail and tail == prev else (1 if tail else 0)
        prev = tail
        if run_t > worst_t:
            worst_t, worst_tail = run_t, tail
    if worst_t:
        checks.append(("짧은 문장 끝소리 반복", worst_t < 3,
                       f"최장 {worst_t}문장 (~{worst_tail})", "40자 미만, 같은 끝 두 음절 3연속 금지"))
    hap = [(len(sn), e == "~합니다") for sn, e in zip(sents, endings)]
    hap_lens = [ln for ln, is_h in hap if is_h]
    if rule_level == 0 and len(hap_lens) >= 4:
        avg = statistics.mean(hap_lens)
        checks.append(("합쇼체 평균 길이", avg >= 40, f"{avg:.0f}자", "40자 이상"))

    present = dist.get("현재형 ~한다", 0)
    if cfg["present_max"] is not None:
        checks.append(("현재형 ~한다·~는다", present <= cfg["present_max"], present, f"{cfg['present_max']}회 이하"))

    for label, types, kind, limit in cfg["share_rules"]:
        v = share(types)
        ok = v <= limit if kind == "max" else v >= limit
        rule = f"{limit:.0%} {'이하' if kind == 'max' else '이상'}" if limit else "0"
        checks.append((f"{label} 비율", ok, f"{v:.0%}", rule))

    yo_share = share(YO)
    is_yo = yo_share >= 0.3
    markers = {}
    for p in HUMAN_MARKERS:
        c = count(p, text)
        if c:
            markers[p] = c
    # 사람 글 표현은 윤문(--base)할 때만 요구한다. 새로 쓸 때 개수를 채우면 오히려 티가 난다
    need = 0 if not editing else (cfg["markers_min"] if level is not None else (1 if is_yo else 0))
    if need and not short:
        checks.append(("사람 글 표현", len(markers) >= need, markers or 0, f"{need}개 이상"))
    if cfg.get("eoyo_mono") and is_yo and not short:
        polite = sum(dist[t] for t in YO | HAPNIDA)
        eoyo = dist.get("~어요", 0) + dist.get("~예요", 0)
        mono = eoyo / polite if polite else 0
        checks.append(("~어요/~예요 편중(존댓말 중)", mono < 0.7, f"{mono:.0%}", "70% 미만, 합니다체와 섞기"))

    est = estimate_level(endings, text, n)
    if level is not None:
        rude = share(NON_POLITE)
        checks.append(("존댓말 아닌 문장(해라체·반말)", rude <= 0.10, f"{rude:.0%}", "10% 이하"))
        if isinstance(est, int):
            checks.append(("구어체 정도", abs(est - level) <= 15, f"약 {est}", f"목표 {level} ±15"))

    # 경고 (WARN)
    lengths = [len(s) for s in sents]
    # 길이 경고는 여섯 문장 이상에만. 짧은 글에 걸면 경고를 없애려고 문장을 덧붙이게 된다
    if len(lengths) >= 6:
        mean = statistics.mean(lengths)
        cv = statistics.pstdev(lengths) / mean if mean else 0
        if cv < 0.35:
            warnings.append(f"문장 길이가 고르다(변동계수 {cv:.2f}). 있는 문장을 쪼개거나 합쳐서 섞는다(새 문장 추가 금지)")
        if not any(l <= 15 for l in lengths):
            warnings.append("15자 이하 짧은 문장이 하나도 없다. 있는 문장을 쪼개서 만든다(새 문장 추가 금지)")
    if len(sents) >= 3 and len(sents[-1]) <= 15:
        warnings.append(f"마지막 문장이 15자 이하 한 줄이다: {sents[-1]} (요점을 다시 찍는 경구형 마무리면 뺀다)")
    triples = TRIPLE_LIST.findall(text)
    if triples:
        warnings.append(f"셋씩 나열 의심 {len(triples)}곳: " + " / ".join(triples[:3]))
    for line in text.split("\n"):
        ls = sentences(line)
        if len(ls) >= 2 and ending(ls[-1]) == "~고요":
            warnings.append(f"문단이 '~고요'로 끝난다: {ls[-1][:30]}")
    lone = [sn for sn, e in zip(sents, raw_endings) if e == "~는데요" and len(sn) < 20]
    if lone:
        warnings.append(f"짧은 단독 '~는데요.' 문장 {len(lone)}개: {lone[0]}")
    jumps = topic_jumps(text)
    if len(jumps) >= 2:
        warnings.append(f"앞 문장과 이어지지 않고 화제가 바뀌는 문장 {len(jumps)}개: "
                        + " / ".join(j[:20] for j in jumps[:3]) + " (한 문단 한 메시지인지 본다)")
    hook = TREND_HOOK.search(text)
    if hook:
        warnings.append(f"트렌드로 여는 문장: {hook.group(0)}")
    if (hook or (sents and sents[0].startswith("요즘"))) and TURN_WORDS.search(text):
        warnings.append("'요즘 다들 → 하지만·오히려' 반전 공식 의심. 뼈대를 다시 본다")
    adv = ADVERBIAL_COMMA.findall(text)
    if adv:
        warnings.append(f"부사격 조사 뒤 쉼표 {len(adv)}곳")
    linkers = {w: text.count(w) for w in EMPHASIS_LINKERS if text.count(w) > 2}
    if linkers:
        warnings.append("예시·강조 연결어 쏠림: " + ", ".join(f"{w} {c}" for w, c in linkers.items()))
    for label, p in SOFT_PHRASES.items():
        found = re.findall(p, text)
        if found:
            warnings.append(f"{label} {len(found)}곳: {found[0].strip()}")
    nom = NOMINALIZATION.findall(text)
    if len(nom) / n > 0.5:
        warnings.append(f"'-적·-화' 명사화가 많다({len(nom)}회). 동사로 풀어라")
    rep = repeated_words(text)
    if rep:
        warnings.append("같은 낱말 반복: " + ", ".join(f"{w} {c}" for w, c in rep.items())
                        + " (주제어·고유명사면 무시)")

    fails = [c for c in checks if not c[1]]
    return {
        "sentences": len(sents),
        "endings": dict(Counter(raw_endings).most_common()),
        "estimated_level": est,
        "target_level": level,
        "rule_level": rule_level,
        "is_yo": is_yo,
        "checks": [{"item": c[0], "pass": c[1], "value": c[2], "rule": c[3]} for c in checks],
        "warnings": warnings,
        "fail_count": len(fails),
        "verdict": "고친다" if len(fails) >= 2 else "수정할 부분이 거의 없다",
    }


def compare(base_raw, out_raw):
    a, b = clean(base_raw), clean(out_raw)
    rate = 1 - difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()
    nums = lambda s: Counter(re.findall(r"\d[\d,.]*\d|\d", s))
    missing = nums(a) - nums(b)
    added = nums(b) - nums(a)
    return {
        "change_rate": round(rate * 100, 1),
        "change_status": "롤백" if rate > 0.5 else "경고" if rate > 0.3 else "OK",
        "numbers_missing": dict(missing),
        "numbers_added": dict(added),
    }


def fmt(v):
    if isinstance(v, dict):
        return ", ".join(f"{k} {len(x) if isinstance(x, list) else x}"
                         + (f"({'/'.join(x[:3])})" if isinstance(x, list) else "") for k, x in v.items())
    if isinstance(v, list):
        return f"{len(v)} ({' / '.join(v[:3])})"
    return str(v)


def main():
    ap = argparse.ArgumentParser(description="peace-humanize 자체 규칙 측정기")
    ap.add_argument("file")
    ap.add_argument("--base", help="원문 파일. 주면 변경률과 숫자 보존을 함께 본다")
    ap.add_argument("--level", type=int, help="구어체 정도 목표 0~100")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if args.level is not None and not 0 <= args.level <= 100:
        ap.error("--level은 0~100")

    raw = read(args.file)
    report = analyze(raw, args.level, editing=bool(args.base))
    if args.base:
        report["compare"] = compare(read(args.base), raw)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    est = report["estimated_level"]
    est_txt = "존댓말 아님(원문 톤 유지 권장)" if est == "non-polite" else (est if est is not None else "-")
    head = f"문장 {report['sentences']}개 | 구어체 정도 추정 {est_txt}"
    if report["target_level"] is not None:
        head += f" | 목표 {report['target_level']} (기준점 {report['rule_level']} 조건 적용)"
    print(head)
    print("종결 분포: " + ", ".join(f"{k} {v}" for k, v in report["endings"].items()))
    print()
    for c in report["checks"]:
        mark = "PASS" if c["pass"] else "FAIL"
        print(f"[{mark}] {c['item']}: {fmt(c['value'])}  (기준 {c['rule']})")
    for w in report["warnings"]:
        print(f"[WARN] {w}")
    if "compare" in report:
        cmp_ = report["compare"]
        print()
        note = " — 레벨 전환이면 보고만" if report["target_level"] is not None else ""
        print(f"변경률 {cmp_['change_rate']}% → {cmp_['change_status']} (30% 경고, 50% 롤백{note})")
        if cmp_["numbers_missing"]:
            print(f"[FAIL] 원문 숫자 누락: {cmp_['numbers_missing']}  ← 의미 불변 위반, 되돌릴 것")
        if cmp_["numbers_added"]:
            print(f"[WARN] 원문에 없던 숫자: {cmp_['numbers_added']}")
    print()
    print(f"위반 {report['fail_count']}종 → 판정: {report['verdict']}")


if __name__ == "__main__":
    main()
