from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from t2i_film_style_pipeline.compiler import (
    compile_film_context,
    source_attribution,
)
from t2i_film_style_pipeline.errors import FilmStyleStorageError
from t2i_film_style_pipeline.models import (
    FilmCharacterAnchor,
    FilmSceneAnchor,
    FilmStyleProfile,
    FilmStyleRequest,
    FilmStyleResult,
    FilmWorkAnchors,
    FilmWorkReference,
    TokenUsage,
    parse_work_reference,
)
from t2i_film_style_pipeline.pipeline import FilmStylePromptRequest
from t2i_film_style_pipeline.profile_messages import profile_messages
from t2i_film_style_pipeline.prompt_models import ContentLevel
from t2i_film_style_pipeline.provider import ModelResponse
from t2i_film_style_pipeline.rules import resolve_film_style_rules
from t2i_film_style_pipeline.service import FilmStyleStudio
from t2i_film_style_pipeline.storage import publish_film_style


def make_request() -> FilmStyleRequest:
    return FilmStyleRequest(
        director="张艺谋",
        works=(
            FilmWorkReference(title="英雄", year=2002),
            FilmWorkReference(title="十面埋伏", year=2004),
        ),
        output_language="chinese",
    )


def make_profile() -> FilmStyleProfile:
    return FilmStyleProfile(
        style_summary="以单色空间、中轴秩序和克制动作建立史诗尺度。",
        work_style_summaries=(
            "用饱和单色章节、纪念碑式空间和书法性运动组织人物冲突。",
            "用纯化自然色块、流动衣料和纵深调度组织浪漫武侠动作。",
        ),
        work_anchors=(
            FilmWorkAnchors(
                adult_characters=(
                    FilmCharacterAnchor(
                        canonical_name="无名",
                        identity_and_appearance=(
                            "成年秦国刺客，黑发束冠，神态克制。"
                        ),
                        canonical_costume="深色战国交领长袍与黑色束冠。",
                        costume_features=("深色战国长袍", "黑色束冠"),
                    ),
                    FilmCharacterAnchor(
                        canonical_name="飞雪",
                        identity_and_appearance=(
                            "成年赵国剑客，长黑发，姿态冷峻。"
                        ),
                        canonical_costume="具有单色章节特征的交领长袍。",
                        costume_features=("单色交领长袍", "宽大衣袖"),
                    ),
                ),
                scenes=(
                    FilmSceneAnchor(
                        canonical_name="秦宫大殿",
                        narrative_context="秦王在大殿尽端接受无名觐见。",
                        environment="战国秦宫的深远中轴殿堂，以黑色殿柱和石质地面建立秩序。",
                        environment_features=("深远中轴", "黑色殿柱", "石质地面"),
                        canonical_props=("长剑", "烛台"),
                    ),
                    FilmSceneAnchor(
                        canonical_name="棋馆",
                        narrative_context="剑客在静止棋局旁以意念交锋。",
                        environment="雨幕包围木构棋馆，棋台位于人物之间。",
                        environment_features=("雨幕", "木构棋馆", "棋台"),
                        canonical_props=("围棋棋子", "长剑"),
                    ),
                ),
            ),
            FilmWorkAnchors(
                adult_characters=(
                    FilmCharacterAnchor(
                        canonical_name="小妹",
                        identity_and_appearance=(
                            "成年舞伎与武者，长黑发，动作轻盈。"
                        ),
                        canonical_costume="层叠彩色舞衣与长袖。",
                        costume_features=("层叠彩色舞衣", "舞袖"),
                    ),
                    FilmCharacterAnchor(
                        canonical_name="金捕头",
                        identity_and_appearance=(
                            "成年捕快，束发，神态警觉。"
                        ),
                        canonical_costume="唐代深色官差服装与革带。",
                        costume_features=("深色官差服", "革带"),
                    ),
                ),
                scenes=(
                    FilmSceneAnchor(
                        canonical_name="牡丹坊",
                        narrative_context="小妹在宾客与捕快面前表演击鼓舞。",
                        environment="唐代歌舞空间，以层叠帘幕、鼓阵和环形观演关系组织。",
                        environment_features=("层叠帘幕", "鼓阵", "环形观演席"),
                        canonical_props=("彩鼓", "长袖"),
                    ),
                    FilmSceneAnchor(
                        canonical_name="竹林",
                        narrative_context="人物在追捕中穿行并交锋。",
                        environment="高密度青竹形成垂直纵深，地面覆盖竹叶。",
                        environment_features=("高密度青竹", "竹叶地面", "垂直纵深"),
                        canonical_props=("长竹", "佩刀"),
                    ),
                ),
            ),
        ),
        palette="让一种主色控制服装、环境和光线。",
        composition="使用中轴、对称和巨大留白。",
        blocking="人物保持仪式化距离，接触是唯一动作焦点。",
        camera="在史诗远景与触感近景之间形成对照。",
        lighting="使用方向明确的天光或单一实景灯。",
        movement="让衣袖、雨线和水纹形成书法性轨迹。",
        production_design="使用纯化建筑和少量高识别材质。",
        material_and_finish="保持饱和色彩、浓密阴影和真实皮肤。",
        signature_devices=(
            "单色章节必须由实物建立。",
            "人物与建筑形成明确尺度关系。",
            "一个运动元素形成书法性轨迹。",
        ),
        refusal_rules=(
            "拒绝普通历史电视剧质感。",
            "拒绝杂乱生活道具。",
            "拒绝逐镜复制来源作品。",
        ),
    )


