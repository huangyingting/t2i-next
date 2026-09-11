from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

WOMAN_CENTERED_STORY_INPUTS = (
    "anamorphic-room.txt",
    "archival-reconstruction.txt",
    "botanical-time-slice.txt",
    "choreographic-score.txt",
    "cinematic-cutaway.txt",
    "color-relay.txt",
    "environmental-portrait.txt",
    "evidence-table.txt",
    "forced-perspective.txt",
    "light-echo.txt",
    "living-map.txt",
    "material-alchemy.txt",
    "miniature-civic-system.txt",
    "negative-space.txt",
    "object-biography.txt",
    "optical-layering.txt",
    "practical-weather.txt",
    "shadow-narrative.txt",
    "spatial-rhythm.txt",
    "threshold-worlds.txt",
    "topographic-body.txt",
)


def test_new_story_inputs_require_a_visible_active_adult_woman() -> None:
    for filename in WOMAN_CENTERED_STORY_INPUTS:
        brief = (
            REPOSITORY_ROOT / "story-inputs" / filename
        ).read_text(encoding="utf-8")
        normalized = " ".join(brief.split())

        assert "WOMAN CAST GATE" in brief
        assert "Every Theme and every Frame must include at least one" in normalized
        assert "unmistakably adult woman" in normalized
        assert "This brief is incompatible with a zero-woman cast." in normalized


