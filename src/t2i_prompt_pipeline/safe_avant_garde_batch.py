"""Safe avant-garde task definitions for the shared batch executor."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from t2i_prompt_pipeline.batch import BatchLimits, BatchResult, BatchTask, run_batch
from t2i_prompt_pipeline.models import (
    AppConfig,
    ContentLevel,
    FrameMode,
    GenerationSpec,
    OutputLanguage,
)

SAFE_AVANT_GARDE_THEME_COUNT = 100
SAFE_AVANT_GARDE_FRAMES_PER_THEME = 6


@dataclass(frozen=True)
class AvantGardeArtist:
    slug: str
    name: str


@dataclass(frozen=True)
class CastConfiguration:
    slug: str
    description: str
    female_count: int
    male_count: int


@dataclass(frozen=True)
class SafeAvantGardeTask:
    task_id: str
    artist: AvantGardeArtist
    cast: CastConfiguration
    spec: GenerationSpec


AVANT_GARDE_ARTISTS = (
    AvantGardeArtist("wassily_kandinsky", "瓦西里·康定斯基"),
    AvantGardeArtist("kazimir_malevich", "卡济米尔·马列维奇"),
    AvantGardeArtist("piet_mondrian", "皮特·蒙德里安"),
    AvantGardeArtist("marcel_duchamp", "马塞尔·杜尚"),
    AvantGardeArtist("man_ray", "曼·雷"),
    AvantGardeArtist("hannah_hoch", "汉娜·赫希"),
    AvantGardeArtist("sophie_taeuber_arp", "索菲·陶柏-阿尔普"),
    AvantGardeArtist("jean_arp", "让·阿尔普"),
    AvantGardeArtist("el_lissitzky", "埃尔·利西茨基"),
    AvantGardeArtist("alexander_rodchenko", "亚历山大·罗德琴科"),
    AvantGardeArtist("lyubov_popova", "柳博芙·波波娃"),
    AvantGardeArtist("varvara_stepanova", "瓦尔瓦拉·斯捷潘诺娃"),
    AvantGardeArtist("natalia_goncharova", "娜塔莉亚·冈察洛娃"),
    AvantGardeArtist("sonia_delaunay", "索尼娅·德劳内"),
    AvantGardeArtist("umberto_boccioni", "翁贝托·薄丘尼"),
    AvantGardeArtist("giacomo_balla", "贾科莫·巴拉"),
    AvantGardeArtist("luigi_russolo", "路易吉·鲁索洛"),
    AvantGardeArtist("giorgio_de_chirico", "乔治·德·基里科"),
    AvantGardeArtist("max_ernst", "马克斯·恩斯特"),
    AvantGardeArtist("joan_miro", "胡安·米罗"),
    AvantGardeArtist("rene_magritte", "勒内·马格利特"),
    AvantGardeArtist("salvador_dali", "萨尔瓦多·达利"),
    AvantGardeArtist("leonora_carrington", "莱奥诺拉·卡林顿"),
    AvantGardeArtist("paul_klee", "保罗·克利"),
)

SAFE_CAST_CONFIGURATIONS = (
    CastConfiguration(
        slug="one_woman_one_man",
        description="一名成年女性和一名成年男性",
        female_count=1,
        male_count=1,
    ),
    CastConfiguration(
        slug="two_women_one_man",
        description="两名成年女性和一名成年男性",
        female_count=2,
        male_count=1,
    ),
    CastConfiguration(
        slug="three_women",
        description="三名成年女性",
        female_count=3,
        male_count=0,
    ),
)


def build_safe_avant_garde_tasks() -> tuple[SafeAvantGardeTask, ...]:
    tasks = []
    for artist in AVANT_GARDE_ARTISTS:
        for cast in SAFE_CAST_CONFIGURATIONS:
            tasks.append(
                SafeAvantGardeTask(
                    task_id=f"{artist.slug}--{cast.slug}",
                    artist=artist,
                    cast=cast,
                    spec=GenerationSpec(
                        brief=_build_brief(artist, cast),
                        theme_count=SAFE_AVANT_GARDE_THEME_COUNT,
                        frames_per_theme=SAFE_AVANT_GARDE_FRAMES_PER_THEME,
                        female_count=cast.female_count,
                        male_count=cast.male_count,
                        content_level=ContentLevel.AESTHETIC,
                        frame_mode=FrameMode.VARIATIONS,
                        output_language=OutputLanguage.CHINESE,
                    ),
                )
            )
    return tuple(tasks)


async def run_safe_avant_garde_batch(
    config: AppConfig,
    state_file: Path,
    *,
    limits: BatchLimits | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> BatchResult:
    return await run_batch(
        config,
        tuple(
            BatchTask(
                task.task_id,
                task.spec,
                f"{task.artist.name} / {task.cast.description}",
            )
            for task in build_safe_avant_garde_tasks()
        ),
        state_file,
        limits=limits,
        on_progress=on_progress,
    )


def _build_brief(
    artist: AvantGardeArtist,
    cast: CastConfiguration,
) -> str:
    return (
        f"以{artist.name}的先锋艺术风格创作{cast.description}的先锋时装群像。"
        "所有人物均明确为25岁以上成年人，全程穿着不透明且完整覆盖胸部、臀部和"
        "性器官区域的先锋服装，不使用内衣、泳装、透视材质或裸色错视，不出现"
        "裸露、性行为、亲吻或性化触摸。每个主题采用不同的场所、色彩体系、"
        "人物调度和一件明确的抽象艺术装置作为视觉锚点，以姿态张力、服装造型、"
        "空间关系和光影塑形构成画面；同一主题的六个画面共享人物、服饰、场景"
        "和装置，只进行互不依赖的取景、机位与构图变化。"
    )