def make_profile_rules() -> tuple[str, ...]:
    from t2i_film_style_pipeline.prompt_models import FilmPromptRequest

    return resolve_film_style_rules(
        FilmPromptRequest(context="Director scene context")
    ).profile


def test_parse_work_reference_accepts_optional_year() -> None:
    assert parse_work_reference("Hero (2002)") == FilmWorkReference(
        title="Hero",
        year=2002,
    )
    assert parse_work_reference("Raise the Red Lantern") == FilmWorkReference(
        title="Raise the Red Lantern"
    )


def test_request_requires_unique_works() -> None:
    with pytest.raises(ValidationError, match="works must be unique"):
        FilmStyleRequest(
            director="Director",
            works=(
                FilmWorkReference(title="Film", year=2000),
                FilmWorkReference(title="film", year=2000),
            ),
        )


def test_prompt_request_uses_short_director_filename() -> None:
    request = FilmStylePromptRequest(
        film_style=make_request(),
        content_level=ContentLevel.HARDCORE,
    )

    prompt_request = request.prompt_request("BRIEF\n\nDirector scene context")

    assert prompt_request.prompt_filename_stem == "张艺谋"
    assert prompt_request.source_prompt_stem is None


def test_prompt_request_accepts_explicit_english_filename() -> None:
    request = FilmStylePromptRequest(
        film_style=make_request(),
        output_filename_stem="Zhang_Yimou",
    )

    prompt_request = request.prompt_request("BRIEF\n\nDirector scene context")

    assert prompt_request.prompt_filename_stem == "Zhang_Yimou"

    with pytest.raises(ValidationError, match="string_pattern_mismatch"):
        FilmStylePromptRequest(
            film_style=make_request(),
            output_filename_stem="张艺谋",
        )


def test_profile_rejects_image_geometry() -> None:
    payload = make_profile().model_dump()
    payload["composition"] = "采用方形画幅和中轴对称。"

    with pytest.raises(ValidationError, match="aspect ratio"):
        FilmStyleProfile.model_validate(payload)


def test_compile_film_context_injects_profile_after_brief_header() -> None:
    request = make_request()
    compiled = compile_film_context(
        request,
        make_profile(),
        scene_direction="只生成雨夜室内场景。",
    )

    assert compiled.startswith("BRIEF\n\nWORK-SPECIFIC VISUAL CONTEXT")
    assert "张艺谋导演的《英雄》（2002）、《十面埋伏》（2004）" in compiled
    assert "逐部作品视觉证据" in compiled
    assert "《英雄》（2002）：用饱和单色章节" in compiled
    assert (
        "这是一个基于张艺谋导演的《英雄》（2002）、"
        "《十面埋伏》（2004）原作人物与场景重新构图的电影画面。"
    ) in compiled
    assert "原作人物与场景锚点" in compiled
    assert "- 无名：成年秦国刺客" in compiled
    assert "- 秦宫大殿：原作情境：秦王在大殿尽端接受无名觐见" in compiled
    assert "环境短语：深远中轴、黑色殿柱、石质地面" in compiled
    assert "道具短语：长剑、烛台" in compiled
    assert "只生成雨夜室内场景。" in compiled
    assert "生成与输出规则" not in compiled
    assert "母风格名称" not in compiled
    assert "作品集合风格总结：" not in compiled
    assert "recipes/" not in compiled


