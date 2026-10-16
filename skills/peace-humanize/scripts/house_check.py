#!/usr/bin/env python3
"""peace-humanize 하우스 룰 측정기. 표준 라이브러리만 쓴다.

사용:
  python house_check.py 글.txt
  python house_check.py 고친글.txt --base 원문.txt
  python house_check.py - < 글.txt          (stdin)
  python house_check.py 글.txt --json       (기계용 출력)

종결어미 분류와 연결어미 쉼표 탐지는 휴리스틱이라 오탐이 있을 수 있다.
"""
import argparse
import difflib
import json
import re
import statistics
import sys
from collections import Counter

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

CONNECTIVE_COMMA = re.compile(r"[가-힣](?:고|며|지만|면서|아서|어서|해서),")
TRIPLE_LIST = re.compile(
    r"[가-힣A-Za-z0-9]+(?:,\s*|·)[가-힣A-Za-z0-9]+(?:,\s*|·|,?\s*그리고\s+|\s*및\s*)[가-힣A-Za-z0-9]+")

YO_TYPES = {"~어요", "~예요", "~는데요", "~고요", "~죠", "기타 요체"}


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
        return "기타"
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
    if t.endswith(("네요", "거든요", "잖아요", "군요", "나요", "까요", "래요", "대요")):
        return "기타 요체"
    if t.endswith("요"):
        return "~어요"
    if asks:
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
    if t.endswith(("어", "아", "야", "지", "해", "게", "네", "래", "걸")):
        return "반말"
    return "명사형·기타"


def count(pattern, text):
    return len(re.findall(pattern, text))


def analyze(raw):
    text = clean(raw)
    sents = sentences(text)
    n = len(sents) or 1
    endings = [ending(s) for s in sents]
    dist = Counter(endings)
    checks = []  # (항목, 통과여부, 값, 기준)

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

    comma_sents = sum(1 for s in sents if "," in s)
    ratio = comma_sents / n
    checks.append(("쉼표 있는 문장 비율", ratio <= 0.3, f"{ratio:.0%} ({comma_sents}/{len(sents)})", "30% 이하"))

    cc = CONNECTIVE_COMMA.findall(text)
    checks.append(("연결어미 뒤 쉼표(추정)", not cc, len(cc), "0회"))

    top_type, top_n = dist.most_common(1)[0] if dist else ("-", 0)
    top_ratio = top_n / n
    checks.append(("최다 종결 비율", top_ratio <= 0.4, f"{top_type} {top_ratio:.0%}", "40% 이하"))

    run, worst, worst_type = 1, 1, endings[0] if endings else "-"
    for a, b in zip(endings, endings[1:]):
        run = run + 1 if a == b else 1
        if run > worst:
            worst, worst_type = run, b
    checks.append(("같은 종결 최장 연속", worst < 3, f"{worst}문장 ({worst_type})", "3연속 금지"))

    checks.append(("종결 유형 수", len(dist) >= 3, len(dist), "3가지 이상"))

    present = dist.get("현재형 ~한다", 0)
    checks.append(("현재형 ~한다·~는다", present <= 3, present, "3회 이하"))

    yo_total = sum(dist[t] for t in YO_TYPES)
    is_yo = yo_total / n >= 0.3
    markers = {}
    if is_yo:
        for p in HUMAN_MARKERS:
            c = count(p, text)
            if c:
                markers[p] = c
        checks.append(("사람 글 표현(요체 글)", bool(markers), markers or 0, "1개 이상"))
        polite = yo_total + dist.get("~합니다", 0)
        eoyo = dist.get("~어요", 0) + dist.get("~예요", 0)
        mono = eoyo / polite if polite else 0
        checks.append(("~어요/~예요 편중(존댓말 중)", mono < 0.7, f"{mono:.0%}", "70% 미만, 합니다체와 섞기"))

    lengths = [len(s) for s in sents]
    warnings = []
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

    fails = [c for c in checks if not c[1]]
    return {
        "sentences": len(sents),
        "endings": dict(dist.most_common()),
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
        return ", ".join(f"{k} {len(x) if isinstance(x, list) else x}" + (f"({'/'.join(x[:3])})" if isinstance(x, list) else "") for k, x in v.items())
    return str(v)


def main():
    ap = argparse.ArgumentParser(description="peace-humanize 하우스 룰 측정기")
    ap.add_argument("file")
    ap.add_argument("--base", help="원문 파일. 주면 변경률과 숫자 보존을 함께 본다")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    raw = read(args.file)
    report = analyze(raw)
    if args.base:
        report["compare"] = compare(read(args.base), raw)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    print(f"문장 {report['sentences']}개 | 요체 글: {'예' if report['is_yo'] else '아니오'}")
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
        print(f"변경률 {cmp_['change_rate']}% → {cmp_['change_status']} (30% 경고, 50% 롤백)")
        if cmp_["numbers_missing"]:
            print(f"[FAIL] 원문 숫자 누락: {cmp_['numbers_missing']}  ← 의미 불변 위반, 되돌릴 것")
        if cmp_["numbers_added"]:
            print(f"[WARN] 원문에 없던 숫자: {cmp_['numbers_added']}")
    print()
    print(f"위반 {report['fail_count']}종 → 판정: {report['verdict']}")


if __name__ == "__main__":
    main()