def test_dress_board_region_names_are_layout_only() -> None:
    brief = (REPOSITORY_ROOT / "story-inputs" / "dress.txt").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(brief.split())

    assert "Do not render the Theme title or region names as visible text." in brief
    assert "Use region names only as internal layout references" in brief
    assert "Begin the scale at visibly sensual" in normalized
    assert (
        "compatible only with CLI cast settings of one woman and zero men"
        in normalized
    )
    assert "zero or one visually restrained body-safe adult product" in normalized
    assert "adult product-and-wearable fashion system" in normalized
    assert (
        "Include one to three clearly designed body-safe adult products"
        in normalized
    )
    assert "BDSM equipment-and-wardrobe design board" in normalized
    assert "Include three to six BDSM-specific designed elements" in normalized
    assert "BDSM EQUIPMENT SPECIFICATION" in normalized
    assert "at least two externally wearable pieces" in normalized
    assert "non-load-bearing, low-pressure, and visibly releasable" in normalized
    assert "HARDCORE VISUAL IMPACT GATE" in normalized
    assert "remains powerful at thumbnail scale" in normalized
    assert "Use at least three of these contrast axes" in normalized
    assert "one dominant statement, two secondary structures" in normalized
    assert "CURATED HARDCORE WARDROBE ARCHETYPES" in normalized
    assert "CURATED HARDCORE EQUIPMENT SYSTEMS" in normalized
    assert "CURATED EXPLICIT BDSM PRODUCT CATEGORIES" in normalized
    assert "SEX TOY PRODUCT SPECIFICATION" in normalized
    assert "CURATED SEX TOY PRODUCT CATEGORIES" in normalized
    assert "CURATED HARDCORE MATERIAL AND COLOR SYSTEMS" in normalized
    assert "nipple clamps" in normalized
    assert "ball gag" in normalized
    assert "bit gag" in normalized
    assert "open-center mouth gag" in normalized
    assert "Any selected hardcore product may appear worn" in normalized
    assert "visible low-tension limiter" in normalized
    assert "visible breathing path" in normalized
    assert "relaxed jaw" in normalized
    assert "chastity-inspired waist belt" in normalized
    assert "ventilated leather half-mask" in normalized
    assert "wide posture collar" in normalized
    assert "bondage mitts" in normalized
    assert "breast-framing leather harness" in normalized
    assert "lightweight padded spreader bar" in normalized
    assert "soft suede flogger" in normalized
    assert "broad padded leather paddle" in normalized
    assert "limited body area necessary" in normalized
    assert "External wearable sex toys may appear fitted" in normalized
    assert "Insertive product categories may be named and shown" in normalized
    assert "must remain completely outside the body" in normalized
    assert "full-size wand massager" in normalized
    assert "strap-on harness carrying a removable silicone dildo" in normalized
    assert "classic silicone dildo" in normalized
    assert "rabbit vibrator" in normalized
    assert "jeweled silicone butt plug" in normalized
    assert "graduated anal-bead set" in normalized
    assert "textured masturbation sleeve" in normalized
    assert "one to three sex toys in addition to its BDSM" in normalized
    assert "PRODUCT AUTHENTICITY GATE" in normalized
    assert "attach to the nipples" in normalized
    assert "attached to lace" in normalized
    assert "must not be called a nipple clamp" in normalized
    assert "CONSTRUCTION AND CONNECTION INTEGRITY" in normalized
    assert "collar seamlessly extends into gloves" in normalized
    assert "material flat lay must show two shoes, two gloves" in normalized
    assert "genuinely different presentation" in normalized
    assert "Change at least four of these" in normalized
    assert "Do not write the internal level names" in normalized
    assert "BDSM may appear at most once" in normalized
    assert "Do not leak English workflow words" in normalized
    assert "Do not pad final prose with compliance-shaped negations" in normalized
    assert "does not satisfy hardcore product emphasis" in normalized
    assert "Do not use the words futuristic" in normalized
    assert "generic mid-gray walls" in normalized
    assert "flat, shadowless catalog lighting" in normalized
    assert "Every named product has its real shape and intended fit" in normalized
    assert "Every Frame differs from other Frames" in normalized
    assert "Final prose never states an internal content level" in normalized
    assert "cybernetic body parts" in normalized
    assert "technology-shaped costume components" in normalized
    assert "utilitarian futurism" not in normalized
    assert "Aesthetic is sensual lingerie-led fashion" in normalized
    assert "hardcore is a BDSM wardrobe-and-equipment system" in normalized
    assert "Present one complete, opaque, non-erotic outfit." not in brief
    assert "At aesthetic level, include none." not in brief

    wardrobe_pool = brief.split(
        "\nCURATED HARDCORE WARDROBE ARCHETYPES\n", maxsplit=1
    )[1].split("\nCURATED HARDCORE EQUIPMENT SYSTEMS\n", maxsplit=1)[0]
    equipment_pool = brief.split(
        "\nCURATED HARDCORE EQUIPMENT SYSTEMS\n", maxsplit=1
    )[1].split("\nCURATED EXPLICIT BDSM PRODUCT CATEGORIES\n", maxsplit=1)[0]
    product_pool = brief.split(
        "\nCURATED EXPLICIT BDSM PRODUCT CATEGORIES\n", maxsplit=1
    )[1].split("\nCURATED SEX TOY PRODUCT CATEGORIES\n", maxsplit=1)[0]
    sex_toy_pool = brief.split(
        "\nCURATED SEX TOY PRODUCT CATEGORIES\n", maxsplit=1
    )[1].split("\nCURATED HARDCORE MATERIAL AND COLOR SYSTEMS\n", maxsplit=1)[0]
    material_pool = brief.split(
        "\nCURATED HARDCORE MATERIAL AND COLOR SYSTEMS\n", maxsplit=1
    )[1].split("\nSIX-VIEW BOARD CONTRACT\n", maxsplit=1)[0]
    for pool in (
        wardrobe_pool,
        equipment_pool,
        product_pool,
        sex_toy_pool,
        material_pool,
    ):
        entries = [
            line.removeprefix("- ").strip()
            for line in pool.splitlines()
            if line.startswith("- ")
        ]
        assert len(entries) >= 12
        assert len(entries) == len(set(entries))

    explicit_product_entries = [
        line.removeprefix("- ").strip()
        for line in product_pool.splitlines()
        if line.startswith("- ")
    ]
    assert len(explicit_product_entries) >= 24
    sex_toy_entries = [
        line.removeprefix("- ").strip()
        for line in sex_toy_pool.splitlines()
        if line.startswith("- ")
    ]
    assert len(sex_toy_entries) >= 20

    assert (
        "The Theme title appears exactly once and the six region labels "
        "each appear once"
    ) not in brief