def test_profile_prompt_uses_only_work_metadata() -> None:
    messages = profile_messages(make_request(), make_profile_rules())
    payload = json.loads(messages[1].content)

    assert payload["director"] == "张艺谋"
    assert payload["works"][0] == {"title": "英雄", "year": 2002}
    assert set(payload) == {"director", "works", "output_language"}
    assert "不得扩展为对导演全部个人风格的概括或模仿" in messages[0].content
    assert "不得写入导演生平、电影史、剧情解析" in messages[0].content


def test_director_rules_own_theme_and_frame_workflow() -> None:
    from t2i_film_style_pipeline.prompt_models import ContentLevel, FilmPromptRequest

    rules = resolve_film_style_rules(
        FilmPromptRequest(
            context="Director scene context",
            content_level=ContentLevel.HARDCORE,
        )
    )

    assert any(
        "电影场景上下文是唯一依据" in rule
        for rule in rules.themes
    )
    assert any(
        "premise 使用一个不换行的完整段落" in rule
        for rule in rules.themes
    )
    assert any("通常写四至八句" in rule for rule in rules.themes)
    assert any(
        "镜头策略与透视倾向是不可省略的必选项" in rule
        and "七项中的至少五项" in rule
        for rule in rules.themes
    )
    assert any("不提供固定人数或角色菜单" in rule for rule in rules.themes)
    assert any("完全独立的图像提示词" in rule for rule in rules.frames)
    assert any(
        "每个画面必须明确写出完整摄影方案" in rule
        for rule in rules.frames
    )
    assert any(
        "天气、温度、服装、裸露程度" in rule
        for rule in rules.themes
    )
    assert any(
        "国籍、成年身份、关系和其他共同属性" in rule
        for rule in rules.frames
    )
    assert any(
        "使用该片 work_anchors 中至少一名原作成年人物" in rule
        for rule in rules.themes
    )
    assert any(
        "当前关系与互动不要求忠于原作" in rule
        for rule in rules.themes
    )
    assert any(
        "必须明确写出 Theme 选定的全部原作成年人物 canonical_name" in rule
        and "costume_features" in rule
        and "environment_features" in rule
        and "canonical_props" in rule
        for rule in rules.frames
    )
    assert any(
        "画幅比例" in rule and "图像尺寸" in rule
        for rule in rules.frames
    )
    assert any("不得暴露母风格" in rule for rule in rules.frames)
    assert any("内容级别：赤裸明确级" in rule for rule in rules.frames)
    assert not any(
        "The Story Description is authoritative" in rule
        for rule in rules.themes
    )
    assert not any(
        "The Story Description is authoritative" in rule
        for rule in rules.frames
    )


@pytest.mark.asyncio
async def test_studio_publishes_profile_run_and_compiled_context(tmp_path) -> None:
    profile = make_profile()
    captured = {}

    class FakeModel:
        async def generate(self, **kwargs):
            captured.update(kwargs)
            return ModelResponse(
                value=profile,
                usage=TokenUsage(total_tokens=42),
            )

    profile_rules = make_profile_rules()
    completed = await FilmStyleStudio(
        FakeModel(),
        profile_rules,
        runs_directory=tmp_path / "runs",
    ).run(make_request(), scene_direction="只生成雨夜室内场景。")

    assert captured["messages"][0].content == "\n".join(profile_rules)
    assert completed.result.profile == profile
    assert completed.result.usage.total_tokens == 42
    assert completed.published.compiled_context_file.exists()
    assert completed.published.compiled_context_file.name == "compiled-context.txt"
    assert (
        completed.published.compiled_context_file.parent
        == completed.published.run_directory
    )
    assert completed.published.profile_file.exists()
    persisted = json.loads(completed.published.profile_file.read_text("utf-8"))
    assert persisted["style_summary"] == profile.style_summary
    assert "profile_name" not in persisted
    assert completed.published.compiled_context_file.read_text("utf-8").startswith(
        "BRIEF\n\nWORK-SPECIFIC VISUAL CONTEXT"
    )
    assert "只生成雨夜室内场景。" in completed.result.compiled_context


@pytest.mark.asyncio
async def test_studio_strips_repeated_source_labels_from_summaries(tmp_path) -> None:
    profile = make_profile().model_copy(
        update={
            "style_summary": "《英雄》：单色空间与中轴秩序。",
            "work_style_summaries": (
                "《英雄》（2002）：单色章节与书法性动作。",
                "十面埋伏 (2004): 自然色块与流动衣料。",
            ),
        }
    )

    class FakeModel:
        async def generate(self, **_kwargs):
            return ModelResponse(value=profile, usage=TokenUsage())

    completed = await FilmStyleStudio(
        FakeModel(),
        make_profile_rules(),
        runs_directory=tmp_path / "runs",
    ).run(make_request())

    assert completed.result.profile.style_summary == "单色空间与中轴秩序。"
    assert completed.result.profile.work_style_summaries == (
        "单色章节与书法性动作。",
        "自然色块与流动衣料。",
    )


