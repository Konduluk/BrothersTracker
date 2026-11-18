import re

GLORY = re.compile(r'^\s*Слава\s*:\s*([\d\s\u00a0.,]+)\s*$', re.I)
LABEL = re.compile(r'^(?:Уровень|Статус|Удача|Кристаллы|Пожертвовано|Слава|Ранг|В братстве|Онлайн)\s*:', re.I)

def parse_warriors(text):
    """Conservative line-oriented parser. Returns nickname->glory; raises on ambiguity."""
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    out = {}
    for i, line in enumerate(lines):
        match = GLORY.fullmatch(line)
        if not match:
            continue
        digits = re.sub(r'\D', '', match.group(1))
        if not digits:
            continue
        # Player name should precede glory, potentially separated by status/level fields.
        candidates = []
        for prev in reversed(lines[max(0, i-9):i]):
            if LABEL.match(prev) or re.fullmatch(r'\d+', prev) or prev in ('В сети', 'Не в сети', 'Онлайн', 'Оффлайн'):
                continue
            if re.match(r'^(?:Слава|Удача|Уровень|Статус|Кристаллы)\b', prev, re.I):
                continue
            if len(prev) > 60 or prev.endswith(':'):
                continue
            candidates.append(prev)
            break
        if candidates:
            name = candidates[0]
            if name in out:
                raise ValueError('Повторяющийся ник в распознанном списке: ' + name)
            out[name] = int(digits)
    return out