def test_post_layout_brief_builds_one_analog_collage_poster() -> None:
    brief = (REPOSITORY_ROOT / "story-inputs" / "post-layout.txt").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(brief.split())

    assert "tactile mid-century cinematic photomontage" in normalized
    assert "REFERENCE EFFECT AND POSTER DNA" in normalized
    assert "one dominant monochrome photographic hero" in normalized
    assert "two to four smaller documentary" in normalized
    assert (
        "one oversized condensed headline assembled on a torn paper slab"
        in normalized
    )
    assert "overlapping torn paper with irregular deckled edges" in normalized
    assert "halftone dots, photocopy grain, coarse newsprint" in normalized
    assert "Deliberate collage is mandatory" in normalized
    assert "portrait 4:5 poster" in normalized
    assert "Repeated photographic crops of the same protagonist" in normalized
    assert "Do not drift into clean corporate minimalism" in normalized
    assert "The reference establishes this design grammar only" in normalized
    assert "ENGLISH-ONLY IMAGE TEXT GATE" in normalized
    assert "seven internal planning concerns" in normalized
    assert "not as a literal response format" in normalized
    assert "Do not print those concern names" in normalized
    assert "SEVEN-PART CONTENT STRUCTURE" in normalized
    assert "Their names are internal authoring cues" in normalized
    assert (
        "Write one compact, fluent paragraph rather than seven labeled lines"
        in normalized
    )
    assert (
        "dedicated image-text passage inside the natural prose is the sole "
        "source of visible image copy"
    ) in normalized
    assert "exact physical carrier and location in the poster" in normalized
    assert "A quoted string without a concrete location is invalid" in normalized
    assert "literal ASCII straight double-quote character" in normalized
    assert "Outside that passage, use no quoted strings" in normalized
    assert "zero Chinese characters" in normalized
    assert "do not authorize Chinese writing in the image" in normalized
    assert "no quotation mark of any kind appears outside that passage" in normalized
    assert "If a word is not explicitly quoted in that passage" in normalized
    assert "zero non-English glyphs appear anywhere" in normalized
    assert "Composition: one exact aspect ratio" not in normalized
    assert "Output: resolution matching" not in normalized
    assert "Composition and Output both specify portrait 4:5" not in normalized
    for label in (
        "Subject:",
        "Scene:",
        "Composition:",
        "Style:",
        "Text:",
        "Details:",
        "Output:",
    ):
        assert label not in brief
    assert "turn one finished design into a collage of proposals" not in normalized