@pytest.mark.asyncio
async def test_studio_replaces_meta_summary_with_visual_work_summary(
    tmp_path,
) -> None:
    profile = make_profile().model_copy(
        update={
            "style_summary": (
                "这是一个从张艺谋的《英雄》中提取的视觉风格系统。"
            ),
        }
    )

    class FakeModel:
        async def generate(self, **_kwargs):
            return ModelResponse(value=profile, usage=TokenUsage())

    completed = await FilmStyleStudio(
        FakeModel(),
        make_profile_rules(),
        runs_directory=tmp_path / "runs",
    ).run(make_request())

    summary = completed.result.profile.style_summary
    assert "张艺谋" not in summary
    assert "英雄" not in summary
    assert "饱和单色章节" in summary
    assert "自然色块" in summary


@pytest.mark.asyncio
async def test_single_work_uses_complete_per_film_summary(tmp_path) -> None:
    request = FilmStyleRequest(
        director="张艺谋",
        works=(FilmWorkReference(title="英雄", year=2002),),
    )
    profile = make_profile().model_copy(
        update={
            "style_summary": "这段元总结会在字符上限处被截断",
            "work_style_summaries": (
                "单色章节、对称构图与书法性动作形成完整风格总结。",
            ),
            "work_anchors": make_profile().work_anchors[:1],
        }
    )

    class FakeModel:
        async def generate(self, **_kwargs):
            return ModelResponse(value=profile, usage=TokenUsage())

    completed = await FilmStyleStudio(
        FakeModel(),
        make_profile_rules(),
        runs_directory=tmp_path / "runs",
    ).run(request)

    assert completed.result.profile.style_summary == (
        "单色章节、对称构图与书法性动作形成完整风格总结。"
    )


@pytest.mark.asyncio
async def test_single_work_opening_summary_uses_complete_first_sentence(
    tmp_path,
) -> None:
    request = FilmStyleRequest(
        director="张艺谋",
        works=(FilmWorkReference(title="英雄", year=2002),),
    )
    profile = make_profile().model_copy(
        update={
            "work_style_summaries": (
                "单色章节与中轴构图建立视觉秩序。后续分析保留在档案中。",
            ),
            "work_anchors": make_profile().work_anchors[:1],
        }
    )

    class FakeModel:
        async def generate(self, **_kwargs):
            return ModelResponse(value=profile, usage=TokenUsage())

    completed = await FilmStyleStudio(
        FakeModel(),
        make_profile_rules(),
        runs_directory=tmp_path / "runs",
    ).run(request)

    assert completed.result.profile.style_summary == (
        "单色章节与中轴构图建立视觉秩序。"
    )
    assert completed.result.profile.work_style_summaries == (
        "单色章节与中轴构图建立视觉秩序。后续分析保留在档案中。",
    )


def test_compiler_requires_one_direct_source_sentence() -> None:
    compiled = compile_film_context(make_request(), make_profile())

    source_sentence = (
        "这是一个基于张艺谋导演的《英雄》（2002）、"
        "《十面埋伏》（2004）原作人物与场景重新构图的电影画面。"
    )
    assert compiled.count(source_sentence) == 1


def test_english_source_attribution_is_work_specific() -> None:
    request = FilmStyleRequest(
        director="Jane Director",
        works=(FilmWorkReference(title="Example", year=1999),),
        output_language="english",
    )

    assert source_attribution(request) == "Example (1999), directed by Jane Director"


def test_publish_removes_staging_when_run_commit_fails(
    tmp_path,
    monkeypatch,
) -> None:
    request = make_request()
    result = FilmStyleResult(
        run_id="run",
        request=request,
        profile=make_profile(),
        compiled_context=compile_film_context(request, make_profile()),
        usage=TokenUsage(),
    )
    def fail_commit(_staging, _destination):
        raise OSError("commit failed")

    monkeypatch.setattr(
        "t2i_film_style_pipeline.storage._commit_run_directory",
        fail_commit,
    )

    with pytest.raises(FilmStyleStorageError, match="commit failed"):
        publish_film_style(
            result,
            runs_directory=tmp_path / "runs",
        )

    assert not (tmp_path / "runs" / "run").exists()
    assert not list((tmp_path / "runs").glob(".run-*.tmp"))
