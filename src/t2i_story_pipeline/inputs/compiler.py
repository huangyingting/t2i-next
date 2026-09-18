"""The only resolver from explicit input data to a frozen run snapshot."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal, Self

from pydantic import ConfigDict, TypeAdapter, ValidationError, model_validator

from t2i_story_pipeline.authoring_rules import (
    resolve_story_rules,
    system_rule_sources,
)
from t2i_story_pipeline.errors import StoryConfigurationError
from t2i_story_pipeline.inputs.context import (
    ContextSelection,
    StageInputContext,
    StageThemeInputPlan,
)
from t2i_story_pipeline.inputs.loader import asset_path, load_yaml_model
from t2i_story_pipeline.inputs.planning import (
    ThemeInputPlan,
    plan_themes,
    validate_requirements,
)
from t2i_story_pipeline.inputs.schema import (
    CatalogDocument,
    InputOverrides,
    InputRequirements,
    ModuleContext,
    ModuleDocument,
    PolicyDocument,
    StoryDocument,
    StoryGeneration,
)
from t2i_story_pipeline.models import (
    Model,
    RuleText,
    StageAuthoring,
    StoryAuthoring,
    StoryQualityPolicy,
    StoryRequest,
    StoryRuleSet,
    StoryRuntime,
    StoryStage,
)

_POLICIES = Path(__file__).resolve().parents[1] / "rule_packs" / "policies"
_MODULE_CONTEXT = TypeAdapter(ModuleContext)


class InputSource(Model):
    """Self-contained source content and the selected rules owned by that source."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["document", "system", "policy", "module", "catalog"]
    id: str
    path: str | None = None
    content: str
    themes: tuple[RuleText, ...] = ()
    frames: tuple[RuleText, ...] = ()
    requirements: InputRequirements | None = None


