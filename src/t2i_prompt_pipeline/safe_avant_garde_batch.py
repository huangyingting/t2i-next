"""Resumable fixed batch for safe avant-garde group portraits."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError, model_validator

from t2i_prompt_pipeline.errors import ConfigurationError, RunStoreError
from t2i_prompt_pipeline.models import (
    AppConfig,
    ContentLevel,
    FrameMode,
    GenerationSpec,
    Model,
    OutputLanguage,
)
from t2i_prompt_pipeline.pipeline import PromptStudio
from t2i_prompt_pipeline.providers.openai_compatible import (
    OpenAICompatibleProvider,
)
from t2i_prompt_pipeline.store import LocalRunStore
from t2i_prompt_pipeline.theme_similarity import ThemeSimilarityAnalyzer

SAFE_AVANT_GARDE_BATCH_ID = "safe-avant-garde-24x3-100x6-v1"
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


class BatchTaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"


class BatchTaskProgress(Model):
    status: BatchTaskStatus = BatchTaskStatus.PENDING
    run_id: str | None = None
    prompt_file: str | None = None

    @model_validator(mode="after")
    def fields_match_status(self) -> BatchTaskProgress:
        if self.status == BatchTaskStatus.PENDING:
            if self.run_id is not None or self.prompt_file is not None:
                raise ValueError("pending 任务不能记录 run 或提示词文件")
        elif self.status == BatchTaskStatus.RUNNING:
            if self.run_id is None or self.prompt_file is not None:
                raise ValueError("running 任务必须只记录 run_id")
        elif self.run_id is None or self.prompt_file is None:
            raise ValueError("completed 任务必须记录 run_id 和提示词文件")
        return self


class SafeAvantGardeBatchState(Model):
    batch_id: Literal["safe-avant-garde-24x3-100x6-v1"] = (
        SAFE_AVANT_GARDE_BATCH_ID
    )
    tasks: dict[str, BatchTaskProgress] = Field(min_length=72, max_length=72)


@dataclass(frozen=True)
class SafeAvantGardeBatchResult:
    completed_tasks: int
    generated_frames: int
    state_file: Path


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
    on_progress: Callable[[str], None] | None = None,
) -> SafeAvantGardeBatchResult:
    tasks = build_safe_avant_garde_tasks()
    resolved_state_file = state_file.resolve()
    state = _load_or_create_state(resolved_state_file, tasks)
    store = LocalRunStore(
        config.runs_directory,
        config.prompts_directory,
    )

    async with OpenAICompatibleProvider(config.provider) as author:
        similarity = (
            ThemeSimilarityAnalyzer(author, config.run_settings.theme_similarity)
            if config.run_settings.theme_similarity is not None
            else None
        )
        studio = PromptStudio(
            author,
            store,
            config.run_settings,
            theme_similarity=similarity,
            on_progress=on_progress,
        )
        for index, task in enumerate(tasks, start=1):
            progress = state.tasks[task.task_id]
            if progress.status == BatchTaskStatus.COMPLETED:
                _verify_existing_run(store, task, progress)
                _emit(
                    on_progress,
                    f"[{index}/72] 已完成，跳过：{task.artist.name} / "
                    f"{task.cast.description}",
                )
                continue

            if progress.run_id is None:
                snapshot = store.create(
                    task.spec,
                    config.run_settings,
                    config.rules,
                )
                progress = BatchTaskProgress(
                    status=BatchTaskStatus.RUNNING,
                    run_id=snapshot.run_id,
                )
                state.tasks[task.task_id] = progress
                _write_state(resolved_state_file, state)
            else:
                _verify_existing_run(store, task, progress)

            _emit(
                on_progress,
                f"[{index}/72] 生成：{task.artist.name} / "
                f"{task.cast.description} / run {progress.run_id}",
            )
            archived = await studio.resume(progress.run_id)
            state.tasks[task.task_id] = BatchTaskProgress(
                status=BatchTaskStatus.COMPLETED,
                run_id=archived.run_id,
                prompt_file=archived.prompt_file,
            )
            _write_state(resolved_state_file, state)

    completed_tasks = sum(
        progress.status == BatchTaskStatus.COMPLETED
        for progress in state.tasks.values()
    )
    return SafeAvantGardeBatchResult(
        completed_tasks=completed_tasks,
        generated_frames=(
            completed_tasks
            * SAFE_AVANT_GARDE_THEME_COUNT
            * SAFE_AVANT_GARDE_FRAMES_PER_THEME
        ),
        state_file=resolved_state_file,
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


def _load_or_create_state(
    path: Path,
    tasks: tuple[SafeAvantGardeTask, ...],
) -> SafeAvantGardeBatchState:
    expected_ids = {task.task_id for task in tasks}
    if not path.exists():
        state = SafeAvantGardeBatchState(
            tasks={
                task.task_id: BatchTaskProgress()
                for task in tasks
            }
        )
        _write_state(path, state)
        return state
    if not path.is_file():
        raise ConfigurationError(f"批次状态路径不是文件：{path}")
    try:
        state = SafeAvantGardeBatchState.model_validate_json(
            path.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, ValidationError) as exc:
        raise ConfigurationError(f"批次状态文件无效：{path}：{exc}") from exc
    if set(state.tasks) != expected_ids:
        raise ConfigurationError(
            f"批次状态任务集合与 {SAFE_AVANT_GARDE_BATCH_ID} 不匹配"
        )
    return state


def _verify_existing_run(
    store: LocalRunStore,
    task: SafeAvantGardeTask,
    progress: BatchTaskProgress,
) -> None:
    if progress.run_id is None:
        raise ConfigurationError(f"任务 {task.task_id} 缺少 run_id")
    snapshot = store.inspect(progress.run_id)
    if snapshot.spec != task.spec:
        raise ConfigurationError(
            f"任务 {task.task_id} 的 run {progress.run_id} 请求不匹配"
        )
    if (
        progress.status == BatchTaskStatus.COMPLETED
        and snapshot.completed is None
    ):
        raise ConfigurationError(
            f"任务 {task.task_id} 被标记完成，但 run "
            f"{progress.run_id} 尚未完成"
        )
    if (
        snapshot.completed is not None
        and progress.prompt_file is not None
        and snapshot.completed.prompt_file != progress.prompt_file
    ):
        raise ConfigurationError(
            f"任务 {task.task_id} 的提示词文件记录不匹配"
        )


def _write_state(path: Path, state: SafeAvantGardeBatchState) -> None:
    temporary_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}-",
            dir=path.parent,
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(
                state.model_dump(mode="json"),
                handle,
                ensure_ascii=False,
                indent=2,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except OSError as exc:
        raise RunStoreError(f"无法保存批次状态：{path}：{exc}") from exc
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _emit(callback: Callable[[str], None] | None, message: str) -> None:
    if callback is not None:
        callback(message)
