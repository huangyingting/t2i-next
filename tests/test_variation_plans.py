from __future__ import annotations

import pytest

from t2i_prompt_pipeline.variation_plans import build_variation_plan


def test_plan_rotates_first_focus_by_theme_id() -> None:
    frame_ids = tuple(f"T01-F{index:02d}" for index in range(1, 6))
    first = build_variation_plan("T01", frame_ids)

    assert first["T01-F01"].startswith("空间关系")
    assert first["T01-F02"].startswith("人物互动")
    assert first["T01-F03"].startswith("锚点细节")

    second = build_variation_plan("T02", ("T02-F01",))
    fifth = build_variation_plan("T05", ("T05-F01",))

    assert second["T02-F01"].startswith("人物互动")
    assert fifth["T05-F01"].startswith("间接构图")


def test_plan_is_stable_for_targeted_completion() -> None:
    complete = build_variation_plan(
        "T03",
        tuple(f"T03-F{index:02d}" for index in range(1, 7)),
    )
    targeted = build_variation_plan("T03", ("T03-F04", "T03-F06"))

    assert targeted["T03-F04"] == complete["T03-F04"]
    assert targeted["T03-F06"] == complete["T03-F06"]
    assert targeted["T03-F06"].startswith("第 2 轮变化")


def test_interaction_focus_uses_existing_tools_only() -> None:
    plan = build_variation_plan("T01", ("T01-F02",))

    assert "工具仅取自 brief 或 Theme" in plan["T01-F02"]
    assert "真实记录工具" not in plan["T01-F02"]
    assert "完整面部或仅手部入画" in plan["T01-F02"]


def test_detail_focus_keeps_the_action_and_conditional_hand_crop() -> None:
    plan = build_variation_plan("T02", ("T02-F02",))

    assert "呈现核心动作" in plan["T02-F02"]
    assert "brief 允许时只取手部" in plan["T02-F02"]
    assert "手部代表可见人物，expression=null" in plan["T02-F02"]


def test_plan_rejects_mismatched_ids() -> None:
    with pytest.raises(ValueError, match="不属于 Theme"):
        build_variation_plan("T01", ("T02-F01",))
