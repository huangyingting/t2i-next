from __future__ import annotations

import pytest

from t2i_film_style_pipeline.compiler import frame_source_sentence
from t2i_film_style_pipeline.content_validation import FilmStyleContentValidator
from t2i_film_style_pipeline.models import FilmStyleRequest, FilmWorkReference
from t2i_story_pipeline.errors import StoryContractError
from t2i_story_pipeline.models import (
    ContentLevel,
    NarrativeFrame,
    NarrativeTheme,
    StoryRequest,
)


def make_film_request() -> FilmStyleRequest:
    return FilmStyleRequest(
        director="测试导演",
        works=(FilmWorkReference(title="测试作品", year=2000),),
    )


def make_story_request(level: ContentLevel) -> StoryRequest:
    return StoryRequest(story="电影场景上下文", content_level=level)


def make_theme(premise: str) -> NarrativeTheme:
    return NarrativeTheme(
        theme_id="T001",
        title="测试主题",
        premise=premise,
        style="以深景构图、方向性光线和真实材质组织完整电影空间。",
    )


def make_frame(prose: str) -> NarrativeFrame:
    return NarrativeFrame(frame_id="F01", prose=prose)


def test_hardcore_requires_explicit_evidence_in_theme_and_frame() -> None:
    film_request = make_film_request()
    validator = FilmStyleContentValidator(film_request)
    request = make_story_request(ContentLevel.HARDCORE)

    with pytest.raises(StoryContractError, match="不得降级"):
        validator.validate_theme(
            request,
            make_theme("两名成年人在房间里拥抱和亲吻。"),
        )

    explicit_theme = make_theme("两名成年人正在自愿进行口交。")
    validator.validate_theme(request, explicit_theme)

    with pytest.raises(StoryContractError, match="不得降级"):
        validator.validate_frame(
            request,
            explicit_theme,
            make_frame(
                f"{frame_source_sentence(film_request)}两名成年人在房间里拥抱。"
            ),
        )
    with pytest.raises(StoryContractError, match="不得降级"):
        validator.validate_frame(
            request,
            explicit_theme,
            make_frame(
                f"{frame_source_sentence(film_request)}两名成年人接吻，"
                "不出现生殖器、口部性行为或插入行为。"
            ),
        )

    with pytest.raises(StoryContractError, match="正文过短"):
        validator.validate_frame(
            request,
            explicit_theme,
            make_frame(
                f"{frame_source_sentence(film_request)}"
                "两名成年人正在自愿进行口交。"
            ),
        )


def test_frame_rejects_refusal_missing_source_and_image_geometry() -> None:
    film_request = make_film_request()
    validator = FilmStyleContentValidator(film_request)
    request = make_story_request(ContentLevel.AESTHETIC)
    theme = make_theme("两名成年人在房间里相互注视。")
    source = frame_source_sentence(film_request)

    with pytest.raises(StoryContractError, match="拒绝"):
        validator.validate_frame(
            request,
            theme,
            make_frame(f"{source}抱歉，我无法协助创作这个画面。"),
        )
    with pytest.raises(StoryContractError, match="来源句"):
        validator.validate_frame(
            request,
            theme,
            make_frame("两名成年人在房间里相互注视。"),
        )
    with pytest.raises(StoryContractError, match="画幅比例"):
        validator.validate_frame(
            request,
            theme,
            make_frame(f"{source}采用接近方形的固定中远景。"),
        )


@pytest.mark.parametrize("level", [ContentLevel.AESTHETIC, ContentLevel.EROTIC])
def test_non_explicit_levels_reject_explicit_sex(level: ContentLevel) -> None:
    validator = FilmStyleContentValidator(make_film_request())

    with pytest.raises(StoryContractError, match="超出当前内容级别"):
        validator.validate_theme(
            make_story_request(level),
            make_theme("两名成年人正在进行口交。"),
        )
