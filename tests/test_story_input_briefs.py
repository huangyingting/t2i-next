from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_story_inputs_use_only_the_current_authoring_contract() -> None:
    story_inputs = sorted((REPOSITORY_ROOT / "story-inputs").glob("*.txt"))

    assert story_inputs
    assert not (REPOSITORY_ROOT / "story-inputs" / "multi-view-scenes.txt").exists()

    for story_input in story_inputs:
        brief = story_input.read_text(encoding="utf-8")

        assert brief.startswith("BRIEF\n\n"), story_input.name
        assert "Theme" in brief, story_input.name
        assert "Frame" in brief, story_input.name
        assert "CLI" not in brief, story_input.name
        assert "Generate exactly the Theme count" not in brief, story_input.name
        assert "Generate exactly the Theme and Frames-per-Theme counts" not in brief, (
            story_input.name
        )
        assert "cast as a creative seed" not in brief, story_input.name
        assert "time advances through causally connected beats" not in brief, (
            story_input.name
        )


def test_rebuilt_legacy_inputs_are_complete_story_descriptions() -> None:
    required_sections = (
        "BRIEF",
        "THEME CONTRACT",
        "FRAME CONTRACT",
        "VARIATION AND REJECTION RULES",
    )

    for filename in ("avantgarde.txt", "snofs.txt", "tentacle.txt"):
        brief = (REPOSITORY_ROOT / "story-inputs" / filename).read_text(
            encoding="utf-8"
        )

        assert all(section in brief for section in required_sections), filename
        assert "At aesthetic level" in brief, filename
        assert "At erotic level" in brief, filename
        assert "At hardcore level" in brief, filename


def test_story_inputs_do_not_override_run_level_cast_or_frame_semantics() -> None:
    film_post = (REPOSITORY_ROOT / "story-inputs" / "film-post.txt").read_text(
        encoding="utf-8"
    )
    zero_gravity = (
        REPOSITORY_ROOT / "story-inputs" / "zero-gravity-intimacy.txt"
    ).read_text(encoding="utf-8")

    assert "Use the exact requested cast and no additional people" in film_post
    assert "must appear clearly in every Theme premise and every poster" in film_post
    assert "At hardcore level" in zero_gravity
    assert "incompatible with hardcore" not in zero_gravity
    assert "Keep intimate actions non-graphic" not in zero_gravity


def test_dress_board_region_names_are_layout_only() -> None:
    brief = (REPOSITORY_ROOT / "story-inputs" / "dress.txt").read_text(encoding="utf-8")
    normalized = " ".join(brief.split())

    assert "Do not render the Theme title or region names as visible text." in brief
    assert "Use region names only as internal layout references" in brief
    assert "Begin the scale at visibly sensual" in normalized
    assert "requires a cast of one woman and zero men" in normalized
    assert "zero or one visually restrained body-safe adult product" in normalized
    assert "adult product-and-wearable fashion system" in normalized
    assert (
        "Include one to three clearly designed body-safe adult products" in normalized
    )
    assert "EXAGGERATED BRIGHT CHARACTER STYLING" in normalized
    assert (
        "hairstyle, outfit design, worn styling, and visible facial expression"
        in normalized
    )
    assert "bright lighting alone" in normalized
    assert "DECISION ORDER" in normalized
    assert "A later choice must never weaken an earlier one" in normalized
    assert "limited high-chroma palette" in normalized
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
    assert "do not leak untranslated English workflow words" in normalized
    assert "Do not pad final prose with compliance-shaped negations" in normalized
    assert "does not satisfy product emphasis" in normalized
    assert "Do not use the words futuristic" in normalized
    assert "generic mid-gray walls" in normalized
    assert "flat, shadowless catalog lighting" in normalized
    assert "Every named product has its real shape and intended fit" in normalized
    assert "Every Frame differs from other Frames" in normalized
    assert "Final prose never states an internal content level" in normalized
    assert "cybernetic body parts" in normalized
    assert (
        "State shared identity, outfit, palette, and inventory facts once"
        in normalized
    )
    assert "technology-shaped costume components" in normalized
    assert "utilitarian futurism" not in normalized
    assert "Aesthetic is sensual lingerie-led fashion" in normalized
    assert "hardcore is a BDSM wardrobe-and-equipment system" in normalized
    assert "Present one complete, opaque, non-erotic outfit." not in brief
    assert "At aesthetic level, include none." not in brief

    wardrobe_pool = brief.split("\nCURATED HARDCORE WARDROBE ARCHETYPES\n", maxsplit=1)[
        1
    ].split("\nCURATED HARDCORE EQUIPMENT SYSTEMS\n", maxsplit=1)[0]
    equipment_pool = brief.split("\nCURATED HARDCORE EQUIPMENT SYSTEMS\n", maxsplit=1)[
        1
    ].split("\nCURATED EXPLICIT BDSM PRODUCT CATEGORIES\n", maxsplit=1)[0]
    product_pool = brief.split(
        "\nCURATED EXPLICIT BDSM PRODUCT CATEGORIES\n", maxsplit=1
    )[1].split("\nCURATED SEX TOY PRODUCT CATEGORIES\n", maxsplit=1)[0]
    sex_toy_pool = brief.split("\nCURATED SEX TOY PRODUCT CATEGORIES\n", maxsplit=1)[
        1
    ].split("\nCURATED HARDCORE MATERIAL AND COLOR SYSTEMS\n", maxsplit=1)[0]
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
        assert len(entries) >= 8
        assert len(entries) == len(set(entries))

    explicit_product_entries = [
        line.removeprefix("- ").strip()
        for line in product_pool.splitlines()
        if line.startswith("- ")
    ]
    assert len(explicit_product_entries) >= 12
    sex_toy_entries = [
        line.removeprefix("- ").strip()
        for line in sex_toy_pool.splitlines()
        if line.startswith("- ")
    ]
    assert len(sex_toy_entries) >= 10

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
        "one oversized condensed headline assembled on a torn paper slab" in normalized
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
    assert "exact physical carrier, poster location" in normalized
    assert "add an ASCII colon" in normalized
    assert "end with an ASCII semicolon" in normalized
    assert "Never enclose copy in quotation marks" in normalized
    assert "zero Chinese characters" in normalized
    assert "do not authorize Chinese writing in the image" in normalized
    assert "no quotation mark surrounds visible copy" in normalized
    assert "If a word is not explicitly declared in that passage" in normalized
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


