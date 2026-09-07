from __future__ import annotations

from t2i_story_pipeline.models import (
    CinematographyIntent,
    CreativeIntent,
    NarrativeMode,
    NarrativeReview,
    NarrativeScene,
    NarrativeScores,
    NarrativeSequence,
    NarrativeTheme,
    NarrativeThemeBatch,
    OutputLanguage,
    ReviewDimension,
    ReviewIssue,
    SceneAction,
    SceneReview,
    StoryBeat,
    StoryBlueprint,
    StoryCharacter,
    StoryRelationship,
    StoryRequest,
)


def make_story_request(
    *,
    theme_count: int = 1,
    frames_per_theme: int = 2,
    output_language: OutputLanguage = OutputLanguage.CHINESE,
) -> StoryRequest:
    return StoryRequest(
        story=(
            "1930年代秋夜，两名三十多岁的成年人在旧车站重逢。"
            "他们确认彼此身份后一起寻找遗失的行李，气氛由警惕转为释然。"
            "湿润月台反射暖色站灯，使用平视中景和侧后方灯光。"
        ),
        theme_count=theme_count,
        frames_per_theme=frames_per_theme,
        output_language=output_language,
    )


def make_narrative_theme(index: int = 1) -> NarrativeTheme:
    emotional_cores = (
        "迟来的信任恢复",
        "戒备在共同劳作中消退",
        "失物承载未说出口的歉意",
        "离别倒计时迫使旧友靠近",
        "共同记忆被一件旧物唤醒",
        "犹豫被一次主动伸手打破",
        "沉默关系重新获得方向",
        "寻找物件转化为寻找理解",
        "短暂协作抵抗漫长疏离",
        "离站之前完成迟到的和解",
    )
    moments = (
        "两只手同时握住皮箱提手",
        "旧照片在两人掌心之间展开",
        "行李车轮压过积水后突然停住",
        "列车蒸汽短暂遮住又显出两人",
        "一人松手而另一人接稳皮箱",
        "站灯熄灭前两人并肩迈出一步",
        "皮箱锁扣弹开露出保存完好的信件",
        "末班车鸣笛时两人停止争执",
        "一人替另一人擦去照片上的雨水",
        "分离的影子在站牌下重新交叠",
    )
    motifs = (
        "分离铁轨与汇合双手",
        "旧照片折痕与人物距离",
        "积水波纹与迟疑脚步",
        "蒸汽遮挡与身份显露",
        "皮箱锁扣与封闭心绪",
        "站灯明灭与关系转折",
        "雨痕方向与共同移动",
        "长椅空位与重新并肩",
        "手套磨损与克制触碰",
        "站牌箭头与人物选择",
    )
    row = (index - 1) // 10
    column = (index - 1) % 10
    core = emotional_cores[row]
    moment = moments[column]
    motif = motifs[column]
    counter_motif = motifs[row]
    visual_motif = (
        f"{motif}贯穿六个画面" if row == column else f"{motif}与{counter_motif}交替出现"
    )
    return NarrativeTheme(
        theme_id=f"T{index:03d}",
        title=f"{core}：{motif}",
        creative_intent=CreativeIntent(
            emotional_core=core,
            narrative_tension=f"即将离站的列车与{core}",
            decisive_moment=f"{moment}，使{core}第一次变得可见",
            visual_motif=visual_motif,
            motif_progression=(f"{motif}从分隔人物的环境痕迹转为连接两人的动作结果"),
            restraint=f"无关旅客、装饰性雨伞以及偏离{core}的道具",
        ),
    )


def make_narrative_theme_batch(
    *,
    start: int = 1,
    count: int = 1,
) -> NarrativeThemeBatch:
    return NarrativeThemeBatch(
        themes=[make_narrative_theme(index) for index in range(start, start + count)]
    )


def make_story_blueprint() -> StoryBlueprint:
    return StoryBlueprint(
        title="旧站重逢",
        logline="两位旧友在车站重逢并找回遗失的行李。",
        time="1930年代秋夜",
        location="旧车站月台",
        environment="湿润月台、木质长椅与旧式行李车",
        atmosphere="由警惕转为释然",
        characters=[
            StoryCharacter(
                character_id="C01",
                display_name="林岚",
                age=31,
                role="旅行者",
                appearance="短黑发、椭圆脸、深色眼睛",
                outfit="深蓝羊毛风衣、灰长裤和黑皮鞋",
                initial_emotion="警惕",
            ),
            StoryCharacter(
                character_id="C02",
                display_name="陈川",
                age=34,
                role="旧友",
                appearance="深棕短发、方脸、浓眉",
                outfit="棕色呢外套、白衬衫和深色皮鞋",
                initial_emotion="急切",
            ),
        ],
        relationships=[
            StoryRelationship(
                participant_ids=["C01", "C02"],
                source_relationship="两名三十多岁的成年人在旧车站重逢",
                relationship="两名三十多岁的成年人在旧车站重逢",
                interaction_dynamic="从试探确认转为共同协作",
            )
        ],
        beats=[
            StoryBeat(
                beat_id="B01",
                participant_ids=["C01", "C02"],
                source_action="他们确认彼此身份",
                action="两人在站牌下确认彼此身份",
                visible_response="双方放松肩膀并靠近半步",
                emotional_turn="警惕转为确认",
                visible_result="两人不再保持相互戒备的距离",
            ),
            StoryBeat(
                beat_id="B02",
                participant_ids=["C01", "C02"],
                source_action="一起寻找遗失的行李",
                action="两人合力从行李车下拉出皮箱",
                visible_response="两人相视微笑",
                emotional_turn="焦急转为释然",
                visible_result="皮箱完整停在两人脚边",
            ),
        ],
        cinematography=CinematographyIntent(
            camera="平视中景为主，结尾使用稍宽镜头",
            lighting="暖色站灯从侧后方照亮人物",
            color_and_texture="低饱和蓝灰与暖黄反光",
        ),
    )


