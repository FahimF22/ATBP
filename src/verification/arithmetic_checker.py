"""
Deterministic checks for claims in math word problems.

1. Arithmetic: finds equations such as "3 x 15 = 45" or "$25 + $15 = $40"
   and recomputes them exactly.
2. Grounding: flags operand numbers that appear neither in the problem nor in
   earlier claims (e.g. a quantity copied wrongly from the problem).

These checks give ground truth for the easiest class of reasoning faults and
do not depend on the model judging its own work.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Text normalisation
# ---------------------------------------------------------------------------

_LATEX_FRAC = re.compile(r"\\[dt]?frac\{([^{}]+)\}\{([^{}]+)\}")
_LATEX_TEXT = re.compile(r"\\(?:text|mathrm|textbf|mathbf)\{([^{}]*)\}")


def normalize(text: str) -> str:
    """Turn LaTeX / unicode math into plain ASCII arithmetic."""
    t = text
    t = _LATEX_TEXT.sub(r" \1 ", t)
    for _ in range(3):
        t = _LATEX_FRAC.sub(r"(\1)/(\2)", t)
    replacements = {
        "\\times": "*", "\\cdot": "*", "\\div": "/", "\\$": "$", "\\%": "%",
        "\\(": " ", "\\)": " ", "\\[": " ", "\\]": " ", "\\,": "", "\\ ": " ",
        "\\left": "", "\\right": "", "\\approx": "~",
        "×": "*", "·": "*", "∙": "*", "⋅": "*", "÷": "/",
        "−": "-", "–": "-", "—": " - ", "＝": "=", "≈": "~",
        "**": "",  # markdown bold
        "{": "", "}": "",
    }
    for old, new in replacements.items():
        t = t.replace(old, new)
    # "3x15" / "3 x 15" between numbers means multiplication
    t = re.sub(r"(?<=[\d)])\s*[xX]\s*(?=[\d($])", " * ", t)
    return t


# ---------------------------------------------------------------------------
# Equation parsing
# ---------------------------------------------------------------------------

_NUM = r"-?(?:\$\s?)?\d[\d,]*(?:\.\d+)?%?|-?\$?\.\d+%?"
# Unsigned number token used when evaluating (minus is handled as an operator).
_UNUM = r"(?:\$\s?)?\d[\d,]*(?:\.\d+)?%?|\$?\.\d+%?"
# An operand: number, optionally wrapped in parentheses, optionally followed
# by up to two unit words ("15 stamps", "3 square feet").
_UNIT = r"(?:\s+(?!x\b|X\b|and\b|so\b|then\b|which\b|is\b)[A-Za-z]+){0,2}"
_OPERAND = rf"\(*\s*(?:{_NUM}){_UNIT}\s*\)*"
_OP = r"\s*[-+*/]\s*"
_EXPR = rf"{_OPERAND}(?:{_OP}{_OPERAND})*"
_EQUATION = re.compile(rf"(?P<eq>{_EXPR}(?:\s*=\s*{_EXPR})+)")


def _to_number(token: str):
    token = token.replace("$", "").replace(",", "").strip()
    pct = token.endswith("%")
    token = token.rstrip("%")
    return float(token), pct


def _expr_variants(expr: str):
    """
    Evaluate an expression. Percent signs are ambiguous ("250 * 60%" means
    0.6, "60% = 60%" means 60), so return every plausible value.
    Returns (values, has_operator, numbers_in_expr) or None if unparsable.
    """
    numbers = []
    pieces_div = []   # "%" -> /100
    pieces_raw = []   # "%" ignored
    has_op = False
    for m in re.finditer(rf"{_UNUM}|[-+*/()]|[A-Za-z]+", expr):
        tok = m.group(0)
        if re.fullmatch(r"[A-Za-z]+", tok):
            continue  # unit words
        if tok in "+-*/":
            if tok == "-" and (not pieces_div or pieces_div[-1] in "+-*/("):
                pieces_div.append("-")
                pieces_raw.append("-")
                continue
            has_op = True
            pieces_div.append(tok)
            pieces_raw.append(tok)
            continue
        if tok in "()":
            pieces_div.append(tok)
            pieces_raw.append(tok)
            continue
        try:
            value, pct = _to_number(tok)
        except ValueError:
            return None
        numbers.append(value)
        pieces_div.append(repr(value / 100 if pct else value))
        pieces_raw.append(repr(value))
    if not numbers:
        return None
    values = []
    for pieces in (pieces_div, pieces_raw):
        src = " ".join(pieces)
        if not re.fullmatch(r"[\d\s.+\-*/()e]+", src):
            return None
        try:
            values.append(eval(src, {"__builtins__": {}}, {}))  # noqa: S307 (digits/ops only)
        except Exception:
            continue
    if not values:
        return None
    return values, has_op, numbers


def _close(a: float, b: float, stated_text: str) -> bool:
    decimals = 0
    m = re.search(r"\.(\d+)", stated_text)
    if m:
        decimals = len(m.group(1))
    tol = 0.5 * 10 ** (-decimals) + 1e-9
    if decimals == 0 and abs(b) >= 1 and abs(a - round(a)) > 1e-9:
        tol = 0.5  # "10 / 3 = 3" style rounding
    return abs(a - b) <= max(tol, 1e-6 * abs(b))


def fmt_number(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.2f}".rstrip("0").rstrip(".")


@dataclass
class ArithmeticIssue:
    equation: str
    stated: float
    correct: float
    stated_text: str

    def message(self) -> str:
        return (f"Arithmetic error in '{self.equation.strip()}': the result should "
                f"be {fmt_number(self.correct)}, not {fmt_number(self.stated)}.")


@dataclass
class ArithmeticReport:
    checked: int = 0                       # equations checked
    issues: list = field(default_factory=list)
    operands: list = field(default_factory=list)  # numbers used on LHS
    results: list = field(default_factory=list)   # numbers stated as results

    @property
    def ok(self) -> bool:
        return not self.issues


def check_arithmetic(text: str) -> ArithmeticReport:
    report = ArithmeticReport()
    norm = normalize(text)
    for m in _EQUATION.finditer(norm):
        segments = [s for s in re.split(r"\s*=\s*", m.group("eq")) if s.strip()]
        if len(segments) < 2:
            continue
        first = _expr_variants(segments[0])
        if first is None or not first[1]:
            continue  # "x = 5" / "250 = 150": no calculation to check
        report.operands.extend(first[2])
        prev_values = first[0]
        prev_text = segments[0]
        for seg in segments[1:]:
            parsed = _expr_variants(seg)
            if parsed is None:
                break
            values, has_op, nums = parsed
            candidates = list(values)
            if has_op:
                candidates.append(nums[0])  # sloppy chain "3*3 = 9*60 = 540"
            stated_text = re.search(_UNUM, seg).group(0)
            report.checked += 1
            matched = any(
                _close(p, c, stated_text) or (stated_text.endswith("%") and _close(p * 100, c, stated_text))
                for p in prev_values for c in candidates
            )
            if not matched:
                report.issues.append(ArithmeticIssue(
                    equation=f"{prev_text} = {seg}",
                    stated=nums[0],
                    correct=prev_values[0],
                    stated_text=stated_text,
                ))
                break
            if not has_op:
                report.results.append(nums[0])
            report.operands.extend(nums if has_op else [])
            prev_values = values
            prev_text = seg
    return report


def fix_arithmetic(text: str) -> tuple[str, list]:
    """
    Replace wrong results with the recomputed values.
    Returns (fixed_text, list of (old, new)). Works on the normalised text.
    """
    norm = normalize(text)
    changes = []
    for _ in range(5):  # a fix can expose the next error in a chain
        report = check_arithmetic(norm)
        if report.ok:
            break
        issue = report.issues[0]
        eq_pos = norm.find(issue.equation.split("=")[0].strip())
        if eq_pos < 0:
            eq_pos = 0
        eq_sign = norm.find("=", eq_pos)
        target = issue.stated_text.replace("$", "").replace("%", "").strip()
        idx = norm.find(target, eq_sign)
        if idx < 0:
            break
        new = fmt_number(issue.correct)
        norm = norm[:idx] + new + norm[idx + len(target):]
        changes.append((issue.stated, issue.correct))
    return norm, changes


# ---------------------------------------------------------------------------
# Grounding
# ---------------------------------------------------------------------------

# Numbers that are general knowledge rather than facts from the problem.
COMMON_CONSTANTS = {
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 100, 1000, 24, 60, 30, 31, 28, 52,
    365, 366, 0.5, 0.25, 0.75, 16, 3600, 20, 50, 25, 11,
}

_NUM_PLAIN = re.compile(r"\$?\d[\d,]*(?:\.\d+)?%?")


def numbers_in(text: str) -> set:
    out = set()
    for tok in _NUM_PLAIN.findall(normalize(text)):
        try:
            value, pct = _to_number(tok)
        except ValueError:
            continue
        out.add(round(value, 6))
        if pct:
            out.add(round(value / 100, 6))
    return out


_WORD_NUMBERS = {
    "half": 0.5, "quarter": 0.25, "third": 3, "twice": 2, "double": 2,
    "triple": 3, "dozen": 12, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30,
    "forty": 40, "fifty": 50, "hundred": 100, "thousand": 1000,
}


def problem_numbers(problem: str) -> set:
    nums = numbers_in(problem)
    low = problem.lower()
    for word, value in _WORD_NUMBERS.items():
        if re.search(rf"\b{word}\b", low):
            nums.add(float(value))
    # percentages may be used as fractions and vice versa
    nums |= {round(n / 100, 6) for n in list(nums)}
    nums |= {round(n * 100, 6) for n in list(nums) if n < 1}
    return nums


def ungrounded_operands(claim_text: str, known: set) -> list:
    """Operands of the claim's calculations that are not known numbers."""
    report = check_arithmetic(claim_text)
    out = []
    for value in report.operands:
        v = round(value, 6)
        if v in known or v in COMMON_CONSTANTS:
            continue
        if round(v / 100, 6) in known or round(v * 100, 6) in known:
            continue
        out.append(value)
    return out