def test_post_briefs_isolate_text_without_removing_poster_copy() -> None:
    film_post = (
        REPOSITORY_ROOT / "story-inputs" / "film-post.txt"
    ).read_text(encoding="utf-8")
    post_layout = (
        REPOSITORY_ROOT / "story-inputs" / "post-layout.txt"
    ).read_text(encoding="utf-8")

    for filename, brief in (
        ("film-post.txt", film_post),
        ("post-layout.txt", post_layout),
    ):
        normalized = " ".join(brief.split())

        assert "TEXT-LAYER ISOLATION LOCK" in normalized, filename
        assert "Frame prose must use English throughout" in normalized, filename
        assert "During Theme generation" in normalized, filename
        assert (
            "Every character in the complete Frame must be ASCII code point"
            in normalized
        ), filename
        assert "U+2018 and U+2019 with a straight apostrophe" in normalized, filename
        assert "dedicated image-text passage" in normalized, filename
        assert "add an ASCII colon" in normalized, filename
        assert "end with an ASCII semicolon" in normalized, filename
        assert "the literal characters `: `" in normalized, filename
        assert "never write the words colon or semicolon" in normalized, filename
        assert "The Frame's final character is `;`" in normalized, filename
        assert "gibberish" in normalized, filename
        assert "unreadable microtext" in normalized, filename
        assert "exactly three readable English strings" not in normalized, filename
        assert "exactly three controlled typography zones" not in normalized, filename

    film_normalized = " ".join(film_post.split())
    assert (
        "Keep the original theatrical copy package and typography freedom"
        in film_normalized
    )
    assert "title, tagline, release line, billing block, credits" in film_normalized
    assert "one original English tagline written for that design" in film_normalized
    assert "and a compact fictional English billing block" in film_normalized
    assert "evidence and archive: receipts, letters, maps" in film_normalized
    assert "handwritten evidence" in film_normalized

    layout_normalized = " ".join(post_layout.split())
    assert "Visible-copy serialization must not change the poster design" in (
        layout_normalized
    )
    assert (
        "Do not remove or simplify editorial fragments, credits, quotations, "
        "dates, venue details" in layout_normalized
    )
    assert (
        "a few short English editorial fragments, credits, quotation blocks, "
        "date or venue details" in layout_normalized
    )
    assert (
        "ticket, photograph edge, credit strip, badge, sign" in layout_normalized
    )


