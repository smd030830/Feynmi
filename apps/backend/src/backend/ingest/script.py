"""위·아래 첨자를 글자로 남긴다.

문서의 첨자는 "위로 올림" 표시만 붙은 보통 글자라, 표시를 버리면 2¹²가 212가 되어 뜻이 바뀐다
(실제 운영체제 과제 DOCX: "2¹² B" → "212 B", "log₂256KB" → "log2256KB").
숫자·기호는 유니코드 첨자(2¹², log₂, P₁)로 바꾸고, 바꿀 수 없는 글자가 섞이면 ^(…) / _(…)로 쓴다.
"""

from typing import Literal

Script = Literal["super", "sub"]

_SUPER = dict(zip("0123456789+-=()in", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁱⁿ", strict=True))
_SUB = dict(zip("0123456789+-=()aeoxhklmnpst", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₒₓₕₖₗₘₙₚₛₜ", strict=True))
_TABLE = {"super": _SUPER, "sub": _SUB}
_MARK = {"super": "^", "sub": "_"}


def scripted(text: str, script: Script) -> str:
    """첨자 글자를 표시한다. 앞뒤 공백은 그대로 둔다."""
    core = text.strip()
    if not core:
        return text
    lead = text[: len(text) - len(text.lstrip())]
    trail = text[len(text.rstrip()) :]
    table = _TABLE[script]
    if all(ch in table for ch in core):
        body = "".join(table[ch] for ch in core)
    elif len(core) == 1:
        body = f"{_MARK[script]}{core}"
    else:
        body = f"{_MARK[script]}({core})"
    return f"{lead}{body}{trail}"
