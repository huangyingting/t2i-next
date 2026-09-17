from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from t2i_film_style_pipeline.compiler import (
    compile_story_description,
    source_attribution,
)
from t2i_film_style_pipeline.errors import FilmStyleStorageError
from t2i_film_style_pipeline.models import (
    FilmStyleProfile,
    FilmStyleRequest,
    FilmStyleResult,
    FilmWorkReference,
    TokenUsage,
    parse_work_reference,
)
from t2i_film_style_pipeline.pipeline import FilmStylePromptRequest
from t2i_film_style_pipeline.profile_messages import profile_messages
from t2i_film_style_pipeline.provider import ModelResponse
from t2i_film_style_pipeline.rules import resolve_film_style_rules
from t2i_film_style_pipeline.service import FilmStyleStudio
from t2i_film_style_pipeline.storage import publish_film_style
from t2i_story_pipeline.models import ContentLevel


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
    from t2i_story_pipeline.models import StoryRequest

    return resolve_film_style_rules(
        StoryRequest(story="Director scene context")
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

    story_request = request.story_request("BRIEF\n\nDirector scene context")

    assert story_request.prompt_filename_stem == "张艺谋"
    assert story_request.source_prompt_stem is None


def test_compile_story_description_injects_profile_after_brief_header() -> None:
    request = make_request()
    compiled = compile_story_description(
        request,
        make_profile(),
        scene_direction="只生成雨夜室内场景。",
    )

    assert compiled.startswith("BRIEF\n\nWORK-SPECIFIC VISUAL CONTEXT")
    assert "张艺谋导演的《英雄》（2002）、《十面埋伏》（2004）" in compiled
    assert "逐部作品视觉证据" in compiled
    assert "《英雄》（2002）：用饱和单色章节" in compiled
    assert (
        "这是一个采用张艺谋导演的《英雄》（2002）、"
        "《十面埋伏》（2004）视觉风格的原创电影场景。"
    ) in compiled
    assert "只生成雨夜室内场景。" in compiled
    assert "生成与输出规则" not in compiled
    assert "母风格名称" not in compiled
    assert "作品集合风格总结：" not in compiled
    assert "story-inputs/film.txt" not in compiled


def test_profile_prompt_uses_only_work_metadata() -> None:
    messages = profile_messages(make_request(), make_profile_rules())
    payload = json.loads(messages[1].content)

    assert payload["director"] == "张艺谋"
    assert payload["works"][0] == {"title": "英雄", "year": 2002}
    assert set(payload) == {"director", "works", "output_language"}
    assert "不得扩展为对导演全部个人风格的概括或模仿" in messages[0].content
    assert "不得写入导演生平、电影史、剧情解析" in messages[0].content


def test_director_rules_own_theme_and_frame_workflow() -> None:
    from t2i_story_pipeline.models import ContentLevel, StoryRequest

    rules = resolve_film_style_rules(
        StoryRequest(
            story="Director scene context",
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
    assert any("八项中的六项" in rule for rule in rules.themes)
    assert any("固定的主题编号菜单" in rule for rule in rules.themes)
    assert any("完全独立的图像提示词" in rule for rule in rules.frames)
    assert any("画幅比例、分辨率" in rule for rule in rules.frames)
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
    assert not (Path(__file__).parents[1] / "story-inputs" / "film.txt").exists()


@pytest.mark.asyncio
async def test_studio_publishes_profile_run_and_compiled_story(tmp_path) -> None:
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
    assert completed.published.compiled_story_file.exists()
    assert completed.published.compiled_story_file.name == "compiled-story.txt"
    assert (
        completed.published.compiled_story_file.parent
        == completed.published.run_directory
    )
    assert completed.published.profile_file.exists()
    persisted = json.loads(completed.published.profile_file.read_text("utf-8"))
    assert persisted["style_summary"] == profile.style_summary
    assert "profile_name" not in persisted
    assert completed.published.compiled_story_file.read_text("utf-8").startswith(
        "BRIEF\n\nWORK-SPECIFIC VISUAL CONTEXT"
    )
    assert "只生成雨夜室内场景。" in completed.result.compiled_story


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
    compiled = compile_story_description(make_request(), make_profile())

    source_sentence = (
        "这是一个采用张艺谋导演的《英雄》（2002）、"
        "《十面埋伏》（2004）视觉风格的原创电影场景。"
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
        compiled_story=compile_story_description(request, make_profile()),
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
