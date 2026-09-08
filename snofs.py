from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from dotenv import load_dotenv

from t2i_story_pipeline.config import load_story_provider_settings
from t2i_story_pipeline.models import (
    ContentLevel,
    OutputLanguage,
    StoryRequest,
)
from t2i_story_pipeline.provider import OpenAIStoryModel
from t2i_story_pipeline.studio import StoryStudio

ENV_FILE = Path(
    "/home/ythuang/.vscode-server-insiders/data/agentSessionData/"
    "f9e89896-49b8-46a6-bf46-f41625b16101/attachments/"
    "18c8fd26-5c22-4b34-9d7e-43973e8bb4c6/file_.env"
)
OUTPUT_ROOT = Path(
    os.environ.get(
        "SNOFS_OUTPUT_ROOT",
        "/home/ythuang/workspace/t2i-next/prompts/2026-09-08/hardcore",
    )
)
THEME_COUNT = int(os.environ.get("SNOFS_THEME_COUNT", "100"))
FRAME_COUNT = int(os.environ.get("SNOFS_FRAME_COUNT", "6"))
CAST_FILTER = os.environ.get("SNOFS_CAST")
CONCURRENCY = 16
THEME_BATCH_SIZE = 5
GENERATION_RETRIES = 0
THEME_OUTPUT_TOKEN_LIMIT = int(
    os.environ.get("SNOFS_THEME_OUTPUT_TOKEN_LIMIT", "65536")
)
FRAME_OUTPUT_TOKEN_LIMIT = int(
    os.environ.get("SNOFS_FRAME_OUTPUT_TOKEN_LIMIT", "65536")
)
ENV_MAPPING = {
    "STORY_OPENAI_BASE_URL": "OPENAI_BASE_URL",
    "STORY_OPENAI_API_KEY_ENV": "OPENAI_API_KEY_ENV",
    "STORY_OPENAI_AUTH_MODE": "OPENAI_AUTH_MODE",
    "STORY_OPENAI_MODEL": "OPENAI_MODEL",
    "STORY_OPENAI_REASONING_EFFORT": "OPENAI_REASONING_EFFORT",
    "STORY_OPENAI_TEMPERATURE": "OPENAI_TEMPERATURE",
    "STORY_OPENAI_OUTPUT_TOKEN_LIMIT": "OPENAI_OUTPUT_TOKEN_LIMIT",
    "STORY_OPENAI_TIMEOUT_SECONDS": "OPENAI_TIMEOUT_SECONDS",
    "STORY_OPENAI_TRANSPORT_RETRIES": "OPENAI_TRANSPORT_RETRIES",
}
DEBUG_PREFIX = "[DEBUG-6f1c]"


def debug(event: str, **details: object) -> None:
    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "event": event,
        **details,
    }
    print(
        f"{DEBUG_PREFIX} {json.dumps(payload, default=str, sort_keys=True)}",
        file=sys.stderr,
        flush=True,
    )

COMMON = (
    "Create natural-language English prompts for an adult hardcore photography "
    "use below suggested tags to design the scenes. "
    "anus "
    "blowjob "
    "boudoir "
    "condoms "
    "deepthroat "
    "braless "
    "cowgirl position "
    "cum "
    "cunnilingus (be specific and maybe put kissing in the negative prompt) "
    "deepthroat "
    "dildo "
    "doggystyle position "
    "fingering (anal and vaginal) "
    "hand in panties "
    "handjob "
    "hitachi magic wand "
    "implied blowjob "
    "ipcam / nightvision ipcam "
    "masturbating (might want to put penis in negative prompt, or specify what she's "
    "rubbing for women) "
    "massage "
    "missionary position "
    "naked, nude, etc. "
    "penis "
    "pregnant (and can specify trimester) "
    "prone position "
    "reverse cowgirl position "
    "sex "
    "sheer "
    "snapchat (and caption/text/etc) "
    "selfie (and mirror selfie) "
    "spooning position "
    "strapon dildo "
    "tentacles "
    "licking testicles "
    "undressing "
    "vagina "
    "wet clothes "
    "Describe concrete visible "
    "states such as a blouse unbuttoned at the collar or a skirt gathered at the "
    "thighs instead of using shorthand tags. Each theme is a simple, credible "
    "human situation. Its six frames are parallel standalone compositions under "
    "the same emotional premise, never sequential stages of undressing or sexual "
    "activity. Every frame starts from zero context and fully describes the time, "
    "place, each adult person's age, Chinese identity, face, build, hair, clothing, "
    "expression, gaze, one static pose or interaction, relevant surroundings, "
    "camera distance and angle, focus, and lighting. Keep appearances consistent "
    "within a theme. Write fluent English only. "
)


