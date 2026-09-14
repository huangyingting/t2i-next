# Spatial-plan proof of concept

This isolated experiment does not modify or replace the story pipeline.

It performs one deterministic-plan validation:

1. Compile and validate a typed spatial plan from `scenario.json`.
2. Generate prose from the immutable valid plan.
3. Independently audit cast, camera, contact, visibility, limbs, and supports.

DeepSeek does not create or alter the spatial plan. It is limited to rendering
validated geometry as prose and independently auditing that prose.

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
Persisted actor entity IDs use lowercase codes (`f1`, `f2`, `f3`, `m1`, and
`m2`). Prompt-facing identities use stable uppercase labels such as
`F1, woman 1` and `M1, man 1`; personal names are not identity keys. Temporary
logical roles used while assembling templates are resolved to actor codes
before any contact, support, restraint, or prop record is persisted.
Catalog schema 2.0 models controlled handheld vibrators and pelvis-mounted
strap-ons explicitly, including prop ownership, occupied hands, attachment
points, contact axes, and segmented visibility. Compiled scenes also include a
complete continuous-body ledger for every coded actor, bilateral limb chains
for supported lifts, and pelvis ownership for anatomical contact endpoints.

Run the deterministic catalog and compiled-prompt validation matrix:

```bash
uv run python experiments/spatial-plan-poc/catalog_validation.py
```

This validates all five catalogs and every compatible pose/activity pair,
checks all six representative scenes, and verifies that malformed prop,
contact, limb-ownership, restraint, and evaluation fixtures are rejected.
Evidence is written to `demo-output/validation-report.json`.

Generate six representative scenes through deterministic geometry compilation
and a DeepSeek-generated non-geometric style layer:

```bash
STORY_OPENAI_MODEL=DeepSeek-V3.2 uv run python experiments/spatial-plan-poc/catalog_scene_demo.py
```

The combined prompts and evaluation are written under `demo-output/`. A run
passes only when style and deterministic geometry checks are clean and every
independent scene evaluation returns `pass`.
