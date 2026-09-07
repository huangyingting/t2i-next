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

**Story Blueprint**:
The run-wide interpretation of one Story Description. It owns the cast,
relationships, ordered Story Beats, setting, atmosphere, and cinematography.
_Avoid_: Foundation, Theme

**Story Beat**:
One causal unit containing a current action, visible response, emotional turn,
and visible result.
_Avoid_: Story Shot, Frame

**Creative Intent**:
The thematic soul of one Narrative Theme. It owns one emotional core,
narrative tension, decisive moment, story-derived visual motif, visible motif
progression, and explicit restraint. It decides what details matter and what
attractive but irrelevant details must be omitted.
_Avoid_: Style preset, mood list, detail expansion

**Narrative Theme**:
One materially distinct creative interpretation of the shared Story Blueprint.
It owns one Creative Intent and exactly the requested ordered Narrative Scenes.
Narrative Themes may not differ only by numbering, adjectives, color, or camera
terminology.
_Avoid_: Legacy Theme, variant label

**Narrative Scene**:
One ordered cinematic account and independently renderable projection of a
Story Beat. It owns a narrative mode, temporal-spatial opening, environmental
evidence, character entry, optional causal context, current actions and
visible responses, material feedback, one static camera composition, visible
sensory evidence, and thematic closure.
_Avoid_: Story Shot, Frame, Theme

**Visible Text**:
Literal text that must appear in one Narrative Scene, together with its
physical carrier, placement, and visual appearance. Its content is immutable
through revision and is rendered inside English double quotes.
_Avoid_: Caption, prose quotation

**Narrative Review**:
The typed quality assessment of every Narrative Scene across temporal-spatial
grounding, environmental storytelling, causal action, physical feedback,
cinematography integration, sensory visualization, thematic closure, and
language coherence, plus creative unity and story specificity. Any score below
four requires an actionable issue and a revision before publication.
_Avoid_: General feedback, critic prose
