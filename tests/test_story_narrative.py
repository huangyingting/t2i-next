from __future__ import annotations

from t2i_story_pipeline.models import (
    NarrativeMode,
    NarrativeScene,
    NarrativeSequence,
    SceneAction,
    VisibleText,
)
from t2i_story_pipeline.render import render_narratives
from tests.story_factories import (
    make_narrative_sequence,
    make_narrative_theme,
    make_story_blueprint,
)


def test_narrative_scene_renders_cinematic_prose_in_story_order() -> None:
    scene = NarrativeScene(
        scene_id="S01",
        beat_id="B01",
        mode=NarrativeMode.DRAMATIC,
        source_context=["他们确认彼此身份后", "一起寻找遗失的行李"],
        visible_character_ids=["C01", "C02"],
        temporal_spatial_opening="1930年代秋夜，雨后的旧车站月台。",
        environmental_evidence=[
            "褪色站牌和锈蚀行李车停在湿润铁轨旁。",
        ],
        character_entry=("林岚刚从末班列车下来，陈川从站牌阴影中快步迎上。"),
        present_actions=[
            SceneAction(
                participant_ids=["C01", "C02"],
                action="两人同时俯身抓住卡在行李车下的皮箱提手。",
                visible_response="车轮轻晃，积水沿铁轨荡开细小波纹。",
                resulting_state="皮箱被拉到两人脚边，锁扣仍保持完整。",
            )
        ],
        material_and_physical_feedback=[
            "湿皮革表面反射站灯，粗糙提手在手套下弯折。",
        ],
        camera_composition=("平视中景沿月台轴线拍摄，焦点落在两人共同握住的提手。"),
        lighting_and_color=("侧后方暖色站灯勾勒人物轮廓，蓝灰雨夜留在背景阴影中。"),
        sensory_evidence=[
            "铁轨边缘的水汽和人物呼出的白雾表现夜间寒意。",
        ],
        thematic_closure="被找回的不只是行李，也是中断多年的信任。",
    )

    rendered = render_narratives(
        make_story_blueprint(),
        make_narrative_theme(),
        NarrativeSequence(scenes=[scene]),
    )[0]

    assert rendered.prose.startswith("1930年代秋夜")
    assert rendered.prose.endswith("中断多年的信任。")
    assert rendered.prose.index("褪色站牌") < rendered.prose.index("林岚刚从")
    assert rendered.prose.index("两人同时俯身") < rendered.prose.index("湿皮革表面")
    assert rendered.prose.index("平视中景") < rendered.prose.index("侧后方暖色站灯")
    assert "时间与地点：" not in rendered.prose
    assert "人物调度：" not in rendered.prose
    assert "C01" not in rendered.prose
    assert "互动与动作：" in rendered.prompt
    assert "摄影：" in rendered.prompt


def test_tableau_uses_only_source_context_for_backstory() -> None:
    scene = NarrativeScene(
        scene_id="S01",
        beat_id="B01",
        mode=NarrativeMode.TABLEAU,
        source_context=["一起寻找遗失的行李"],
        visible_character_ids=["C01"],
        temporal_spatial_opening="午后，安静的旧书店窗边。",
        environmental_evidence=["磨损木书架与积尘书脊围住狭窄角落。"],
        character_entry="林岚独自坐在窗边木椅上。",
        present_actions=[
            SceneAction(
                participant_ids=["C01"],
                action="她用拇指缓慢抚平旧书卷起的封面。",
                visible_response="脆弱纸页随指尖压力轻微下沉。",
                resulting_state="封面重新贴合在泛黄扉页上。",
            )
        ],
        material_and_physical_feedback=[
            "粗糙纸纤维和光滑指甲形成细微质感对比。",
        ],
        camera_composition="近距离侧面中景把手指与书脊放在同一焦平面。",
        lighting_and_color="窗侧暖光照亮纸页边缘，书架保持低亮度。",
        sensory_evidence=["光束中的浮尘表现室内长期封闭的空气。"],
        thematic_closure="被抚平的封面让停滞的午后出现一丝秩序。",
    )

    prose = render_narratives(
        make_story_blueprint(),
        make_narrative_theme(),
        NarrativeSequence(scenes=[scene]),
    )[0].prose

    assert "她用拇指" in prose
    assert "多年未见" not in prose


def test_visible_text_is_rendered_verbatim_in_double_quotes() -> None:
    sequence = make_narrative_sequence(frame_count=1)
    sequence.scenes[0].visible_text = [
        VisibleText(
            content="北平站",
            carrier="褪色木质站牌",
            placement="人物后方画面右上角",
            appearance="手写黑色宋体，油漆边缘剥落",
        )
    ]

    rendered = render_narratives(
        make_story_blueprint(),
        make_narrative_theme(),
        sequence,
    )[0]

    assert '"北平站"' in rendered.prose
    assert '"北平站"' in rendered.prompt
    assert "褪色木质站牌" in rendered.prompt


def test_renderer_replaces_internal_ids_and_avoids_double_restraint() -> None:
    sequence = make_narrative_sequence(frame_count=1)
    sequence.scenes[0].character_entry = (
        "C01从站牌旁走向C02，B01至B03的寻找已经结束。"
    )
    theme = make_narrative_theme()
    theme.creative_intent.restraint = "舍弃无关旅客"

    rendered = render_narratives(
        make_story_blueprint(),
        theme,
        sequence,
    )[0]

    assert "C01" not in rendered.prose
    assert "C02" not in rendered.prose
    assert "B01" not in rendered.prose
    assert "B03" not in rendered.prose
    assert "舍弃舍弃" not in rendered.prompt