def _legacy_everyday_social_caricature_contract() -> None:
    brief = (
        REPOSITORY_ROOT / "story-inputs" / "everyday-social-caricature.txt"
    ).read_text(encoding="utf-8")
    normalized = " ".join(brief.split())

    assert "EAST ASIAN CAST AND SETTING LOCK" in normalized
    assert "Every visible person is a fictional East Asian adult" in normalized
    assert (
        "mainland Chinese, Taiwanese, Hong Kong Chinese, Japanese, South Korean, "
        "and Singaporean Chinese"
        in normalized
    )
    assert "Set every Theme and Frame in mainland China, Taiwan, Hong Kong" in normalized
    assert "Use plausible local names in ASCII Latin letters" in normalized
    assert "Every Theme premise must explicitly identify each person's allowed identity" in (
        normalized
    )
    assert "Every Frame must identify every adult as an East Asian woman or East Asian man" in normalized
    assert "WOMAN-CENTERED AGENCY" in normalized
    assert "At least one adult woman is the unmistakable narrative" in normalized
    assert "Use exactly the requested cast and add no bystanders" in normalized
    assert "ENGLISH OUTPUT AND REAL-PERSON PHOTOMONTAGE LOCK" in normalized
    assert "complete Frame in English, regardless of the requested output language" in (
        normalized
    )
    assert "Use English-only ASCII characters" in normalized
    assert "Reject any code point outside ASCII U+0020 through U+007E" in normalized
    assert "Write personal names in normal Title Case" in normalized
    assert "reserve uppercase words exclusively for exact visible copy" in normalized
    assert (
        "Flat satirical photomontage assembled from photographs of real adult "
        "performers:"
        in normalized
    )
    assert "exact cast supplied by the generation request" in normalized
    assert "Exactly [requested total] East Asian adults fill the image" in normalized
    assert "Omit a gender phrase when its requested count is zero" in normalized
    assert "Never infer, default, or hard-code any count in this brief" in normalized
    assert "two East Asian women and one East Asian man" not in normalized
    assert "repeat the complete opening cast declaration verbatim" in normalized
    assert "final two-entry text passage" in normalized
    assert "Every visible person must remain unmistakably photographic and human" in (
        normalized
    )
    assert "Do not use illustration, drawing, painting" in normalized
    assert "anime, manga, chibi" in normalized
    assert "real photographic adult cutouts" in normalized
    assert "The final style sentence must positively restate" in normalized
    assert "LIFE AS THE SOURCE" in normalized
    assert "invisible domestic labor" in normalized
    assert "friendship rituals" in normalized
    assert "dating, courtship, commitment" in normalized
    assert "workplace meetings" in normalized
    assert "attention, imitation, approval, self-presentation" in normalized
    assert "CARICATURE AND CONTROLLED DISTORTION" in normalized
    assert "Exaggerate decisively" in normalized
    assert "SATIRICAL CARICATURE HARD GATE" in normalized
    assert "one controlled caricatural exaggeration" in normalized
    assert "thirty to forty percent of the image" in normalized
    assert "Exactly one physical supporting object" in normalized
    assert "CONTROLLED WHOLE-BODY EXAGGERATION" in normalized
    assert "Every adult appears as one intact photographic person" in normalized
    assert "Use no more than one anatomical or silhouette exaggeration" in normalized
    assert "Never cut, paste, duplicate, float, detach, fold, splice" in normalized
    assert "Do not exaggerate breasts, buttocks, genitals, tongue" in normalized
    assert "Do not use exact body-part canvas percentages" in normalized
    assert "Branch immediately after the cast sentence" in normalized
    assert "For hardcore, the second sentence must begin with the explicit act" in (
        normalized
    )
    assert "All requested adults are already joined in one consensual explicit act:" in (
        normalized
    )
    assert "This sentence contains only names, involved anatomy, present contact" in (
        normalized
    )
    assert "within the first eighty English words after the fixed opening phrase" in (
        normalized
    )
    assert "Only after this early content proof" in normalized
    assert "complete head-to-foot outfit" in normalized
    assert "including top, bottom or one-piece garment, and footwear" in normalized
    assert "describe each adult's remaining or displaced clothing" in normalized
    assert "Clothing must not cover or contradict required contact" in normalized
    assert "Immediately after the selected-level proof" in normalized
    assert "All figures are frontal whole-person photographic cutouts" in normalized
    assert "before faces, metaphor, setting, or props" in normalized
    assert "Never mention instructions, sentence numbers, requirements" in normalized
    assert "Exaggerate decisively, but select exactly one item" in normalized
    assert "Never assign a second item from the list to the same person" in normalized
    assert "These choices are mutually exclusive" in normalized
    assert "whole-body scaling leaves hair, garments, limbs, and face unaltered" in (
        normalized
    )
    assert "scaled between seventy and one hundred thirty percent" in normalized
    assert "without changing the size or shape of any facial organ" in normalized
    assert "Never resize or paste a face or isolated organ" in normalized
    assert "All faces must remain unmistakably mature" in normalized
    assert "Reject smooth doll faces, huge sparkling eyes" in normalized
    assert "DRAW FIRST, DESCRIBE SECOND" in normalized
    assert "silently draw at least three radically different thumbnail" in normalized
    assert "using only black shapes and one accent color" in normalized
    assert "silently assemble one complete final photomontage" in normalized
    assert "separately photographed real adult performers" in normalized
    assert "following the viewer's scan order from dominant icon" in normalized
    assert "If a symbol requires explanation, redesign it before writing" in normalized
    assert "fill thirty-five to fifty percent of the entire image area" in normalized
    assert "VISUAL LABEL AND POWER MAP" in normalized
    assert "Give each side a concrete visual label" in normalized
    assert "Use one blunt visual contest that survives without context" in normalized
    assert "If the scene can be mistaken for an ordinary lifestyle illustration" in (
        normalized
    )
    assert "METAPHOR AND SYMBOL SYSTEM" in normalized
    assert "Use an animal, object, garment, or emblem as a visual label" in normalized
    assert "Every symbol must have one clear referent" in normalized
    assert "ACTION-METAPHOR COUPLING GATE" in normalized
    assert "one closed causal force chain" in normalized
    assert "central woman's intimate movement applies one visible directional force" in (
        normalized
    )
    assert "another participant's body transmits that same force" in normalized
    assert "primary metaphor visibly changes mechanical state because of the bodies" in (
        normalized
    )
    assert "changed mechanism redirects pressure into every remaining participant" in (
        normalized
    )
    assert "At least two adults must directly touch, load, grip, brace, block" in normalized
    assert "If removing the explicit interaction leaves the metaphor unchanged" in (
        normalized
    )
    assert "Because [central woman] [physical verb]" in normalized
    assert "CONTENT-LEVEL INTEGRATION" in normalized
    assert "At aesthetic level" in normalized
    assert "name one complete opaque outfit for each adult" in normalized
    assert "Show no bare torso, transparent garment, lingerie" in normalized
    assert "At erotic level" in normalized
    assert "At hardcore level" in normalized
    assert "Every requested participant must make direct intimate physical contact" in (
        normalized
    )
    assert "through penetration, oral-genital contact, or direct genital stimulation" in (
        normalized
    )
    assert "Looking, kissing, touching shoulders or hips" in normalized
    assert "Include no clothed spectator or queued participant" in normalized
    assert "Do not pin, trap, force, dominate, restrain" in normalized
    assert "include no loose props or debris" in normalized
    assert "NON-NEGOTIABLE PRIORITY" in normalized
    assert "everyone awake, alert, willing" in normalized
    assert "PLANNED ENGLISH LABEL SYSTEM" in normalized
    assert "Every Theme must choose one meaningful pair of opposed English labels" in (
        normalized
    )
    assert "Each label contains one or two short words" in normalized
    assert "Lock the exact pair during Theme generation" in normalized
    assert "Locked image labels: FIRST LABEL | SECOND LABEL." in normalized
    assert "The Frame must preserve this exact pair" in normalized
    assert "Give each label one large, simple physical carrier" in normalized
    assert "No other readable or pseudo-readable content may appear" in normalized
    assert "The two clean label carriers are the only text-bearing surfaces" in (
        normalized
    )
    assert "LEXICAL TEXT-CARRIER BAN" in normalized
    assert "Do not use any of these English words or their plurals" in normalized
    assert "Replace any candidate containing one of these words" in normalized
    assert "microtext, card, pass, knife, cleaver, blade" in normalized
    assert "weapon, pin, pinned, trap, trapped, force, forced" in normalized
    assert "THEME CONTENT-PROOF GATE" in normalized
    assert "The Theme premise itself must contain the complete visible proof" in (
        normalized
    )
    assert "Do not substitute vague phrases such as sexual activity" in normalized
    assert "Hardcore does not imply BDSM" in normalized
    assert "one Theme sentence must account for every requested participant" in normalized
    assert "Touching only oneself, clothing, furniture, or a prop does not qualify" in (
        normalized
    )
    assert "Never describe any participant as preparing, approaching" in normalized
    assert "Every erotic Frame must include at least one" in normalized
    assert "Bare shoulders, cleavage, exposed thighs, sleepwear" in normalized
    assert "the explicit interaction is the sole ongoing human action" in normalized
    assert "No participant simultaneously reads, types, calculates" in normalized
    assert "The humor comes from desire, etiquette, attention" in normalized
    assert "DIRECT AND POPULAR LEGIBILITY" in normalized
    assert "understandable without text" in normalized
    assert "Use a poster-like hierarchy" in normalized
    assert "at least four fifths of the composition" in normalized
    assert "Photograph each real performer frontally or in a shallow side pose" in (
        normalized
    )
    assert "one exact orthographic poster plane" in normalized
    assert "must not resemble people photographed together in a real room" in normalized
    assert "single matte field with no floor line, wall corner, ceiling" in normalized
    assert "IMAGE-TEXT GATE" in normalized
    assert "Every Frame must visibly include the Theme's exact pair" in normalized
    assert "Every letter must be at least one twentieth of the image height" in (
        normalized
    )
    assert "each complete label must occupy at least one eighth" in normalized
    assert "inside the central eighty percent of the canvas" in normalized
    assert "minimum ten-percent safety margin" in normalized
    assert "inside ten-percent safety margin: WORK;" in normalized
    assert "Spell each locked label exactly twice in the complete Frame" in normalized
    assert "Repetition reinforces correct image rendering" in normalized
    assert "dedicated image-text passage at the absolute end" in normalized
    assert "Write exactly two entries" in normalized
    assert "minimum letter height, horizontal orientation, type weight" in normalized
    assert "Use the literal characters `: `" in normalized
    assert "Do not add an IMAGE-TEXT heading" in normalized
    assert "The Frame's final character" in normalized
    assert "Write this dedicated passage once only" in normalized
    assert "never restart or duplicate either carrier-copy entry" in normalized
    assert "Use this serialization grammar exactly" in normalized
    assert "After each colon, write only the exact locked label" in normalized
    assert "Every other surface must contain zero letters" in normalized
    assert "its entire visible typographic content must be one of the two" in normalized
    assert "If removing the words makes the satire unintelligible" in normalized
    assert "Do not use interpretive phrases such as symbolizes" in normalized
    assert "do not hard-code a sentence count" in normalized
    assert "one stable anchor sentence per adult when needed" in normalized
    assert "verbatim opening cast declaration" in normalized
    assert "The only supporting object is one [singular object]" in normalized
    assert "Name no other loose object, debris, food scatter" in normalized
    assert "Perform a final character scan on every Theme and Frame" in normalized
    assert "REAL-PERSON PHOTOMONTAGE LANGUAGE" in normalized
    assert "premium physical editorial photomontage" in normalized
    assert "full natural color and photographic tonal variation" in normalized
    assert "THEME CONTRACT" in normalized
    assert "FRAME CONTRACT" in normalized
    assert "WITHIN-THEME CONTINUITY LOCK" in normalized
    assert "names, allowed identities, ages, facial anchors, hair" in normalized
    assert "base garments, chosen exaggerations, primary metaphor, and label pair" in (
        normalized
    )
    assert "Clothing may shift only as required by the selected interaction" in normalized
    assert "requested women and men visually unambiguous" in normalized
    assert "No generic shocked open mouths" in normalized
    assert "VARIATION AND REJECTION RULES" in normalized


