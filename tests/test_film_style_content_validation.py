from __future__ import annotations

import pytest

from t2i_film_style_pipeline.compiler import frame_source_sentence
from t2i_film_style_pipeline.content_validation import FilmStyleContentValidator
from t2i_film_style_pipeline.errors import FilmStyleContractError
from t2i_film_style_pipeline.models import FilmStyleRequest, FilmWorkReference
from t2i_film_style_pipeline.prompt_models import (
    ContentLevel,
    FilmPromptRequest,
    NarrativeFrame,
    NarrativeTheme,
)
from tests.test_film_style_pipeline import make_profile, make_request


def make_film_request() -> FilmStyleRequest:
    return FilmStyleRequest(
        director="测试导演",
        works=(FilmWorkReference(title="测试作品", year=2000),),
    )


def make_prompt_request(level: ContentLevel) -> FilmPromptRequest:
    return FilmPromptRequest(context="电影场景上下文", content_level=level)


def make_validation_profile():
    profile = make_profile()
    return profile.model_copy(update={"work_anchors": profile.work_anchors[:1]})


def make_theme(premise: str) -> NarrativeTheme:
    return NarrativeTheme(
        theme_id="T001",
        title="测试主题",
        premise=f"原作人物无名与飞雪位于秦宫大殿。{premise}",
        style="以深景构图、方向性光线和真实材质组织完整电影空间。",
    )


def make_frame(prose: str) -> NarrativeFrame:
    return NarrativeFrame(frame_id="F01", prose=prose)


def complete_camera_frame(film_request: FilmStyleRequest) -> NarrativeFrame:
    return make_frame(
        f"{frame_source_sentence(film_request)}"
        "战国冬夜的秦宫大殿以深远中轴、黑色殿柱和石质地面组成三层空间，"
        "原作人物无名与飞雪位于殿内，长剑放在两人之间。无名穿深色战国长袍"
        "与黑色束冠，飞雪穿单色交领长袍与宽大衣袖，两名明显成年的人物"
        "隔桌相望，彼此主动伸手并持续对视。"
        "摄影机机位设在两人"
        "正面约三米处，保持眼平高度，以三分之二侧前角度平视，使用"
        "五十毫米标准镜头拍摄中景，自然透视维持人物与房间的可信尺度；"
        "主焦点落在两张面孔，次级清晰区域保留相触的手部，浅景深使"
        "前景门框略微柔化并形成框景，背景窗格仍可辨认。左侧烛火提供"
        "柔暖主光，右后方冷色月光勾出肩线，阴影保留旧木、粗布和纸面的"
        "细节，低饱和灰褐环境只以深红器物形成色彩重音，细密颗粒和"
        "柔和高光保持克制、自然、完整且可以直接摄影执行的长片质感。"
    )


def test_hardcore_theme_can_be_broad_but_frame_requires_explicit_evidence() -> None:
    film_request = make_film_request()
    validator = FilmStyleContentValidator(film_request, make_validation_profile())
    request = make_prompt_request(ContentLevel.HARDCORE)

    validator.validate_theme(
        request,
        make_theme("两名成年人在房间里探索多种明确的成人亲密互动。"),
    )

    explicit_theme = make_theme("两名成年人正在自愿进行口交。")
    validator.validate_theme(request, explicit_theme)

    with pytest.raises(FilmStyleContractError, match="不得降级"):
        validator.validate_frame(
            request,
            explicit_theme,
            make_frame(
                f"{frame_source_sentence(film_request)}两名成年人在房间里拥抱。"
            ),
        )
    with pytest.raises(FilmStyleContractError, match="不得降级"):
        validator.validate_frame(
            request,
            explicit_theme,
            make_frame(
                f"{frame_source_sentence(film_request)}两名成年人接吻，"
                "不出现生殖器、口部性行为或插入行为。"
            ),
        )

    with pytest.raises(FilmStyleContractError, match="正文过短"):
        validator.validate_frame(
            request,
            explicit_theme,
            make_frame(
                f"{frame_source_sentence(film_request)}"
                "两名成年人正在自愿进行口交。"
            ),
        )