class ResolvedStoryInput(Model):
    """Persist this entire value; resume never needs to rediscover input assets."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    request: StoryRequest
    runtime: StoryRuntime
    quality: StoryQualityPolicy
    rules: StoryRuleSet
    sources: tuple[InputSource, ...]
    modules: tuple[ModuleContext, ...] = ()
    plans: tuple[ThemeInputPlan, ...]

    @model_validator(mode="after")
    def complete_plan(self) -> Self:
        expected = [f"T{index:03d}" for index in range(1, self.request.theme_count + 1)]
        if [plan.theme_id for plan in self.plans] != expected:
            raise ValueError("input plan IDs must exactly cover request.theme_count")
        for plan in self.plans:
            if (
                plan.cast.female_count != self.request.female_count
                or plan.cast.male_count != self.request.male_count
            ):
                raise ValueError("input plan cast must match the effective request")
        keys = [(source.kind, source.id) for source in self.sources]
        if len(keys) != len(set(keys)):
            raise ValueError("input source IDs must be unique within each kind")
        documents = [source for source in self.sources if source.kind == "document"]
        if len(documents) != 1:
            raise ValueError("resolved input must freeze exactly one source document")
        document = StoryDocument.model_validate_json(documents[0].content)
        _validate_source(documents[0], document, self.request)
        policies = [source for source in self.sources if source.kind == "policy"]
        if len(policies) != 1:
            raise ValueError("resolved input must freeze exactly one named policy")
        policy = PolicyDocument.model_validate_json(policies[0].content)
        _validate_source(policies[0], policy, self.request)
        if policy.id != document.policy:
            raise ValueError("frozen policy must match the source document")
        catalogs = [
            CatalogDocument.model_validate_json(source.content)
            for source in self.sources
            if source.kind == "catalog"
        ]
        if len(catalogs) != int(document.allocation is not None):
            raise ValueError("resolved allocation must freeze exactly its catalog")
        for source, catalog in zip(
            (source for source in self.sources if source.kind == "catalog"),
            catalogs,
            strict=True,
        ):
            _validate_source(source, catalog, self.request)
        cast = document.generation.cast.model_copy(
            update={
                "female_count": self.request.female_count,
                "male_count": self.request.male_count,
            }
        )
        expected_plans = plan_themes(
            self.request, cast, document.allocation, catalogs[0] if catalogs else None
        )
        if self.plans != expected_plans:
            raise ValueError("input plans do not match the frozen allocation and cast")
        module_ids = [module.id for module in self.modules]
        kinds = [module.kind for module in self.modules]
        if len(kinds) != len(set(kinds)):
            raise ValueError("multiple modules own the same capability dimension")
        if module_ids != [reference.id for reference in document.modules]:
            raise ValueError("module contexts must match the frozen document")
        module_sources = [source for source in self.sources if source.kind == "module"]
        if [source.id for source in module_sources] != module_ids:
            raise ValueError("module contexts must freeze their source documents")
        for context, source, reference in zip(
            self.modules, module_sources, document.modules, strict=True
        ):
            module = ModuleDocument.model_validate_json(source.content)
            _validate_source(source, module, self.request)
            expected_context = _MODULE_CONTEXT.validate_python(
                {
                    "id": module.id,
                    "kind": module.kind,
                    "parameters": reference.parameters,
                }
            )
            if expected_context != context:
                raise ValueError("module context differs from frozen source parameters")
        requirements = _requirements(self.sources)
        default_request = document.generation.request(document.description, document.id)
        default_plans = plan_themes(
            default_request,
            document.generation.cast,
            document.allocation,
            catalogs[0] if catalogs else None,
        )
        validate_requirements(default_request, default_plans, requirements)
        validate_requirements(self.request, self.plans, requirements)
        return self

    def fingerprint(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def context_for(
        self,
        stage: StoryStage,
        theme_ids: list[str],
        *,
        frame_ids: list[str] | None = None,
    ) -> dict[str, object]:
        """Project selected slots without source metadata or other-stage rules.

        Modules participate only in stages with selected authoring. Their closed
        parameter schemas describe that module's stage context, never templates.
        The returned plain JSON data is independent of this frozen snapshot.
        """
        try:
            selection = ContextSelection(
                stage=stage, theme_ids=theme_ids, frame_ids=frame_ids
            )
            expected_frames = tuple(
                f"F{index:02d}" for index in range(1, self.request.frames_per_theme + 1)
            )
            requested_frames = selection.frame_ids or expected_frames
            if not set(requested_frames) <= set(expected_frames):
                raise ValueError("unknown input plan frame_ids")
            by_id = {plan.theme_id: plan for plan in self.plans}
            unknown = set(selection.theme_ids) - by_id.keys()
            if unknown:
                raise ValueError(f"unknown input plan theme_ids: {sorted(unknown)}")
            active_modules = {
                source.id
                for source in self.sources
                if source.kind == "module"
                and (
                    source.themes
                    if selection.stage == StoryStage.THEMES
                    else source.frames
                )
            }
            context = StageInputContext(
                modules=tuple(
                    module for module in self.modules if module.id in active_modules
                ),
                plans=tuple(
                    StageThemeInputPlan.from_plan(
                        by_id[theme_id],
                        selection.stage,
                        self.request.frames_per_theme,
                        requested_frames,
                    )
                    for theme_id in selection.theme_ids
                ),
            )
            return context.model_dump(mode="json")
        except ValueError as exc:
            raise StoryConfigurationError(
                "Cannot select Story input context "
                f"for {self.request.source_prompt_stem or 'direct-story'}: {exc}"
            ) from exc


def _requirements(
    sources: tuple[InputSource, ...] | list[InputSource],
) -> tuple[tuple[str, InputRequirements], ...]:
    return tuple(
        (f"{source.kind} {source.id} ({source.path or 'inline'})", source.requirements)
        for source in sources
        if source.requirements is not None
    )


def _source(
    kind: Literal["document", "policy", "module", "catalog"],
    value: StoryDocument | PolicyDocument | ModuleDocument | CatalogDocument,
    path: Path | None,
    request: StoryRequest,
) -> InputSource:
    authoring = getattr(value, "authoring", StoryAuthoring())
    return InputSource(
        kind=kind,
        id=value.id or "direct-story",
        path=str(path) if path is not None else None,
        content=value.model_dump_json(),
        themes=authoring.themes.selected(request.content_level),
        frames=authoring.frames.selected(request.content_level),
        requirements=getattr(value, "requirements", None),
    )


def _validate_source(
    source: InputSource,
    value: StoryDocument | PolicyDocument | ModuleDocument | CatalogDocument,
    request: StoryRequest,
) -> None:
    expected = _source(
        source.kind,
        value,
        Path(source.path) if source.path is not None else None,
        request,
    )
    if (
        source.id != expected.id
        or source.requirements != expected.requirements
        or source.themes != expected.themes
        or source.frames != expected.frames
    ):
        raise ValueError(
            f"{source.kind} {source.id}: metadata differs from frozen source content"
        )


def _effective(
    document: StoryDocument, overrides: InputOverrides
) -> tuple[StoryRequest, StoryGeneration, StoryRuntime, StoryQualityPolicy]:
    generation = document.generation.model_dump(mode="python")
    runtime = document.runtime.model_dump(mode="python")
    quality = document.validation.model_dump(mode="python")
    cast = document.generation.cast.model_dump(mode="python")
    for name, value in overrides.model_dump(exclude_none=True).items():
        if name in ("female_count", "male_count"):
            cast[name] = value
        elif name in generation:
            generation[name] = value
        elif name in runtime:
            runtime[name] = value
        elif name == "theme_quality_mode":
            quality["themes"]["mode"] = value
        elif name == "frame_quality_mode":
            quality["frames"]["mode"] = value
    generation["cast"] = cast
    effective = StoryGeneration.model_validate(generation)
    return (
        effective.request(document.description, document.id),
        effective,
        StoryRuntime.model_validate(runtime),
        StoryQualityPolicy.model_validate(quality),
    )


def resolve_story_input(
    document: StoryDocument,
    overrides: InputOverrides | None = None,
    *,
    asset_root: Path | None = None,
    source_path: Path | None = None,
) -> ResolvedStoryInput:
    """Validate defaults and overrides before producing provider-free run inputs.

    Asset lookup is relative only to the explicit root or source document.
    A direct document has no implicit cwd asset root and may omit its source id.
    """
    source_path = source_path or document._source_path
    label = f"{source_path or 'inline Story'} ({document.id or 'direct-story'})"
    try:
        # Revalidate even if the caller used model_copy or mutated nested models.
        document = StoryDocument.model_validate(document.model_dump())
        overrides = InputOverrides.model_validate(
            (overrides or InputOverrides()).model_dump()
        )
        root = (
            asset_root
            if asset_root is not None
            else (source_path.parent if source_path is not None else None)
        )
        if (document.modules or document.allocation is not None) and root is None:
            raise ValueError(
                "explicit asset_root or source_path is required for assets"
            )
        request, generation, runtime, quality = _effective(document, overrides)
        policy_path = _POLICIES / f"{document.policy}.yaml"
        policy = load_yaml_model(policy_path, PolicyDocument)
        sources = [
            _source("document", document, source_path, request),
            _source("policy", policy, policy_path, request),
        ]
        modules: list[ModuleContext] = []
        dimensions: dict[str, str] = {}
        for reference in document.modules:
            assert root is not None
            path = asset_path(root, "_modules", reference.id)
            module = load_yaml_model(path, ModuleDocument)
            if module.id != reference.id:
                raise ValueError(f"{path}: module id must match {reference.id}")
            if module.kind in dimensions:
                raise ValueError(
                    f"{path}: incompatible modules {dimensions[module.kind]} and "
                    f"{module.id} both own the {module.kind} dimension"
                )
            dimensions[module.kind] = module.id
            try:
                modules.append(
                    _MODULE_CONTEXT.validate_python(
                        {
                            "id": module.id,
                            "kind": module.kind,
                            "parameters": reference.parameters,
                        }
                    )
                )
            except ValidationError as exc:
                raise ValueError(f"{path}: invalid module parameters: {exc}") from exc
            sources.append(_source("module", module, path, request))
        catalog = None
        if document.allocation is not None:
            assert root is not None
            path = asset_path(root, "_catalogs", document.allocation.catalog)
            catalog = load_yaml_model(path, CatalogDocument)
            if catalog.id != document.allocation.catalog:
                raise ValueError(f"{path}: catalog id must match allocation catalog")
            sources.append(_source("catalog", catalog, path, request))

        requirements = _requirements(sources)
        default_request = document.generation.request(document.description, document.id)
        try:
            default_plans = plan_themes(
                default_request, document.generation.cast, document.allocation, catalog
            )
            validate_requirements(default_request, default_plans, requirements)
        except ValueError as exc:
            raise ValueError(f"invalid document defaults: {exc}") from exc
        plans = plan_themes(request, generation.cast, document.allocation, catalog)
        validate_requirements(request, plans, requirements)

        authoring = StoryAuthoring(
            themes=StageAuthoring(
                common=tuple(rule for source in sources for rule in source.themes)
            ),
            frames=StageAuthoring(
                common=tuple(rule for source in sources for rule in source.frames)
            ),
        )
        rules = resolve_story_rules(request, authoring=authoring)
        for path in system_rule_sources(request):
            text = path.read_text(encoding="utf-8-sig")
            selected = tuple(
                stripped
                for line in text.splitlines()
                if (stripped := line.strip()) and not stripped.startswith("#")
            )
            sources.append(
                InputSource(
                    kind="system",
                    id=path.relative_to(path.parents[1]).as_posix(),
                    path=str(path),
                    content=text,
                    themes=selected if path.name != "frames.rules" else (),
                    frames=selected if path.name != "themes.rules" else (),
                )
            )
        return ResolvedStoryInput(
            request=request,
            runtime=runtime,
            quality=quality,
            rules=rules,
            sources=tuple(sources),
            modules=tuple(modules),
            plans=plans,
        )
    except (OSError, UnicodeError, ValueError, StoryConfigurationError) as exc:
        raise StoryConfigurationError(
            f"Cannot resolve Story input {label}: {exc}"
        ) from exc
