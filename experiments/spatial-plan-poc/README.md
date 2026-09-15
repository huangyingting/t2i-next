# Spatial-plan proof of concept

This isolated experiment does not modify or replace the story pipeline.

It performs one deterministic-plan validation:

1. Compile and validate a typed spatial plan from `scenario.json`.
2. Generate prose from the immutable valid plan.
3. Independently audit cast, camera, contact, visibility, limbs, and supports.

DeepSeek does not create or alter the spatial plan, character profiles,
settings, presentation plans, or visibility decisions. Final critical prose is
compiled deterministically; DeepSeek is used only for independent evaluation.

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
Persisted actor roles use lowercase codes (`f1`, `f2`, `f3`, `m1`, and `m2`).
Prompt-facing identities use stable uppercase labels such as `F1, woman 1` and
`M1, man 1`; personal names are not identity keys. Catalog schema 3.0 has one
actor identity system: `role`. Relationship edges use references such as
`focus_role`, `owner_role`, and `controller_role`; `pose_function` separately
describes a role's temporary geometric duty. Cast and focus membership are
stored once at their owning level rather than repeated in every pose and
activity. The superseded slot identity fields are not accepted or persisted.

Catalog schema 3.0 models controlled handheld vibrators and pelvis-mounted
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

## Five-input scene architecture

The current scene compiler uses five typed inputs and one deterministic
resolver:

1. `SpatialPlan` owns cast, pose, contact, support, occlusion, projection, and
   camera geometry.
2. `CharacterProfile` owns stable adult identity, stature, build, face, base
   hair, body-detail profile, grooming profile, and fantasy body traits.
3. `SettingPreset` owns world genre, location, era, time, weather,
   architecture, materials, environment props, motivated light sources,
   typed physical support realizations, mood tags, and exact-cast hazards.
4. `StylePreset` owns a coherent visual recipe: medium, rendering language,
   surface texture, contrast, color treatment, lighting treatment, atmosphere,
   and compatible mood tags.
5. `PresentationPreset` owns scene-local wardrobe, accessories, makeup, and
   soft appearance biases. The resolver turns it into a `PresentationPlan`
   containing the final wardrobe state, footwear, hair styling, surface finish,
   motivated lighting use, and selected style recipe.

[`scene_layers.py`](./scene_layers.py) defines these schemas, their independent
fingerprints, and the deterministic resolver. Final visibility is derived from
the spatial contacts, contact visibility, restraint regions, and wardrobe
state. It is not an independently generated layer. Body details are emitted
only for relevant regions that the spatial plan marks visible.

Resolver priority is fixed: adult constraints, exact cast and body continuity,
spatial contacts and supports, locked character identity, setting
compatibility, wardrobe and visibility, lighting, then atmosphere. Lower
layers cannot override higher-priority geometry.

Every setting must explicitly exclude background people, humanoid statues,
person-shaped shadows, and mirrors that show extra bodies. Lighting must use a
source declared by the selected setting. Wardrobe must be moved clear of every
required contact rather than changing the contact.

The compiler deduplicates shared wardrobe and makeup themes across roles,
omits invisible body details, and stores full typed data in `layers.json`
instead of repeating schema metadata in the prompt. Reports retain token
measurements for observation, but token count does not truncate style content
or determine whether a scene passes.
Scene resolution is deterministic and never makes a per-scene style-generation
call. Dynamic creative inference uses one blueprint call for the complete
batch; DeepSeek evaluation remains optional. Evaluation requests send the
compiled prompt and scene ID only, because selections, fingerprints, and layer
JSON are redundant with validation performed locally.

The current six-scene reference stores 5,565 estimated tokens of complete typed
layer data while emitting 1,076 estimated tokens of prompt layer prose. This
reduction removes schema metadata and repetition, not style content.

Generate six representative scenes through deterministic geometry and layer
compilation, then independently evaluate them with DeepSeek:

```bash
STORY_OPENAI_MODEL=DeepSeek-V3.2 uv run python experiments/spatial-plan-poc/catalog_scene_demo.py
```

The combined prompts, resolved layers, token metrics, and evaluation are
written under `demo-output/`. The six presets include a rainy neon apartment,
an amber performance studio, a modern corridor, a midnight luxury hotel, a
soft morning bedroom, and a dark-fantasy demon palace. A run passes only when
all layer and geometry checks are clean and every independent evaluation
returns `pass`.

Generate twelve stratified pose-diversity prompts and evaluate them with
DeepSeek:

```bash
STORY_OPENAI_MODEL=DeepSeek-V3.2 uv run python \
  experiments/spatial-plan-poc/catalog_diversity_12.py --batch 1 --evaluate
```

The prompts, resolved layers, independent fingerprints, exact selections,
token metrics, 128-pose reference metrics, and evaluation are written under
`diversity-12-output/`. The reference subset uses eight variants from each of
all sixteen pose families. The twelve rendered tests must use twelve different
families, activities, and settings while covering all cast configurations, all
three body levels, all seven support surfaces, all six camera viewpoints, and
all three shot scales.

Generate the complementary second batch with the same coverage contract:

```bash
STORY_OPENAI_MODEL=DeepSeek-V3.2 STORY_OPENAI_TEMPERATURE=0 uv run python \
  experiments/spatial-plan-poc/catalog_diversity_12.py --batch 2 --evaluate
```

The second batch is written independently under
`diversity-12-round2-output/`; it does not overwrite the first batch. It
emphasizes the less-tested right-side lying, upright standing, bent standing,
elevated bridge, dual controlled props, BDSM, wall-supported group, and lifted
support topologies.

## Dynamic creative blueprints

For a new visual world, use a natural-language setting brief rather than
writing twelve scene presets by hand:

```bash
STORY_OPENAI_MODEL=DeepSeek-V3.2 STORY_OPENAI_TEMPERATURE=0 uv run python \
  experiments/spatial-plan-poc/demon_hardcore_12.py \
  --creative-brief "An infernal royal palace of black iron and ritual fire" \
  --creative-seed 42 --evaluate
```

The model is called once to infer a typed `CreativeBlueprint` with three
independent sub-blueprints. `WorldBlueprint` contains coherent location cards,
typed support identifiers paired with physical object descriptions, and
motivated light sources. `StyleBlueprint`
contains complete internally coherent style recipes rather than independently
shuffled style adjectives. `PresentationBlueprint` contains wardrobe,
accessory, makeup, and soft appearance-bias option pools. The model cannot
choose cast, anatomy, activity, pose, actor support, contact, lens, camera
placement, or framing.

A local seeded constraint solver processes the most restrictive poses first,
filters locations by their required physically realized supports, filters styles by
compatible mood tags, and greedily maximizes unused locations, styles, and
location/style pairs. Shuffled cycles provide presentation variation. The
result is twelve semantically unique combinations of `SettingPreset`,
`StylePreset`, and `PresentationPreset`, compiled with the twelve locked
spatial plans.

The same brief, seed, model, blueprint schema, and system prompt reuse a
content-addressed cache and reproduce the same creative selections without
another blueprint call. Changing any of those inputs invalidates the cache.
Use `--refresh-blueprint` to deliberately replace a cached inference; refreshed
model output is not guaranteed to match an earlier inference even with the same
seed. The compiler emits the complete selected style recipe in the prompt and
keeps the full structured style data in `layers.json`. The current blueprint
snapshot, cache key, prompts, selections, resolved layers, token metrics, and
optional independent evaluation are written under
`demon-hardcore-12-output/`.