@pytest.mark.parametrize(
    "premise",
    [
        "两名成年人正在进行明确的阴蒂摩擦与刺激行为。",
        "一名成年人的手指正在直接抚触另一名成年人的外阴。",
        "两名成年人正在进行生殖器摩擦。",
        "Two adults are engaged in clitoral stimulation.",
        "One adult is performing manual genital stimulation on another adult.",
    ],
)
def test_hardcore_accepts_contextual_manual_stimulation(
    premise: str,
) -> None:
    validator = FilmStyleContentValidator(
        make_film_request(),
        make_validation_profile(),
    )

    validator.validate_theme(
        make_prompt_request(ContentLevel.HARDCORE),
        make_theme(premise),
    )


@pytest.mark.parametrize(
    "premise",
    [
        "两名成年人亲吻，但不展示阴蒂摩擦与刺激。",
        "画面不得呈现手指直接抚触外阴。",
        "Two adults embrace without clitoral stimulation.",
    ],
)
def test_hardcore_frame_rejects_negated_manual_stimulation(
    premise: str,
) -> None:
    validator = FilmStyleContentValidator(
        make_film_request(),
        make_validation_profile(),
    )

    film_request = make_film_request()
    source = frame_source_sentence(film_request)
    with pytest.raises(FilmStyleContractError, match="不得降级"):
        validator.validate_frame(
            make_prompt_request(ContentLevel.HARDCORE),
            make_theme("两名成年人探索多种明确的成人亲密互动。"),
            make_frame(
                source
                + premise
                + "画面补充足够长的环境、人物与摄影描述，但不改变上述行为。"
                * 20
            ),
        )


def test_frame_rejects_refusal_missing_source_and_image_geometry() -> None:
    film_request = make_film_request()
    validator = FilmStyleContentValidator(film_request, make_validation_profile())
    request = make_prompt_request(ContentLevel.AESTHETIC)
    theme = make_theme("两名成年人在房间里相互注视。")
    source = frame_source_sentence(film_request)

    with pytest.raises(FilmStyleContractError, match="拒绝"):
        validator.validate_frame(
            request,
            theme,
            make_frame(f"{source}抱歉，我无法协助创作这个画面。"),
        )
    with pytest.raises(FilmStyleContractError, match="来源句"):
        validator.validate_frame(
            request,
            theme,
            make_frame("两名成年人在房间里相互注视。"),
        )
    with pytest.raises(FilmStyleContractError, match="画幅比例"):
        validator.validate_frame(
            request,
            theme,
            make_frame(f"{source}采用接近方形的固定中远景。"),
        )


@pytest.mark.parametrize("level", [ContentLevel.AESTHETIC, ContentLevel.EROTIC])
@pytest.mark.parametrize(
    "premise",
    [
        "两名成年人正在进行口交。",
        "一名成年人的手指正在直接抚触另一名成年人的外阴。",
        "Two adults are engaged in genital rubbing.",
    ],
)
def test_non_explicit_levels_reject_explicit_sex(
    level: ContentLevel,
    premise: str,
) -> None:
    validator = FilmStyleContentValidator(
        make_film_request(),
        make_validation_profile(),
    )

    with pytest.raises(FilmStyleContractError, match="超出当前内容级别"):
        validator.validate_theme(
            make_prompt_request(level),
            make_theme(premise),
        )


def test_frame_requires_complete_camera_evidence() -> None:
    film_request = make_film_request()
    validator = FilmStyleContentValidator(film_request, make_validation_profile())
    request = make_prompt_request(ContentLevel.AESTHETIC)
    theme = make_theme("两名成年人在书房里相互注视。")
    complete = complete_camera_frame(film_request)

    validator.validate_frame(request, theme, complete)

    incomplete = complete.model_copy(
        update={
            "prose": complete.prose.replace(
                "五十毫米标准镜头",
                "普通摄影设备",
            )
        }
    )
    with pytest.raises(FilmStyleContractError, match="镜头或焦距"):
        validator.validate_frame(request, theme, incomplete)

    natural_height = complete.model_copy(
        update={
            "prose": complete.prose.replace(
                "保持眼平高度",
                "与两人胸口平齐",
            )
        }
    )
    validator.validate_frame(request, theme, natural_height)

    natural_distance_and_lens = complete.model_copy(
        update={
            "prose": complete.prose.replace(
                "正面约三米处",
                "正面两个身位外",
            ).replace(
                "五十毫米标准镜头",
                "中焦镜头",
            )
        }
    )
    validator.validate_frame(request, theme, natural_distance_and_lens)


