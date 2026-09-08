from __future__ import annotations

from t2i_story_pipeline.models import (
    ContentLevel,
    NarrativeFrame,
    NarrativeFrameSequence,
    NarrativeTheme,
    NarrativeThemeBatch,
    NarrativeThemeResult,
    StoryRequest,
    StoryResult,
    TokenUsage,
)


def make_story_request(
    *,
    theme_count: int = 1,
    frames_per_theme: int = 2,
    female_count: int | None = None,
    male_count: int | None = None,
    content_level: ContentLevel = ContentLevel.AESTHETIC,
    source_prompt_stem: str | None = None,
) -> StoryRequest:
    return StoryRequest(
        story=(
            "1930年代秋夜，两名三十岁的成年人在旧车站重逢。"
            "他们双方自愿拥抱，彼此回应且任何一方都可以停止。"
            "他们一起寻找遗失的行李，湿润月台反射暖色站灯。"
        ),
        theme_count=theme_count,
        frames_per_theme=frames_per_theme,
        female_count=female_count,
        male_count=male_count,
        content_level=content_level,
        source_prompt_stem=source_prompt_stem,
    )


def make_theme(index: int = 1) -> NarrativeTheme:
    return NarrativeTheme(
        theme_id=f"T{index:03d}",
        title=f"遗失行李的方向 {index}",
        premise=f"两名成年人从第 {index} 条线索确认行李去向。",
        style="1930年代北平电影风格",
    )


def make_theme_batch(
    *,
    start: int = 1,
    count: int = 1,
    semantic_name: str = "lost_luggage_reunion",
) -> NarrativeThemeBatch:
    return NarrativeThemeBatch(
        semantic_name=semantic_name,
        themes=[make_theme(index) for index in range(start, start + count)]
    )


def make_frame_sequence(
    *,
    frame_count: int = 2,
    theme_index: int = 1,
) -> NarrativeFrameSequence:
    actions = (
        "左侧人物正在握紧旧皮箱提手，右侧人物保持俯身姿态，"
        "指节与皮革受力处清晰可见",
        "右侧人物正在掀起旧皮箱搭扣，左侧人物保持半蹲姿态，"
        "铜扣与指腹接触处清晰可见",
        "左侧人物正在按住皮箱上的行李标签，右侧人物保持直立姿态，"
        "纸张边缘因压力贴紧皮革",
        "右侧人物正在指向箱角的新鲜裂痕，左侧人物保持俯身姿态，"
        "裂口纤维与指尖处于同一焦点",
        "左侧人物正在托住皮箱下沉的箱底，右侧人物保持屈膝姿态，"
        "皮革底面因承重形成浅凹",
        "右侧人物正在扣合皮箱锁舌，左侧人物保持直立姿态，"
        "锁舌与锁孔在指尖下准确咬合",
    )
    return NarrativeFrameSequence(
        frames=[
            NarrativeFrame(
                frame_id=f"F{index:02d}",
                prose=(
                    "1930年代北平电影风格，"
                    f"1930年代秋夜，旧车站第{theme_index}站台。"
                    f"两名三十岁的成年人停在第{index}根站柱旁，"
                    "短发被雨水打湿，深色大衣沾着月台水汽，"
                    "紧绷的目光落在同一只旧皮箱上。"
                    f"此刻，{actions[index - 1]}。"
                    "镜头采用平视中景，站柱构成纵深，浅景深同时聚焦"
                    "提手与两人的警惕目光。"
                    "光线来自侧后方暖色站灯，潮湿反光烘托警惕气氛。"
                ),
            )
            for index in range(1, frame_count + 1)
        ]
    )


def make_story_result(
    *,
    theme_count: int = 1,
    frames_per_theme: int = 2,
    female_count: int | None = None,
    male_count: int | None = None,
    content_level: ContentLevel = ContentLevel.AESTHETIC,
    source_prompt_stem: str | None = None,
) -> StoryResult:
    return StoryResult(
        run_id="abcdef123456",
        semantic_name="lost_luggage_reunion",
        request=make_story_request(
            theme_count=theme_count,
            frames_per_theme=frames_per_theme,
            female_count=female_count,
            male_count=male_count,
            content_level=content_level,
            source_prompt_stem=source_prompt_stem,
        ),
        themes=[
            NarrativeThemeResult(
                theme=make_theme(index),
                frames=make_frame_sequence(
                    frame_count=frames_per_theme,
                    theme_index=index,
                ).frames,
            )
            for index in range(1, theme_count + 1)
        ],
        usage=TokenUsage(total_tokens=30),
    )
