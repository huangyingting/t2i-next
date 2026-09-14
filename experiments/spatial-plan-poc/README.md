# Spatial-plan proof of concept

This isolated experiment does not modify or replace the story pipeline.

It performs one three-call validation:

1. Generate a typed spatial plan from `scenario.json`.
2. Reject structural contradictions and generate prose from the valid plan.
3. Independently audit cast, camera, contact, visibility, limbs, and supports.

Run it from the repository root:

```bash
STORY_OPENAI_MODEL=DeepSeek-V3.2 uv run python experiments/spatial-plan-poc/run.py
```

Evidence is written under `output/`. A successful process exits with status 0
only when deterministic prose checks pass, a deliberately contradictory
visibility fixture is rejected, a tampered multi-camera/local-anatomy sentence
is rejected, and the six-part semantic audit passes.

Run the isolated eight-case diversity matrix:

```bash
STORY_OPENAI_MODEL=DeepSeek-V3.2 uv run python experiments/spatial-plan-poc/diversity.py
```

Its prompts and diversity metrics are written under `diversity-output/`.
DeepSeek drafts are retained separately for comparison, while final critical
geometry prose is compiled deterministically from each accepted plan.

Generate the five 256-entry multi-cast pose catalogs:

```bash
uv run python experiments/spatial-plan-poc/catalog_generator.py
```

The materialized catalogs and coverage manifest are written under `catalogs/`.

Generate six representative scenes through deterministic geometry compilation
and a DeepSeek-generated non-geometric style layer:

```bash
STORY_OPENAI_MODEL=DeepSeek-V3.2 uv run python experiments/spatial-plan-poc/catalog_scene_demo.py
```

The combined prompts and evaluation are written under `demo-output/`.