def test_frame_rejects_compliance_boilerplate() -> None:
    film_request = make_film_request()
    validator = FilmStyleContentValidator(film_request, make_validation_profile())
    request = make_prompt_request(ContentLevel.AESTHETIC)
    theme = make_theme("两名成年人在书房里相互注视。")
    complete = complete_camera_frame(film_request)
    boilerplate = complete.model_copy(
        update={
            "prose": complete.prose.replace(
                "两名明显成年的人物",
                "两名平等而自愿的明显成年人物",
            )
        }
    )

    with pytest.raises(FilmStyleContractError, match="结论式合规话术"):
        validator.validate_frame(request, theme, boilerplate)


def test_theme_requires_original_character_and_scene_anchors() -> None:
    film_request = make_film_request()
    validator = FilmStyleContentValidator(film_request, make_validation_profile())
    request = make_prompt_request(ContentLevel.AESTHETIC)
    theme = NarrativeTheme(
        theme_id="T001",
        title="缺少锚点",
        premise="两名成年人在一间书房里相互注视。",
        style="使用深景构图、方向性光线和真实材质。",
    )

    with pytest.raises(FilmStyleContractError, match="原作成年人物 canonical_name"):
        validator.validate_theme(request, theme)


def test_frame_cannot_switch_to_another_works_anchors() -> None:
    film_request = make_request()
    validator = FilmStyleContentValidator(film_request, make_profile())
    request = make_prompt_request(ContentLevel.AESTHETIC)
    theme = make_theme("两名成年人在书房里相互注视。")
    complete = complete_camera_frame(film_request)
    cross_work = complete.model_copy(
        update={
            "prose": (
                complete.prose.replace("无名与飞雪", "小妹与金捕头")
                .replace("秦宫大殿", "牡丹坊")
            )
        }
    )

    with pytest.raises(FilmStyleContractError, match="必须延续 Theme"):
        validator.validate_frame(request, theme, cross_work)


def test_frame_requires_original_costume_environment_and_props() -> None:
    film_request = make_film_request()
    validator = FilmStyleContentValidator(film_request, make_validation_profile())
    request = make_prompt_request(ContentLevel.AESTHETIC)
    theme = make_theme("两名成年人在书房里相互注视。")
    complete = complete_camera_frame(film_request)

    missing_costume = complete.model_copy(
        update={
            "prose": (
                complete.prose.replace("深色战国长袍", "深色衣服")
                .replace("黑色束冠", "头冠")
            )
        }
    )
    with pytest.raises(FilmStyleContractError, match="原作人物服装特征：无名"):
        validator.validate_frame(request, theme, missing_costume)

    missing_environment = complete.model_copy(
        update={
            "prose": (
                complete.prose.replace("深远中轴", "纵向空间")
                .replace("黑色殿柱", "立柱")
                .replace("石质地面", "地面")
            )
        }
    )
    with pytest.raises(FilmStyleContractError, match="environment_features"):
        validator.validate_frame(request, theme, missing_environment)

    missing_props = complete.model_copy(
        update={"prose": complete.prose.replace("长剑", "木尺")}
    )
    with pytest.raises(FilmStyleContractError, match="canonical_props"):
        validator.validate_frame(request, theme, missing_props)


def test_aesthetic_frame_requires_strong_sensory_evidence() -> None:
    film_request = make_film_request()
    validator = FilmStyleContentValidator(film_request, make_validation_profile())
    request = make_prompt_request(ContentLevel.AESTHETIC)
    theme = make_theme("两名成年人在书房里相互注视。")
    complete = complete_camera_frame(film_request)
    weak = complete.model_copy(
        update={
            "prose": (
                complete.prose.replace("相触的手部", "桌面")
                .replace("肩线", "屋檐")
                .replace("粗布", "石墙")
            )
        }
    )

    with pytest.raises(FilmStyleContractError, match="美学级感官证据不足"):
        validator.validate_frame(request, theme, weak)
