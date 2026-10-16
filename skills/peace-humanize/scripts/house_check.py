#!/usr/bin/env python3
"""peace-humanize 하우스 룰 측정기. 표준 라이브러리만 쓴다.

사용:
  python house_check.py 글.txt
  python house_check.py 고친글.txt --base 원문.txt
  python house_check.py 고친글.txt --base 원문.txt --level 70
  python house_check.py - < 글.txt          (stdin)
  python house_check.py 글.txt --json       (기계용 출력)

--level N  구어도 목표(0=공문 … 100=반말 구어). 주면 레벨별 종결 조건과
           목표 구어도(±15)를 함께 본다. 안 주면 하우스 룰(50 기준)로 잰다.

종결어미 분류, 구어도 추정, 쉼표 탐지는 휴리스틱이라 오탐이 있을 수 있다.
"""
import argparse
import difflib
import json
import re
import statistics
import sys
from collections import Counter

# ── 하우스 룰 어휘 ────────────────────────────────────────────
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
HAPNIDA = {"~합니다"}
YO = {"~어요", "~예요", "~는데요", "~고요", "~죠", "기타 요체"}
BANMAL = {"반말 ~어", "반말 ~지", "반말 ~거든·~잖아", "반말 ~더라·~네", "반말 ~는데", "감탄·반말 질문"}
SCORE = {"~합니다": 30, "~어요": 60, "~예요": 60, "~고요": 60,
         "~는데요": 70, "~죠": 70, "기타 요체": 70}
for t in FORMAL:
    SCORE[t] = 0
for t in BANMAL:
    SCORE[t] = 100

# 기준점별 조건. 기준점 사이 숫자는 가장 가까운 기준점 조건을 쓴다.
LEVELS = {
    0: dict(max_top=0.6, min_types=2, run3=False, present_max=None, markers_min=0,
            share_rules=[("요체·반말·질문", YO | BANMAL, "max", 0.0)]),
    30: dict(max_top=0.5, min_types=3, run3=True, present_max=3, markers_min=0,
             share_rules=[("요체", YO, "max", 0.10), ("반말·감탄", BANMAL, "max", 0.10)]),
    50: dict(max_top=0.4, min_types=3, run3=True, present_max=3, markers_min=1,
             share_rules=[], eoyo_mono=True),
    70: dict(max_top=0.4, min_types=4, run3=True, present_max=3, markers_min=2,
             share_rules=[("요체", YO, "min", 0.5), ("합니다체", HAPNIDA, "max", 0.25),
                          ("반말·감탄", BANMAL, "max", 0.10)]),
    100: dict(max_top=0.5, min_types=3, run3=True, present_max=None, markers_min=0,
              share_rules=[("반말", BANMAL, "min", 0.6), ("존댓말", YO | HAPNIDA, "max", 0.0)]),
}


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
        for m in re.finditer(r"[^.!?…]+(?:[.!?…]+[\"'”’)\]]*|$)", line):
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
    if t.endswith(("니다", "니까")):
        return "~합니다"
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
        if j == 20:
            return "과거형 ~었다"
        return "평서 ~다(이다·있다 등)"
    if t.endswith(("음", "함", "임", "됨", "기")):
        return "명사형"
    if t.endswith("지"):
        return "반말 ~지"
    if t.endswith(("어", "아", "야", "해", "게", "걸", "자", "고")):
        return "반말 ~어"
    return "명사형·기타"


def count(pattern, text):
    return len(re.findall(pattern, text))


def estimate_level(endings, text, n):
    scored = [SCORE[e] for e in endings if e in SCORE]  # 제목 같은 명사형·기타 줄은 뺀다
    if not scored:
        return None
    base = statistics.mean(scored)
    bump = min(10, 20 * len(COLLOQUIAL.findall(text)) / n)
    return round(min(100, base + bump))


def nearest_level(n):
    return min(LEVELS, key=lambda k: abs(k - n))


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


