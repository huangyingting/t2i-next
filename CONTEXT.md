# Prompt Generation

This context turns a creative brief into shared visual guidance, alternative
themes, and independently renderable frames.

## Language

**Brief**:
The user's semantic description of the desired subject, roles, action, and
setting.
_Avoid_: Prompt, request text

**Cast Plan**:
The run-wide semantic roster resolved from the Brief. It identifies each
person's role and gender, but contains no visual appearance or clothing.
_Avoid_: Character count, cast list

**Cast Constraint**:
An optional requested female or male total used to complete an ambiguous
Brief. It cannot override people explicitly described by the Brief.
_Avoid_: Character override

**Cast Default**:
One adult woman used only when the Brief and Cast Constraints leave the cast
undetermined. It is a fallback, not a constraint on an explicit cast.
_Avoid_: Default constraint

**Theme Character**:
A Theme-specific visual realization of one Cast Plan member, including stable
appearance, age, display label, and base outfit.
_Avoid_: Cast member

**Style Guide**:
The run-wide visual anchor and the range within which Themes may vary.
_Avoid_: Style, style option

**Theme**:
One complete visual interpretation of the Brief, with its own scene, look, and
Theme Characters.
_Avoid_: Scenario, style variant

**Frame**:
One independently renderable still image containing only currently visible
facts.
_Avoid_: Shot description, scene

## Standalone Story Generation

The `t2i_story_pipeline` package is independent from Prompt Generation above.
Do not reuse its Foundation, Theme, Frame, rules, persistence, or renderer.

**Story Description**:
The user's prose account of time, place, adult characters, relationships,
interaction, action, emotion, environment, camera intent, and lighting intent.
_Avoid_: Brief, configuration

**Story Document**:
The sole file-input format for Story Generation: a UTF-8 `.yaml` document
containing an explicit ID, a natural-language Story Description, and optional
generation settings, stage authoring rules, quality policy, and runtime settings.
Explicit CLI options override document settings; omitted options do not.
Only the resolved request, rules, and settings are used on resume.
_Avoid_: Plain-text input, visual specification, executable workflow

**Story Rule Set**:
The immutable ordered authoring rules compiled for the Theme and Frame stages
of one story run. Built-in rules define only stage semantics and universal
contracts; optional rules from `story-inputs/rules/` add reusable project
policy. Story Document authoring rules are appended for their selected stage,
before the output-language rule. The resolved set is frozen with the run and
reused on resume.
_Avoid_: Story Description, Prompt Generation rules, per-input special case

**Story Quality Policy**:
An opt-in set of local Frame evidence checks, frozen in run settings.
`off` skips these checks, `report` records warnings without quality retries,
and `enforce` rejects failed output with bounded generation retries.
Basic schema, count, persistence, and safety contracts remain independent.
Checks do not add authoring instructions or call a model evaluator.
_Avoid_: Safety switch, semantic guarantee, automatic review stage

**Story Quality Report**:
The result's policy mode, `skipped`, `passed`, or `warnings` status, and
structured issues identifying the check and Theme/Frame. Attempt records keep
historical issues; the final report describes only accepted checkpoints.
_Avoid_: Hidden warnings, model score

**Story Description Authority**:
The rule that medium, layout, regions, views, scale systems, visual hierarchy,
and other subject-specific presentation behavior live in the Story Description
rather than Python branches. The story compiler understands stages and schema,
not named input archetypes.
_Avoid_: Brief-type detection, story-input adapter

**Story Content Level**:
The requested visible-content floor for every Narrative Frame: `aesthetic`,
`erotic`, or `hardcore`. It changes authoring instructions, never the adult
consent safety contract. Only the selected level is compiled into provider
prompts.
_Avoid_: Legacy Content Level, safety mode

**Nationality Default**:
Chinese nationality assigned independently to each person whose nationality
is not explicit in the Story Description. Setting, name, language, and
appearance are not nationality declarations.
_Avoid_: Ethnicity inference, setting inference

**Setting Default**:
China as the country containing the story setting when the Story Description
does not state a country or a place that identifies one. An unspecified
studio, room, or landscape is not permission to invent a foreign setting.
_Avoid_: Foreign setting invention, location inference

**Story Semantic Name**:
A short lowercase English snake_case name summarizing the whole Story
Description. It identifies published prompt files for direct Story Description
input; document runs retain it as generation metadata but name output from
the Source Prompt Stem.
_Avoid_: Run name, Theme title, source prompt stem