@dataclass(frozen=True, slots=True)
class CastSpec:
    slug: str
    filename: str
    instruction: str
    chinese_women: int
    chinese_men: int


CASTS = (
    CastSpec(
        slug="1_woman",
        filename="snofs_erotic_1_chinese_woman_0002.txt",
        instruction=(
            "Every frame contains exactly one person: a twenty-eight-year-old "
            "Chinese woman. Introduce her in every frame with the exact phrase "
            '"adult Chinese woman." No other person, reflection, limb, or silhouette '
            "may appear."
        ),
        chinese_women=1,
        chinese_men=0,
    ),
    CastSpec(
        slug="2_women",
        filename="snofs_erotic_2_chinese_women_0002.txt",
        instruction=(
            "Every frame contains exactly two people: a twenty-eight-year-old "
            "Chinese woman and a thirty-two-year-old Chinese woman. Introduce each "
            'person separately with the exact phrase "adult Chinese woman," so the '
            "phrase appears at least twice in every frame. No other person, "
            "reflection, limb, or silhouette may appear."
        ),
        chinese_women=2,
        chinese_men=0,
    ),
    CastSpec(
        slug="3_women",
        filename="snofs_erotic_3_chinese_women_0002.txt",
        instruction=(
            "Every frame contains exactly three people: a twenty-seven-year-old "
            "Chinese woman, a thirty-one-year-old Chinese woman, and a "
            "thirty-five-year-old Chinese woman. Introduce each person separately "
            'with the exact phrase "adult Chinese woman," so the phrase appears at '
            "least three times in every frame. No other person, reflection, limb, "
            "or silhouette may appear."
        ),
        chinese_women=3,
        chinese_men=0,
    ),
    CastSpec(
        slug="1_woman_1_man",
        filename="snofs_erotic_1_chinese_woman_1_chinese_man_0002.txt",
        instruction=(
            "Every frame contains exactly two people: a twenty-nine-year-old "
            "Chinese woman and a thirty-four-year-old Chinese man. Introduce them "
            'with the exact phrases "adult Chinese woman" and "adult Chinese man" '
            "in every frame. They are equal consenting partners. No other person, "
            "reflection, limb, or silhouette may appear."
        ),
        chinese_women=1,
        chinese_men=1,
    ),
    CastSpec(
        slug="2_women_1_man",
        filename="snofs_erotic_2_chinese_women_1_chinese_man_0002.txt",
        instruction=(
            "Every frame contains exactly three people: a twenty-eight-year-old "
            "Chinese woman, a thirty-two-year-old Chinese woman, and a "
            "thirty-six-year-old Chinese man. Introduce each person separately "
            'with the exact phrase "adult Chinese woman" or "adult Chinese man," '
            'so "adult Chinese woman" appears at least twice and "adult Chinese '
            'man" appears at least once in every frame. They are equal consenting '
            "partners. No other person, reflection, limb, or silhouette may appear."
        ),
        chinese_women=2,
        chinese_men=1,
    ),
)