def test_creative_brief_uses_open_ended_high_concept_ideation() -> None:
    brief = (REPOSITORY_ROOT / "story-inputs" / "creative.txt").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(brief.split())

    assert "PLAN THE WHOLE BATCH FIRST" in normalized
    assert "at least twice as many candidate concepts as requested" in normalized
    assert "ONE-OBJECT AND MULTI-OBJECT MODES" in normalized
    assert "visible mix of single-object and multi-object ensemble Themes" in normalized
    assert "aiming for roughly half of each" in normalized
    assert "coherent ensemble of two to five familiar objects" in normalized
    assert "small inhabitants of a real everyday environment" in normalized
    assert "travel between objects" in normalized
    assert "use one object to alter another" in normalized
    assert "Do not scatter unrelated giant props" in normalized
    assert "use at least eight clearly different ordinary-use families" in normalized
    assert "span at least five normal size bands" in normalized
    assert "choose at least three objects" in normalized
    assert "larger than an adult hand" in normalized
    assert "choose no more than three objects" in normalized
    assert "inside a closed adult hand" in normalized
    assert "THE ONE-SENTENCE IDEA" in normalized
    assert "OBJECT TRUTH" in normalized
    assert "HUMAN STAKE" in normalized
    assert "CONCEPT ENGINE" in normalized
    assert "If removing the cast leaves a materials demonstration" in normalized
    assert "CREATIVE-ENGINE SPREAD" in normalized
    assert "at least six substantially different primary engines" in normalized
    assert "No more than two Themes may center on" in normalized
    assert "No more than two may share one relationship grammar" in normalized
    assert "CANDIDATE TOURNAMENT" in normalized
    assert "six genuinely different image opportunities" in normalized
    assert "six images simply tour six components" in normalized
    assert "competition, market, permission system, or intimacy economy" in normalized
    assert "ORDINARY-USE COLLISION" in normalized
    assert "In at least two of the six regions" in normalized
    assert "uses the object in a way instantly recognizable" in normalized
    assert "use the object as designed" in normalized
    assert "EXTERIOR-ONLY SCALE CONTRACT" in normalized
    assert "Never place any body inside the object" in normalized
    assert "Ordinary use never authorizes entry" in normalized
    assert "SIX PROOFS, NOT SIX PARTS" in normalized
    assert "one object-specific ordinary-use collision" in normalized
    assert "At least four stunts must change the cast's goal" in normalized
    assert "At least two must remain compelling" in normalized
    assert "THEME-STAGE CONTRACT" in normalized
    assert "exactly five semicolons" in normalized
    assert "FRAME-STAGE GRID CONTRACT" in normalized
    assert (
        "Every Narrative Frame is one complete portrait 2-column by 3-row grid"
        in normalized
    )
    assert "regardless of frames_per_theme" in normalized
    assert "Never distribute a board across Frames" in normalized
    assert "use one Frame per region" in normalized
    assert (
        "A portrait 2-column by 3-row grid forms one image with six cleanly "
        "separated regions."
        in normalized
    )
    assert (
        "Every person remains outside all colossal everyday objects throughout "
        "the board."
        in normalized
    )
    assert '"Region 1:" through "Region 6:"' in normalized
    assert "When frames_per_theme is 1" not in normalized
    assert "work as a standalone campaign key visual" in normalized
    assert "Do not sanitize erotic or hardcore into neutral imagery" in normalized
    assert "MINIATURE-WORLD CAMERA LANGUAGE" in normalized
    assert "controlled tilt-shift or macro-style selective focus" in normalized
    assert "THUMBNAIL SCALE HIERARCHY" in normalized
    assert "read first at thumbnail size" in normalized
    assert "at least four wide or medium views" in normalized
    assert "showing complete adult bodies" in normalized
    assert "no more than two regions for close detail" in normalized
    assert "one whole-object or ensemble hero view" in normalized
    assert "avoid using a broad featureless flank as a wall" in normalized
    assert "conceal the cast-to-object ratio" in normalized
    assert "graphic surface systems may reinforce scale" in normalized
    assert "miniature eye level along the object's surface" in normalized
    assert "high oblique views revealing tiny bodies" in normalized
    assert "This is crisp editorial advertising photography" in normalized
    assert "not a movie still" in normalized
    assert "Do not use cinematic color grading" in normalized
    assert "BRIGHT CLEAN COLOR STANDARD" in normalized
    assert "bright, clean, high-key color" in normalized
    assert "deliberate complementary contrast" in normalized
    assert "one immediately legible dominant color relationship" in normalized
    assert "bold surrounding color field" in normalized
    assert "Avoid boards dominated by stainless steel gray" in normalized
    assert "same tonal band" in normalized
    assert "commercial tabletop campaign" in normalized
    assert "open shadows with visible detail" in normalized
    assert "PHOTOGRAPHIC MATERIAL STANDARD" in normalized
    assert "FINAL CREATIVE PRIORITIES" in normalized
    assert "they are not a hard quality gate" in normalized
    assert "Eliminate a candidate when" not in normalized
    assert "Reject the Theme when" not in normalized
    assert "- T001:" not in brief


