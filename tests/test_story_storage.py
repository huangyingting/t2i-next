from __future__ import annotations

from t2i_story_pipeline.models import (
    NarrativeThemeResult,
    StoryResult,
    TokenUsage,
)
from t2i_story_pipeline.render import render_narratives
from t2i_story_pipeline.storage import publish_story
from tests.story_factories import (
    make_narrative_review,
    make_narrative_sequence,
    make_narrative_theme,
    make_story_blueprint,
    make_story_request,
)


def test_publish_story_writes_json_prose_and_prompt_files(tmp_path) -> None:
    request = make_story_request()
    blueprint = make_story_blueprint()
    sequence = make_narrative_sequence()
    theme = make_narrative_theme()
    result = StoryResult(
        run_id="abcdef123456",
        request=request,
        blueprint=blueprint,
        themes=[
            NarrativeThemeResult(
                theme=theme,
                sequence=sequence,
                narratives=render_narratives(blueprint, theme, sequence),
                reviews=[make_narrative_review(passing=True)],
                revision_count=0,
            )
        ],
        usage=TokenUsage(total_tokens=30),
    )

    published = publish_story(result, tmp_path)

    assert published.json_file.exists()
    assert published.prompt_file.exists()
    assert published.prose_file.exists()
    assert len(published.prompt_file.read_text().splitlines()) == 2
    prose_lines = published.prose_file.read_text().splitlines()
    assert len(prose_lines) == 2
    assert prose_lines[0].startswith("1930年代秋夜")
    assert "时间与地点：" not in prose_lines[0]
    assert '"run_id": "abcdef123456"' in (
        published.json_file.read_text(encoding="utf-8")
    )


def test_publish_story_writes_six_hundred_ordered_prompts(tmp_path) -> None:
    request = make_story_request(theme_count=100, frames_per_theme=6)
    blueprint = make_story_blueprint()
    themes = []
    for index in range(1, 101):
        theme = make_narrative_theme(index)
        sequence = make_narrative_sequence(
            frame_count=6,
            theme=theme,
        )
        themes.append(
            NarrativeThemeResult(
                theme=theme,
                sequence=sequence,
                narratives=render_narratives(blueprint, theme, sequence),
                reviews=[
                    make_narrative_review(
                        passing=True,
                        frame_count=6,
                    )
                ],
                revision_count=0,
            )
        )
    result = StoryResult(
        run_id="abcdef123456",
        request=request,
        blueprint=blueprint,
        themes=themes,
        usage=TokenUsage(total_tokens=3165),
    )

    published = publish_story(result, tmp_path)

    assert len(published.prose_file.read_text().splitlines()) == 600
    assert len(published.prompt_file.read_text().splitlines()) == 600
    payload = published.json_file.read_text(encoding="utf-8")
    assert '"theme_id": "T001"' in payload
    assert '"theme_id": "T100"' in payload
