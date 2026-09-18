from t2i_story_pipeline.inputs import StoryDocument, resolve_story_input
from t2i_story_pipeline.models import StoryStage


def test_still_image_contract_allows_exposure_and_zero_gravity_without_sequences():
    resolved = resolve_story_input(
        StoryDocument(description="Two adult travelers float in an orbital station.")
    )
    rules = resolved.rules.text_for(StoryStage.FRAMES)

    assert "blur or light trails" in rules
    assert "not additional bodies or chronological Frames" in rules
    assert "Grounded scenes require credible support" in rules
    assert "zero-gravity scenes require coherent free-flight" in rules
    assert "not sequential story steps" in rules
    assert "must not travel between positions" not in rules
    assert "one physically possible held pose" not in rules


def test_views_and_background_do_not_weaken_transport_or_cast_authority():
    resolved = resolve_story_input(
        StoryDocument(description="A board of different views of one adult traveler.")
    )
    rules = resolved.rules.text_for(StoryStage.FRAMES)

    assert "not additional output Frames" in rules
    assert "Within each depicted view" in rules
    assert "one <FRAME>...</FRAME> block per requested_frame_slots item" in rules
    assert (
        "No description, authoring, module, policy, or quality setting "
        "may override safety"
    ) in rules
    assert "requested counts and slots" in rules
    assert "sole authority for cast scope" in rules
    assert "Repeated views of one identity do not increase the cast" in rules
    assert "explicitly permitted background adults" in rules
    assert "population bounds and adult status" in rules


def test_theme_rules_keep_planned_slots_and_background_choices_stable():
    resolved = resolve_story_input(
        StoryDocument(description="An adult crowd at a station.")
    )
    rules = resolved.rules.text_for(StoryStage.THEMES)

    assert "the program assigns all Theme IDs" in rules
    assert (
        "Never recompute routing from Theme IDs, batch position, retry order, "
        "or prose formulas."
    ) in rules
    assert "preserve that choice within the Theme" in rules
