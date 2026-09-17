from __future__ import annotations

import re

import pytest

from t2i_film_style_pipeline.errors import FilmStyleConfigurationError
from t2i_film_style_pipeline.prompt_models import ContentLevel, FilmPromptRequest
from t2i_film_style_pipeline.rules import resolve_film_style_rules


def make_prompt_request(
    content_level: ContentLevel = ContentLevel.AESTHETIC,
) -> FilmPromptRequest:
    return FilmPromptRequest(
        context="BRIEF\n\nDirector-work film scene generation.",
        content_level=content_level,
    )


def test_film_style_rules_select_only_the_requested_content_level() -> None:
    rules = resolve_film_style_rules(
        make_prompt_request(ContentLevel.EROTIC),
    )

    for stage_rules in (rules.themes, rules.frames):
        text = "\n".join(stage_rules)
        assert "内容级别：极致情色级" in text
        assert "内容级别：美学级" not in text
        assert "内容级别：赤裸明确级" not in text


@pytest.mark.parametrize(
    ("content_level", "required_rule", "forbidden_rule"),
    [
        (
            ContentLevel.AESTHETIC,
            "不出现明确性行为",
            "允许直接呈现自慰、口部性行为、插入",
        ),
        (
            ContentLevel.EROTIC,
            "把裸露、欲望、身体接近和双向触碰推到最高可见强度",
            "允许直接呈现自慰、口部性行为、插入",
        ),
        (
            ContentLevel.HARDCORE,
            "正在发生的具体性行为、性器官及其接触方式",
            "不得出现明确性行为",
        ),
    ],
)
def test_film_style_content_levels_define_clear_visual_bounds(
    content_level,
    required_rule,
    forbidden_rule,
) -> None:
    rules = resolve_film_style_rules(
        make_prompt_request(content_level),
    )
    text = "\n".join(rules.frames)

    assert required_rule in text
    assert forbidden_rule not in text
    assert "最大化感官表现时" in text
    assert "主动" in text
    assert "自愿" in text


@pytest.mark.parametrize("output_language", ["chinese", "english"])
def test_every_builtin_film_style_rule_is_written_in_chinese(
    output_language,
) -> None:
    rules = resolve_film_style_rules(
        FilmPromptRequest(
            context="BRIEF\n\nDirector-work film scene generation.",
            output_language=output_language,
        )
    )

    for rule in (*rules.profile, *rules.themes, *rules.frames):
        assert re.search(r"[\u4e00-\u9fff]", rule), rule


def test_film_style_rules_append_optional_user_files_in_stage_order(
    tmp_path,
) -> None:
    (tmp_path / "content_levels").mkdir()
    (tmp_path / "profile.rules").write_text(
        "Film user profile rule.\n",
        encoding="utf-8",
    )
    (tmp_path / "common.rules").write_text(
        "# ignored\nFilm user common rule.\n\n",
        encoding="utf-8",
    )
    (tmp_path / "themes.rules").write_text(
        "Film user Theme rule.\n",
        encoding="utf-8",
    )
    (tmp_path / "frames.rules").write_text(
        "Film user Frame rule.\n",
        encoding="utf-8",
    )
    (tmp_path / "content_levels" / "aesthetic.rules").write_text(
        "Film user aesthetic rule.\n",
        encoding="utf-8",
    )

    rules = resolve_film_style_rules(
        make_prompt_request(),
        user_directory=tmp_path,
    )

    assert rules.profile[-1] == "Film user profile rule."
    assert rules.themes[-4:-1] == (
        "Film user common rule.",
        "Film user Theme rule.",
        "Film user aesthetic rule.",
    )
    assert rules.frames[-4:-1] == (
        "Film user common rule.",
        "Film user Frame rule.",
        "Film user aesthetic rule.",
    )
    assert "电影场景上下文" in rules.themes[-1]
    assert "电影场景上下文" in rules.frames[-1]


def test_film_style_rules_reject_missing_user_directory(tmp_path) -> None:
    with pytest.raises(
        FilmStyleConfigurationError,
        match="film-style user rules directory does not exist",
    ):
        resolve_film_style_rules(
            make_prompt_request(),
            user_directory=tmp_path / "missing",
        )