def test_edo_warai_e_brief_respects_all_content_levels() -> None:
    brief = (REPOSITORY_ROOT / "story-inputs" / "edo-warai-e.txt").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(brief.split())

    assert "ADULT CAST, CONSENT, AND CONTENT LEVEL" in normalized
    assert "Honor the exact CLI-requested content_level" in normalized
    assert "aesthetic: keep every adult fully dressed" in normalized
    assert "erotic: make unmistakable adult sensuality visible" in normalized
    assert "clearly erotic but non-explicit interaction" in normalized
    assert "hardcore: show an explicit, consensual adult sexual act" in normalized
    assert "already occurring in every Theme and Frame" in normalized
    assert "do not hide the defining content" in normalized
    assert "LEVEL-AWARE CLOTHING AND BODY" in normalized
    assert "At erotic level, robes may fall open" in normalized
    assert "At hardcore level, adults may be partly or fully nude" in normalized
    assert "directly establish the requested content level" in normalized
    assert "Begin every Frame with the selected level's defining state" in normalized
    assert "preserve the Theme's explicit act in every Frame" in normalized
    assert "intimate but fully clothed interaction" not in normalized
    assert "human anatomy natural and fully covered" not in normalized
    assert "Reject any Frame that depends on nudity" not in normalized


def test_pose_brief_selects_a_varied_text_free_six_pose_group() -> None:
    brief = (REPOSITORY_ROOT / "story-inputs" / "pose.txt").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(brief.split())

    assert "RANDOM POSE-GROUP SELECTION" in normalized
    assert "CAMERA-ANGLE SELECTION" in normalized
    assert "SEXUAL-INTENT GATE" in normalized
    assert "recognizable consensual adult sexual position" in normalized
    assert "Neutral dance, yoga, fitness, wellness, fashion" in normalized
    assert "The body mechanics themselves must carry the sexual intent" in normalized
    assert "Do not neutralize a pool entry" in normalized
    assert "independent varied selection" in normalized
    assert "selection of exactly six pose blueprints" in normalized
    assert "Do not take six adjacent entries" in normalized
    assert "non-sequentially from at least four different pose-family" in normalized
    assert "assign exactly six distinct camera-angle blueprints" in normalized
    assert "use at least four different azimuth families" in normalized
    assert "at least three camera-height or elevation bands" in normalized
    assert "even as a left-right mirror" in normalized
    assert "50-85 mm on full frame" in normalized
    assert "CURATED CAMERA-ANGLE POOL" in normalized
    assert "pose-and-camera blueprints" in normalized
    assert "front three-quarter from left hip height" in normalized
    assert "one dominant region and five supporting regions" in normalized
    assert "Selecting a concrete wearable look is mandatory" in normalized
    assert "WARDROBE EXPOSURE LADDER" in normalized
    assert "strict three-step progression" in normalized
    assert "Aesthetic uses full-size clothing" in normalized
    assert "erotic uses lingerie-size clothing" in normalized
    assert "hardcore uses minimal or micro-scale" in normalized
    assert "coverage could be mistaken for the neighboring level" in normalized
    assert "OCCASION AND SETTING SELECTION" in normalized
    assert "one concrete adult occasion" in normalized
    assert "All six regions inside that Frame must share" in normalized
    assert "Different Frames and different Themes" in normalized
    assert "Exhaust unused setting families" in normalized
    assert "CURATED OCCASION AND LOCATION FAMILIES" in normalized
    assert "PROFESSIONAL IMAGE-MAKING" in normalized
    assert "PRIVATE RESIDENTIAL" in normalized
    assert "HOSPITALITY AND RETREAT" in normalized
    assert "ART, DESIGN, AND PERFORMANCE" in normalized
    assert "PRIVATE WELLNESS AND LEISURE" in normalized
    assert "ARCHITECTURAL SHOWCASES" in normalized
    assert "SECLUDED OUTDOOR SETTINGS" in normalized
    assert "SEASONAL AND ATMOSPHERIC OCCASIONS" in normalized
    assert "not one permanent room" in normalized
    assert "Shared background means shared within one Frame only" in normalized
    assert "different Frames or Themes to reuse the same occasion" in normalized
    assert "Each Frame names one concrete occasion and location" in normalized
    assert "Name the exact garment and accessory pieces" in normalized
    assert "The Theme premise must name the complete selected look" in normalized
    assert "Every Frame must fully restate that look" in normalized
    assert "Include at least one real garment or wearable accessory" in normalized
    assert "wardrobe is never implicit, generic" in normalized
    assert "Garment scale follows the strict exposure ladder" in normalized
    assert "becomes exactly one physical line" in normalized
    assert "all six regions inside that Frame's single uninterrupted" in normalized
    assert "Never distribute one board across multiple Frames" in normalized
    assert "use one Frame per region" in normalized
    assert "no Frame is one region, a board fragment" in normalized
    assert "The finished board contains no visible title, pose names" in normalized
    assert brief.count("\nCURATED POSE POOL\n") == 1
    assert brief.count("\nCURATED CAMERA-ANGLE POOL\n") == 1
    assert brief.count("\nCURATED OCCASION AND LOCATION FAMILIES\n") == 1

    occasion_pool = brief.split(
        "\nCURATED OCCASION AND LOCATION FAMILIES\n", maxsplit=1
    )[1].split("\nCAMERA-ANGLE SELECTION\n", maxsplit=1)[0]
    occasion_entries = [
        line.removeprefix("- ").strip()
        for line in occasion_pool.splitlines()
        if line.startswith("- ")
    ]
    assert len(occasion_entries) >= 40
    assert len(occasion_entries) == len(set(occasion_entries))

    camera_pool = brief.split(
        "\nCURATED CAMERA-ANGLE POOL\n", maxsplit=1
    )[1].split("\nCURATED POSE POOL\n", maxsplit=1)[0]
    camera_entries = [
        line.removeprefix("- ").strip()
        for line in camera_pool.splitlines()
        if line.startswith("- ")
    ]
    assert len(camera_entries) >= 15
    assert len(camera_entries) == len(set(camera_entries))
    assert any("frontal" in entry for entry in camera_entries)
    assert any("side" in entry for entry in camera_entries)
    assert any("rear" in entry for entry in camera_entries)

    pool = brief.split("\nCURATED POSE POOL\n", maxsplit=1)[1]
    pose_entries = [
        line.removeprefix("- ").strip()
        for line in pool.splitlines()
        if line.startswith("- ")
    ]
    assert len(pose_entries) >= 81
    assert len(pose_entries) == len(set(pose_entries))
    assert "invisible wall" not in pool
    assert "seductively" not in pool
    assert "slowly" not in pool
    assert "CURATED SELF-TOUCH POOL" in pool
    assert "NON-EXPLICIT INTIMATE TOUCH" in pool
    assert "DIRECT STATIC ADULT SELF-TOUCH - HARDCORE ONLY" in pool
    for family in (
        "FRONT-PRESENTING STANDING",
        "REAR-PRESENTING STANDING AND HINGED",
        "SEATED AND STRADDLING",
        "KNEELING AND HEEL-SUPPORTED",
        "CROUCHED AND SQUATTING",
        "SUPINE AND PELVIS-LIFTED",
        "SIDE-LYING AND TWISTED",
        "PRONE AND CHEST-SUPPORTED",
        "HANDS-AND-KNEES AND FOREARM-SUPPORTED",
    ):
        assert family in pool