class CountingModel:
    def __init__(self, delegate: OpenAIStoryModel) -> None:
        self.delegate = delegate
        self.stages: list[str] = []
        self.active_calls = 0
        self.peak_active_calls = 0

    async def generate(self, **kwargs):
        stage = kwargs["stage"].value
        self.stages.append(stage)
        call_number = len(self.stages)
        requested_output_tokens = kwargs["max_output_tokens"]
        if stage == "themes":
            kwargs["max_output_tokens"] = THEME_OUTPUT_TOKEN_LIMIT
        elif stage == "frames":
            kwargs["max_output_tokens"] = FRAME_OUTPUT_TOKEN_LIMIT
        effective_output_tokens = kwargs["max_output_tokens"]
        started_at = perf_counter()
        self.active_calls += 1
        self.peak_active_calls = max(self.peak_active_calls, self.active_calls)
        debug(
            "provider_call_started",
            call_number=call_number,
            stage=stage,
            active_calls=self.active_calls,
            peak_active_calls=self.peak_active_calls,
            requested_output_tokens=requested_output_tokens,
            effective_output_tokens=effective_output_tokens,
        )
        result = None
        try:
            result = await self.delegate.generate(**kwargs)
        finally:
            self.active_calls -= 1
            if result is None:
                debug(
                    "provider_call_ended_without_response",
                    call_number=call_number,
                    stage=stage,
                    active_calls=self.active_calls,
                    peak_active_calls=self.peak_active_calls,
                    elapsed_seconds=round(perf_counter() - started_at, 3),
                )
        response_payload = result.value.model_dump(mode="json")
        response_item_counts = {
            key: len(value)
            for key, value in response_payload.items()
            if isinstance(value, list)
        }
        response_characters = len(result.value.model_dump_json())
        debug(
            "provider_call_completed",
            call_number=call_number,
            stage=stage,
            active_calls=self.active_calls,
            peak_active_calls=self.peak_active_calls,
            elapsed_seconds=round(perf_counter() - started_at, 3),
            response_type=type(result.value).__name__,
            response_fields=sorted(response_payload),
            response_item_counts=response_item_counts,
            response_characters=response_characters,
            token_usage=result.usage.model_dump(mode="json"),
        )
        return result


def completed_prompt(path: Path) -> bool:
    if not path.is_file():
        return False
    prompts = path.read_text(encoding="utf-8").splitlines()
    return len(prompts) == THEME_COUNT * FRAME_COUNT and all(prompts)


def identity_complete(prose: str, cast: CastSpec) -> bool:
    lowered = prose.lower()
    return (
        lowered.count("adult chinese woman") >= cast.chinese_women
        and lowered.count("adult chinese man") >= cast.chinese_men
    )


def ensure_identity_wording(prose: str, cast: CastSpec) -> str:
    if identity_complete(prose, cast):
        return prose
    women = [
        f"subject {index + 1} is an adult Chinese woman"
        for index in range(cast.chinese_women)
    ]
    men = [
        f"subject {cast.chinese_women + index + 1} is an adult Chinese man"
        for index in range(cast.chinese_men)
    ]
    return f"The image establishes that {', and '.join(women + men)}. {prose}"