def analyze(raw, level=None):
    text = clean(raw)
    sents = sentences(text)
    n = len(sents) or 1
    endings = [ending(s) for s in sents]
    dist = Counter(endings)
    share = lambda types: sum(dist[t] for t in types) / n
    checks = []  # (항목, 통과여부, 값, 기준)
    warnings = []

    rule_level = nearest_level(level) if level is not None else 50
    cfg = LEVELS[rule_level]

    # 하우스 룰 2·3장
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

    # 쉼표 (하우스 룰 1장 + KatFish)
    comma_sents = sum(1 for s in sents if "," in s)
    ratio = comma_sents / n
    checks.append(("쉼표 있는 문장 비율", ratio <= 0.3, f"{ratio:.0%} ({comma_sents}/{len(sents)})", "30% 이하"))
    conj_spans = [m.span(1) for m in CONJ_COMMA.finditer(text)]
    cc = [m for m in CONNECTIVE_COMMA.finditer(text)
          if not any(a <= m.start() < b for a, b in conj_spans)]
    checks.append(("연결어미 뒤 쉼표(추정)", not cc, len(cc), "0회"))
    conj = CONJ_COMMA.findall(text)
    checks.append(("문두 접속부사 뒤 쉼표", not conj, Counter(conj) and dict(Counter(conj)) or 0, "0회"))

    # 사물 존칭 (레벨 무관)
    hon = [m.group(0) for m in OBJECT_HONORIFIC.finditer(text)]
    checks.append(("사물 존칭", not hon, hon or 0, "0회"))

    # 종결어미 (하우스 룰 7장 / register-levels.md)
    counted = [e for e in endings if e != "명사형·기타"] or endings
    cdist = Counter(counted)
    cn = len(counted) or 1
    top_type, top_n = cdist.most_common(1)[0] if cdist else ("-", 0)
    top_ratio = top_n / cn
    checks.append(("최다 종결 비율", top_ratio <= cfg["max_top"], f"{top_type} {top_ratio:.0%}",
                   f"{cfg['max_top']:.0%} 이하"))

    run, worst, worst_type = 1, 1, counted[0] if counted else "-"
    for a, b in zip(counted, counted[1:]):
        run = run + 1 if a == b else 1
        if run > worst:
            worst, worst_type = run, b
    if cfg["run3"]:
        checks.append(("같은 종결 최장 연속", worst < 3, f"{worst}문장 ({worst_type})", "3연속 금지"))
    elif worst >= 4:
        warnings.append(f"같은 종결이 {worst}문장 연속({worst_type})")

    checks.append(("종결 유형 수", len(cdist) >= cfg["min_types"], len(cdist), f"{cfg['min_types']}가지 이상"))

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
    need = cfg["markers_min"] if level is not None else (1 if is_yo else 0)
    if need:
        checks.append(("사람 글 표현", len(markers) >= need, markers or 0, f"{need}개 이상"))
    if cfg.get("eoyo_mono") and is_yo:
        polite = sum(dist[t] for t in YO | HAPNIDA)
        eoyo = dist.get("~어요", 0) + dist.get("~예요", 0)
        mono = eoyo / polite if polite else 0
        checks.append(("~어요/~예요 편중(존댓말 중)", mono < 0.7, f"{mono:.0%}", "70% 미만, 합니다체와 섞기"))

    est = estimate_level(endings, text, n)
    if level is not None and est is not None:
        checks.append(("구어도", abs(est - level) <= 15, f"약 {est}", f"목표 {level} ±15"))

    # 경고 (WARN)
    lengths = [len(s) for s in sents]
    if len(lengths) >= 4:
        mean = statistics.mean(lengths)
        cv = statistics.pstdev(lengths) / mean if mean else 0
        if cv < 0.35:
            warnings.append(f"문장 길이가 고르다(변동계수 {cv:.2f}). 짧은 문장과 긴 문장을 섞어라")
        if not any(l <= 15 for l in lengths):
            warnings.append("15자 이하 짧은 문장이 하나도 없다")
    triples = TRIPLE_LIST.findall(text)
    if triples:
        warnings.append(f"셋씩 나열 의심 {len(triples)}곳: " + " / ".join(triples[:3]))
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
        "endings": dict(dist.most_common()),
        "estimated_level": est,
        "target_level": level,
        "rule_level": rule_level,
        "is_yo": is_yo,
        "checks": [{"item": c[0], "pass": c[1], "value": c[2], "rule": c[3]} for c in checks],
        "warnings": warnings,
        "fail_count": len(fails),
        "verdict": "고친다" if len(fails) >= 2 else "손볼 게 거의 없다",
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
    ap = argparse.ArgumentParser(description="peace-humanize 하우스 룰 측정기")
    ap.add_argument("file")
    ap.add_argument("--base", help="원문 파일. 주면 변경률과 숫자 보존을 함께 본다")
    ap.add_argument("--level", type=int, help="구어도 목표 0~100")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if args.level is not None and not 0 <= args.level <= 100:
        ap.error("--level은 0~100")

    raw = read(args.file)
    report = analyze(raw, args.level)
    if args.base:
        report["compare"] = compare(read(args.base), raw)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    est = report["estimated_level"]
    head = f"문장 {report['sentences']}개 | 구어도 추정 {est if est is not None else '-'}"
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