def make_narrative_sequence(
    *,
    frame_count: int = 2,
    theme: NarrativeTheme | None = None,
) -> NarrativeSequence:
    scenes = [
        NarrativeScene(
            scene_id="S01",
            beat_id="B01",
            mode=NarrativeMode.DRAMATIC,
            source_context=[
                "他们确认彼此身份后",
                "一起寻找遗失的行李",
            ],
            visible_character_ids=["C01", "C02"],
            temporal_spatial_opening="1930年代秋夜，雨后的旧车站月台。",
            environmental_evidence=[
                "褪色站牌和锈蚀行李车停在湿润铁轨旁。",
            ],
            character_entry=("林岚刚从末班列车下来，陈川从站牌阴影中快步迎上。"),
            present_actions=[
                SceneAction(
                    participant_ids=["C01", "C02"],
                    action=("两人同时俯身抓住卡在行李车下的皮箱提手。"),
                    visible_response=("车轮轻晃，积水沿铁轨荡开细小波纹。"),
                    resulting_state=("皮箱被拉到两人脚边，锁扣仍保持完整。"),
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
            thematic_closure=("被找回的不只是行李，也是中断多年的信任。"),
        ),
        NarrativeScene(
            scene_id="S02",
            beat_id="B02",
            mode=NarrativeMode.ATMOSPHERIC,
            source_context=["气氛由警惕转为释然"],
            visible_character_ids=["C01", "C02"],
            temporal_spatial_opening="同一秋夜，末班列车即将离站。",
            environmental_evidence=[
                "空月台尽头只剩一盏站灯和连续雨痕。",
            ],
            character_entry="两人并肩站在找回的皮箱旁。",
            present_actions=[
                SceneAction(
                    participant_ids=["C01", "C02"],
                    action="林岚把旧照片递还给陈川。",
                    visible_response="陈川双手接过并露出微笑。",
                    resulting_state="照片与皮箱都回到各自主人的手中。",
                )
            ],
            material_and_physical_feedback=[
                "湿皮箱边角留下擦痕，照片表面映出微弱灯光。",
            ],
            camera_composition="稍宽的平视镜头保留空月台纵深。",
            lighting_and_color="暖色站灯包围两人，远处保持蓝灰暗部。",
            sensory_evidence=[
                "蒸汽和白雾在灯下缓慢散开，表现潮冷空气。",
            ],
            thematic_closure="空旷月台见证了一次迟到多年的和解。",
        ),
    ]
    while len(scenes) < frame_count:
        scene = scenes[-1].model_copy(deep=True)
        scene.scene_id = f"S{len(scenes) + 1:02d}"
        scenes.append(scene)
    if theme is not None:
        phases = (
            "作为分隔人物的环境痕迹尚未形成连接",
            "在人物靠近时第一次进入共同焦点",
            "被当前动作推动并产生方向变化",
            "在环境反馈中由阻隔转为呼应",
            "把两个人物的动作结果连接起来",
            "在最终物件状态中完成主题收束",
        )
        for scene, phase in zip(scenes, phases, strict=False):
            scene.environmental_evidence.append(
                f"{theme.creative_intent.visual_motif}，{phase}。"
            )
            scene.thematic_closure = (
                f"{phase}，让{theme.creative_intent.emotional_core}获得可见的动作结果。"
            )
    return NarrativeSequence(scenes=scenes[:frame_count])


def make_narrative_review(
    *,
    passing: bool,
    frame_count: int = 2,
) -> NarrativeReview:
    scores = NarrativeScores(
        temporal_spatial_grounding=5,
        environmental_storytelling=5,
        causal_action=5 if passing else 2,
        physical_feedback=5,
        cinematography_integration=5,
        sensory_visualization=5,
        thematic_closure=5,
        language_coherence=5,
        creative_unity=5,
        story_specificity=5,
    )
    issues = (
        []
        if passing
        else [
            ReviewIssue(
                scene_id="S01",
                dimension=ReviewDimension.CAUSAL_ACTION,
                problem="当前动作与结果之间缺少可见反馈。",
                required_change="补充行李车晃动和积水波纹。",
            )
        ]
    )
    return NarrativeReview(
        scene_reviews=[
            SceneReview(
                scene_id=f"S{index:02d}",
                scores=(
                    scores
                    if index == 1
                    else NarrativeScores(
                        temporal_spatial_grounding=5,
                        environmental_storytelling=5,
                        causal_action=5,
                        physical_feedback=5,
                        cinematography_integration=5,
                        sensory_visualization=5,
                        thematic_closure=5,
                        language_coherence=5,
                        creative_unity=5,
                        story_specificity=5,
                    )
                ),
                issues=issues if index == 1 else [],
            )
            for index in range(1, frame_count + 1)
        ],
        overall_summary=(
            "全部场景达到要求。" if passing else "首个场景需要补充动作反馈。"
        ),
    )