def publish_prompts(path: Path, prompts: list[str]) -> None:
    debug(
        "publish_started",
        output_file=str(path),
        prompt_count=len(prompts),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=f".{path.name}-",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write("\n".join(prompts) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        debug(
            "publish_completed",
            output_file=str(path),
            prompt_count=len(prompts),
            output_bytes=path.stat().st_size,
        )
    except OSError:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


async def main() -> None:
    if not 512 <= THEME_OUTPUT_TOKEN_LIMIT <= 65536:
        raise ValueError(
            "SNOFS_THEME_OUTPUT_TOKEN_LIMIT must be between 512 and 65536"
        )
    if not 512 <= FRAME_OUTPUT_TOKEN_LIMIT <= 65536:
        raise ValueError(
            "SNOFS_FRAME_OUTPUT_TOKEN_LIMIT must be between 512 and 65536"
        )
    debug(
        "run_started",
        output_root=str(OUTPUT_ROOT),
        theme_count=THEME_COUNT,
        frames_per_theme=FRAME_COUNT,
        expected_prompts_per_cast=THEME_COUNT * FRAME_COUNT,
        cast_filter=CAST_FILTER,
        concurrency=CONCURRENCY,
        theme_batch_size=THEME_BATCH_SIZE,
        generation_retries=GENERATION_RETRIES,
        theme_output_token_limit=THEME_OUTPUT_TOKEN_LIMIT,
        frame_output_token_limit=FRAME_OUTPUT_TOKEN_LIMIT,
    )
    load_dotenv(ENV_FILE, override=False)
    debug("environment_loaded", env_file_exists=ENV_FILE.is_file())
    mapped_settings = []
    for target, source in ENV_MAPPING.items():
        if source in os.environ:
            os.environ[target] = os.environ[source]
            mapped_settings.append(target)
    debug("provider_environment_mapped", setting_names=sorted(mapped_settings))
    settings = load_story_provider_settings()
    settings.transport_retries = max(settings.transport_retries, 8)
    original_output_token_limit = settings.output_token_limit
    settings.output_token_limit = max(
        settings.output_token_limit,
        THEME_OUTPUT_TOKEN_LIMIT,
        FRAME_OUTPUT_TOKEN_LIMIT,
    )
    debug(
        "provider_configured",
        model=settings.model,
        reasoning_effort=settings.reasoning_effort,
        temperature=settings.temperature,
        original_output_token_limit=original_output_token_limit,
        output_token_limit=settings.output_token_limit,
        timeout_seconds=settings.timeout_seconds,
        transport_retries=settings.transport_retries,
        content_level=ContentLevel.EROTIC.value,
        concurrency=CONCURRENCY,
        theme_batch_size=THEME_BATCH_SIZE,
        generation_retries=GENERATION_RETRIES,
        theme_output_token_limit=THEME_OUTPUT_TOKEN_LIMIT,
        frame_output_token_limit=FRAME_OUTPUT_TOKEN_LIMIT,
    )
    summaries: list[dict[str, object]] = []
    async with OpenAIStoryModel(settings) as provider:
        for cast in CASTS:
            if CAST_FILTER is not None and cast.slug != CAST_FILTER:
                debug(
                    "cast_filtered_out",
                    cast=cast.slug,
                    cast_filter=CAST_FILTER,
                )
                continue
            output_file = OUTPUT_ROOT / cast.filename
            existing_lines = (
                output_file.read_text(encoding="utf-8").splitlines()
                if output_file.is_file()
                else []
            )
            is_complete = completed_prompt(output_file)
            debug(
                "cast_inspected",
                cast=cast.slug,
                output_file=str(output_file),
                output_exists=output_file.is_file(),
                existing_lines=len(existing_lines),
                expected_lines=THEME_COUNT * FRAME_COUNT,
                complete=is_complete,
            )
            if is_complete:
                prompts = output_file.read_text(encoding="utf-8").splitlines()
                identity_misses = [
                    index
                    for index, prompt in enumerate(prompts)
                    if not identity_complete(prompt, cast)
                ]
                prompts = [
                    ensure_identity_wording(prompt, cast) for prompt in prompts
                ]
                if identity_misses:
                    publish_prompts(output_file, prompts)
                debug(
                    "cast_skipped_existing",
                    cast=cast.slug,
                    output_file=str(output_file),
                    prompt_count=len(prompts),
                    identity_prefixes=len(identity_misses),
                )
                summary = {
                    "cast": cast.slug,
                    "status": "existing",
                    "identity_prefixes": len(identity_misses),
                    "txt": str(output_file),
                }
                summaries.append(summary)
                print(json.dumps(summary), flush=True)
                continue
            debug(
                "cast_generation_started",
                cast=cast.slug,
                output_file=str(output_file),
                theme_count=THEME_COUNT,
                frames_per_theme=FRAME_COUNT,
            )
            model = CountingModel(provider)
            result = await StoryStudio(
                model,
                concurrency=CONCURRENCY,
                theme_batch_size=THEME_BATCH_SIZE,
                generation_retries=GENERATION_RETRIES,
            ).generate(
                StoryRequest(
                    story=COMMON + " " + cast.instruction,
                    theme_count=THEME_COUNT,
                    frames_per_theme=FRAME_COUNT,
                    content_level=ContentLevel.EROTIC,
                    output_language=OutputLanguage.ENGLISH,
                )
            )
            prompts = [
                frame.prose
                for theme in result.themes
                for frame in theme.frames
            ]
            identity_misses = [
                index
                for index, prompt in enumerate(prompts)
                if not identity_complete(prompt, cast)
            ]
            debug(
                "cast_generation_completed",
                cast=cast.slug,
                themes=len(result.themes),
                frames=len(prompts),
                provider_calls=len(model.stages),
                peak_concurrent_provider_calls=model.peak_active_calls,
                identity_misses=len(identity_misses),
            )
            prompts = [
                ensure_identity_wording(prompt, cast) for prompt in prompts
            ]
            publish_prompts(output_file, prompts)
            summary = {
                "cast": cast.slug,
                "status": "generated",
                "themes": len(result.themes),
                "frames": len(prompts),
                "provider_calls": len(model.stages),
                "peak_concurrent_provider_calls": model.peak_active_calls,
                "identity_prefixes": len(identity_misses),
                "usage": result.usage.model_dump(mode="json"),
                "txt": str(output_file),
            }
            summaries.append(summary)
            print(json.dumps(summary), flush=True)
    debug(
        "run_completed",
        processed_casts=len(summaries),
        statuses=[summary["status"] for summary in summaries],
    )
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