def test_everyday_social_caricature_centers_women_and_lived_interaction() -> None:
    brief = (
        REPOSITORY_ROOT / "story-inputs" / "everyday-social-caricature.txt"
    ).read_text(encoding="utf-8")
    normalized = " ".join(brief.split())

    assert len(brief.splitlines()) <= 150
    assert len(brief) <= 17_000
    assert brief.isascii()

    required_contract = (
        "Create original, woman-centered editorial caricatures",
        "humorous at first glance and bitter on reflection",
        "Satirize conduct and relationships, never identity itself",
        "PRIORITY",
        "exact requested cast",
        "action-metaphor causality",
        "CAST, SETTING, AND OUTPUT",
        "exactly the script-requested number of women and men",
        "Every visible person is a fictional, willing, alert East Asian adult",
        "mainland Chinese, Taiwanese, Hong Kong Chinese, Japanese",
        "Set the scene in mainland China, Taiwan, Hong Kong, Japan",
        "Give each exactly one identity phrase from this list verbatim",
        "Never add a second nationality, citizenship, diaspora",
        "State each person's gender explicitly",
        "never all-capital surnames",
        "English-only ASCII",
        "replace smart punctuation, multiplication signs, and non-English glyphs",
        "CONTENT LEVEL",
        "At aesthetic level",
        "At erotic level",
        "At hardcore level",
        "name every participant's anatomy-and-contact role",
        "holding unrelated items, directing a pose, or touching clothing does not count",
        "order the cast A > B > C and onward",
        "permit only adjacent-pair sexual contacts",
        "C never touches A",
        "one exclusive target",
        "the act is independently chosen recreation",
        "never evidence, payment, initiation, punishment, leverage",
        "No one demands, requires, forces, purchases, trades, rewards, or records the act",
        "WARDROBE AND CLEAN BACKGROUND",
        "striking head-to-foot editorial styling",
        "one bold clothing silhouette",
        "high-contrast color blocking",
        "without becoming another deformation, label, symbol, or metaphor",
        "Reject generic default officewear",
        "one broad matte color field plus at most two simple geometric cues",
        "Include no room inventory, decorative clutter",
        "The cast, primary structure, and paired motif dominate the image",
        "BITING PHYSICAL CARICATURE",
        "exactly two coordinated layers of deformation",
        "one coherent facial caricature combining at least two altered features",
        "elongated longitudinally, widened transversely, or enlarged uniformly",
        "two to four times ordinary scale",
        "shortened longitudinally, narrowed transversely, or reduced uniformly",
        "one-half to one-quarter ordinary scale",
        "Name both facial alterations explicitly",
        "exactly one allowed verb-axis pair and one numeric scale",
        "Never combine opposing size verbs or alter a second axis",
        "A general expression or unquantified adjective does not qualify",
        "The matching limb and adjacent parts remain ordinary",
        "never satisfy the required nonfacial layer",
        "may not invent, spread, intensify, or transfer a deformation",
        "Every other adult receives exactly one different secondary",
        "Choose either one facial cluster or one body or limb change, never both",
        "If body or limb is chosen, keep the face ordinary",
        "if face is chosen, keep all body proportions ordinary",
        "Scale changes stop cleanly at named joints",
        "The face, body, gesture, and action must communicate the same trait",
        "SHARED ACTION AND METAPHOR",
        "one closed reaction circuit",
        "thirty-five to fifty percent of the canvas",
        "State each contact point, force direction, immediate physical change",
        "Give every named adult one visible contact-force-result clause",
        "For hardcore scenes, the explicit act is the sole ongoing human action",
        "PHYSICAL STAGING",
        "Describe one frozen instant",
        "left-to-right and overlap position, facing, weight-bearing support",
        "Every contact must name two anatomically reachable surfaces",
        "Preserve one coherent occupancy map",
        "no limb passes through a body or structure",
        "no unsupported hovering",
        "No body may thread, loop, wrap, weave through, or be bisected",
        "Reflective props show abstract glare, never duplicated people or anatomy",
        "never attachment, balance, reach path, collision, or load transfer",
        "hard edges may touch only feet, knees, hands, or forearms",
        "A broad flat surface may support the back or seat without pressure",
        "no structure may press, wedge, trap, or bisect the head",
        "B must occupy the physical center and directly neighbor both endpoints",
        "Left-to-right order must be A-B-C or C-B-A",
        "No person or limb may reach across, behind, around, over, under, or through the third person",
        "If the tableau cannot be reconstructed physically",
        "establish the complete physical staging map before describing",
        "exactly one supporting motif represented by two related physical instances",
        "HYBRID NEWSPAPER PHOTOMONTAGE",
        "separately photographed real adult performers",
        "bold adult newspaper screen print",
        "photographic texture inside each deformed cutout",
        "exactly four dominant flat spot-color fields outside natural skin and hair",
        "Controlled graphic foreshortening",
        "impossible independently of camera proximity",
        "TEXT PAIR",
        "Locked image labels: FIRST LABEL | SECOND LABEL.",
        "each locked label exactly once and only in the terminal serialization",
        "Never choose an inherently text-bearing object as the primary structure",
        "COMPLIANCE GATE",
        "participant contact graph, occupancy map",
        "discard the whole draft and rebuild it",
        "THEME CONTRACT",
        '"Cast:" lists every Title Case name, age of at least twenty-five',
        '"Deformations:" lists CENTRAL NAME',
        "explicit woman or man",
        "feature plus alteration; feature plus alteration",
        "one nonfacial part, allowed verb-axis pair, and valid scale",
        '"Consent:" states that every adult freely chose recreation',
        '"Staging:" fixes A-B-C or C-B-A spatial order, B centered',
        '"Hardcore proof: Chain A > B > C.',
        "No other sexual contact.",
        "unified real-person newspaper photomontage medium",
        "FRAME CONTRACT",
        "Hybrid real-person newspaper photomontage with biting anatomical caricature:",
        "Exactly [requested total] East Asian adults fill the image",
        "Preserve every Theme age, identity, wardrobe, deformation, chain order",
        "VARIATION AND REJECTION",
        "mixed media",
        "interchangeable clothing",
        "cluttered background",
        "nonadjacent or repeated contact pair",
        "contact count other than cast-size-minus-one",
        "chain midpoint outside the spatial center",
        "contact reaching across the third adult",
        "shared anatomical target",
        "a supporting adult with both facial and bodily change",
        "opposing scale verbs",
        "deformation spreading to adjacent parts",
        "a body threaded through a structure",
        "hard edge against a core body part",
        "structure pressing or trapping a body",
        "non-ASCII glyph",
        "unsupported, intersecting, or irreconstructible staging",
    )
    for marker in required_contract:
        assert marker in normalized

    conflicting_contracts = (
        "Continue immediately with the complete dominant visual icon",
        "Do not use photographic",
        "Select a coherent original medium",
        "roughly one third of the image",
        "Choose one dominant deformation grammar per Theme",
        "both adults' different dominant deformations",
        "five to eight complete sentences",
        "premise of no more than two sentences",
        "foreground, middle ground, background",
        "forced perspective",
        "the viewpoint, distance, or perspective",
    )
    for conflict in conflicting_contracts:
        assert conflict not in normalized


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
        "separated regions." in normalized
    )
    assert (
        "Every person remains outside all colossal everyday objects throughout "
        "the board." in normalized
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
    assert "Honor the exact requested content level" in normalized
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


def test_edo_warai_e_requires_live_action_ukiyo_e_evidence() -> None:
    brief = (REPOSITORY_ROOT / "story-inputs" / "edo-warai-e.txt").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(brief.split())

    assert "PERFORMED UKIYO-E TRANSLATION" in brief
    assert "UKIYO-E COLOR GATE" in brief
    assert "DISTANCE-READ FLATNESS GATE" in brief
    assert "EDO MATERIAL PATINA" in brief
    assert "Flat, borderless nishiki-e theatrical picture plane" in normalized
    assert "enacted by real adult performers" in normalized
    assert "not a literal woodblock print" in normalized
    assert "keyblock-like contour separation" in normalized
    assert "nishiki-e palette" in normalized
    assert "flat separated color blocks" in normalized
    assert "one bokashi-style gradient" in normalized
    assert (
        "At thumbnail size and viewing distance, every Frame must read as a flat "
        "nishiki-e composition" in normalized
    )
    assert "exactly three shallow stacked bands" in normalized
    assert "dominant flat silhouettes" in normalized
    assert "no volumetric light-and-shadow modeling" in normalized
    assert "Bokashi belongs to one background plane" in normalized
    assert "Close inspection may reveal live performers" in normalized
    assert "must never overturn the flat distance read" in normalized
    assert (
        '"Flat, borderless nishiki-e theatrical picture plane in a '
        "[chūban-like or ōban-like] [vertical or horizontal] proportion, enacted "
        "by real adult performers. Exactly three shallow stacked picture bands: "
        "a lower prop strip, a central adult tableau, and an upper architectural "
        "strip, all parallel to the image surface. Adult faces, limbs, garments, "
        "and furniture read as contour-enclosed matte color shapes with crisp "
        "overlaps and two-step values; contour and flat shadow shapes carry all "
        "form. "
        "Edo-period material patina appears only as bounded wear on physical "
        'costumes, props, and set surfaces."' in normalized
    )
    assert "all adults remain in the central picture band" in normalized
    assert "No near-far scale change or projecting foreshortened limbs" in normalized
    assert "Repeat this exact flat-medium lock immediately after" in normalized
    assert (
        "All visible bodies, garments, props, and room planes return immediately "
        "to contour-enclosed matte color shapes on the same flat three-band "
        "nishiki-e surface." in normalized
    )
    assert (
        "combine exactly two close-read performer cues chosen only from" in normalized
    )
    assert "Target 700 to 900 English words" in normalized
    assert "never exceed 1000 English words" in normalized
    assert "one solvable three-dimensional arrangement" not in normalized
    assert "foreground, middle ground, and background" not in normalized
    assert "live-action image of real adult performers" not in normalized
    assert "individual hairs" not in normalized
    assert "subtle skin variation" not in normalized
    assert "three to five specific signs of ordinary age and handling" in normalized
    assert "protected seams remain richer" in normalized
    assert "Distribute wear according to touch, friction, smoke, moisture" in normalized
    assert "must not turn the whole image brown, beige, gray, or desaturated" in (
        normalized
    )
    assert "Keep adult skin as a warm, bounded matte field" in normalized
    assert "global sepia or yellow cast" in normalized
    assert "photographic grain" in normalized
    assert "scanned-print damage" in normalized
    assert "Return only positive prose describing the depicted scene" in normalized
    assert "Enforce every rule silently" in normalized
    assert "Every word must belong to the image-generation description" in normalized
    assert '"The current fully clothed non-erotic interaction is"' in normalized
    assert '"The current erotic but non-explicit interaction is"' in normalized
    assert '"The current explicit consensual adult sexual act is"' in normalized
    assert "name the occurring act directly" in normalized
    assert "Prussian blue is permitted only for settings from the 1820s onward" in (
        normalized
    )
    assert "full-frame or medium-format camera" not in normalized
    assert "mm equivalent" not in normalized
    assert "aperture behavior" not in normalized
    assert "depth of field" not in normalized


def test_ming_gongbi_mixi_tu_owns_historical_painting_contract() -> None:
    brief = (REPOSITORY_ROOT / "story-inputs" / "ming-gongbi-mixi-tu.txt").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(brief.split())

    assert brief.startswith("BRIEF\n\n")
    assert "LATE-MING JIANGNAN WORLD" in brief
    assert "GONGBI LINE DISCIPLINE" in brief
    assert "LAYERED GONGBI COLOR" in brief
    assert "CHINESE PAINTING SPACE" in brief
    assert "FLAT GONGBI PICTURE-PLANE GATE" in brief
    assert "ARCHIVAL FACSIMILE MEDIUM LOCK" in brief
    assert "HUMANIZED GONGBI FIGURE DETAIL" in brief
    assert "BORDERLESS FULL-BLEED SILK GATE" in brief
    assert "AGED SILK AND PIGMENT PATINA" in brief
    assert "anonymous late-Ming Jiangnan workshop album leaf" in normalized
    assert "between 1573 and 1644" in normalized
    assert "prepared silk or sized xuan paper" in normalized
    assert "gossamer-line delicacy" in normalized
    assert "iron-wire steadiness" in normalized
    assert "ruled-line jiehua discipline" in normalized
    assert "visual logic of sanfan jiuran" in normalized
    assert "five to seven principal color families" in normalized
    assert "scattered perspective" in normalized
    assert "flat picture plane must dominate the first read" in normalized
    assert "minimal tonal modeling" in normalized
    assert "no volumetric light-and-shadow modeling" in normalized
    assert "Age must be visible at first glance and thumbnail size" in normalized
    assert "roughly two-thirds of the impression" in normalized
    assert "one-third from visible material age" in normalized
    assert "Full-canvas continuous-silk flat archival facsimile" in normalized
    assert "two to four shallow, stacked, overlapping bands" in normalized
    assert "contour-enclosed color fields" in normalized
    assert "darker tea-brown edge oxidation" in normalized
    assert "one shallow age crease" in normalized
    assert "aged prepared-silk painting extends continuously to every canvas edge" in (
        normalized
    )
    assert (
        "no visible mounting margin, mat, frame, border, or rectangular edge band"
        in normalized
    )
    assert "Edge patina must break, vary, and dissolve inward irregularly" in normalized
    assert "Human specificity comes from line drawing and bounded washes" in normalized
    assert "subtle facial asymmetry" in normalized
    assert "exactly three restrained skin tones" in normalized
    assert "convincingly human but unmistakably painted" in normalized
    assert "flat archival facsimile of a hand-painted antique silk album leaf" in (
        normalized
    )
    assert "borderless full-bleed composition" in normalized
    assert (
        "Every person, garment, object, and architectural plane exists only as ink "
        "contour and pigment on silk" in normalized
    )
    assert "Repeat this compact medium lock immediately after" in normalized
    assert "use exactly four descriptive sentences" in normalized
    assert "No sentence after the fixed five-sentence opening may exceed 60" in (
        normalized
    )
    assert 'literal phrase "three shallow stacked bands"' in normalized
    assert "between 350 and 750 English words" in normalized
    assert "Count before returning" in normalized
    assert (
        "The entire image remains a visibly aged, flat, hand-painted gongbi silk "
        "album leaf made from ink contours and mineral pigment" in normalized
    )
    assert "three to five localized, physically plausible age cues" in normalized
    assert "Japanese ukiyo-e" in normalized
    assert "modern guochao illustration" in normalized
    assert "Do not generate readable Chinese" in normalized
    assert '"The current explicit consensual adult sexual act is"' in normalized
    assert "directly naming or describing male reproductive anatomy" in normalized
    assert "Every human mentioned in the Theme or Frame must belong" in normalized
    assert "Do not introduce an absent spouse" in normalized

    frame_contract = brief.split("\nFRAME CONTRACT\n", maxsplit=1)[1]
    for photography_trigger in (
        "observed-from-life",
        "lifelike",
        "living adult sitters",
        "subtle flesh variation",
        "credible weight",
        "painted from observation",
    ):
        assert photography_trigger not in frame_contract


def test_pose_brief_selects_a_varied_text_free_six_pose_group() -> None:
    brief = (REPOSITORY_ROOT / "story-inputs" / "pose.txt").read_text(encoding="utf-8")
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

    camera_pool = brief.split("\nCURATED CAMERA-ANGLE POOL\n", maxsplit=1)[1].split(
        "\nCURATED POSE POOL\n", maxsplit=1
    )[0]
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


def test_threshold_emergence_brief_locks_cast_geometry_and_batch_variety() -> None:
    brief = (REPOSITORY_ROOT / "story-inputs" / "threshold-emergence.txt").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(brief.split())

    assert "EMERGING WOMEN + WITNESS WOMEN = REQUESTED WOMEN" in normalized
    assert "EMERGING MEN + WITNESS MEN = REQUESTED MEN" in normalized
    assert "Never treat the requested cast as witnesses" in normalized
    assert "Every visible or implied human counts toward the cast" in normalized
    assert "The source-side body must remain recognizably human anatomy" in normalized
    assert "The source plane intersects the emerging person once" in normalized
    assert "HALF-IN, HALF-OUT SILHOUETTE" in normalized
    assert "roughly forty to sixty percent of the body is on each side" in normalized
    assert "the pelvis plus at least one complete connected leg inside" in normalized
    assert "REFERENCE CRAWL CHOREOGRAPHY" in normalized
    assert "The adult crawls headfirst perpendicular to the screen" in normalized
    assert "the bezel stays fully visible around the waist" in normalized
    assert "SINGLE-SCENE RENDERING CONTRACT" in normalized
    assert "one camera, one continuous outer location" in normalized
    assert "appears only inside the exact bounded area" in normalized
    assert "End every Frame with one concise geometry-lock sentence" in normalized
    assert "no split screen, second set, reflected duplicate" in normalized
    assert "Do not flatten, paint, pixelate, dissolve" in normalized
    assert "no full-body ripple, translucent overlay" in normalized
    assert "same natural skin, clothing, volume" in normalized
    assert "Do not promise text and then negate it elsewhere" in normalized
    assert "Use each lane exactly once in a five-Theme batch" in normalized
    assert "one home, dinner, party, or other private social setting" in normalized
    assert (
        "one cinema, theater, concert, sports, game, or other communal leisure setting"
        in normalized
    )
    assert "one garden, park, beach, mountain, farm" in normalized
    assert "one train, station, ferry, airport, road stop" in normalized


def test_magazine_cover_brief_builds_a_finished_newsstand_cover() -> None:
    brief = (REPOSITORY_ROOT / "story-inputs" / "magazine-cover.txt").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(brief.split())

    assert "MAGAZINE, NOT POSTER" in normalized
    assert "one original recurring masthead at the top" in normalized
    assert "exactly two short secondary cover lines" in normalized
    assert "Do not use movie-poster signals" in normalized
    assert "Do not use social-post signals" in normalized
    assert "Do not show a physical mockup" in normalized
    assert "flat, full-bleed portrait 3:4 front cover" in normalized
    assert "MASTHEAD CONTRACT" in normalized
    assert "COVER-LINE PACKAGE" in normalized
    assert "Keep total visible copy under twenty-four English words" in normalized
    assert "NO MICROTEXT" in normalized
    assert "four percent of the cover height" in normalized
    assert "Do not render a barcode, QR code, ISBN, ISSN" in normalized
    assert "Do not use lowercase letters, digits, punctuation" in normalized
    assert "Every exact string must match `[A-Z]+( [A-Z]+)*`" in normalized
    assert "Never use `&`; write `AND` instead" in normalized
    assert "never a date, month, year, volume, edition" in normalized
    assert "trademark symbol, registered mark, superscript" in normalized
    assert "ENGLISH-ONLY IMAGE TEXT GATE" in normalized
    assert "TEXT-LAYER ISOLATION LOCK" in normalized
    assert "Frame prose must use English throughout" in normalized
    assert (
        "Every character in the complete Frame must be ASCII code point" in normalized
    )
    assert "A single non-ASCII character invalidates the Frame" in normalized
    assert (
        "The cover contains exactly five readable English strings and zero other "
        "letters, words, numbers, symbols, pseudo-letters, or glyph-like marks."
        in normalized
    )
    assert "exactly three controlled typography zones" in normalized
    assert "one aligned information block" in normalized
    assert (
        "The five declared English strings are the complete typographic layer"
        in normalized
    )
    assert (
        "all remaining cover areas are pure photography, uninterrupted color, "
        "or blank negative space" in normalized
    )
    assert "Quarantine all exact visible copy until that final passage" in normalized
    assert (
        "any all-uppercase sequence of two or more letters anywhere earlier"
        in normalized
    )
    assert "Each of the five exact strings appears once and only once" in normalized
    assert "The Frame's final character is the semicolon" in normalized
    assert "dedicated image-text passage" in normalized
    assert "It contains exactly five entries in this order" in normalized
    assert "add a colon, then write the exact uppercase text" in normalized
    assert "Never surround visible text with quotation marks" in normalized
    assert (
        "one dominant hero image occupying roughly sixty to eighty percent"
        in normalized
    )
    assert "At hardcore level" in normalized
    assert "the result is one flat portrait 3:4 magazine front cover" in normalized
