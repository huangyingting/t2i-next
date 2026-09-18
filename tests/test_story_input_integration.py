from __future__ import annotations

import json
import re

import pytest
import yaml

from t2i_story_pipeline.errors import (
    StoryProviderResponseError,
    StoryRunIncompleteError,
    StoryStorageError,
)
from t2i_story_pipeline.inputs import (
    InputOverrides,
    load_story_document,
    resolve_story_input,
)
from t2i_story_pipeline.models import StoryStage
from t2i_story_pipeline.provider import StoryProviderSettings, TextModelResponse
from t2i_story_pipeline.run_store import LocalStoryRunStore, StoryRunSettings
from t2i_story_pipeline.studio import StoryStudio
from tests.story_factories import (
    make_frame_sequence,
    make_story_input,
    make_story_request,
)
from tests.test_story_studio import RoutedStoryModel


@pytest.fixture
def planned_input(tmp_path):
    assets = tmp_path / "assets"
    catalogs = assets / "_catalogs"
    modules = assets / "_modules"
    catalogs.mkdir(parents=True)
    modules.mkdir()
    catalog_path = catalogs / "station-details.yaml"
    catalog_path.write_text(
        yaml.safe_dump(
            {
                "id": "station-details",
                "slots": ["gamma", "alpha", "delta", "beta"],
                "entries": [
                    {
                        "id": name,
                        "themes": [
                            f"THEME_{name.upper()} establishes a station detail."
                        ],
                        "frames": [f"FRAME_{name.upper()} renders the station detail."],
                        "frame_assignment": {
                            "frames_per_theme": 2,
                            "slots": [
                                {
                                    "frame_id": frame_id,
                                    "rules": [
                                        f"VIEW_{name.upper()}_{frame_id} uses "
                                        f"the {viewpoint} station viewpoint."
                                    ],
                                }
                                for frame_id, viewpoint in (
                                    ("F01", "front"), ("F02", "rear")
                                )
                            ],
                        },
                    }
                    for name in ("alpha", "beta", "gamma", "delta")
                ],
            }
        ),
        encoding="utf-8",
    )
    module_path = modules / "station-layout.yaml"
    module_path.write_text(
        yaml.safe_dump(
            {
                "id": "station-layout",
                "kind": "layout_multiview",
                "authoring": {
                    "themes": {"common": ["MODULE_THEME keeps a unified station."]},
                    "frames": {
                        "common": ["MODULE_FRAME uses two internal view regions."]
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    document_path = tmp_path / "station.yaml"
    document_path.write_text(
        yaml.safe_dump(
            {
                "id": "station",
                "description": "A collection of quiet station compositions.",
                "generation": {"theme_count": 4, "frames_per_theme": 1},
                "requirements": {"theme_count": {"min": 3}},
                "allocation": {
                    "type": "fixed_slots",
                    "catalog": "station-details",
                },
                "modules": [
                    {
                        "id": "station-layout",
                        "parameters": {"layout": "grid", "rows": 1, "columns": 2},
                    }
                ],
                "authoring": {
                    stage: {
                        "common": [f"DOCUMENT_{stage.upper()} retains a quiet mood."],
                        "content_levels": {
                            "aesthetic": [f"SELECTED_{stage.upper()} uses soft light."],
                            "erotic": [f"UNSELECTED_{stage.upper()} uses warm light."],
                            "hardcore": [f"OTHER_{stage.upper()} uses stark light."],
                        },
                    }
                    for stage in ("themes", "frames")
                },
                "runtime": {
                    "theme_batch_size": 2,
                    "concurrency": 1,
                    "generation_retries": 1,
                },
            }
        ),
        encoding="utf-8",
    )
    resolved = resolve_story_input(
        load_story_document(document_path), asset_root=assets
    )
    return resolved, (document_path, catalog_path, module_path)


def assert_selected_facts(messages, stage, entries):
    text = "\n".join(message.content for message in messages)
    payload = json.loads(messages[1].content)
    if stage == StoryStage.THEMES or payload["frames_per_theme"] != 2:
        assert all(
            not plan["frame_slots"] for plan in payload["input_context"]["plans"]
        )
        assert "VIEW_" not in text
    selected_prefix = "THEME" if stage == StoryStage.THEMES else "FRAME"
    other_prefix = "FRAME" if stage == StoryStage.THEMES else "THEME"
    for name in ("alpha", "beta", "gamma", "delta"):
        assert (f"{selected_prefix}_{name.upper()}" in text) == (name in entries)
        assert f"{other_prefix}_{name.upper()}" not in text
    assert f"MODULE_{selected_prefix}" in text
    assert f"MODULE_{other_prefix}" not in text
    assert f"SELECTED_{stage.value.upper()}" in text
    assert "UNSELECTED_" not in text
    assert "OTHER_" not in text


class RetryingPlannedModel(RoutedStoryModel):
    def __init__(self, *, failed_frame=None):
        super().__init__()
        self.failed_frame = failed_frame
        self.later_theme_calls = 0
        self.theme_calls = []
        self.frame_calls = []

    async def generate(self, **kwargs):
        self.theme_calls.append(kwargs["messages"])
        payload = json.loads(kwargs["messages"][1].content)
        if len(payload["existing_themes"]) == 2:
            self.later_theme_calls += 1
            if self.later_theme_calls == 1:
                raise StoryProviderResponseError("temporary later batch failure")
        return await super().generate(**kwargs)

    async def generate_text(self, **kwargs):
        self.frame_calls.append(kwargs["messages"])
        payload = json.loads(kwargs["messages"][1].content)
        if (
            payload["theme"]["theme_id"] == "T003"
            and self.failed_frame == "F02"
            and payload["requested_frame_slots"] == ["F01", "F02"]
        ):
            response = await super().generate_text(**kwargs)
            frame = make_frame_sequence(theme_index=3, frame_count=1).frames[0]
            return TextModelResponse(
                text=f"<FRAME>{frame.prose}</FRAME><FRAME>invalid\nmultiline</FRAME>",
                usage=response.usage,
            )
        if payload["theme"]["theme_id"] == "T003" and (
            self.failed_frame is None
            or self.failed_frame in payload["requested_frame_slots"]
        ):
            raise StoryProviderResponseError("temporary station detail failure")
        return await super().generate_text(**kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize("batch_size", [1, 3])
@pytest.mark.parametrize("frames_per_theme", [1, 3])
async def test_catalog_assignments_are_independent_of_theme_batch_boundaries(
    tmp_path, planned_input, batch_size, frames_per_theme
):
    original, paths = planned_input
    resolved = resolve_story_input(
        load_story_document(paths[0]),
        InputOverrides(
            theme_batch_size=batch_size, frames_per_theme=frames_per_theme
        ),
        asset_root=paths[1].parent.parent,
    )
    assert resolved.plans == original.plans
    assert resolved.fingerprint() != original.fingerprint()
    assert resolved.request.theme_count == 4
    assert resolved.runtime.theme_batch_size == batch_size
    settings = StoryRunSettings(
        provider=StoryProviderSettings(model="test-model"),
        **resolved.runtime.model_dump(),
        quality=resolved.quality,
    )
    model = RoutedStoryModel()
    store = LocalStoryRunStore(tmp_path / "runs", tmp_path / "prompts")
    completed = await StoryStudio(model, store, settings).run(resolved)
    assert len(completed.result.themes) == 4
    assert all(
        len(theme.frames) == frames_per_theme for theme in completed.result.themes
    )
    theme_calls = 0
    for stage, messages in zip(model.stages, model.messages, strict=True):
        payload = json.loads(messages[1].content)
        if stage == StoryStage.THEMES:
            start = len(payload["existing_themes"])
            plans = resolved.plans[start : start + payload["theme_count"]]
            theme_calls += 1
        else:
            plans = [resolved.plans[int(payload["theme"]["theme_id"][1:]) - 1]]
        assert_selected_facts(messages, stage, [plan.entry.id for plan in plans])
    assert theme_calls == (4 + batch_size - 1) // batch_size


@pytest.mark.asyncio
async def test_catalog_plans_survive_batch_retry_and_offline_resume(
    tmp_path, planned_input
):
    resolved, source_paths = planned_input
    expected_entries = ["gamma", "alpha", "delta", "beta"]
    assert [plan.entry.id for plan in resolved.plans] == expected_entries
    assert [plan.theme_id for plan in resolved.plans] == [
        "T001",
        "T002",
        "T003",
        "T004",
    ]
    for instruction in (
        resolved.request.story,
        *resolved.rules.themes,
        *resolved.rules.frames,
    ):
        assert re.search(r"\bT\d{3}\b", instruction) is None
    settings = StoryRunSettings(
        provider=StoryProviderSettings(model="test-model"),
        **resolved.runtime.model_dump(),
        quality=resolved.quality,
    )
    store = LocalStoryRunStore(tmp_path / "runs", tmp_path / "prompts")
    model = RetryingPlannedModel()
    with pytest.raises(StoryRunIncompleteError) as failure:
        await StoryStudio(model, store, settings).run(resolved)
    run_id = failure.value.run_id
    snapshot = store.inspect(run_id)
    assert failure.value.missing_themes == 0
    assert failure.value.missing_frames == 1
    assert set(snapshot.frames) == {"T001", "T002", "T004"}
    assert snapshot.input == resolved
    assert snapshot.manifest.input_fingerprint == resolved.fingerprint()
    assert len(model.theme_calls) == 3
    for messages, selected in zip(
        model.theme_calls,
        [expected_entries[:2], expected_entries[2:], expected_entries[2:]],
        strict=True,
    ):
        assert_selected_facts(messages, StoryStage.THEMES, selected)
    retry_payloads = [
        json.loads(messages[1].content) for messages in model.theme_calls[1:]
    ]
    assert retry_payloads[0]["input_context"] == retry_payloads[1]["input_context"]
    for messages in model.frame_calls:
        theme_id = json.loads(messages[1].content)["theme"]["theme_id"]
        assert_selected_facts(
            messages, StoryStage.FRAMES, [expected_entries[int(theme_id[1:]) - 1]]
        )

    frozen_path = tmp_path / "runs" / run_id / "resolved-input.json"
    frozen_bytes = frozen_path.read_bytes()
    saved_frame_path = tmp_path / "runs" / run_id / "frames" / "T001" / "F01.json"
    saved_bytes = saved_frame_path.read_bytes()
    for path in source_paths:
        path.unlink()
    assert all(not path.exists() for path in source_paths)
    offline_store = LocalStoryRunStore(tmp_path / "runs")
    restored = offline_store.inspect(run_id)
    assert restored.input == resolved
    assert {source.kind for source in restored.input.sources} >= {
        "document",
        "catalog",
        "module",
        "policy",
        "system",
    }
    resumed_model = RoutedStoryModel()
    completed = await StoryStudio(resumed_model, offline_store, settings).resume(run_id)
    assert resumed_model.stages == [StoryStage.FRAMES]
    assert_selected_facts(resumed_model.messages[0], StoryStage.FRAMES, ["delta"])
    assert len(completed.result.themes) == 4
    assert frozen_path.read_bytes() == frozen_bytes
    assert saved_frame_path.read_bytes() == saved_bytes
    assert [theme.theme.theme_id for theme in completed.result.themes] == [
        plan.theme_id for plan in resolved.plans
    ]
    assert offline_store.inspect(run_id).input.fingerprint() == resolved.fingerprint()


@pytest.mark.asyncio
async def test_frame_assignment_projection_survives_partial_retry_and_offline_resume(
    tmp_path, planned_input
):
    _, source_paths = planned_input
    resolved = resolve_story_input(
        load_story_document(source_paths[0]),
        InputOverrides(frames_per_theme=2, generation_retries=2),
        asset_root=source_paths[1].parent.parent,
    )
    settings = StoryRunSettings(
        provider=StoryProviderSettings(model="test-model"),
        **resolved.runtime.model_dump(),
        quality=resolved.quality,
    )
    store = LocalStoryRunStore(tmp_path / "runs", tmp_path / "prompts")
    model = RetryingPlannedModel(failed_frame="F02")
    with pytest.raises(StoryRunIncompleteError) as failure:
        await StoryStudio(model, store, settings).run(resolved)
    run_id = failure.value.run_id
    assert failure.value.missing_frames == 1
    snapshot = store.inspect(run_id)
    assert [frame.frame_id for frame in snapshot.frames["T003"].frames] == ["F01"]

    for messages in model.theme_calls:
        payload = json.loads(messages[1].content)
        assert all(
            not plan["frame_slots"] for plan in payload["input_context"]["plans"]
        )
        assert "VIEW_" not in "\n".join(message.content for message in messages)
    failed_contexts = []
    viewpoints = {"F01": "front", "F02": "rear"}
    for messages in model.frame_calls:
        payload = json.loads(messages[1].content)
        frame_ids = payload["requested_frame_slots"]
        plans = payload["input_context"]["plans"]
        assert len(plans) == 1
        plan = plans[0]
        entry_id = plan["entry"]["id"]
        assert plan["frame_slots"] == [
            {
                "frame_id": frame_id,
                "rules": [
                    f"VIEW_{entry_id.upper()}_{frame_id} uses "
                    f"the {viewpoints[frame_id]} station viewpoint."
                ],
            }
            for frame_id in frame_ids
        ]
        for other_frame in {"F01", "F02"} - set(frame_ids):
            assert f"VIEW_{entry_id.upper()}_{other_frame}" not in "\n".join(
                message.content for message in messages
            )
        if plan["theme_id"] == "T003" and frame_ids == ["F02"]:
            failed_contexts.append(payload["input_context"])
    assert len(failed_contexts) == 2
    assert failed_contexts[0] == failed_contexts[1]

    frozen_path = tmp_path / "runs" / run_id / "resolved-input.json"
    frame_path = tmp_path / "runs" / run_id / "frames" / "T003" / "F01.json"
    frozen_bytes = frozen_path.read_bytes()
    frame_bytes = frame_path.read_bytes()
    for path in source_paths:
        path.unlink()
    offline_store = LocalStoryRunStore(tmp_path / "runs")
    resumed_model = RoutedStoryModel()
    completed = await StoryStudio(resumed_model, offline_store, settings).resume(run_id)

    assert resumed_model.stages == [StoryStage.FRAMES]
    resumed = json.loads(resumed_model.messages[0][1].content)
    assert resumed["requested_frame_slots"] == ["F02"]
    assert resumed["input_context"] == failed_contexts[0]
    assert len(completed.result.themes) == 4
    assert all(len(theme.frames) == 2 for theme in completed.result.themes)
    assert frozen_path.read_bytes() == frozen_bytes
    assert frame_path.read_bytes() == frame_bytes
    assert offline_store.inspect(run_id).input == resolved


@pytest.fixture
def frozen_run(tmp_path):
    settings = StoryRunSettings(provider=StoryProviderSettings(model="test-model"))
    resolved = make_story_input(make_story_request(), settings)
    store = LocalStoryRunStore(tmp_path / "runs", tmp_path / "prompts")
    snapshot = store.create(resolved, settings)
    return store, snapshot, tmp_path / "runs" / snapshot.run_id


@pytest.mark.parametrize("legacy_manifest", [False, True])
def test_old_run_without_resolved_input_is_rejected(frozen_run, legacy_manifest):
    store, snapshot, directory = frozen_run
    (directory / "resolved-input.json").unlink()
    if legacy_manifest:
        path = directory / "manifest.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        del payload["input_fingerprint"]
        path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(
        StoryStorageError, match="resolved-input.json|input_fingerprint"
    ):
        store.inspect(snapshot.run_id)


@pytest.mark.parametrize("target", ["manifest", "resolved"])
def test_input_fingerprint_detects_tampering(frozen_run, target):
    store, snapshot, directory = frozen_run
    if target == "manifest":
        path = directory / "manifest.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["input_fingerprint"] = "0" * 64
    else:
        path = directory / "resolved-input.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["runtime"]["concurrency"] = 3
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(StoryStorageError, match="输入快照指纹不匹配"):
        store.inspect(snapshot.run_id)


@pytest.mark.parametrize("duplicate", ["request", "rules", "runtime", "quality"])
def test_snapshot_rejects_conflicting_duplicate_configuration(frozen_run, duplicate):
    store, snapshot, directory = frozen_run
    filename = (
        f"{duplicate}.json" if duplicate in ("request", "rules") else "manifest.json"
    )
    path = directory / filename
    payload = json.loads(path.read_text(encoding="utf-8"))
    if duplicate == "request":
        payload["story"] = "A different station."
    elif duplicate == "rules":
        payload["frames"].append("An uncompiled station rule.")
    elif duplicate == "runtime":
        payload["settings"]["concurrency"] = 3
    else:
        payload["settings"]["quality"]["frames"]["mode"] = "off"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(StoryStorageError):
        store.inspect(snapshot.run_id)


@pytest.mark.parametrize("setting", ["concurrency", "quality"])
def test_create_rejects_settings_not_compiled_into_input(tmp_path, setting):
    resolved = make_story_input(make_story_request())
    values = {"provider": StoryProviderSettings(model="test-model")}
    if setting == "concurrency":
        values["concurrency"] = 3
    else:
        values["quality"] = {"frames": {"mode": "off"}}
    settings = StoryRunSettings.model_validate(values)
    store = LocalStoryRunStore(tmp_path / "runs", tmp_path / "prompts")
    with pytest.raises(StoryStorageError):
        store.create(resolved, settings)
    assert not (tmp_path / "runs").exists()
    assert not (tmp_path / "prompts").exists()


@pytest.mark.asyncio
async def test_resume_rejects_new_settings_before_model_calls(frozen_run):
    store, snapshot, _ = frozen_run
    changed = StoryRunSettings(
        provider=snapshot.manifest.settings.provider, concurrency=3
    )
    model = RoutedStoryModel()
    with pytest.raises(StoryStorageError, match="manifest"):
        await StoryStudio(model, store, changed).resume(snapshot.run_id)
    assert model.stages == []
