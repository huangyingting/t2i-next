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