**Source Prompt Stem**:
The Story Document's explicit `id`, frozen as `source_prompt_stem` in the Story
Request. It is the first part of the published filename, before content level
and numeric female and male counts. Renaming the YAML file does not change it.
_Avoid_: Input filename, full prompt path, Story Semantic Name

**Cast Slug**:
A deterministic lowercase English snake_case rendering of the requested
female and male totals for direct Story Description input. Document outputs
instead include explicit numeric female and male count segments.
_Avoid_: Model-generated cast name, inferred cast

**Era Consistency**:
The requirement that every visible object, material, technology, garment,
title, and expression agree with the Story Description's time, place, and
social setting. Explicit time travel, alternate history, or intentional
anachronism in the Story Description overrides ordinary historical fidelity.
_Avoid_: Exact-date invention, silent modernization

**Narrative Theme**:
One micro-story concept derived from the Story Description. It owns a short
title, a complete stable premise, and an actionable visual direction appropriate
to its medium, without a fixed sentence quota. The model submits these fields
without an ID; the program assigns the Narrative Theme ID. Differences between Narrative
Themes come from story events rather than prop, color, or camera substitutions.
The premise is a bounded story seed, not a scene-by-scene action list.
_Avoid_: Legacy Theme, variant label

**Narrative Frame**:
One final, independently renderable prose paragraph. It naturally integrates
time and place, event-bearing environment, a complete restatement of every
visible adult character, a legible static relationship, physical state,
camera, and light in the order that reads most naturally. It has no fixed
sentence openings, mandatory causal formula, intermediate visual-specification
fields, evaluator, or renderer.
_Avoid_: Narrative Scene, Story Shot, structured prompt

**Narrative Sequence**:
The ordered one-to-six Narrative Frames belonging to one Narrative Theme.
They share stable Theme facts as parallel visual alternatives, rather than an
implicit chronological progression; each remains independently understandable.
_Avoid_: Review cycle, storyboard schema

**Story Frame Batch**:
One model text response containing exactly one `<FRAME>...</FRAME>` block for
each requested missing slot. The program owns IDs, validates each paragraph,
and checkpoints accepted frames individually. Retry and resume request only
missing slots with accepted frames as context. Ambiguous boundaries or a wrong
block count reject the whole response rather than guessing slot ownership.
_Avoid_: Structured Frame output, per-frame model call, renderer

## Standalone Spatial Pipeline

The `t2i_spatial_pipeline` package is independent from both Prompt Generation
and Standalone Story Generation. Do not reuse their stages, persistence, or
provider configuration.

**Creative Brief**:
The user's natural-language direction for the spatial batch's world, era,
atmosphere, and visual presentation. It does not prescribe catalog IDs.
_Avoid_: Brief, Story Description

**Creative Blueprint**:
The single model-derived Character, World, Style, and Presentation design
space shared by a twelve-scene batch. It contains one reusable adult
character-design slot for each role required by the batch's requested cast
configurations. Cast selection, pose, contact, and camera geometry remain
deterministic local constraints.
_Avoid_: Foundation, Narrative Theme

**Character Design Profile**:
The model-derived physical identity for one reusable F1, F2, F3, M1, or M2
slot: adult age, nationality, height, weight, build, proportions, skin, face,
hair style and color, intimate anatomy, pubic-hair design, and fantasy traits.
Profiles are independently designed and remain stable across the batch.
_Avoid_: Cast selection, shared default person

**Scene Request**:
One deterministic selection of cast configuration, pose family and variant,
activity, viewpoint, and shot scale. The released design builds twelve Scene
Requests from the packaged catalogs for a cast and seed.
_Avoid_: Frame, Narrative Frame

**Spatial Plan**:
The validated catalog entry and compatible activity selected for one Scene
Request. It owns body endpoints, support surfaces, contact edges, reachability,
and restraint topology.
_Avoid_: Creative Blueprint, prose prompt

**Scene Layers**:
The resolved character, setting, style, presentation, and expression facts
combined with a Spatial Plan. Each layer has one owner and a stable
fingerprint.
_Avoid_: Story Theme, Foundation

**Role Coverage Mode**:
The model-derived `selective_access` or `styled_nude` state for one visible
role in one presentation recipe. Roles in the same scene may use different
states, and no batch-wide nudity quota overrides the Creative Brief.
_Avoid_: Scene-wide wardrobe state, fixed nudity ratio

**Spatial Prompt**:
One independently renderable final prompt compiled from geometry and Scene
Layers. A batch passes only when every prompt and all batch diversity
thresholds pass local validation.
_Avoid_: Narrative Frame, test output
