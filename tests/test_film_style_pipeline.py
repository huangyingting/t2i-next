from __future__ import annotations

import json

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
from t2i_film_style_pipeline.prompts import profile_messages
from t2i_film_style_pipeline.provider import ModelResponse
from t2i_film_style_pipeline.service import FilmStyleStudio
from t2i_film_style_pipeline.storage import publish_film_style


def make_request() -> FilmStyleRequest:
    return FilmStyleRequest(
        director="张艺谋",
        works=(
            FilmWorkReference(title="英雄", year=2002),
            FilmWorkReference(title="十面埋伏", year=2004),
        ),
        base_brief="BRIEF\n\nCreate original adult wuxia stills.",
        output_language="chinese",
    )


def make_profile() -> FilmStyleProfile:
    return FilmStyleProfile(
        profile_name="单色礼序",
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


def test_parse_work_reference_accepts_optional_year() -> None:
    assert parse_work_reference("Hero (2002)") == FilmWorkReference(
        title="Hero",
        year=2002,
    )
    assert parse_work_reference("Raise the Red Lantern") == FilmWorkReference(
        title="Raise the Red Lantern"
    )


def test_request_requires_current_story_contract_and_unique_works() -> None:
    with pytest.raises(ValidationError, match="base brief must start"):
        FilmStyleRequest(
            director="Director",
            works=(FilmWorkReference(title="Film"),),
            base_brief="legacy brief",
        )
    with pytest.raises(ValidationError, match="works must be unique"):
        FilmStyleRequest(
            director="Director",
            works=(
                FilmWorkReference(title="Film", year=2000),
                FilmWorkReference(title="film", year=2000),
            ),
            base_brief="BRIEF\n\nCurrent brief.",
        )


def test_compile_story_description_injects_profile_after_brief_header() -> None:
    request = make_request()
    compiled = compile_story_description(request, make_profile())

    assert compiled.startswith("BRIEF\n\nWORK-SPECIFIC FILM STYLE PROFILE")
    assert "张艺谋执导的作品《英雄》（2002）、《十面埋伏》（2004）" in compiled
    assert "“单色礼序”" in compiled
    assert "逐部电影风格总结" in compiled
    assert "《英雄》（2002）：用饱和单色章节" in compiled
    assert "作品集合风格总结：" in compiled
    assert "每个 Frame 的第一分句" in compiled
    assert compiled.endswith("Create original adult wuxia stills.")


def test_profile_prompt_uses_only_work_metadata() -> None:
    messages = profile_messages(make_request())
    payload = json.loads(messages[1].content)

    assert payload["director"] == "张艺谋"
    assert payload["works"][0] == {"title": "英雄", "year": 2002}
    assert "base_brief" not in payload
    assert "unrestricted personal style" in messages[0].content


@pytest.mark.asyncio
async def test_studio_publishes_profile_run_and_compiled_story(tmp_path) -> None:
    profile = make_profile()

    class FakeModel:
        async def generate(self, **_kwargs):
            return ModelResponse(
                value=profile,
                usage=TokenUsage(total_tokens=42),
            )

    completed = await FilmStyleStudio(
        FakeModel(),
        runs_directory=tmp_path / "runs",
        output_directory=tmp_path / "outputs",
    ).run(make_request(), source_stem="hero-erotic")

    assert completed.result.profile == profile
    assert completed.result.usage.total_tokens == 42
    assert completed.published.prompt_file.exists()
    assert "张艺谋" in completed.published.prompt_file.name
    assert completed.result.run_id in completed.published.prompt_file.name
    assert completed.published.profile_file.exists()
    persisted = json.loads(completed.published.profile_file.read_text("utf-8"))
    assert persisted["profile_name"] == "单色礼序"
    assert completed.published.prompt_file.read_text("utf-8").startswith(
        "BRIEF\n\nWORK-SPECIFIC FILM STYLE PROFILE"
    )


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
        runs_directory=tmp_path / "runs",
        output_directory=tmp_path / "outputs",
    ).run(make_request(), source_stem="base")

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
        runs_directory=tmp_path / "runs",
        output_directory=tmp_path / "outputs",
    ).run(make_request(), source_stem="base")

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
        base_brief="BRIEF\n\nCreate original stills.",
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
        runs_directory=tmp_path / "runs",
        output_directory=tmp_path / "outputs",
    ).run(request, source_stem="base")

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
        base_brief="BRIEF\n\nCreate original stills.",
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
        runs_directory=tmp_path / "runs",
        output_directory=tmp_path / "outputs",
    ).run(request, source_stem="base")

    assert completed.result.profile.style_summary == (
        "单色章节与中轴构图建立视觉秩序。"
    )
    assert completed.result.profile.work_style_summaries == (
        "单色章节与中轴构图建立视觉秩序。后续分析保留在档案中。",
    )


def test_compiler_source_attribution_overrides_base_blanket_ban() -> None:
    compiled = compile_story_description(make_request(), make_profile())

    assert "唯一来源署名优先于基础 brief" in compiled
    assert "该例外只适用于这一次来源署名" in compiled


def test_english_source_attribution_is_work_specific() -> None:
    request = FilmStyleRequest(
        director="Jane Director",
        works=(FilmWorkReference(title="Example", year=1999),),
        base_brief="BRIEF\n\nCreate original stills.",
        output_language="english",
    )

    assert source_attribution(request) == "Example (1999), directed by Jane Director"


def test_compiled_story_can_exceed_base_brief_limit() -> None:
    base_brief = "BRIEF\n\n" + ("x" * (55000 - len("BRIEF\n\n")))
    request = FilmStyleRequest(
        director="Director",
        works=(FilmWorkReference(title="Film"),),
        base_brief=base_brief,
    )
    profile = make_profile().model_copy(
        update={
            "work_style_summaries": (
                "单色章节与书法性动作形成完整风格总结。",
            ),
        }
    )
    compiled = compile_story_description(request, profile)

    result = FilmStyleResult(
        run_id="run",
        request=request,
        profile=profile,
        compiled_story=compiled,
        usage=TokenUsage(),
    )

    assert len(result.compiled_story) > 55000


def test_publish_removes_prompt_when_run_commit_fails(
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
    prompt_file = tmp_path / "outputs" / "compiled.txt"

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
            prompt_file=prompt_file,
        )

    assert not prompt_file.exists()
    assert not (tmp_path / "runs" / "run").exists()
    assert not list((tmp_path / "runs").glob(".run-*.tmp"))
