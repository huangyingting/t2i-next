"""Non-negotiable safety checks for story source and generated artifacts."""

from __future__ import annotations

import re

from t2i_story_pipeline.errors import UnsafeStoryError

_MINOR = re.compile(
    r"未成年|女童|男童|儿童|小学生|中学生|高中生|少女|少年|"
    r"\b(?:minor|child|schoolgirl|schoolboy|teen(?:age[rd]?)?)s?\b",
    re.IGNORECASE,
)
_PAST_AGE_REFERENCE = re.compile(
    r"(?:少年|少女)(?:时代|时期|时光|岁月|记忆|往事|旧梦)",
    re.IGNORECASE,
)
_CURRENT_AMBIGUOUS_WOMAN = re.compile(
    r"少女(?!时代|时期|时光|岁月|记忆|往事|旧梦)"
)
_CURRENT_AMBIGUOUS_MAN = re.compile(
    r"少年(?!时代|时期|时光|岁月|记忆|往事|旧梦)"
)
_SEXUAL_VIOLENCE = re.compile(
    r"强奸|性侵|性暴力|猥亵|非自愿性行为|"
    r"\b(?:rape|sexual assault|sexual violence|non-consensual sex)\b",
    re.IGNORECASE,
)
_SEXUAL_CONTEXT = re.compile(
    r"裸体|全裸|半裸|赤裸|"
    r"(?:裸露.{0,8}(?:身体|皮肤|上身|下身|胸部|乳房|臀部|大腿|私处)|"
    r"(?:身体|皮肤|上身|下身|胸部|乳房|臀部|大腿|私处).{0,8}裸露)|"
    r"胸部|乳房|性器官|内衣|内裤|"
    r"臀部|私处|性爱|性行为|情色|性化|"
    r"\b(?:nude|naked|breasts?|genitals?|underwear|sexual|erotic)\b",
    re.IGNORECASE,
)
_COERCION = re.compile(
    r"胁迫|强迫|被迫|逼迫|强行|强制|拖入|压制|按住|反拧|"
    r"无法退出|不能拒绝|被捆|施暴|武器威胁|挣扎|反抗|"
    r"违背.{0,8}意愿|不顾.{0,8}意愿|"
    r"\b(?:coerc(?:e|ion)|forced?|dragged|pinned|restrained|"
    r"cannot refuse|cannot leave|held against .{0,20} will)\b",
    re.IGNORECASE,
)
_INTIMACY = re.compile(
    r"亲吻|接吻|爱抚|抚摸|亲密接触|性爱|性行为|"
    r"\b(?:kiss(?:ing)?|caress(?:ing)?|intimate|sexual)\b",
    re.IGNORECASE,
)
_CONSENT = re.compile(
    r"合意|自愿|双方主动|彼此回应|相互回应|可以停止|随时退出|"
    r"\b(?:consensual|mutual(?:ly)? willing|may stop|can leave)\b",
    re.IGNORECASE,
)


def validate_source_story(
    text: str,
    *,
    require_intimate_consent: bool = False,
) -> None:
    if match := _current_minor_match(text):
        raise UnsafeStoryError(
            f"故事人物必须明确成年，检测到未成年或年龄模糊表达：{match.group(0)}"
        )
    _validate_no_coercive_sexual_content(text)
    if (
        require_intimate_consent or _INTIMACY.search(text)
    ) and not _CONSENT.search(text):
        raise UnsafeStoryError("亲密互动必须在故事中明确表达双方合意、回应或可随时停止")


def validate_generated_story(text: str) -> None:
    if match := _current_minor_match(text):
        raise UnsafeStoryError(f"生成内容出现未成年或年龄模糊表达：{match.group(0)}")
    if match := _SEXUAL_VIOLENCE.search(text):
        raise UnsafeStoryError(f"不支持性胁迫或性暴力内容：{match.group(0)}")


def normalize_generated_adult_language(text: str) -> str:
    text = _CURRENT_AMBIGUOUS_WOMAN.sub("成年女性", text)
    return _CURRENT_AMBIGUOUS_MAN.sub("成年男性", text)


def _validate_no_coercive_sexual_content(text: str) -> None:
    if match := _SEXUAL_VIOLENCE.search(text):
        raise UnsafeStoryError(f"不支持性胁迫或性暴力内容：{match.group(0)}")
    coercion = _coercive_sexual_match(text)
    if coercion:
        raise UnsafeStoryError(f"不支持胁迫语境中的性化内容：{coercion.group(0)}")


def _current_minor_match(text: str) -> re.Match[str] | None:
    without_past_references = _PAST_AGE_REFERENCE.sub("", text)
    return _MINOR.search(without_past_references)


def _coercive_sexual_match(text: str) -> re.Match[str] | None:
    for coercion in _COERCION.finditer(text):
        start = max(0, coercion.start() - 80)
        end = min(len(text), coercion.end() + 80)
        if _SEXUAL_CONTEXT.search(text[start:end]):
            return coercion
    return None
