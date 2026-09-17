"""验证导演风格 Theme 与 Frame 的关键语义契约。"""

from __future__ import annotations

import re
from dataclasses import dataclass

from t2i_film_style_pipeline.compiler import frame_source_sentence
from t2i_film_style_pipeline.models import (
    FilmStyleRequest,
    contains_image_geometry,
)
from t2i_story_pipeline.errors import StoryContractError
from t2i_story_pipeline.models import (
    ContentLevel,
    NarrativeFrame,
    NarrativeTheme,
    StoryRequest,
)

_REFUSAL = re.compile(
    r"抱歉|无法(?:协助|提供|创作)|不能(?:协助|提供|创作)|"
    r"\b(?:sorry|i cannot|i can't|unable to assist)\b",
    re.IGNORECASE,
)
_EXPLICIT_SEX = re.compile(
    r"(?:阴茎|生殖器|性器官).{0,24}(?:插入|进入|接触).{0,16}"
    r"(?:阴道|肛门|外阴|性器官)|"
    r"(?:插入|进入).{0,16}(?:阴道|肛门)|"
    r"(?:口|口舌|舌头|嘴唇).{0,20}(?:阴茎|外阴|阴蒂|生殖器|性器官)|"
    r"(?:阴茎|外阴|阴蒂|生殖器|性器官).{0,20}(?:口|口舌|舌头|嘴唇)|"
    r"自慰|手淫|指交|乳交|性交|肛交|口交|"
    r"\b(?:penetrat(?:e|es|ed|ing|ion)|oral sex|fellatio|cunnilingus|"
    r"masturbat(?:e|es|ed|ing|ion)|anal sex|vaginal sex)\b",
    re.IGNORECASE,
)
_NEGATED_CONTENT = re.compile(
    r"(?:不(?:再)?(?:出现|包含|呈现|涉及)|"
    r"不得(?:出现|包含|呈现|涉及)|没有|并无)"
    r"[^。；;\n]{0,120}(?:[。；;\n]|$)|"
    r"\b(?:without|does not (?:show|include|depict)|"
    r"do not (?:show|include|depict)|no)\b"
    r"[^.;\n]{0,160}(?:[.;\n]|$)",
    re.IGNORECASE,
)


def _contains_explicit_sex(value: str) -> bool:
    affirmative_content = _NEGATED_CONTENT.sub(" ", value)
    return _EXPLICIT_SEX.search(affirmative_content) is not None


@dataclass(frozen=True, slots=True)
class FilmStyleContentValidator:
    film_request: FilmStyleRequest

    def validate_theme(
        self,
        request: StoryRequest,
        theme: NarrativeTheme,
    ) -> None:
        self._validate_output(theme.premise, label=f"{theme.theme_id} premise")
        self._validate_content_level(
            request,
            theme.premise,
            label=f"{theme.theme_id} premise",
        )

    def validate_frame(
        self,
        request: StoryRequest,
        theme: NarrativeTheme,
        frame: NarrativeFrame,
    ) -> None:
        label = f"{theme.theme_id}-{frame.frame_id}"
        prose = frame.prose
        self._validate_output(prose, label=label)
        source_sentence = frame_source_sentence(self.film_request)
        if not prose.startswith(source_sentence) or prose.count(source_sentence) != 1:
            raise StoryContractError(
                f"{label} 必须且只能以指定作品来源句开头一次"
            )
        if contains_image_geometry(prose):
            raise StoryContractError(
                f"{label} 不得包含画幅比例、横竖方向或图像尺寸"
            )
        self._validate_content_level(request, prose, label=label)
        minimum_length = (
            300 if self.film_request.output_language == "chinese" else 600
        )
        if len(prose) < minimum_length:
            raise StoryContractError(
                f"{label} 画面正文过短，无法完整覆盖环境、人物、互动、"
                "摄影和光线"
            )

    @staticmethod
    def _validate_output(value: str, *, label: str) -> None:
        if _REFUSAL.search(value):
            raise StoryContractError(
                f"{label} 返回了拒绝或无法协助文本，必须改写为有效画面内容"
            )

    @staticmethod
    def _validate_content_level(
        request: StoryRequest,
        value: str,
        *,
        label: str,
    ) -> None:
        contains_explicit_sex = _contains_explicit_sex(value)
        if request.content_level == ContentLevel.HARDCORE:
            if not contains_explicit_sex:
                raise StoryContractError(
                    f"{label} 未直接写出可见的明确性行为及其身体接触，"
                    "不得降级为普通亲密互动"
                )
            return
        if contains_explicit_sex:
            raise StoryContractError(
                f"{label} 超出当前内容级别，不得出现明确性行为"
            )
