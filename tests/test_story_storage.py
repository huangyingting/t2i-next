from __future__ import annotations

import json

from t2i_story_pipeline.models import QualityFeedback, StoryStage
from t2i_story_pipeline.storage import publish_story
from tests.story_factories import make_story_result


def test_publish_story_writes_json_and_one_prompt_file(tmp_path) -> None:
    result = make_story_result()
    result.quality_feedback = [
        QualityFeedback(
            stage=StoryStage.FRAMES,
            item_id="T001/F01",
            issues=["镜头句缺少拍摄角度"],
        )
    ]

    published = publish_story(result, tmp_path)

    assert published.json_file.exists()
    assert published.prompt_file.exists()
    assert len(published.prompt_file.read_text().splitlines()) == 2
    assert published.prompt_file.read_text().splitlines()[0].startswith(
        "1930年代北平电影风格"
    )
    assert '"run_id": "abcdef123456"' in published.json_file.read_text(
        encoding="utf-8"
    )
    payload = json.loads(published.json_file.read_text(encoding="utf-8"))
    assert payload["request"]["content_level"] == "aesthetic"
    assert payload["quality_feedback"] == [
        {
            "stage": "frames",
            "item_id": "T001/F01",
            "issues": ["镜头句缺少拍摄角度"],
        }
    ]
    assert "镜头句缺少拍摄角度" not in published.prompt_file.read_text(
        encoding="utf-8"
    )
    assert list(tmp_path.glob("*")) == [
        published.json_file,
        published.prompt_file,
    ]


def test_publish_story_writes_six_hundred_ordered_prompts(tmp_path) -> None:
    result = make_story_result(theme_count=100, frames_per_theme=6)

    published = publish_story(result, tmp_path)

    lines = published.prompt_file.read_text().splitlines()
    assert len(lines) == 600
    assert "第1站台" in lines[0]
    assert "第100站台" in lines[-1]
