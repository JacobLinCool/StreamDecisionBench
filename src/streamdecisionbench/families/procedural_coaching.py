"""Procedural Coaching: a coach watching someone carry out a multi-step procedure.

The coach sees the written procedure with a status mark on every step, what
the person is doing right now and the surroundings, and decides what to say.
Both scenarios share one latent vocabulary (current step, whether it is
finished, values that can differ from the procedure, hazards) but differ in
difficulty:

* ``procedure_a`` (easy) - a voice coach guiding a home cook through a
  nine-step mushroom risotto. One choice question with four options whose
  texts say when to use them; four prioritised rules; every tick states,
  present or absent, whether anything at the stove is smoking or on fire and
  whether the current step departs from the recipe, so distractor ticks tempt
  through the scene only; the only arithmetic is comparing a step timer with
  the recipe's time.
* ``procedure_b`` (hard) - a lab coach for a trainee who makes 1x TAE buffer
  and casts and runs an agarose gel (protective equipment first, then nine
  numbered steps). Two questions per decision (action, six options; target
  step, nine steps plus 'none'); six prioritised rules; deviations that are
  visible only by comparing a recorded value, a date or a setup detail with
  the protocol; two deviations at once, where the earliest one is the target;
  a deviation that is a correction while its step is current, a rollback once
  the trainee has moved on, and nothing once it has been put right; a gel
  orientation and a lifted lid conveyed only by the observation log; the
  role text declares the closed-world conventions for the other rule facts.

Surface scripts are written in blocks whose first tick is stated explicitly;
``_script`` checks that the blocks are contiguous and cover exactly ``STEPS``
ticks, so a surface line can never drift away from the latent event it
describes. Decision facts are rendered from the latent state, except the two
log-only facts of procedure_b, whose log lines are anchored to the latent
events they describe; surface lines never carry a fact the latent lacks.
"""

from __future__ import annotations

import copy
import datetime
from typing import Any, Callable, Iterable

from streamdecisionbench.authoring import Choice, Scenario, Tick, Timeline, override, pick, span_tags
from streamdecisionbench.schema import STEPS

FAMILY = "procedural_coaching"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def clock(start_s: int, seconds: int) -> str:
    total = start_s + seconds
    return f"{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}"


def dur(seconds: int) -> str:
    """'5 min 45 s', '6 min', '45 s'."""
    m, s = divmod(seconds, 60)
    if m and s:
        return f"{m} min {s} s"
    if m:
        return f"{m} min"
    return f"{s} s"


def mmss(seconds: int) -> str:
    return f"{seconds // 60}:{seconds % 60:02d}"


def _script(convert: Callable[[Any], dict[str, Any]], *blocks: tuple[int, list[Any]]) -> list[dict[str, Any]]:
    """Concatenate tick-anchored script blocks, checking that each starts where the last ended."""
    out: list[dict[str, Any]] = []
    for start, lines in blocks:
        if start != len(out):
            raise ValueError(f"script block declared at t{start} actually starts at t{len(out)}")
        out.extend(convert(item) for item in lines)
    if len(out) != STEPS:
        raise ValueError(f"script has {len(out)} lines, expected {STEPS}")
    return out


def _set_tags(ticks: list[Tick], spec: dict[int, Iterable[str]]) -> list[Tick]:
    """Replace the event tags at the given ticks (used to re-tag counterfactuals)."""
    out = [copy.deepcopy(tk) for tk in ticks]
    for t, tags in spec.items():
        out[t].tags = list(tags)
    return out


def _decoy_lines(pools: dict[str, list[str]], gold: str, t: int, prefix: str,
                 usable: Callable[[str], bool]) -> tuple[list[str], bool]:
    """Lexical-decoy register: irrelevant lines that borrow a wrong option's words.

    The first line always borrows from a wrong action. About a third of the
    ticks get a second line drawn from every pool (the gold action's included),
    so the absence of an action's vocabulary is not itself a cue. ``usable``
    drops lines whose speaker is not around at tick ``t``. Returns the lines
    and whether the first one goes into the primary field (the second, if
    any, goes into the other field).
    """
    avail = {a: [d for d in lines if usable(d)] for a, lines in pools.items()}
    wrong = [a for a in avail if a != gold and avail[a]]
    first = pick(avail[pick(wrong, f"{prefix}-decoy-target", t)], f"{prefix}-decoy", t)
    lines = [first]
    if pick([True, False, False], f"{prefix}-decoy2", t):
        pool = [d for a in avail for d in avail[a] if d != first]
        lines.append(pick(pool, f"{prefix}-decoy2-line", t))
    return lines, pick([True, False], f"{prefix}-decoy-place", t)


# ===========================================================================
# Scenario A - home cook, mushroom risotto; one question, four options
# ===========================================================================

A_STEPS = {
    1: "Dice the onion and slice the mushrooms.",
    2: "Heat the stock in the small pot until it simmers, then turn that burner to low.",
    3: "Melt the butter in the wide pan over medium heat, add the onion and soften it for 6 minutes.",
    4: "Add the mushrooms and cook them for 5 minutes.",
    5: "Add the rice and toast it for 2 minutes, stirring.",
    6: "Pour in the wine and stir until the pan is dry.",
    7: "Keep the pan on medium heat and add the hot stock one ladle at a time, stirring, for 16 minutes.",
    8: "Take the pan off the heat, then stir in the butter and parmesan.",
    9: "Cover the pan and let the risotto rest for 2 minutes.",
}
A_STEPS_P = {
    1: "chop the onion small and cut the mushrooms into slices",
    2: "warm the broth in the little saucepan to a simmer, then drop that ring to its lowest setting",
    3: "let the butter foam in the large frying pan on a moderate flame, tip in the onion and sweat it for six minutes",
    4: "stir in the mushrooms and give them five minutes",
    5: "tip in the rice and keep it moving for two minutes so the grains toast",
    6: "splash in the white wine and keep stirring until no liquid is left",
    7: "with the flame kept moderate, ladle in the hot broth a scoop at a time, stirring throughout, for sixteen minutes",
    8: "lift the pan away from the flame, then beat in the butter and the grated cheese",
    9: "put a lid on and leave the risotto to stand for two minutes",
}
# structural_cf: tonight's card swaps the wine in step 6 for a ladle of stock.
A_STEP6_SWAP = (
    "Pour in a ladle of the hot stock and stir until the pan is dry. "
    "(Changed on tonight's card: stock instead of the wine, because the cook's partner is off alcohol this month.)"
)
A_STEP6_SWAP_P = (
    "ladle in some of the hot broth and keep stirring until no liquid is left "
    "(altered for this evening: broth takes the place of the white wine, as the partner is avoiding alcohol this month)"
)
A_NOTES = (
    "In step 3 a splash of olive oil with the butter is fine. "
    "In step 7, if the stock runs out, use hot water from the kettle instead."
)
A_NOTES_P = (
    "Written at the bottom of the card: a little olive oil alongside the butter is allowed in stage 3, "
    "and if the broth is used up during stage 7, freshly boiled kettle water may take its place."
)

# Timed steps and the recipe's time in seconds.
A_TIMED = {3: 360, 4: 300, 5: 120, 7: 960, 9: 120}

A_POLICY = [
    "1. If anything at the stove is smoking or on fire, tell the cook to stop and switch off the heat. Steam from a pot and a burner's own gas flame do not count.",
    "2. Otherwise, if the cook is doing the current step differently from the recipe (a wrong ingredient, the wrong heat, or leaving out an instruction of that step), tell the cook what to fix in the current step. The card notes list allowed swaps, and carrying on past a step's time is not a mistake.",
    "3. Otherwise, if the current step is finished, a later step remains, and the cook has not started it, tell the cook the next step. A timed step is finished once its timer has reached the recipe's time; any other step is finished when everything it describes is done.",
    "4. Otherwise, stay silent.",
]
A_POLICY_P = [
    "1. Should anything at the cooker be giving off smoke or be alight, have the cook halt and turn the burners off. Vapour rising from a pan and the ordinary flame of a gas ring are no reason.",
    "2. Failing that, should the cook be carrying out the stage in hand otherwise than the card says (the wrong ingredient, the wrong flame, or a missed instruction of that stage), flag what has to change in it. Swaps the card itself permits are fine, and going on longer than a stage's time is not an error.",
    "3. Failing that, should the stage in hand be complete while a further stage remains untouched, announce what comes after it. A stage with a time is complete as soon as its clock reaches the card's time; any other stage is complete once all it describes has been done.",
    "4. In any other case, keep quiet.",
]

A_OPTIONS = {
    "wait": "Stay silent for now. Use this when none of the other three situations applies.",
    "prompt_next": "Tell the cook the next step of the recipe. Use this when the current step is finished and a later step has not begun.",
    "correct": "Tell the cook what to fix in the current step. Use this when they are doing that step differently from the recipe.",
    "stop_heat": "Tell the cook to stop and switch off the heat. Use this when something at the stove is smoking or on fire.",
}
A_OPTIONS_P = {
    "wait": "Keep quiet and let them get on with it; right whenever nothing else on this list fits.",
    "prompt_next": "Announce what comes after the stage in hand; right once that stage is complete and a further one is still untouched.",
    "correct": "Flag what has to change in the stage in hand; right when it is being carried out otherwise than the card says.",
    "stop_heat": "Have them halt and turn the burners off; right when something at the cooker is giving off smoke or is alight.",
}
A_OPTIONS_D = {
    "wait": "Stay silent for the moment. Use this when none of the other three situations applies.",
    "prompt_next": "Tell the cook the next recipe step. Use this when the current step is finished and a later step has not begun.",
    "correct": "Tell the cook what to fix in the current step. Use this when that step is being done differently from the recipe.",
    "stop_heat": "Tell the cook to stop and switch off the heat. Use this when something at the stove is smoking or on fire.",
}

# Progress of an untimed current step (or of a timed step whose timer has not
# started): canonical phrasing, paraphrase phrasing.
A_PROGRESS = {
    "p1_onion": ("the onion is not fully diced yet; the mushrooms are still whole", "the onion is not fully chopped yet and the mushrooms have not been touched"),
    "p1_mush": ("the onion is diced, but the mushrooms are still whole in their punnet", "the onion is chopped, yet every mushroom is still uncut in its box"),
    "p1_slicing": ("the onion is diced and about half of the mushrooms are sliced", "the onion is chopped and roughly half the mushrooms have been cut"),
    "p1_last": ("the onion is diced and only a few mushrooms are still unsliced", "the onion is chopped and just a handful of mushrooms remain uncut"),
    "p2_heating": ("the stock is warming on a high flame and is not simmering yet", "the broth is heating on a high flame and has not reached a simmer"),
    "p2_near": ("small bubbles are forming at the edge of the stock, but it is not simmering yet; its burner is still on high", "tiny bubbles are appearing round the rim of the broth, which is not yet simmering and still on a high flame"),
    "p3_butter": ("the butter is melting in the wide pan on medium; the onion is not in yet, so the timer has not started", "butter is foaming in the large pan on a moderate flame; the onion has not gone in, so its clock has not been started"),
    "p6_wet": ("the wine is still bubbling in the pan", "wine is still bubbling around the rice"),
    "p6_almost": ("only a little wine is left in the pan", "only a thin film of wine is left in the pan"),
    "p6_dry": ("the wine has cooked off and the pan is dry", "the wine has cooked away and no liquid is left in the pan"),
    "p6s_wine": ("white wine is bubbling in the pan; no stock has gone in", "white wine is bubbling around the rice and no broth has gone in"),
    "p6s_almost": ("only a little wine is left in the pan; no stock has gone in", "just a film of wine is left in the pan and no broth has gone in"),
    "p8_in": ("the butter and parmesan are in and being stirred, not fully melted in yet", "the butter and cheese have gone in and are being worked through, not fully melted"),
    "p8_off": ("the butter and parmesan are being stirred through and are not fully melted yet", "the butter and cheese are still being beaten through and have not fully melted"),
}

# Which burners are lit: canonical phrasing, paraphrase phrasing. A neutral
# description that never states a verdict.
A_STOVE = {
    "off": ("All the burners are off.", "Every ring on the hob is off."),
    "stock_high": ("The stock pot's burner is on high; the other burners are off.", "Only the broth pan's ring is lit, on a high flame."),
    "both": ("Burners: the stock pot on low at the back, the wide pan on medium at the front.",
             "The broth pan sits on its lowest setting at the back and the large pan on a moderate flame at the front."),
    "stock_only": ("The stock pot is on low; the wide pan's burner is off.", "The broth pan is on its lowest setting; the large pan's ring is off."),
    "pan_only": ("Only the wide pan's burner is lit, on medium; the stock pot's burner is off.",
                 "Only the large pan's ring is lit, on a moderate flame; the broth pan's ring is off."),
    "both_high": ("Burners: the stock pot on low at the back, the wide pan on high at the front.",
                  "The broth pan sits on its lowest setting at the back and the large pan on a full flame at the front."),
}

# Hazards and mistakes: canonical phrasings (varied per tick), paraphrase phrasing.
A_HAZARDS = {
    "pan_smoke": (
        [
            "Grey smoke is rising from the wide pan, where rice stuck to the rim is scorching.",
            "Smoke is curling up from the wide pan; grains stuck at the rim are burning.",
        ],
        "smoke is pouring off the large pan, where rice caught on the rim is scorching",
    ),
    # Worded so that it holds while the towel hangs by the burner (t68), is
    # grabbed (t69) and is flapped over the stove (t70).
    "towel_fire": (
        [
            "A corner of the tea towel is on fire, right beside the burner.",
            "The tea towel is burning at one corner, next to the lit burner.",
        ],
        "one corner of the tea towel has caught light right by the ring and is burning",
    ),
    "spatula_smoke": (
        [
            "A plastic spatula left in the stock pot is melting against the hot rim and giving off smoke.",
            "Smoke is coming off a plastic spatula that is melting on the rim of the stock pot.",
        ],
        "a plastic spatula left in the broth pan is melting on the hot rim and smoking",
    ),
}
# Whether anything at the stove is smoking or on fire is stated at every tick:
# a hazard sentence, or one of these (distractor ticks included).
A_NO_HAZARD = [
    "Nothing at the stove is smoking or burning.",
    "The stove area is clear: no smoke, nothing on fire.",
    "Nothing on or around the stove is giving off smoke or burning.",
]
A_NO_HAZARD_LIT = "No smoke or flame at the stove apart from the burners' normal gas flames."
A_NO_HAZARD_P = [
    "Nothing at the cooker is smoking or alight.",
    "There is no smoke and nothing burning at the cooker.",
    "No smoke is rising at the cooker, and nothing there is alight.",
]
# Always stated on the three ticks after a hazard ends, when the scene may still
# mention the window or a doused towel, so the end of the hazard never rests on
# inference.
A_NO_HAZARD_AFTER = [
    "Nothing at the stove is smoking or burning any more.",
    "No smoke is coming from anything at the stove now, and nothing is on fire.",
]
A_NO_HAZARD_AFTER_P = [
    "Nothing at the cooker is smoking or alight any longer.",
    "Nothing at the cooker is giving off smoke now, and nothing is burning.",
]
A_MISTAKES = {
    "cold_water": (
        [
            "The cook is pouring cold water from the tap into the rice while the stock pot on the back burner is still half full.",
            "Instead of the hot stock, the cook is adding cold tap water to the rice; the stock pot is still half full.",
        ],
        "the cook is tipping cold tap water onto the rice even though the broth pan at the back is still half full",
    ),
    "pan_on_heat": (
        [
            "The cook is stirring the butter and parmesan in while the wide pan is still sitting on the lit burner.",
            "The wide pan is still on the lit burner while the cook stirs in the butter and parmesan.",
        ],
        "the cook is beating in the butter and cheese with the large pan still over a lit ring",
    ),
    "burner_high": (
        [
            "The cook has turned the burner under the risotto up from medium to high.",
            "The risotto is now on a high flame; the cook turned it up from medium.",
        ],
        "the cook has turned the ring under the risotto up from moderate to full",
    ),
    "wine_not_stock": (
        [
            "White wine is going into the rice, although tonight's card uses a ladle of hot stock in step 6 instead of wine.",
            "The rice is cooking in white wine, but tonight's step 6 says hot stock, not wine.",
        ],
        "the rice is taking white wine, though this evening's card puts broth in stage 6 in place of the wine",
    ),
}
# Whether the current step departs from the recipe is stated at every tick: a
# mistake sentence, or one of these. They speak about the current step only, as
# rule 2 does, and count the card notes' allowed swaps as following the recipe.
A_ON_RECIPE = [
    "Nothing in the cook's current step departs from the recipe or its card notes.",
    "The current step is going as the recipe and its card notes say.",
    "In the current step the cook is following the recipe, card notes included.",
]
A_ON_RECIPE_P = [
    "Everything in the stage in hand matches the card and its notes.",
    "The cook is sticking to the card, notes included, in the stage in hand.",
    "Nothing in the stage in hand strays from the card or its notes.",
]
# The same fact on a hazard tick, where the hazard sentence comes first.
A_ON_RECIPE_HAZ = [
    "Apart from that, nothing in the cook's current step departs from the recipe.",
    "That aside, the current step is going as the recipe says.",
]
A_ON_RECIPE_HAZ_P = [
    "Beyond that, nothing in the stage in hand strays from the card.",
    "That aside, the stage in hand is going by the card.",
]
# Once all nine steps are done, no step is being carried out.
A_FINISHED = [
    "The recipe is finished, so no step is being carried out now.",
    "With all nine steps done, the cook is no longer carrying out any step.",
]
A_FINISHED_P = [
    "The card is finished, so no stage is being carried out any more.",
    "With all nine stages complete, the cook is no longer working on any stage.",
]

# Irrelevant content for the lexical-decoy register, keyed by the option whose
# vocabulary it borrows. None of it concerns this stove. Lines naming the
# partner are used only while the partner is in the kitchen.
A_DECOYS = {
    "wait": [
        "On the radio, a librarian lists the situations in which visitors must stay silent.",
        "A radio advert for a meditation app tells listeners to stay silent for now and just breathe.",
        "The school newsletter on the fridge asks parents to stay silent for now about the surprise party.",
        "A radio quiz host tells the studio audience to stay silent until the contestant answers.",
        "A text from the cook's brother says he will stay silent for now about the holiday plans.",
        "The partner's phone game tells players to stay silent while the other players answer.",
    ],
    "prompt_next": [
        "A cookbook on the shelf lies open at a bread recipe whose next step begins once the first rise is finished.",
        "On the radio, a TV cook reads out the next step of her cake recipe.",
        "A flyer on the fridge says the next evening cookery course has not begun taking bookings yet.",
        "A text from the cook's sister asks for the next step of the flat-pack wardrobe instructions.",
        "The radio's gardening slot tells listeners the next step once their tulips have finished flowering.",
        "The partner reads out the next step of a flat-pack wardrobe guide, then puts the leaflet down.",
    ],
    "correct": [
        "A text from the landlord says he will fix the dripping bathroom tap differently this time.",
        "On the radio, a caller asks how to fix a knitting pattern she has been doing differently from the instructions.",
        "A note on the fridge says to fix the garden fence on Saturday.",
        "The radio's cycling slot explains what to fix first when a bike's brakes squeal.",
        "A text from the cook's brother asks what to fix in his CV before Monday.",
        "The partner mutters about having to fix the wobbly hallway chair.",
    ],
    "stop_heat": [
        "The radio weather report warns of a heat wave and tells listeners to switch off heaters they are not using.",
        "A news bulletin on the radio mentions a fire at a stove factory two towns away.",
        "A leaflet on the counter from the fire brigade explains how to switch off the heat in a chip-pan fire.",
        "A radio advert urges listeners to stop smoking this autumn.",
        "A text from the cook's sister says her boiler has stopped and she has switched off the heating until the plumber comes.",
        "The partner mentions that a colleague has finally managed to stop smoking.",
    ],
}


def _a_partner_in_kitchen(t: int) -> bool:
    """The partner comes home at t25, leaves for a work call at t35 and comes back at t53."""
    return 25 <= t <= 34 or t >= 53


def _a_line(entry: tuple[str, str, str]) -> dict[str, str]:
    """One tick of scenario A surface: what the cook says, what the camera shows, a gist for the paraphrase."""
    return {"say": entry[0], "doing": entry[1], "gist": entry[2]}


A_SCRIPT = _script(
    _a_line,
    (0, [  # step 1, prep
        ("Okay coach, I'm starting. Onion first.", "The cook peels a large onion at the chopping board.", "peels a large onion at the chopping board"),
        ("", "The cook halves the onion and starts cutting it into strips.", "halves the onion and begins cutting it into strips"),
        ("My eyes are streaming already.", "The cook dices the onion, blinking hard.", "chops the onion small with streaming eyes"),
        ("Right, that's done!", "The cook scrapes the diced onion into a bowl and pulls the punnet of mushrooms closer.", "announces 'that's done' after scraping the chopped onion into a bowl, then draws the box of mushrooms over to the board"),
        ("Chestnut mushrooms, the shop had no button ones.", "The cook slices mushrooms on the board.", "cuts chestnut mushrooms into slices, explaining the shop had no button ones"),
        ("", "The cook slices the last few mushrooms, humming along to the radio.", "cuts the last few mushrooms while humming along to the radio"),
    ]),
    (6, [  # step 2, stock heating
        ("Mushrooms done. Stock on.", "The cook tips the sliced mushrooms into a second bowl, pours the stock into the small pot and lights its burner on high.", "tips the cut mushrooms into a bowl and sets the broth over a high flame in the little saucepan"),
        ("", "The cook wipes the board and drops the knife in the sink while the stock warms.", "wipes the board and puts the knife in the sink while the broth warms"),
        ("Whoa, that's a lot of steam.", "Thick steam rolls off the stock pot and fogs the window above the stove.", "remarks on the thick steam rolling off the broth pan and fogging the window"),
        ("", "The cook lifts the lid of the stock pot and peers in.", "lifts the lid of the broth pan to look in"),
    ]),
    (10, [  # stock turned low, step 3 begins
        ("It's bubbling. Turning it down. Butter in the big pan.", "The cook turns the stock burner to low, sets the wide pan on medium and drops in the butter.", "turns the broth down to its lowest and drops butter into the large pan on a moderate flame"),
        ("Onion's going in.", "The cook tips the diced onion into the foaming butter and starts the timer.", "tips the onion into the foaming butter and starts the clock"),
        ("Smells good already.", "The cook stirs the onion with a wooden spoon; it sizzles gently.", "stirs the gently sizzling onion with a wooden spoon"),
    ]),
    (13, [  # step 3, onion softening
        ("I'm adding a splash of olive oil too.", "The cook adds a small splash of olive oil to the butter and onion.", "adds a small splash of olive oil to the butter and onion"),
        ("", "The cook stirs, then checks the recipe card propped against the kettle.", "stirs and glances at the recipe card propped against the kettle"),
        ("Softening, softening.", "The onion is turning translucent at the edges.", "watches the onion turn see-through at the edges"),
        ("", "The cook grates parmesan into a small dish between stirs.", "grates cheese into a dish between stirs"),
        ("That's plenty of cheese.", "The cook sets the grater aside next to the dish of grated parmesan and gives the onion a stir.", "sets the grater down beside the dish of grated cheese and stirs the onion"),
        ("", "The cook weighs the rice into a cup on the kitchen scale.", "weighs the rice into a cup"),
        ("Three hundred grams of rice, ready to go.", "The cup of rice sits next to the stove.", "has the rice weighed and waiting by the hob"),
        ("", "The cook opens the white wine and pours half a glass into a measuring jug.", "opens the white wine and measures half a glass into a jug"),
        ("One for the pan, none for me. Yet.", "The cook stirs the onion; it is soft and glossy.", "jokes about the wine and stirs the soft, glossy onion"),
        ("", "The cook wipes the counter and rinses the grater.", "wipes the counter and rinses the grater"),
    ]),
    (23, [  # step 4, mushrooms (the onion timer reached 6:00 as they went in)
        ("Onion's had its six minutes. Mushrooms in.", "The cook tips the sliced mushrooms into the wide pan and restarts the timer.", "tips the mushrooms into the large pan and restarts the clock"),
        ("They're drinking up all the butter.", "The cook stirs the mushrooms; they are soaking up the fat.", "stirs the mushrooms as they soak up the butter"),
        ("Hi love, dinner in about half an hour.", "The cook's partner comes in with shopping bags and kisses the cook on the cheek.", "greets their partner, who arrives with shopping bags"),
        ("Put the ice cream straight in the freezer, would you?", "The partner unpacks groceries onto the counter while the cook stirs.", "asks the partner to put the ice cream away while stirring"),
        ("No, the Jacksons are coming on Saturday at eight, not seven.", "The partner asks about the weekend guests; the cook answers while shaking the pan.", "tells the partner the Saturday guests arrive at eight, shaking the pan"),
        ("Can you feed the dog? He's staring at me.", "The dog sits by the stove, watching; the partner fills its bowl.", "asks the partner to feed the dog, who is watching the hob"),
        ("Ugh, that alarm needs a new battery.", "The smoke alarm in the hallway gives one short low-battery chirp.", "grumbles about one low-battery chirp from the hallway smoke alarm"),
        ("", "The partner stands on a chair and fits a fresh battery into the hallway alarm.", "stirs while the partner fits a fresh battery in the hallway alarm"),
        ("The mushrooms are going golden.", "The cook stirs; the mushrooms are browning in patches.", "notes the mushrooms browning in patches"),
        ("", "The cook moves the cup of rice next to the pan.", "moves the cup of rice next to the pan"),
    ]),
    (33, [  # step 5, toasting (the mushroom timer reached 5:00 as the rice went in)
        ("Mushrooms have had their five minutes. Rice in, toasting now.", "The cook pours the rice over the mushrooms, resets the timer and starts stirring.", "pours in the rice, resets the clock for toasting and starts stirring"),
        ("It's crackling.", "The cook stirs the rice constantly; the grains crackle in the fat.", "stirs the crackling rice constantly"),
        ("", "The cook keeps stirring as the partner leaves to take a work call in the other room.", "keeps stirring as the partner leaves for a work call"),
        ("The grains are going see-through at the edges.", "The cook keeps stirring; some rice has stuck to the rim of the pan.", "keeps stirring as the grains turn translucent, with some stuck to the rim"),
    ]),
    (37, [  # smoke from the pan
        ("Hang on, what's that smell?", "The cook stops stirring and stares at the pan.", "stops stirring and sniffs at a burning smell"),
        ("Oh no, oh no.", "The cook coughs and waves a hand over the pan; the burner is still on.", "coughs and waves a hand over the pan with the ring still lit"),
        ("Where's the lid?", "The cook rummages through a drawer; the burner is still on.", "rummages in a drawer for a lid with the ring still lit"),
    ]),
    (40, [  # smoke gone, toasting done, wine not in
        ("Okay, burner off, window open.", "The cook has switched the burner off and opened the window; the pan has stopped smoking and fresh air is coming in.", "has turned the ring off and opened the window; the pan has stopped smoking and fresh air is coming in"),
        ("Phew. The rice looks fine, just a few dark grains.", "The cook picks a few dark grains off the rim and relights the burner on medium.", "picks off a few dark grains and relights the ring on a moderate flame"),
        ("", "The air over the stove has cleared; the cook folds the tea towel and lays it by the sink.", "folds the tea towel and lays it by the sink now that the air over the cooker has cleared"),
    ]),
    (43, [  # step 6, wine
        ("Wine in.", "The cook pours the half glass of wine over the rice and stirs; it hisses.", "pours the half glass of wine over the rice and stirs"),
        ("", "The cook stirs as the wine bubbles and the smell of alcohol rises.", "stirs as the wine bubbles up"),
        ("Smells like a proper restaurant now.", "The cook stirs while the wine reduces.", "stirs the reducing wine and says it smells like a restaurant"),
        ("", "The cook drags the spoon through the rice; a thin film of wine seeps back into the trail.", "drags the spoon through the rice and watches wine seep back into the trail"),
    ]),
    (47, [  # pan dry; the cook lingers before the stock
        ("That's dry.", "The cook drags the spoon through the rice again; the trail stays dry.", "drags the spoon through the rice again and the trail stays dry"),
        ("Sorry, my sister's asking about Sunday.", "The cook leans on the counter and types on the phone.", "leans on the counter texting their sister about Sunday"),
        ("", "The cook sends another message; the stock pot simmers on low at the back.", "sends another message while the broth simmers at the back"),
    ]),
    (50, [  # step 7, stock
        ("First ladle of stock.", "The cook ladles hot stock from the small pot over the rice, starts the timer and stirs.", "ladles in the first hot broth, starts the clock and stirs"),
        ("", "The cook stirs slowly while the stock is absorbed.", "stirs slowly while the broth is absorbed"),
        ("Another ladle.", "The cook adds a second ladle of hot stock and stirs.", "adds a second scoop of broth and stirs"),
        ("", "The partner comes back in and starts setting the table behind the cook, who keeps stirring.", "stirs while the partner sets the table"),
        ("Use the blue plates, the white ones are in the dishwasher.", "The cook stirs and points the partner to the blue plates.", "stirs and points the partner to the blue plates"),
        ("", "The cook adds a third ladle of stock and stirs.", "adds a third scoop of broth and stirs"),
    ]),
    (56, [  # cold tap water instead of stock
        ("The tap's closer, I'll just use water.", "The cook fills a jug from the cold tap and pours it over the rice.", "fills a jug at the cold tap and pours it over the rice"),
        ("", "The cook pours a second jug of cold tap water over the rice; the bubbling stops.", "pours a second jug of cold tap water in and the bubbling stops"),
        ("It's gone all quiet in there.", "The cook refills the jug at the cold tap for another go.", "refills the jug at the cold tap"),
    ]),
    (59, [  # back to stock
        ("Fine, fine, back to the stock.", "The cook empties the jug into the sink, ladles hot stock from the small pot instead and stirs.", "empties the jug, goes back to scooping in the hot broth and stirs"),
        ("", "The pan is bubbling again; the cook stirs steadily.", "stirs steadily as the pan bubbles again"),
        ("Is someone having a barbecue?", "Charcoal smoke from the neighbour's garden drifts in through the open window while the cook stirs.", "asks about the charcoal smoke drifting in from the neighbour's barbecue while stirring"),
        ("", "The cook pushes the window half shut and goes back to stirring.", "half-closes the window and goes back to stirring"),
        ("Hi Mum! You're on speaker, I'm cooking.", "The cook's phone rings; the cook props it on the shelf and keeps stirring.", "takes a call from their mother on speaker while stirring"),
        ("Yes, risotto. No, not the one from the magazine.", "The cook adds a ladle of stock and stirs while talking.", "tells their mother about the risotto while adding broth and stirring"),
        ("Sunday's fine, we'll bring dessert.", "The cook stirs, laughing at something on the call.", "agrees to Sunday plans, laughing, while stirring"),
        ("Okay, love you, bye.", "The cook ends the call, adds another ladle of stock and stirs.", "ends the call, adds another scoop and stirs"),
        ("", "Between stirs, the cook drapes the tea towel over the oven handle; its corner hangs close to the burner.", "drapes the tea towel over the oven handle near the ring between stirs"),
    ]),
    (68, [  # tea towel fire
        ("Is something burning?", "The cook spins round at the smell.", "spins round at a burning smell"),
        ("It's on fire! The towel!", "The cook grabs at the tea towel.", "shouts that the towel is on fire and grabs at it"),
        ("Water, water!", "The cook flaps the tea towel over the stove.", "flaps the tea towel over the hob, shouting for water"),
    ]),
    (71, [  # fire out, stock step continues
        ("Okay. Okay. It's out.", "The towel lies soaked in the sink; the risotto burner is on medium and the cook is stirring again.", "has doused the towel in the sink and is stirring again over a moderate flame"),
        ("My heart is pounding.", "The cook stirs and adds a ladle of stock.", "says their heart is pounding, adds a scoop of broth and stirs"),
        ("", "The partner hangs a fresh tea towel on a hook well away from the stove while the cook stirs.", "stirs while the partner hangs a fresh towel away from the hob"),
        ("Note to self: towels live on the hook.", "The cook stirs; the rice is turning creamy.", "stirs, making a note to keep towels on the hook as the rice turns creamy"),
        ("Mm, it's done! It's so creamy.", "The cook tastes a spoonful of rice from the edge of the pan between stirs.", "tastes the rice between stirs and declares it done and creamy"),
        ("", "The cook adds a ladle of stock and stirs.", "adds another scoop of broth and stirs"),
        ("Bit more chew to it than I thought.", "The cook tastes again, nods and keeps stirring.", "tastes again, finds it chewier than expected and keeps stirring"),
        ("Stock's gone. Kettle water then.", "The cook turns off the empty stock pot's burner, ladles hot water from the just-boiled kettle into the rice and stirs.", "finds the broth used up, turns off its ring, ladles hot water from the just-boiled kettle into the rice and stirs"),
        ("", "The cook stirs as the kettle water is absorbed.", "stirs in the kettle water"),
        ("The kids next door are singing.", "Children's singing floats in from next door while the cook stirs.", "hears the children next door singing while stirring"),
        ("", "The cook adds a last splash of kettle water and stirs.", "adds a last splash of kettle water and stirs"),
    ]),
    (82, [  # step 8 with the pan still on the flame
        ("Butter and cheese!", "The cook drops the butter and the parmesan into the pan and stirs hard.", "drops in the butter and grated cheese and stirs hard"),
        ("", "The cook beats the cheese in; the rice spits and bubbles.", "beats the cheese in as the rice spits and bubbles"),
        ("It's sticking a bit.", "The cook scrapes at the base of the pan.", "scrapes at the base of the pan where it sticks"),
    ]),
    (85, [  # off the heat, then resting
        ("Off the heat, right.", "The cook slides the wide pan onto a trivet on the counter, switches the burner off and keeps stirring.", "slides the pan onto a trivet, turns the ring off and keeps stirring"),
        ("", "The butter melts into the rice as the cook stirs.", "stirs as the butter melts into the rice"),
        ("Glossy! Lid on, timer on.", "The cook covers the pan and starts the rest timer.", "covers the pan and starts the resting clock"),
        ("", "The cook runs the plates under the hot tap to warm them.", "warms the plates under the hot tap"),
        ("Parsley, where's the parsley?", "The cook chops a handful of parsley.", "chops a handful of parsley"),
        ("", "The partner pours two glasses of the leftover wine.", "watches the partner pour two glasses of the leftover wine"),
    ]),
    (91, [  # recipe complete
        ("Moment of truth.", "The cook stops the rest timer and lifts the lid.", "stops the resting clock and lifts the lid"),
        ("Oh, that looks amazing.", "The cook spoons risotto onto the warm plates.", "spoons the risotto onto the warm plates"),
        ("", "The cook scatters parsley and extra parmesan over each plate.", "scatters parsley and extra grated cheese over the plates"),
        ("Try it, try it.", "The partner takes a forkful and gives a thumbs up.", "offers the partner a taste and gets a thumbs up"),
        ("", "The cook carries the plates to the table.", "carries the plates to the table"),
        ("So what's next, coach?", "The cook sits down and looks at the phone propped by the stove.", "sits down and asks the coach what is next"),
        ("Seriously, thank you, that was easy.", "The cook raises a glass toward the phone.", "thanks the coach and raises a glass"),
        ("", "The partner fills the empty pans with soapy water in the sink.", "watches the partner soak the pans in the sink"),
        ("Next week, fresh pasta?", "The cook eats and laughs with the partner at the table.", "eats and suggests fresh pasta next week"),
    ]),
)

# Counterfactual surfaces: minimal_cf edits and the structural_cf wine story.
A_CF_SPATULA = {
    7: ("What's that smell?", "A plastic spatula left leaning in the stock pot has slumped against the hot rim.", "notices a smell from the broth pan, where a plastic spatula has slumped against the rim"),
    8: ("Whoa, is that smoke?", "Fumes curl up from the stock pot and drift toward the window above the stove.", "asks whether that is smoke as fumes curl up from the broth pan"),
    9: ("", "The cook lifts the lid of the stock pot and peers in; the spatula is still stuck to the rim.", "lifts the broth pan's lid while the spatula is still stuck to the rim"),
    10: ("Spatula's in the bin. Stock down, butter in.", "The cook has binned the melted spatula, turns the stock burner to low, sets the wide pan on medium and drops in the butter.", "bins the melted spatula, turns the broth down and drops butter into the large pan"),
}
A_CF_STOCK = {
    56: ("Next ladle.", "The cook ladles hot stock from the small pot over the rice and stirs.", "scoops hot broth from the little saucepan over the rice and stirs"),
    57: ("", "The cook ladles a second scoop of hot stock and stirs; the rice keeps bubbling.", "scoops in more hot broth and stirs as the rice keeps bubbling"),
    58: ("It's bubbling away nicely.", "The cook stirs, then dips the ladle back into the stock pot.", "stirs and dips the ladle back into the broth pan"),
    59: ("Keep it moving.", "The cook stirs steadily and adds another ladle of hot stock.", "stirs steadily and adds another scoop of hot broth"),
    60: ("", "The pan keeps bubbling; the cook stirs steadily.", "stirs steadily as the pan keeps bubbling"),
}
A_CF_HIGH = {
    75: ("Mm, it's done! It's so creamy.", "The cook turns the burner under the risotto up to high, then tastes a spoonful of rice from the edge of the pan.", "turns the ring up to full, then tastes the rice and declares it done and creamy"),
    76: ("", "The rice bubbles hard as the cook adds a ladle of stock and stirs.", "adds a scoop of broth and stirs as the rice bubbles hard"),
    77: ("Bit more chew to it than I thought.", "The cook tastes again; the pan is spitting.", "tastes again as the pan spits"),
    78: ("Stock's gone. Kettle water then, and back to medium.", "The cook turns the risotto burner back to medium, turns off the empty stock pot's burner, ladles hot water from the just-boiled kettle into the rice and stirs.", "turns the flame back to moderate and, now the broth is used up, ladles hot kettle water into the rice and stirs"),
}
A_SCF_WINE = {
    47: ("A bit more, like always.", "The cook tips a second splash of wine from the bottle over the rice and stirs.", "tips a second splash of wine from the bottle over the rice and stirs"),
    48: ("I'll just let that bubble off.", "The cook stirs the rice; wine is still bubbling around the grains.", "stirs as wine keeps bubbling around the grains"),
    49: ("", "The cook drags the spoon through the rice; a thin film of wine seeps back into the trail.", "drags the spoon through the rice and watches wine seep back into the trail"),
    90: ("", "The partner pours two glasses of sparkling water.", "watches the partner pour two glasses of sparkling water"),
}


class HomeRisotto(Scenario):
    family = FAMILY
    scenario_id = "procedure_a"
    title = "Voice coaching a home cook through a mushroom risotto"
    tier = "easy"
    difficulty_features = [
        "single_choice_question",
        "four_options_with_use_when_clauses",
        "four_rule_priority_policy",
        "explicit_hazards_and_mistakes",
        "timer_vs_recipe_time",
        "untimed_step_completion",
    ]
    decision_structures = ["maintain", "advance", "wait", "recover", "resolve-conflict", "terminate"]
    deadline_steps = 2

    TICK_SECONDS = 30
    START = 18 * 3600 + 30 * 60  # 18:30:00
    # Timer runs per timed step: (step, first tick, last running tick). The
    # timer is started 15 s before the first snapshot of its run.
    TIMER_RUNS = [(3, 11, 22), (4, 23, 32), (5, 33, 39), (7, 50, 81), (9, 87, 90)]
    # Stopped timers: toasting stops 15 s after the t39 snapshot when the
    # burner goes off (3 min 30 s); the rest timer is stopped at 2 min 15 s.
    STOPPED = {40: 210, 41: 210, 42: 210, **{t: 135 for t in range(91, STEPS)}}

    # ---------------------------------------------------------------- questions
    def questions(self, variant: str) -> list[Any]:
        if variant == "paraphrase":
            instructions = {
                "role": "You speak into a home cook's earbuds while they make a mushroom risotto from a nine-stage recipe card. The stage in hand is the one the cook is busy with, or the last one they completed if they have not moved on to another. Judge only the moment described: an answer stays right for as long as its rule is the first that fits, even if you already gave it a moment ago.",
                "rules": A_POLICY_P,
                "question": "Go through the rules in order and act on the first that fits this moment. What should you say to the cook now?",
            }
            options = A_OPTIONS_P
        else:
            instructions = {
                "role": "You are a voice coach in a home cook's earbuds, guiding them through a nine-step mushroom risotto. `recipe` lists the steps with their status; `card_notes` are the recipe card's own notes; `cook_now` is what the cook says and what the kitchen camera shows; `kitchen` describes the stove and the rest of the kitchen. The current step is the one the cook is working on, or the one they last finished if they have not started another. Judge only the moment shown: an action stays right for as long as its rule is the first that matches, even if you already said it a moment ago.",
                "policy": A_POLICY,
                "question": "Apply the first rule that matches the current state. What should the coach do right now?",
            }
            options = A_OPTIONS_D if variant == "lexical_decoy" else A_OPTIONS
        return [Choice("action", instructions, dict(options))]

    # ------------------------------------------------------------------ latent
    def _timer(self, t: int) -> tuple[int | None, bool]:
        for _, first, last in self.TIMER_RUNS:
            if first <= t <= last:
                return 15 + self.TICK_SECONDS * (t - first), False
        if t in self.STOPPED:
            return self.STOPPED[t], True
        return None, False

    def _canonical(self) -> list[Tick]:
        tl = Timeline(
            {
                "step": 1,
                "timer_s": None,
                "timer_stopped": False,
                "progress": "p1_onion",
                "end_met": False,
                "mistake": None,
                "hazard": None,
                "stock_out": False,
                "stove": "off",
                "wine_swap": False,
                "step6_wine": False,
            }
        )
        events: dict[int, tuple[dict[str, Any], str]] = {
            3: ({"progress": "p1_mush"}, "'That's done' refers to the onion only; the mushrooms are still whole."),
            4: ({"progress": "p1_slicing"}, ""),
            5: ({"progress": "p1_last"}, ""),
            6: ({"step": 2, "progress": "p2_heating", "stove": "stock_high"}, "Prep finished and the stock goes on in the same moment."),
            8: ({}, "Steam from the stock pot is not smoke."),
            9: ({"progress": "p2_near"}, ""),
            10: ({"step": 3, "progress": "p3_butter", "stove": "both"}, "Stock simmering on low; step 3 starts at once, timer not yet running."),
            11: ({"progress": None}, "Onion in; step 3 timer running."),
            13: ({}, "Olive oil with the butter is allowed by the card notes."),
            22: ({}, "Onion timer at 5:45 of 6:00: not finished yet."),
            23: ({"step": 4}, "The onion timer reached 6:00 as the mushrooms went in; mushroom timer running."),
            29: ({}, "A low-battery chirp from the hallway alarm; no smoke at the stove."),
            32: ({}, "Mushroom timer at 4:45 of 5:00: not finished yet."),
            33: ({"step": 5}, "Mushrooms done at 5:00; the rice goes straight in."),
            36: ({}, "Toasting at 1:45 of 2:00: not finished yet."),
            37: ({"hazard": "pan_smoke"}, "Toasting has reached 2 minutes (2:15), but the pan is smoking: the safety rule outranks the next-step rule."),
            40: ({"hazard": None, "stove": "stock_only"}, "Smoke gone; toasting finished (timer stopped at 3:30); wine not poured."),
            41: ({"stove": "both"}, "Burner relit on medium; nothing added to the rice yet."),
            43: ({"step": 6, "progress": "p6_wet", "step6_wine": True}, "Wine in."),
            46: ({"progress": "p6_almost"}, "A film of wine is left: the pan is not dry yet."),
            47: ({"progress": "p6_dry", "end_met": True}, "Pan dry: step 6 is finished (untimed); the cook is texting and no stock has gone in."),
            50: ({"step": 7, "progress": None, "end_met": False}, "First ladle of stock; the stock step's timer starts."),
            56: ({"mistake": "cold_water"}, "Cold tap water instead of the hot stock, with stock still in the pot."),
            59: ({"mistake": None}, "The cook goes back to the stock."),
            61: ({}, "Barbecue smoke drifting in from outside, not at the stove."),
            68: ({"hazard": "towel_fire"}, "Tea towel on fire beside the burner."),
            71: ({"hazard": None}, "Fire out; stirring resumes."),
            75: ({}, "The cook calls it done at 12:45 of 16 minutes."),
            78: ({"stock_out": True, "stove": "pan_only"}, "Stock used up; kettle water is allowed by the card notes."),
            82: ({"step": 8, "progress": "p8_in", "mistake": "pan_on_heat"}, "Stock step finished (16:15); butter and cheese go in with the pan still on the flame."),
            85: ({"mistake": None, "progress": "p8_off", "stove": "off"}, "Pan moved off the heat."),
            87: ({"step": 9, "progress": None}, "Butter and cheese stirred in; rest timer started."),
            90: ({}, "Rest at 1:45 of 2:00; step 9 is the last step, so there is no next step either way."),
            91: ({}, "Rest timer stopped at 2:15: all nine steps are done."),
            96: ({}, "'What's next?' after the last step: no later step remains."),
        }
        tags = span_tags(
            {
                "distractor": [3, 8, 13, 29, 61, 75, 78, 96],
                "minimal_change": [47, 56, 82],
                "recovery": [59, 71, 85],
                "hold_under_activity": [(10, 12), (25, 28), (63, 66)],
                "priority_conflict": [(37, 39)],
                "boundary": [(91, 99)],
                "arithmetic": [(21, 22), (31, 32), (35, 37), 75, (80, 81)],
            }
        )
        for t in range(STEPS):
            updates, note = events.get(t, ({}, ""))
            timer, stopped = self._timer(t)
            tl.step(dict(A_SCRIPT[t]), tags[t], note, timer_s=timer, timer_stopped=stopped, **updates)
        return tl.ticks

    def timeline(self, variant: str) -> list[Tick]:
        ticks = self._canonical()
        if variant == "minimal_cf":
            # (1) t7-9: a plastic spatula melts and smokes in the stock pot instead of plain steam.
            ticks = override(ticks, [7, 8, 9], hazard="spatula_smoke",
                             note="A plastic spatula is melting and smoking in the stock pot.",
                             surface=lambda tk, i: _a_line(A_CF_SPATULA[i]))
            ticks = override(ticks, [10], note="Melted spatula binned; stock simmering on low; step 3 starts.",
                             surface=lambda tk, i: _a_line(A_CF_SPATULA[i]))
            # (2) t56-58: the cook keeps ladling hot stock instead of cold tap water.
            ticks = override(ticks, [56, 57, 58], mistake=None, note="Hot stock, as the recipe says; no mistake.",
                             surface=lambda tk, i: _a_line(A_CF_STOCK[i]))
            ticks = override(ticks, [59, 60], note="Still ladling hot stock.", surface=lambda tk, i: _a_line(A_CF_STOCK[i]))
            # (3) t75-77: the cook turns the risotto burner up from medium to high.
            ticks = override(ticks, [75, 76, 77], mistake="burner_high", stove="both_high",
                             note="Burner turned up to high during step 7, which says medium.",
                             surface=lambda tk, i: _a_line(A_CF_HIGH[i]))
            ticks = override(ticks, [78], note="Back to medium; stock used up, kettle water allowed.",
                             surface=lambda tk, i: _a_line(A_CF_HIGH[i]))
            ticks = _set_tags(ticks, {
                7: ["minimal_change"], 8: [], 9: [], 10: ["recovery", "hold_under_activity"],
                56: [], 59: [],
                75: ["minimal_change", "distractor", "arithmetic"], 76: [], 77: [], 78: ["recovery", "distractor"],
            })
        elif variant == "structural_cf":
            # Tonight's card swaps the wine in step 6 for a ladle of stock
            # because the cook's partner is off alcohol this month. The cook
            # pours wine out of habit at t43-49, which is now a wrong
            # ingredient in the current step 6; the stock step starts at t50
            # as in the canonical story.
            ticks = [copy.deepcopy(tk) for tk in ticks]
            for tk in ticks:
                tk.latent["wine_swap"] = True
            ticks = override(ticks, [43, 44, 45, 46, 47, 48, 49], mistake="wine_not_stock",
                             note="Wine going into the rice although tonight's step 6 uses stock instead of wine.")
            ticks = override(ticks, [43, 44, 45, 47, 48], progress="p6s_wine")
            ticks = override(ticks, [46, 49], progress="p6s_almost")
            ticks = override(ticks, [47, 48, 49], end_met=False, surface=lambda tk, i: _a_line(A_SCF_WINE[i]))
            ticks = override(ticks, [90], surface=lambda tk, i: _a_line(A_SCF_WINE[i]))
            ticks = _set_tags(ticks, {43: ["minimal_change"], 47: []})
            ticks[40].note = "Toasting finished; the next step is 6, which tonight uses stock instead of wine."
            ticks[50].note = "The cook starts the stock step; step 7 is done as written."
        return ticks

    # ------------------------------------------------------------------ policy
    @staticmethod
    def _finished(z: dict[str, Any]) -> bool:
        """Rule 3's definition: a timed step is finished once its timer reaches the recipe time."""
        step = z["step"]
        if step in A_TIMED and z["timer_s"] is not None:
            return z["timer_s"] >= A_TIMED[step]
        return z["end_met"]

    def policy(self, z: dict[str, Any]) -> dict[str, Any]:
        if z["hazard"] is not None:
            action = "stop_heat"
        elif z["mistake"] is not None:
            action = "correct"
        elif self._finished(z) and z["step"] < 9:
            action = "prompt_next"
        else:
            action = "wait"
        return {"action": action}

    def construction(self, variant: str) -> dict[str, Any]:
        return {
            "canonical": {"summary": "Risotto session. Gold: wait t0-36; stop_heat t37-39 (toasting pan smoking while toasting is already past 2:00: rule 1 over rule 3); prompt_next t40-42 (toasting stopped at 3:30, wine not poured); wait t43-46 (wine reducing); prompt_next t47-49 (untimed step 6 finished: the pan is dry and the cook is texting, no stock yet); wait t50-55; correct t56-58 (cold tap water instead of hot stock); wait t59-67; stop_heat t68-70 (tea towel fire); wait t71-81; correct t82-84 (butter and cheese stirred in on the flame); wait t85-99 (recipe complete at t91). Distractors: 'that's done' for half the prep (t3), steam (t8), olive oil (t13), an alarm chirp (t29), barbecue smoke (t61), 'it's done' at 12:45 of 16 (t75), kettle water once the stock runs out (t78), 'what's next?' after the last step (t96). Every tick states whether anything at the stove is smoking or on fire and whether the current step departs from the recipe (distractor ticks included); on the three ticks after a hazard ends (t40-42, t71-73) the no-smoke sentence says 'any more'."},
            "paraphrase": {"summary": "Same latent trajectory; stage/card/hob/broth vocabulary, one prose paragraph instead of fields, m:ss clocks, reworded rules and options."},
            "lexical_decoy": {"summary": "Same latent trajectory; radio, fridge, text-message and partner lines (partner lines only while the partner is in the kitchen) that borrow a wrong option's vocabulary, blended into the kitchen line or the camera line, with an occasional second line from any pool."},
            "minimal_cf": {"summary": "Three edits of one decision fact each: t7-9 a plastic spatula melts and smokes in the stock pot (wait->stop_heat); t56-58 the cook ladles hot stock instead of cold tap water (correct->wait); t75-77 the cook turns the burner up from medium to high during step 7, still calling it done at 12:45 as in canonical (wait->correct)."},
            "structural_cf": {"summary": "Tonight's card swaps the wine in step 6 for a ladle of hot stock because the cook's partner is off alcohol this month. The cook pours wine out of habit at t43-49, a wrong ingredient in the current step 6 (wait/prompt_next->correct); the stock step starts at t50 as in the canonical story, and from then on step 6 is marked 'done with white wine instead of the stock', which rule 2 ignores because step 6 is no longer current."},
        }.get(variant, {})

    # ------------------------------------------------------------------ render
    def _complete(self, z: dict[str, Any]) -> bool:
        return z["step"] == 9 and self._finished(z)

    @staticmethod
    def _step_text(z: dict[str, Any], i: int, reg: int) -> str:
        if i == 6 and z["wine_swap"]:
            return (A_STEP6_SWAP, A_STEP6_SWAP_P)[reg]
        return (A_STEPS, A_STEPS_P)[reg][i]

    def _status(self, z: dict[str, Any], i: int) -> str:
        if self._complete(z) or i < z["step"]:
            if i == 9 and z["timer_stopped"]:
                return f"done; timer stopped at {dur(z['timer_s'])}"
            if i == 6 and z["wine_swap"] and z["step6_wine"]:
                # structural_cf: the cook used wine although tonight's card says stock.
                return "done with white wine instead of the stock"
            return "done"
        if i > z["step"]:
            return "not started"
        if i in A_TIMED and z["timer_s"] is not None:
            recipe = dur(A_TIMED[i])
            if z["timer_stopped"]:
                # Toasting (t40-42): the burner is relit at t41, so the status
                # does not say why the timer stopped; `kitchen` gives the burners.
                return f"current: timer stopped at {dur(z['timer_s'])}; recipe time {recipe}"
            # Step 9 is 'cover and rest': the cover is part of the step, so it is stated.
            covered = "pan covered; " if i == 9 else ""
            return f"current: {covered}timer at {dur(z['timer_s'])} of the recipe's {recipe}"
        return "current: " + A_PROGRESS[z["progress"]][0]

    def _status_p(self, z: dict[str, Any], i: int) -> str:
        if self._complete(z) or i < z["step"]:
            if i == 9 and z["timer_stopped"]:
                return f"complete, its clock halted with {mmss(z['timer_s'])} elapsed"
            return "complete"
        if i > z["step"]:
            return "untouched"
        if i in A_TIMED and z["timer_s"] is not None:
            if z["timer_stopped"]:
                return f"in hand, its clock halted with {mmss(z['timer_s'])} elapsed (the card's time is {mmss(A_TIMED[i])})"
            covered = "lid on, " if i == 9 else ""
            return f"in hand, {covered}its clock showing {mmss(z['timer_s'])} elapsed against the card's {mmss(A_TIMED[i])}"
        return "in hand: " + A_PROGRESS[z["progress"]][1]

    @staticmethod
    def _after_hazard(history: list[Tick]) -> bool:
        """Whether any of the three ticks before the newest one had a hazard."""
        return any(tk.latent["hazard"] is not None for tk in history[-4:-1])

    def _kitchen(self, z: dict[str, Any], t: int, reg: int, after_hazard: bool) -> list[str]:
        """Stove description, then rule 1's and rule 2's facts, both stated at every tick.

        Rule 1: a hazard sentence, or a sentence saying nothing at the stove is
        smoking or burning (on the three ticks after a hazard ends it says
        'any more', because the scene may still mention the open window or the
        doused towel).
        Rule 2: a mistake sentence, or a sentence saying the current step
        follows the recipe and its card notes (once the recipe is complete, a
        sentence saying no step is being carried out). Distractor ticks get
        these sentences too: the steam, outside smoke or allowed swap still
        tempts a wrong answer, but the state never leaves the fact unsaid.
        """
        parts = [A_STOVE[z["stove"]][reg]]
        if z["hazard"] is not None:
            haz = A_HAZARDS[z["hazard"]]
            parts.append(pick(haz[0], "a-haz", t) if reg == 0 else "At the cooker, " + haz[1] + ".")
        elif after_hazard:
            parts.append(pick((A_NO_HAZARD_AFTER, A_NO_HAZARD_AFTER_P)[reg], f"a-after-{reg}", t))
        else:
            options = A_NO_HAZARD + ([A_NO_HAZARD_LIT] if z["stove"] != "off" else []) if reg == 0 else A_NO_HAZARD_P
            parts.append(pick(options, f"a-nohaz-{reg}", t))
        if z["stock_out"] and z["step"] == 7:
            parts.append(("The stock pot is used up, so the cook is using hot water from the kettle.",
                          "The broth has run out, so the cook has switched to hot water from the kettle.")[reg])
        if z["mistake"] is not None:
            mis = A_MISTAKES[z["mistake"]]
            parts.append(pick(mis[0], "a-mis", t) if reg == 0 else "Right now " + mis[1] + ".")
        elif self._complete(z):
            parts.append(pick((A_FINISHED, A_FINISHED_P)[reg], f"a-fin-{reg}", t))
        elif z["hazard"] is not None:
            parts.append(pick((A_ON_RECIPE_HAZ, A_ON_RECIPE_HAZ_P)[reg], f"a-okhaz-{reg}", t))
        else:
            parts.append(pick((A_ON_RECIPE, A_ON_RECIPE_P)[reg], f"a-ok-{reg}", t))
        return parts

    def render(self, history: list[Tick], variant: str) -> Any:
        tick = history[-1]
        z = tick.latent
        t = len(history) - 1
        if variant == "paraphrase":
            return self._render_paraphrase(history)
        s = tick.surface
        recipe = [f"{i}. {self._step_text(z, i, 0)} [{self._status(z, i)}]" for i in A_STEPS]
        if self._complete(z):
            recipe.append("All nine steps are done.")
        state: dict[str, Any] = {
            "time": clock(self.START, self.TICK_SECONDS * t),
            "recipe": recipe,
            "card_notes": A_NOTES,
            "cook_now": (f"Says: \"{s['say']}\" " if s["say"] else "") + f"Camera: {s['doing']}",
            "kitchen": " ".join(self._kitchen(z, t, 0, self._after_hazard(history))),
        }
        if variant == "lexical_decoy":
            partner = _a_partner_in_kitchen(t)
            lines, first_in_kitchen = _decoy_lines(A_DECOYS, self.policy(z)["action"], t, "a",
                                                   lambda d: partner or "partner" not in d.lower())
            fields = ["kitchen", "cook_now"] if first_in_kitchen else ["cook_now", "kitchen"]
            for field, line in zip(fields, lines):
                state[field] = f"{state[field]} {line}"
        return state

    def _render_paraphrase(self, history: list[Tick]) -> str:
        tick = history[-1]
        z = tick.latent
        t = len(history) - 1
        complete = self._complete(z)
        doing = "has finished" if complete else "is working through"
        parts = [f"It is {clock(self.START, self.TICK_SECONDS * t)}, and the cook {doing} a nine-stage card for mushroom risotto."]
        # Paraphrase format: completed stages are summarised, the rest are read out in full.
        if complete:
            parts.append(f"Every one of the nine stages is complete; the resting clock of stage 9 was halted with {mmss(z['timer_s'])} elapsed.")
        else:
            step = z["step"]
            # The list starts at the stage in hand, which may itself be complete,
            # so its heading must not suggest that every listed stage is still to do.
            rest = "From the stage in hand on, the card reads: "
            done = {0: "The card, stage by stage: ", 1: "Stage 1 is complete. " + rest,
                    2: "Stages 1 and 2 are complete. " + rest}.get(step - 1, f"Stages 1 to {step - 1} are complete. " + rest)
            parts.append(done + "; ".join(
                f"({i}) {self._step_text(z, i, 1)} - {self._status_p(z, i)}" for i in A_STEPS_P if i >= step) + ".")
        parts.append(A_NOTES_P)
        parts.extend(self._kitchen(z, t, 1, self._after_hazard(history)))
        parts.append(f"At this moment the cook {tick.surface['gist']}.")
        return " ".join(parts)


# ===========================================================================
# Scenario B - lab trainee, TAE buffer and agarose gel; action + target step
# ===========================================================================

B_PPE = "Before step 1: lab coat, nitrile gloves and safety glasses on."
B_PPE_P = "coat, nitrile gloves and goggles before stage 1"
B_STEPS = {
    1: "Make 1x TAE: add 50 mL of 10x TAE stock to 450 mL of deionised water in a 1 L bottle; cap, mix and label it.",
    2: "Weigh 1.0 g of agarose into a 250 mL flask and add 100 mL of 1x TAE.",
    3: "Microwave in 30-second bursts, swirling between bursts, until no specks remain.",
    4: "Cool the flask to 55-60 °C, then swirl in 10 µL of SYBR Safe.",
    5: "Pour the gel into the casting tray around the comb and let it set for 15 minutes.",
    6: "Remove the comb, place the gel in the tank with the wells at the black electrode, and cover it with 3-5 mm of 1x TAE.",
    7: "Load 5 µL of DNA ladder in lane 1 and 10 µL of each sample A-F in lanes 2-7.",
    8: "Close the lid, connect black to black and red to red, and run at 120 V for 15 minutes.",
    9: "Switch off the power supply, unplug the leads, then image the gel on the blue-light imager.",
}
B_STEPS_P = {
    1: "dilute the 10x TAE concentrate - 50 mL of it into 450 mL of deionised water in a litre bottle - then cap, mix and label it",
    2: "one gram of agarose into a 250 mL flask, topped up with 100 mL of that working buffer",
    3: "heat it in the microwave half a minute at a time, swirling after each go, until not a speck is left",
    4: "let it drop to between 55 and 60 degrees, then swirl in 10 microlitres of SYBR Safe",
    5: "pour it into the casting tray around the comb and give it fifteen minutes to set",
    6: "pull the comb, sit the gel in the tank with its wells towards the black electrode, and flood it with working buffer to 3-5 mm above the gel",
    7: "5 microlitres of size ladder into well 1 and 10 microlitres of each sample A to F into wells 2 to 7",
    8: "lid on, black lead to black and red to red, then 120 volts for fifteen minutes",
    9: "power the unit off and pull out the leads, then lift the gel out and photograph it under blue light",
}
B_NOTES = "Fine bubbles at both electrodes during a run are normal. Samples A-F are pre-mixed with loading dye."
B_NOTES_P = "The printout adds that a stream of small bubbles at both electrodes while the gel runs is expected, and that samples A to F already contain loading dye."
B_NO_APPROVAL = "Supervisor (Dr. Ruth Adeyemi) notes for bench 3 today: none."
B_NO_APPROVAL_P = "Dr. Ruth Adeyemi, the supervisor, has left no notes for bench 3 today."
B_APPROVAL = "Supervisor (Dr. Ruth Adeyemi) notes for bench 3 today, left at 08:50: 'The SYBR Safe tube in drawer 3 is past the date on its label. I tested it on Monday and it still works, so use it for today's practice gel.'"
B_APPROVAL_P = "Dr. Ruth Adeyemi, the supervisor, left word for bench 3 at 08:50 this morning that the SYBR Safe tube in drawer 3 is past its printed date but passed her check on Monday, and that it is to be used for today's practice gel."

# The role text declares the closed-world conventions the renderer keeps
# (SPEC 3.5): the hazards of rule 1 other than the lid are always reported in
# `bench`; what a step needs is at hand, in date and working unless `bench`
# shows otherwise; and a finished step's record shows any value that differs
# from the protocol. The power supply's state is given at every tick, and while
# it is on, `bench` says when the tank lid is closed and `log` shows it lifted.
B_ROLE = (
    "You coach a trainee, Jonah, through a written lab protocol: making 1x TAE buffer, then casting and running an agarose gel. "
    "`protocol` lists the protective equipment to put on first and then the nine numbered steps, each with its status; a finished step's status "
    "gives the values recorded for it, and a finished step whose status shows no value that differs from the protocol has no difference left to put right. "
    "`notes` are the protocol's notes and today's supervisor notes; `bench` describes equipment and reagents; `log` holds the latest observations, newest last. "
    "`bench` always reports liquid on the power supply or its leads and anyone holding a flask fresh from the microwave without the heat-resistant glove, "
    "so if it reports neither, neither is happening; anything the current step needs is at hand, in date and working unless `bench` shows otherwise. "
    "The current step is the numbered step the trainee is working on now; between steps it is the step finished last, a step being redone is the current step, "
    "and before step 1 has begun there is no current step. Judge only the moment shown: an action stays right for as long as its rule is the "
    "first that matches, even if it was already given a moment ago."
)
B_ROLE_P = (
    "You are coaching Jonah, a trainee, through a printed bench protocol in which he dilutes TAE running buffer and then casts and runs an agarose gel. "
    "Each update tells you what is happening at the bench, the time, his progress through the protective kit and the nine numbered stages, and the "
    "printout itself. Each completed stage comes with what was logged for it, and a completed stage whose log shows nothing at odds with the printout "
    "has nothing left to make good. An update always mentions liquid reaching the power pack or its cables and anyone gripping a flask just out of the "
    "microwave without the heat-proof mitt, so if it mentions neither, neither is happening; whatever the stage in hand relies on is present, in date "
    "and working unless the update says otherwise. The stage in hand is the numbered stage Jonah is busy with; while he is between stages it is the one "
    "he completed last, a stage he is repeating is the stage in hand, and before stage 1 begins there is none. Work only from the moment described: an "
    "answer holds for as long as its rule is the first that fits, even if it was given at the previous update."
)
B_POLICY = [
    "1. If something at the bench is unsafe right now - the power supply is switched on while the tank lid is off, liquid has run onto the power supply or its leads, or someone is holding a flask fresh from the microwave without the heat-resistant glove: action = stop for safety; step = none.",
    "2. Otherwise, if a reagent or instrument that the current step needs is past the expiry date on its label, missing or faulty, no in-date working replacement is at hand, and the supervisor has not approved using it anyway: action = call the supervisor; step = the current step.",
    "3. Otherwise, if a step before the current step was done differently from the protocol (a wrong amount, setting, orientation or item) and has not since been redone or put right: action = send back to redo; step = that earlier step (the earliest one if there are several).",
    "4. Otherwise, if the current step is being done, or has been done, differently from the protocol (a wrong amount, setting, orientation or item) and the difference has not since been put right (for a step being redone, only the new attempt counts): action = correct the current step; step = the current step. Carrying on past a timed step's time is not a difference.",
    "5. Otherwise, if the current step is finished, a later step remains and the trainee has not started it: action = prompt the next step; step = that next step. A timed step is finished once its timer reaches the protocol's time; any other step is finished when everything it describes is done.",
    "6. Otherwise: action = stay quiet; step = none.",
]
B_POLICY_P = [
    "1. Should anything at the bench be dangerous at this moment - the power pack running while the tank's cover is off, liquid reaching the power pack or its cables, or anyone gripping a flask just out of the microwave without the heat-proof mitt: halt over a hazard, with no stage named.",
    "2. Failing that, should a chemical or device that the stage in hand relies on be beyond the use-by date printed on it, absent or broken, with no in-date, working substitute to hand and no go-ahead from the supervisor to use it regardless: summon the supervisor, naming the stage in hand.",
    "3. Failing that, should any stage before the stage in hand have been carried out otherwise than the printout says (a wrong quantity, setting, direction or item) and not yet been repeated or made good: go back and repeat, naming that earlier stage (the first such stage if there are more).",
    "4. Failing that, should the stage in hand be under way, or already completed, otherwise than the printout says (a wrong quantity, setting, direction or item), with the departure not yet made good (in a stage being repeated, only the fresh attempt matters): flag a fix in the stage in hand, naming it. Letting a timed stage run beyond its time is not a departure.",
    "5. Failing that, should the stage in hand be complete while a further stage remains and Jonah has not begun it: cue the following stage, naming it. A stage with a time is complete as soon as its timer reaches the printed time; any other stage is complete once all it describes has been done.",
    "6. In any other case: keep silent, with no stage named.",
]

B_ACTIONS = {
    "wait": "Stay quiet and keep watching the trainee work.",
    "prompt_next": "Tell the trainee to start on the next protocol step.",
    "correct": "Tell the trainee what to change in the current step.",
    "rollback": "Send the trainee back to redo an earlier step.",
    "safety": "Make the trainee stop at once for a safety problem.",
    "escalate": "Call the lab supervisor over to deal with it.",
}
B_ACTIONS_P = {
    "wait": "Keep silent and let Jonah carry on unprompted.",
    "prompt_next": "Cue Jonah to begin the following stage.",
    "correct": "Flag the fix needed in the stage in hand.",
    "rollback": "Have Jonah go back and repeat a completed stage.",
    "safety": "Halt Jonah immediately over a hazard.",
    "escalate": "Summon the supervisor to handle the matter.",
}
B_ACTIONS_D = {
    "wait": "Stay quiet and keep watching while the trainee works.",
    "prompt_next": "Tell the trainee to start the next protocol step.",
    "correct": "Tell the trainee what to change in the current step.",
    "rollback": "Send the trainee back to redo an earlier step.",
    "safety": "Make the trainee stop at once for a safety problem.",
    "escalate": "Call the lab supervisor over to deal with this.",
}
B_TARGETS = {
    "step1": "Step 1, the 1x TAE buffer",
    "step2": "Step 2, agarose into the flask",
    "step3": "Step 3, melting in the microwave",
    "step4": "Step 4, cooling and adding stain",
    "step5": "Step 5, pouring and setting the gel",
    "step6": "Step 6, gel into the tank",
    "step7": "Step 7, loading ladder and samples",
    "step8": "Step 8, the electrophoresis run",
    "step9": "Step 9, switching off and imaging",
    "none": "No particular step",
}
B_TARGETS_P = {
    "step1": "Stage 1: diluting the running buffer",
    "step2": "Stage 2: agarose and buffer in the flask",
    "step3": "Stage 3: dissolving it by microwave",
    "step4": "Stage 4: letting it cool, then staining",
    "step5": "Stage 5: casting the gel",
    "step6": "Stage 6: comb out, gel in position",
    "step7": "Stage 7: filling the wells",
    "step8": "Stage 8: running the gel",
    "step9": "Stage 9: power off and the picture",
    "none": "No stage in particular",
}

# Progress before step 1 (protective equipment) and of the current step:
# canonical phrasing, paraphrase phrasing. '{stock}' and '{agarose}' are filled
# from the latent amounts of the current batch.
B_PROGRESS = {
    "p0_coat": ("in progress: lab coat on; gloves and safety glasses not on yet", "the coat is on, the gloves and goggles are not"),
    "p0_gloves": ("in progress: lab coat and nitrile gloves on; safety glasses not on yet", "coat and gloves are on, goggles still missing"),
    "p1_start": ("1 L bottle and 500 mL cylinder set out; nothing measured yet", "bottle and cylinder are out, nothing measured"),
    "p1_cyl": ("450 mL of deionised water measured in the cylinder, not yet in the bottle", "450 mL of deionised water is in the cylinder, not yet poured"),
    "p1_water": ("450 mL of deionised water in the bottle; no 10x stock added yet", "the bottle holds 450 mL of deionised water and none of the concentrate"),
    "p1_added": ("stock addition done: {stock} mL of 10x TAE stock added to the 450 mL of deionised water in the bottle; not mixed yet", "the concentrate has gone in, {stock} mL of it on top of the 450 mL of water, still unmixed"),
    "p1_mix": ("450 mL of deionised water and {stock} mL of 10x TAE stock in the bottle; being capped and mixed", "the 450 mL of water and {stock} mL of concentrate are being capped and mixed"),
    "p1_fin": ("finished, with {stock} mL of 10x TAE stock + 450 mL of deionised water, mixed and labelled", "finished, with {stock} mL of concentrate in 450 mL of water, mixed and labelled"),
    "p1_redo0": ("being redone: the first bottle and the flask have just been poured away; nothing measured again yet", "being repeated: the first bottle and the flask have gone down the sink, nothing measured again yet"),
    "p1_redo_water": ("being redone: 450 mL of deionised water in the rinsed bottle; no 10x stock added yet", "being repeated: 450 mL of deionised water in the rinsed bottle, no concentrate yet"),
    "p1_redo_added": ("being redone: 450 mL of deionised water and {stock} mL of 10x TAE stock in the bottle; not mixed yet", "being repeated: 450 mL of water and {stock} mL of concentrate in the bottle, unmixed"),
    "p1_redo_mix": ("being redone: 450 mL of deionised water and {stock} mL of 10x TAE stock in the bottle; being capped and mixed", "being repeated: 450 mL of water and {stock} mL of concentrate are being capped and mixed"),
    "p2_weighed": ("{agarose} g of agarose weighed into a 250 mL flask; no buffer added yet", "{agarose} g of agarose is in the 250 mL flask, no buffer yet"),
    "p3_b1": ("1 burst of 30 s so far; cloudy", "one half-minute burst so far, still cloudy"),
    "p3_b2": ("2 bursts so far, swirled between; cloudy with many specks", "two bursts, swirled in between, still cloudy and full of specks"),
    "p3_b3": ("3 bursts so far; clearing, but specks remain", "three bursts; clearing, specks still there"),
    "p3_b4": ("4 bursts so far; a few clear specks still float in the liquid", "four bursts; a few glassy specks are still drifting in it"),
    "p3_fin": ("finished after 5 bursts, clear with no specks left", "finished after five bursts, clear with not a speck left"),
    "p4_cool": ("flask cooling on the cork ring; stain not added yet", "the flask is cooling on the cork ring with no stain in yet"),
    "p4_drawn": ("flask at 58 °C; 10 µL of SYBR Safe drawn up in the pipette, not added to the flask yet", "the flask is at 58 degrees and 10 microlitres of SYBR Safe are drawn up in the pipette, not yet added"),
    "p6_in": ("comb out; gel lowered into the tank; no buffer poured yet", "comb out, the gel sits in the tank with no buffer yet"),
    "p6_pour": ("comb out; gel in the tank; 1x TAE being poured over it", "comb out, gel in the tank, working buffer going in over it"),
    "p6_level": ("comb out; gel in the tank under about 4 mm of 1x TAE", "comb out, the gel sits under roughly 4 mm of working buffer"),
    "p6_fixed": ("finished after turning the gel round: comb out, wells at the black electrode, buffer back up to about 4 mm; no lane loaded yet", "finished once the gel was turned round: comb out, wells facing the black electrode, buffer back to about 4 mm, no well loaded yet"),
    "p7_l1": ("ladder in lane 1; lanes 2-7 empty", "ladder in well 1, wells 2 to 7 empty"),
    "p7_l2": ("ladder in lane 1, sample A in lane 2; lanes 3-7 empty", "ladder in well 1 and sample A in well 2, wells 3 to 7 empty"),
    "p7_l4": ("ladder in lane 1, samples A-C in lanes 2-4; lanes 5-7 empty", "ladder in well 1, samples A to C in wells 2 to 4, the last three wells empty"),
    "p7_l6": ("ladder in lane 1, samples A-E in lanes 2-6; lane 7 empty", "ladder in well 1, samples A to E in wells 2 to 6, well 7 still empty"),
    "p8_lid": ("all seven lanes loaded; lid closed; leads not connected and voltage not set yet", "all seven wells filled and the lid on, cables not yet plugged in and no voltage dialled"),
    "p8_leads": ("lid closed; black lead in the black socket, red in red; voltage not set yet", "lid on, black cable to black and red to red, voltage still unset"),
    "p8_set": ("lid closed; black lead in black, red in red; voltage dial set; run not started yet", "lid on, black cable to black and red to red, voltage dialled in, run not yet started"),
    "p9_off": ("power supply switched off; leads still plugged in", "the power pack is off, cables still in"),
    "p9_unplug": ("power off and leads unplugged; gel still in the tank", "power off and cables out, the gel still in the tank"),
    "p9_out": ("gel tray out of the tank, draining", "the gel tray is out of the tank and draining"),
    "p9_imager": ("gel on the blue-light imager, cover closed", "the gel is on the blue-light imager with the cover down"),
    "p9_screen": ("image on screen, not saved yet", "the picture is on screen but not yet saved"),
    "p9_fin": ("finished, image saved", "finished, the picture saved"),
}
B_DONE = {
    1: ("done; recorded: {stock} mL of 10x stock + 450 mL of water", "complete, logged as {stock} mL of the 10x concentrate in 450 mL of water"),
    2: ("done; recorded: {agarose} g of agarose + 100 mL of 1x TAE", "complete, logged as {agarose} g of agarose in 100 mL of working buffer"),
    3: ("done", "complete, clear after five bursts"),
    4: ("done; stain added at 58 °C", "complete, stain added at 58 degrees"),
    5: ("done", "complete"),
    6: ("done; recorded: comb out, wells at the {wells} electrode, about 4 mm of buffer", "complete, logged as comb out and wells towards the {wells} electrode under about 4 mm of buffer"),
    7: ("done; all seven lanes loaded", "complete, all seven wells filled"),
    8: ("done", "complete"),
    9: ("done", "complete"),
}
B_DONE_P = {
    1: "the buffer logged as {stock} mL of concentrate in 450 mL of water",
    2: "the flask as {agarose} g of agarose in 100 mL of working buffer",
    3: "the melt as clear after five bursts",
    4: "the stain as added at 58 degrees",
    6: "the gel as out of its comb and sitting with its wells towards the {wells} electrode under about 4 mm of buffer",
    7: "the wells as ladder in 1 and samples A to F in 2 to 7",
}

# Irrelevant content for the lexical-decoy register, keyed by the option whose
# vocabulary it borrows. None of it concerns Jonah's bench. Lines naming Felix
# are used only while Felix is at his bench (he is in the cold room at t27 and
# packs up at t83).
B_DECOYS = {
    "wait": [
        "A sign on the cold-room door asks visitors to stay quiet and keep watching for the defrost light.",
        "The seminar flyer says new trainees should stay quiet and keep watching during their first week of shadowing.",
        "Over the intercom, facilities ask everyone to keep watching their email for the lift schedule.",
        "Mina tells Felix she will stay quiet at lab meeting and keep watching how the new postdoc presents.",
    ],
    "prompt_next": [
        "Mina says she will start on the next protocol step of her cloning project on Monday.",
        "A cooking show on Felix's radio tells listeners to start on the next step once the dough has risen.",
        "The department newsletter pinned by the door says the next protocol step for new trainees is the October quiz.",
        "An email on Mina's screen tells her to start the next step of her visa application.",
    ],
    "correct": [
        "Felix asks Mina what to change in the current draft of his conference poster.",
        "A reviewer's email on Mina's screen asks her to change the current step 4 of her methods section.",
        "Mina says the lab manual's autoclave page needs a change in the current edition.",
        "Over the intercom, facilities say they will change the current parking rules next week.",
    ],
    "rollback": [
        "Felix complains that the plate-reader software rolled back to an earlier version overnight.",
        "Mina says she has to go back and redo an earlier step of her Western blot next week.",
        "The department sent the freezer inventory back to be redone from an earlier version.",
        "An email tells Mina her ethics form has been sent back to redo an earlier section.",
    ],
    "safety": [
        "An email from the building safety officer says that at next Tuesday's fire drill everyone must stop at once and use the stairs.",
        "A poster by the eyewash station lists the safety problems found at last year's inspection.",
        "Felix mentions that his old lab once had to stop at once over a fume-hood safety problem.",
        "Mina reads out a notice that the safety problem with the third-floor lift is fixed.",
    ],
    "escalate": [
        "Mina says she will call the lab supervisor of the imaging core over to deal with a booking clash next month.",
        "Facilities ask each lab supervisor to deal with the new bench labels by the end of October.",
        "Felix jokes that he will call his old supervisor over to deal with the coffee rota.",
        "An email asks every lab supervisor to deal with their overdue equipment logs.",
    ],
}


def _b_felix_present(t: int) -> bool:
    return t <= 83 and t != 27


def _b_line(entry: tuple[str, ...]) -> dict[str, str]:
    """One tick of scenario B surface: the observation log line, a gist for the
    paraphrase, and optionally an extra bench remark in both registers (texture only)."""
    out = {"log": entry[0], "gist": entry[1]}
    if len(entry) > 2:
        out["bench"] = entry[2]
        out["bench_p"] = entry[3]
    return out


GLOVE_ON = ("The heat-resistant glove is on Jonah's right hand.", "The heat-proof mitt is on Jonah's right hand.")

B_SCRIPT = _script(
    _b_line,
    (0, [  # protective equipment, before step 1
        ("Jonah arrives at bench 3 with the printed protocol and buttons up a lab coat.", "has just reached bench 3 with the printout and is buttoning up a lab coat"),
        ("Jonah pulls on a pair of nitrile gloves and pats his pockets for his safety glasses.", "is pulling on nitrile gloves and patting his pockets for his goggles"),
    ]),
    (2, [  # step 1, buffer; Felix chats about reagents
        ("Jonah puts on his safety glasses and sets a 1 L bottle and a 500 mL measuring cylinder on the bench.", "has his goggles on and has set out a litre bottle and a 500 mL cylinder"),
        ("Jonah fills the cylinder from the deionised-water tap and reads the meniscus at 450 mL.", "runs deionised water into the cylinder up to the 450 mL mark"),
        ("Jonah pours the water into the bottle. Felix, at the next bench: 'Heads up, we're out of 50x TAE and the reorder is stuck until next week.'", "tips the water into the bottle while Felix, at the next bench, grumbles that the 50x TAE has run out and its reorder is stuck until next week"),
        ("Jonah takes the 10x TAE stock bottle off the shelf. Felix: 'And the agarose jar is nearly empty too, maybe 20 grams left.'", "fetches the 10x TAE concentrate from the shelf as Felix adds that the agarose jar is almost empty"),
    ]),
    (6, [  # 5 mL of stock instead of 50 mL
        ("Jonah draws 5 mL of 10x TAE stock into a 10 mL serological pipette, empties it into the bottle and drops the pipette in the waste.", "pipettes 5 mL of the 10x concentrate into the bottle in one go and drops the pipette in the waste"),
        ("Jonah caps the bottle and inverts it ten times to mix.", "caps the bottle and turns it over and over to mix it"),
        ("Jonah writes '1x TAE, JP, 25/09' on the bottle with a marker.", "labels the bottle as 1x TAE with his initials and the date"),
    ]),
    (9, [  # step 2 with 1.50 g of agarose, then step 3 on the under-strength buffer
        ("Jonah weighs 1.50 g of agarose on the balance and tips it into a 250 mL flask.", "weighs out one and a half grams of agarose and tips it into a 250 mL flask"),
        ("Jonah adds 100 mL of the new buffer, pulls on the heat-resistant glove and starts a 30-second burst in the microwave.", "adds 100 mL of his new buffer, pulls on the heat-proof mitt and starts a half-minute burst in the microwave", *GLOVE_ON),
        ("Wearing the glove, Jonah swirls the cloudy flask, puts it back and starts a second burst.", "swirls the cloudy flask in the mitt and starts a second burst", *GLOVE_ON),
    ]),
    (12, [  # step 1 redone
        ("Jonah rereads the protocol, mutters 'fifty, not five, and one gram, not one and a half', lifts the flask out with the glove and pours it and the bottle down the sink.", "rereads the printout, mutters 'fifty, not five, and one gram, not one and a half', and pours the flask and the bottle away with the mitt on", "Jonah is holding the emptied flask in the heat-resistant glove.", "Jonah holds the emptied flask in the heat-proof mitt."),
        ("Jonah rinses the bottle and measures 450 mL of deionised water into it again.", "rinses the bottle and runs 450 mL of deionised water into it again"),
        ("Jonah measures 50 mL of 10x TAE stock in a 50 mL cylinder and adds it to the bottle.", "measures 50 mL of the concentrate in a small cylinder and adds it"),
        ("Jonah caps the bottle and inverts it to mix. Felix: 'Happens to everyone once.'", "caps and inverts the bottle while Felix tells him it happens to everyone once"),
    ]),
    (16, [  # step 2 again
        ("Jonah relabels the bottle and weighs 1.00 g of agarose into a clean 250 mL flask.", "relabels the bottle and weighs a fresh gram of agarose into a clean flask"),
    ]),
    (17, [  # step 3, microwave
        ("Jonah adds 100 mL of the fresh buffer, pulls on the heat-resistant glove and starts a 30-second burst in the microwave.", "adds 100 mL of the fresh buffer, pulls on the mitt and starts a half-minute burst", *GLOVE_ON),
        ("The burst ends; wearing the heat-resistant glove, Jonah swirls the cloudy flask and starts a second burst.", "swirls the cloudy flask in the mitt and starts a second burst", "The microwave is running the second burst; the heat-resistant glove is on Jonah's right hand.", "The second burst is running; the heat-proof mitt is on Jonah's right hand."),
        ("Wearing the glove, Jonah swirls again; the liquid is clearing around the specks. He starts a third burst.", "swirls again in the mitt as the liquid clears around the remaining specks, and starts a third burst", *GLOVE_ON),
        ("Jonah swirls with the glove on and runs a fourth burst; the microwave beeps 'End'. Jonah: 'Done!' He hangs the heat-resistant glove on its hook to write in his notebook.", "swirls in the mitt, runs a fourth burst, hears the microwave beep 'End', calls out 'Done!' and hangs the mitt on its hook to write in his notebook", "The flask is still inside the closed microwave; the heat-resistant glove is on its hook.", "The flask is still shut inside the microwave, and the mitt hangs on its hook."),
    ]),
    (21, [  # hot flask handled in nitrile gloves
        ("Jonah swirls the flask by its neck inside the microwave and runs a fifth burst; the liquid is now clear. He lifts the flask out by its neck in his nitrile gloves.", "swirls the flask by its neck, runs a fifth burst, finds the liquid clear and lifts the flask out by its neck in his nitrile gloves"),
        ("Jonah swirls the flask and holds it up to the light, checking for specks.", "swirls the flask and holds it up to the light"),
        ("'Ow, that's hot.' Jonah shifts the flask from hand to hand, looking for the cork ring.", "yelps that it is hot and passes the flask from hand to hand, looking for the cork ring"),
    ]),
    (24, [  # step 4; the only stain tube at hand is out of date
        ("Jonah pulls on the heat-resistant glove, sets the flask on the cork ring to cool, and takes the SYBR Safe tube out of drawer 3.", "pulls on the mitt, stands the flask on the cork ring to cool and takes the SYBR Safe tube from drawer 3", "Jonah is holding the SYBR Safe tube.", "Jonah holds the SYBR Safe tube."),
        ("Jonah turns the tube to read its label and frowns. 'Felix, is there another SYBR Safe?'", "reads the tube's label, frowns and asks Felix whether there is another SYBR Safe", "The flask is standing on the cork ring; nobody is holding it.", "Nobody is touching the flask on its cork ring."),
        ("Felix checks drawer 3 and the rack above it: 'That's the only one out here.'", "watches Felix search drawer 3 and the rack above it and report that this is the only tube out", "Jonah is holding the SYBR Safe tube.", "Jonah holds the SYBR Safe tube."),
        ("Felix: 'There might be a new lot in the cold room, let me look.' He heads out; Jonah holds the old tube.", "waits with the old tube while Felix goes to look for a new lot in the cold room"),
    ]),
    (28, [  # a new tube arrives; cooling continues
        ("Felix comes back with a sealed SYBR Safe tube from the cold room and hands it to Jonah.", "takes a sealed SYBR Safe tube that Felix has brought back from the cold room", "Jonah is holding the new tube.", "Jonah holds the new tube."),
        ("Jonah drops the old tube into the expired-reagents box and points the infrared thermometer at the flask.", "drops the old tube into the box for expired reagents and checks the flask with the infrared thermometer"),
        ("Jonah wipes the balance pan and closes the agarose jar.", "wipes the balance pan and closes the agarose jar", "The flask is standing on the cork ring; nobody is holding it.", "Nobody is touching the flask on its cork ring."),
        ("Jonah reads the flask temperature again and flicks the new tube to bring the liquid down.", "rechecks the flask's temperature and flicks the new tube"),
        ("Jonah draws 10 µL of SYBR Safe from the new tube into the pipette and brings the tip to the neck of the flask.", "draws 10 microlitres of SYBR Safe from the new tube into the pipette and brings it to the neck of the flask"),
    ]),
    (33, [  # step 5, pour and set (timer from 0:30)
        ("Jonah dispenses the stain into the flask and swirls it in, then pours the gel into the casting tray around the comb and starts the 15-minute timer.", "has swirled the stain into the flask, poured the gel into the casting tray around the comb and started the fifteen-minute timer"),
        ("Jonah nudges a small bubble away from the comb teeth with a pipette tip.", "nudges a small bubble away from the comb with a pipette tip"),
        ("Jonah rinses the emptied, cooled flask at the sink.", "rinses out the empty, cooled flask at the sink"),
        ("Jonah knocks over the wash bottle; about 50 mL of water spreads across the bench by the sink.", "knocks the wash bottle over and about 50 mL of water spreads across the bench by the sink", "The spilled water is by the sink, about two metres from the power supply.", "The spill is by the sink, a good two metres from the power pack."),
        ("Jonah mops up the water with paper towels.", "mops up the water with paper towels", "The puddle by the sink is nearly gone.", "Only a trace of the puddle by the sink is left."),
        ("Jonah drops the wet towels in the bin and dries his gloves.", "bins the wet towels and dries his gloves"),
        ("Jonah writes '1% agarose, poured 14:24:15' in his notebook.", "notes in his notebook that the 1% gel was poured at 14:24:15"),
        ("Felix: 'Can I borrow your 1 kb ladder later? Ours is empty.' Jonah: 'Sure, after I load.'", "agrees to lend Felix his ladder once he has loaded"),
        ("Jonah squints at the buffer bottle: 'Did I really put 50 in this time?' He shrugs and goes back to his notebook.", "squints at the buffer bottle, wonders aloud whether he really put 50 mL in this time, then shrugs and goes back to his notebook"),
        ("Felix tells Jonah about his plan to go climbing in the Alps this weekend.", "listens to Felix describe a climbing weekend in the Alps"),
        ("Mina comes over: her Western blot failed overnight and she wants to know who used the transfer tank last.", "is asked by Mina, whose Western blot failed overnight, who last used the transfer tank"),
        ("Mina and Felix argue about whether the transfer buffer was made with methanol.", "listens as Mina and Felix argue about methanol in the transfer buffer"),
        ("Mina asks Jonah to sign the -80 °C freezer log; he signs it.", "signs the minus-eighty freezer log for Mina"),
        ("Felix reads out the ordering list: pipette tips, ethanol and more 50x TAE.", "hears Felix read out the order list of tips, ethanol and 50x TAE"),
        ("Jonah fetches the rack of samples A-F from the fridge and sets it by the tank.", "brings the rack of samples A to F from the fridge and sets it by the tank"),
        ("Jonah checks the tank: clean and dry, with its lid and leads beside it.", "checks that the tank is clean and dry, its lid and cables beside it"),
        ("Jonah taps the edge of the casting tray: 'It's gone cloudy. Looks set to me.'", "taps the tray and remarks that the gel has gone cloudy and looks set"),
        ("Jonah reads step 6 aloud to himself.", "reads the tank stage aloud to himself"),
        ("Jonah checks the imager booking sheet: his slot runs from 15:00 to 15:30.", "confirms on the booking sheet that his imager slot is 15:00 to 15:30"),
        ("Jonah writes the lane plan in his notebook: ladder in lane 1, samples A-F in lanes 2-7.", "writes his lane plan into the notebook"),
    ]),
    (53, [  # set time reached; Jonah has not started step 6
        ("The timer beeps; Jonah silences it and keeps writing up this morning's PCR in his notebook.", "has silenced the timer, which beeped at fifteen minutes, and carries on writing up the morning's PCR"),
        ("Jonah chats with Felix about the annealing temperature he used for the PCR.", "chats with Felix about the annealing temperature of his PCR"),
        ("Jonah flips back through his notebook to copy out the primer names.", "leafs back through his notebook for the primer names"),
    ]),
    (56, [  # gel in the tank the wrong way round (conveyed by the log only)
        ("Jonah eases the comb out and lowers the gel tray into the tank with its wells next to the red socket.", "eases out the comb and lowers the gel into the tank with its wells beside the red socket"),
        ("Jonah pours 1x TAE from his bottle into the tank over the gel.", "pours working buffer from his bottle into the tank over the gel, whose wells sit by the red socket"),
        ("Jonah tops the buffer up until it is about 4 mm over the gel and checks the level at eye height.", "tops the buffer up to about 4 mm over the gel, its wells still by the red socket, and checks the level at eye height"),
    ]),
    (59, [  # turned round and topped up; Jonah chats before loading
        ("Jonah glances from the wells to the sockets: 'Wells go at black.' He lifts the tray out, turns it round, sets it back and tops the buffer back up to about 4 mm.", "looks from the wells to the sockets, says 'wells go at black', turns the tray round and tops the buffer back up to about 4 mm"),
        ("Jonah: 'There, the tank's sorted.' He takes out his phone to answer a message from his flatmate.", "says the tank is sorted and answers a message from his flatmate on his phone"),
        ("Felix asks about Jonah's weekend; Jonah leans on the bench chatting, the pipette still in its stand.", "chats with Felix about the weekend, the pipette still in its stand"),
    ]),
    (62, [  # step 7, loading; step 8, setting up the run
        ("Jonah draws 5 µL of ladder into the P10 pipette and loads it into lane 1.", "draws 5 microlitres of ladder into the pipette and loads it into the first well"),
        ("Jonah turns the P10 dial from 5.0 to 10.0 µL and loads sample A into lane 2.", "turns the pipette dial from 5 to 10 microlitres and loads sample A into well 2"),
        ("Jonah loads 10 µL each of samples B and C into lanes 3 and 4; Felix leans over to watch.", "loads 10 microlitres each of samples B and C into wells 3 and 4 while Felix leans over to watch"),
        ("Jonah loads 10 µL each of samples D and E into lanes 5 and 6, steadying his wrist on the bench.", "loads 10 microlitres each of samples D and E into wells 5 and 6, wrist steadied on the bench"),
        ("Jonah loads 10 µL of sample F into lane 7 and closes the tank lid.", "loads 10 microlitres of sample F into the last well and puts the lid on the tank"),
        ("Jonah plugs the black lead into the black socket and the red lead into the red one on the power supply.", "plugs the black cable into black and the red into red on the power pack"),
        ("Jonah turns the voltage dial to 120 V.", "dials the power pack to 120 volts"),
        ("Jonah presses Run; the display shows the current climbing.", "has pressed Run and is watching the current climb on the display"),
    ]),
    (70, [  # run under way (timer from 0:30 at t69)
        ("Jonah watches the blue dye move out of the wells into the gel.", "watches the blue dye leave the wells and enter the gel"),
        ("Jonah puts the leftover samples back in the fridge.", "returns the leftover samples to the fridge"),
        ("Fine bubbles stream up from both electrodes. Jonah: 'Is it supposed to fizz like that?'", "sees fine bubbles streaming from both electrodes and wonders aloud whether it should fizz like that"),
        ("Jonah wipes down the balance and throws away the used weigh boats.", "wipes the balance and bins the weigh boats"),
        ("Felix collects the ladder tube and thanks Jonah.", "hands Felix the ladder tube and gets a thank-you"),
        ("Dr. Adeyemi, the lab supervisor, stops by the bench and asks Jonah how the gel is going.", "is asked by Dr. Adeyemi, the supervisor, stopping by, how the gel is going"),
        ("The supervisor asks which sample is in which lane; Jonah reads out his lane plan.", "reads out his lane plan when the supervisor asks which sample is where"),
        ("Dr. Adeyemi says that next week Jonah will clone the band from lane 4.", "hears from Dr. Adeyemi that he will clone the lane 4 band next week"),
        ("The supervisor reminds Felix that lab meeting has moved to Tuesday.", "listens as the supervisor tells Felix that lab meeting has moved to Tuesday"),
        ("Dr. Adeyemi heads back to her office.", "watches Dr. Adeyemi head back to her office"),
        ("Jonah books a second imager slot for Monday.", "books a second imager slot for Monday"),
        ("Jonah writes the run start time, 14:51:15, in his notebook.", "notes the run's 14:51:15 start in his notebook"),
        ("The dye front is about halfway down the gel.", "sees the dye front about halfway down the gel"),
        ("Jonah stretches and rolls his shoulders; Felix is packing up for the day.", "stretches while Felix packs up for the day"),
        ("Jonah: 'Dye front's three-quarters down, surely that's enough.' He leaves the run going.", "says the dye front is three-quarters down and surely that is enough, but leaves the run going"),
        ("Mina asks whether anyone has seen her box of 1.5 mL tubes.", "is asked by Mina about her missing box of 1.5 mL tubes"),
        ("Jonah finds Mina's tube box on the top shelf and hands it down.", "finds Mina's tube box on the top shelf and hands it down"),
        ("Jonah watches the purple and blue dyes separating in the gel.", "watches the purple and blue dyes pull apart in the gel"),
        ("Jonah refills the pipette-tip box from a bag.", "refills the tip box from a bag"),
    ]),
    (89, [  # run time passed; lid lifted with the power supply still running (log only)
        ("Jonah lifts the lid off the tank to get a closer look at the dye front.", "lifts the lid off the tank for a closer look at the dye front"),
        ("Holding the lid in one hand, Jonah points at the gel with the other, counting the dye bands.", "holds the lid in one hand and counts the dye bands with the other"),
        ("Jonah, still holding the lid, tilts his head to read the lane numbers.", "still holds the lid and tilts his head to read the lane numbers"),
    ]),
    (92, [  # step 9 and completion
        ("Jonah sets the lid on the bench and presses Stop; the display goes dark.", "puts the lid down on the bench and presses Stop, and the display goes dark"),
        ("Jonah unplugs both leads from the power supply.", "pulls both cables out of the power pack"),
        ("Jonah lifts the gel tray out of the tank and lets the buffer drain.", "lifts the gel tray out and lets it drain"),
        ("Jonah slides the gel onto the blue-light imager and closes the amber cover.", "slides the gel onto the blue-light imager and shuts the amber cover"),
        ("The imager screen shows the ladder in lane 1 and one bright band in each of lanes 2-7.", "sees the ladder in lane 1 and a bright band in each sample lane on the screen"),
        ("Jonah saves the image as JP_250926_gel1.tif.", "saves the picture as JP_250926_gel1.tif"),
        ("Jonah drops the gel into the solid-waste bin and pours the tank buffer back into his bottle.", "bins the gel and pours the tank buffer back into his bottle"),
        ("The supervisor, Dr. Adeyemi, looks at the image over Jonah's shoulder: 'Nice clean bands.'", "shows the picture to the supervisor, Dr. Adeyemi, who calls the bands nice and clean"),
    ]),
)

# Counterfactual surfaces.
B_CF_SPILL = {
    36: ("Jonah knocks over the wash bottle; the water runs along the bench and under the power supply.", "knocks the wash bottle over and the water runs along the bench under the power pack"),
    37: ("Jonah stares at the water pooling round the power supply's plug and leads, paper towels in hand.", "stands with paper towels, staring at the water pooling round the power pack's plug and cables"),
    38: ("Jonah dabs at the near edge of the puddle; the water round the power supply's plug and leads is still untouched.", "dabs at the near edge of the puddle while the water round the power pack's plug and cables stays where it is"),
    39: ("Jonah unplugs the power supply at the wall, dries it and its leads, and moves it to a dry spot.", "unplugs the power pack at the wall, dries it and its cables and moves it somewhere dry",
         "The power supply's mains plug is out of the wall for now; the wet paper towels are in the bin.",
         "The power pack is unplugged at the wall for now, and the wet towels are in the bin."),
    # The supply was unplugged at the wall at t39; it goes back in before the run.
    48: ("Jonah plugs the dried power supply back in at the wall, leaves it switched off and checks the tank: clean and dry, with its lid and leads beside it.",
         "plugs the dried power pack back in at the wall, leaves it off and checks that the tank is clean and dry, its lid and cables beside it"),
}
B_CF_VOLTS = {
    68: ("Jonah turns the voltage dial to 210 V.", "dials the power pack to 210 volts"),
    69: ("Jonah presses Run; the display shows the current climbing fast.", "has pressed Run and is watching the current climb fast on the display"),
    70: ("Jonah watches the blue dye race out of the wells into the gel.", "watches the blue dye race out of the wells into the gel"),
    71: ("Jonah looks at the display, turns the dial down to 120 V, then puts the leftover samples back in the fridge.", "reads the display, turns the dial down to 120 volts and returns the leftover samples to the fridge"),
}
B_CF_LID = {
    89: ("Jonah leans in to look at the dye front through the closed lid.", "leans in to study the dye front through the closed lid"),
    90: ("Jonah points at the gel through the lid, counting the dye bands.", "counts the dye bands through the lid"),
    91: ("Jonah tilts his head to read the lane numbers through the lid.", "tilts his head to read the lane numbers through the lid"),
    92: ("Jonah presses Stop; the display goes dark.", "presses Stop, and the display goes dark"),
    93: ("Jonah unplugs both leads from the power supply and lifts the lid off the tank.", "pulls both cables out of the power pack and lifts the lid off"),
}
B_SCF_APPROVED = {
    25: ("Jonah turns the tube to read its label, then the supervisor's note taped round it, and nods.", "reads the tube's label and then the supervisor's note taped round it, and nods",
         "The flask is standing on the cork ring; nobody is holding it.", "Nobody is touching the flask on its cork ring."),
    26: ("Felix: 'That's the tube Ruth tested on Monday. It's fine.'", "hears Felix confirm that this is the tube the supervisor tested on Monday",
         "Jonah is holding the SYBR Safe tube.", "Jonah holds the SYBR Safe tube."),
    27: ("Jonah flicks the tube to bring the liquid down and stands it in the rack.", "flicks the tube and stands it in the rack"),
    28: ("Felix goes back to his bench to label plates.", "watches Felix go back to labelling plates"),
    29: ("Jonah points the infrared thermometer at the flask.", "checks the flask with the infrared thermometer"),
    31: ("Jonah reads the flask temperature again and checks that the tube's cap is tight.", "rechecks the flask's temperature and makes sure the tube's cap is tight"),
    32: ("Jonah draws 10 µL of SYBR Safe from the tube into the pipette and brings the tip to the neck of the flask.", "draws 10 microlitres of SYBR Safe from the tube into the pipette and brings it to the neck of the flask"),
}


class GelTrainee(Scenario):
    family = FAMILY
    scenario_id = "procedure_b"
    title = "Coaching a lab trainee through TAE buffer and an agarose gel run"
    tier = "hard"
    difficulty_features = [
        "two_questions_per_decision",
        "six_action_options",
        "ten_way_target_step",
        "six_rule_priority_policy",
        "priority_conflicts",
        "implicit_facts",
        "value_vs_protocol_comparison",
        "earliest_deviation_target",
        "expiry_date_comparison",
        "timer_vs_protocol_time",
        "correct_then_rollback_same_deviation",
        "corrected_deviation_clears",
    ]
    decision_structures = ["maintain", "advance", "wait", "recover", "rollback", "escalate", "resolve-conflict", "terminate"]
    deadline_steps = 2

    TICK_SECONDS = 45
    START = 14 * 3600  # 14:00:00
    LAST = 9
    # Timed steps and the protocol time in seconds; timer runs (first tick, last tick).
    TIMED = {5: 900, 8: 900}
    SET_RUN = (33, 55)
    ELECTRO_RUN = (69, 91)
    # Log lines are stamped when the logged event happened. Both timers were
    # started, and the set timer beeped at 15:00, 30 s before the snapshot
    # that first shows them (reading 0:30 and 15:30); every other line is
    # stamped at its own snapshot.
    LOG_OFFSET_S = {33: -30, 53: -30, 69: -30}
    # SYBR Safe lot numbers (texture only): the old tube in drawer 3 and the new
    # lot from the cold room. Their expiry months and today's date, which rule 2
    # compares, are latent facts (`tube_expiry`, `today`).
    LOTS = {"old": "2291", "new": "3160"}
    TEMPS = {24: 84, 25: 80, 26: 76, 27: 72, 28: 69, 29: 66, 30: 63, 31: 61, 32: 58}

    # ---------------------------------------------------------------- questions
    def questions(self, variant: str) -> list[Any]:
        if variant == "paraphrase":
            action_q = "Work down the rules and stop at the first one that fits. What should you do at this moment?"
            target_q = "Work down the rules and stop at the first one that fits. Which stage, if any, should your words be about at this moment?"
            return [
                Choice("action", {"role": B_ROLE_P, "rules": B_POLICY_P, "question": action_q}, dict(B_ACTIONS_P)),
                Choice("target", {"role": B_ROLE_P, "rules": B_POLICY_P, "question": target_q}, dict(B_TARGETS_P)),
            ]
        actions = B_ACTIONS_D if variant == "lexical_decoy" else B_ACTIONS
        return [
            Choice("action", {"role": B_ROLE, "policy": B_POLICY, "question": "Apply the first rule that matches the current state. What should the coach do right now?"}, dict(actions)),
            Choice("target", {"role": B_ROLE, "policy": B_POLICY, "question": "Apply the first rule that matches the current state. Which protocol step should the coach's message be about right now?"}, dict(B_TARGETS)),
        ]

    # ------------------------------------------------------------------ latent
    def _timer(self, t: int) -> int | None:
        for first, last in (self.SET_RUN, self.ELECTRO_RUN):
            if first <= t <= last:
                return 30 + self.TICK_SECONDS * (t - first)
        return None

    def _canonical(self) -> list[Tick]:
        tl = Timeline(
            {
                "step": 0,
                "progress": "p0_coat",
                "finished": False,
                "timer_s": None,
                "stock_ml": None,
                "agarose_g": None,
                "redo": False,
                "second_try": [],
                "hazard": None,
                "power": "off",
                "lid": "beside",
                "stain": None,
                "tube_expiry": {"old": "2026-08", "new": "2027-03"},
                "today": "2026-09-25",
                "approved": False,
                "temp_c": None,
                "wells": None,
                "volts": None,
            }
        )
        events: dict[int, tuple[dict[str, Any], str]] = {
            0: ({}, "Putting on protective equipment; no numbered step has begun, so there is no current step."),
            1: ({"progress": "p0_gloves"}, ""),
            2: ({"step": 1, "progress": "p1_start"}, "Glasses on; step 1 starts in the same moment."),
            3: ({"progress": "p1_cyl"}, ""),
            4: ({"progress": "p1_water"}, "Felix: the 50x TAE is out. The protocol uses the 10x stock, which is on the shelf and in date."),
            5: ({}, "Agarose jar 'nearly empty' with about 20 g left; the protocol needs 1.0 g."),
            6: ({"progress": "p1_added", "stock_ml": 5}, "5 mL of 10x stock where the protocol says 50 mL: a deviation in the current step, visible only by comparison."),
            7: ({"progress": "p1_mix"}, ""),
            8: ({"progress": "p1_fin", "finished": True}, "Step 1 finished with the wrong amount; it is still the current step (rule 4 over rule 5)."),
            9: ({"step": 2, "progress": "p2_weighed", "finished": False, "agarose_g": 1.5}, "Step 2 under way with 1.50 g of agarose (protocol 1.0 g); the earlier step 1 deviation comes first (rule 3 over rule 4)."),
            10: ({"step": 3, "progress": "p3_b1"}, "Step 2 finished with 1.50 g and step 3 started: steps 1 and 2 both deviate; the earliest is step 1."),
            11: ({"progress": "p3_b2"}, "Still two earlier deviations; rollback targets the earliest, step 1."),
            12: ({"step": 1, "progress": "p1_redo0", "stock_ml": None, "agarose_g": None, "redo": True}, "Jonah redoes step 1; it is the current step again, and only the new attempt counts."),
            13: ({"progress": "p1_redo_water"}, ""),
            14: ({"progress": "p1_redo_added", "stock_ml": 50}, "50 mL this time."),
            15: ({"progress": "p1_redo_mix"}, ""),
            16: ({"step": 2, "progress": "p2_weighed", "agarose_g": 1.0, "redo": False, "second_try": [1, 2]}, "Buffer redone; step 2 again with 1.00 g."),
            17: ({"step": 3, "progress": "p3_b1"}, "Step 2 done; first microwave burst."),
            18: ({"progress": "p3_b2"}, ""),
            19: ({"progress": "p3_b3"}, ""),
            20: ({"progress": "p3_b4"}, "The microwave's 'End' and 'Done!' do not finish step 3: specks remain."),
            21: ({"progress": "p3_fin", "finished": True, "hazard": "hot_flask"}, "Step 3 finished, but the hot flask is held without the heat-resistant glove: rule 1 outranks rule 5."),
            24: ({"step": 4, "progress": "p4_cool", "finished": False, "hazard": None, "stain": "old"}, "Glove on; cooling starts. The only SYBR Safe at hand is labelled EXP 2026-08, before today, and there is no supervisor note."),
            28: ({"stain": "both"}, "An in-date tube (EXP 2027-03) is now at hand."),
            29: ({"stain": "new"}, ""),
            32: ({"progress": "p4_drawn"}, "Flask at 58 °C and the stain drawn up in the pipette, but not in the flask yet: step 4 is not finished."),
            33: ({"step": 5, "progress": None, "stain": None}, "Gel poured; set timer running."),
            36: ({}, "Water spilled by the sink, away from the dry, switched-off power supply."),
            41: ({}, "Doubt about the buffer, but step 1 is recorded as 50 mL (second attempt)."),
            49: ({}, "'Looks set' at 12:30 of 15:00: not finished."),
            52: ({}, "Set timer 14:45: not finished."),
            53: ({}, "Set timer 15:30: step 5 finished; Jonah is writing notes, not on step 6."),
            56: ({"step": 6, "progress": "p6_in", "wells": "red"}, "Gel placed with the wells at the red socket (log only); the protocol says black."),
            57: ({"progress": "p6_pour"}, ""),
            58: ({"progress": "p6_level"}, "Buffer at 4 mm but the wells are still at red: step 6 done differently (rule 4); it is not finished, since its wells are not at black."),
            59: ({"progress": "p6_fixed", "wells": "black", "finished": True}, "Gel turned round and buffer topped up: step 6 is finished and put right, step 7 not started (untimed completion)."),
            60: ({}, "'The tank's sorted'; Jonah is on his phone."),
            62: ({"step": 7, "progress": "p7_l1", "finished": False}, "Loading started."),
            63: ({"progress": "p7_l2"}, "Pipette dial changed from 5 to 10 uL: the ladder is 5, the samples are 10."),
            64: ({"progress": "p7_l4"}, ""),
            65: ({"progress": "p7_l6"}, ""),
            66: ({"step": 8, "progress": "p8_lid", "lid": "on"}, "Loading done; lid closed (step 8 started)."),
            67: ({"progress": "p8_leads"}, ""),
            68: ({"progress": "p8_set", "volts": 120}, ""),
            69: ({"progress": None, "power": "on"}, "Run started at 120 V."),
            72: ({}, "Bubbles at both electrodes are normal per the protocol notes."),
            84: ({}, "'Surely enough' at 11:45 of 15:00: not finished."),
            88: ({}, "Run timer 14:45: not finished."),
            89: ({"lid": "held"}, "Run past 15:00 (15:30), step 9 not started, but the log shows the lid lifted while the display shows the supply running: rule 1 outranks rule 5."),
            92: ({"step": 9, "progress": "p9_off", "power": "off", "lid": "bench", "finished": False}, "Power switched off; step 9 under way."),
            93: ({"progress": "p9_unplug"}, ""),
            94: ({"progress": "p9_out"}, ""),
            95: ({"progress": "p9_imager"}, ""),
            96: ({"progress": "p9_screen"}, ""),
            97: ({"progress": "p9_fin", "finished": True}, "Image saved: the protocol is complete."),
            99: ({}, "Supervisor's praise is not a reason to act."),
        }
        tags = span_tags(
            {
                "distractor": [(4, 5), 20, 36, 41, 49, 63, 72, 84],
                "minimal_change": [6, 56, 89],
                "recovery": [12, 28, 92],
                "hold_under_activity": [(43, 46), (75, 79), (85, 87)],
                "priority_conflict": [(8, 9), (21, 23), (89, 91)],
                "boundary": [(97, 99)],
                "arithmetic": [(6, 11), (24, 27), 49, (52, 55), 84, (88, 91)],
                "implicit": [(56, 58), (89, 91)],
            }
        )
        for t in range(STEPS):
            updates, note = events.get(t, ({}, ""))
            tl.step(dict(B_SCRIPT[t]), tags[t], note, timer_s=self._timer(t), temp_c=self.TEMPS.get(t), **updates)
        return tl.ticks

    def timeline(self, variant: str) -> list[Tick]:
        ticks = self._canonical()
        if variant == "minimal_cf":
            # (1) t36-38: the spilled water runs under the power supply.
            ticks = override(ticks, [36, 37, 38], hazard="spill_psu", note="Spilled water is pooling round the power supply's plug and leads.",
                             surface=lambda tk, i: _b_line(B_CF_SPILL[i]))
            ticks = override(ticks, [39], note="Power supply unplugged, dried and moved; the hazard is over.",
                             surface=lambda tk, i: _b_line(B_CF_SPILL[i]))
            ticks = override(ticks, [48], note="The dried power supply is plugged back in at the wall; it stays switched off.",
                             surface=lambda tk, i: _b_line(B_CF_SPILL[i]))
            # (2) t68-70: the dial is set to 210 V instead of 120 V.
            ticks = override(ticks, [68, 69, 70], volts=210, note="Voltage set to 210 V; the protocol says 120 V.",
                             surface=lambda tk, i: _b_line(B_CF_VOLTS[i]))
            ticks = override(ticks, [71], note="Dial turned down to 120 V: the difference has been put right.",
                             surface=lambda tk, i: _b_line(B_CF_VOLTS[i]))
            # (3) t89-91: Jonah looks through the closed lid instead of lifting it.
            ticks = override(ticks, [89, 90, 91, 92], lid="on", surface=lambda tk, i: _b_line(B_CF_LID[i]))
            ticks = override(ticks, [93], surface=lambda tk, i: _b_line(B_CF_LID[i]))
            for t in (89, 90, 91):
                ticks[t].note = "Run past 15:00 with the lid on; step 9 not started."
            ticks[92].note = "Power switched off; step 9 under way."
            ticks = _set_tags(ticks, {
                36: ["minimal_change"], 37: [], 38: [], 39: ["recovery"],
                68: ["minimal_change", "arithmetic"], 69: ["arithmetic"], 70: ["arithmetic"], 71: ["recovery"],
                89: ["minimal_change", "arithmetic"], 90: ["arithmetic"], 91: ["arithmetic"],
            })
        elif variant == "structural_cf":
            # The supervisor tested the out-of-date SYBR Safe on Monday and left a
            # written go-ahead this morning, so rule 2 never fires: t24-27 become
            # stay quiet while the flask cools, and the old tube is used.
            ticks = [copy.deepcopy(tk) for tk in ticks]
            for tk in ticks:
                tk.latent["approved"] = True
            ticks = override(ticks, [28, 29, 30, 31, 32], stain="old")
            ticks = override(ticks, sorted(B_SCF_APPROVED), surface=lambda tk, i: _b_line(B_SCF_APPROVED[i]))
            for t in (24, 25, 26, 27):
                ticks[t].note = "The stain tube is past its date, but the supervisor's written approval is on file: rule 2 does not apply."
            ticks[28].note = "Cooling continues; the approved tube stays in use."
            ticks[29].note = ""
            ticks = _set_tags(ticks, {24: ["recovery", "arithmetic"], 28: []})
        return ticks

    # ------------------------------------------------------------------ policy
    @staticmethod
    def _expired(z: dict[str, Any], tube: str) -> bool:
        """A tube labelled 'EXP YYYY-MM' is past its date once that month is over."""
        return z["tube_expiry"][tube] < z["today"][:7]

    def _blocked(self, z: dict[str, Any]) -> bool:
        """Rule 2: the current step needs a reagent that is expired, with no in-date replacement at hand and no approval."""
        if z["step"] != 4 or z["stain"] is None:
            return False
        at_hand = ["old", "new"] if z["stain"] == "both" else [z["stain"]]
        return all(self._expired(z, tube) for tube in at_hand) and not z["approved"]

    @staticmethod
    def _deviations(z: dict[str, Any]) -> set[int]:
        """Steps whose current recorded amount, orientation or setting differs from the protocol text.

        Values that have been put right (or poured away for a redo) are no
        longer in the latent state, so this is rule 4's 'not since put right'.
        """
        out: set[int] = set()
        if z["stock_ml"] is not None and z["stock_ml"] != 50:
            out.add(1)
        if z["agarose_g"] is not None and z["agarose_g"] != 1.0:
            out.add(2)
        if z["wells"] is not None and z["wells"] != "black":
            out.add(6)
        if z["volts"] is not None and z["volts"] != 120:
            out.add(8)
        return out

    def _finished(self, z: dict[str, Any]) -> bool:
        step = z["step"]
        if step in self.TIMED and z["timer_s"] is not None:
            return z["timer_s"] >= self.TIMED[step]
        return z["finished"]

    @staticmethod
    def _unsafe(z: dict[str, Any]) -> bool:
        return z["hazard"] is not None or (z["power"] == "on" and z["lid"] != "on")

    def policy(self, z: dict[str, Any]) -> dict[str, Any]:
        step = z["step"]
        deviations = self._deviations(z)
        earlier = sorted(s for s in deviations if s < step)
        if self._unsafe(z):
            action, target = "safety", "none"
        elif self._blocked(z):
            action, target = "escalate", f"step{step}"
        elif earlier:
            action, target = "rollback", f"step{earlier[0]}"
        elif step in deviations:
            action, target = "correct", f"step{step}"
        elif step >= 1 and self._finished(z) and step < self.LAST:
            action, target = "prompt_next", f"step{step + 1}"
        else:
            action, target = "wait", "none"
        return {"action": action, "target": target}

    def construction(self, variant: str) -> dict[str, Any]:
        return {
            "canonical": {"summary": "Gel session. Protective equipment is a precondition, then nine numbered steps. Gold (action/target): wait t0-5 (no current step at t0-1); correct/1 t6-8 (5 mL of 10x stock, protocol 50 mL; step 1 finished at t8, rule 4 over rule 5); rollback/1 t9-11 (step 2 done with 1.50 g of agarose and step 3 started: two earlier deviations, the earliest is step 1); wait t12-20 (steps 1 and 2 redone, microwaving; 'End'/'Done!' with specks at t20); safety t21-23 (hot flask held in nitrile gloves; step 3 finished, rule 1 over rule 5); escalate/4 t24-27 (only stain tube at hand labelled EXP 2026-08, today 25 Sep 2026, no supervisor note); wait t28-52 (new tube; stain; gel setting; spill by the sink t36; buffer doubt t41; 'looks set' at 12:30 t49); prompt/6 t53-55 (set timer at 15 min 30 s to 17 min); correct/6 t56-58 (log: wells next to the red socket); prompt/7 t59-61 (comb out, gel turned round and topped up to about 4 mm, so step 6 is finished and put right; Jonah chats instead of loading); wait t62-88 (loading; run; bubbles t72; supervisor visit t75-79; 'surely enough' at 11:45 t84); safety t89-91 (log: lid lifted while the display shows 120 V and current; run past 15:00: rule 1 over rule 5); wait t92-99 (switch off, image; complete at t97)."},
            "paraphrase": {"summary": "Same latent trajectory; one narrated paragraph with stage/concentrate/power-pack vocabulary (current and previous observation, bench, clock, progress summary, printout), reworded role, rules, questions, action options and stage options."},
            "lexical_decoy": {"summary": "Same latent trajectory; irrelevant lab chatter, notices and emails borrowing a wrong action's vocabulary (Felix lines only while he is in the lab), blended into the bench line or the log, with an occasional second line from any pool; action options lightly reworded."},
            "minimal_cf": {"summary": "Three edits of one decision fact each: t36-38 the spilled water runs under the power supply (wait->safety/none, dried at t39); t68-70 the dial is set to 210 V (wait->correct/8; turned down, so put right, at t71); t89-91 Jonah looks through the closed lid (safety/none->prompt_next/9)."},
            "structural_cf": {"summary": "The supervisor tested the out-of-date SYBR Safe on Monday and left written approval this morning (shown in the notes at every tick). Rule 2 never fires: t24-27 become wait/none, and the approved old tube is used through t32."},
        }.get(variant, {})

    # ------------------------------------------------------------------ render
    def _complete(self, z: dict[str, Any]) -> bool:
        return z["step"] == self.LAST and z["finished"]

    @staticmethod
    def _fill(text: str, z: dict[str, Any]) -> str:
        agarose = f"{z['agarose_g']:.2f}" if z["agarose_g"] is not None else ""
        return text.format(stock=z["stock_ml"], agarose=agarose, wells=z["wells"])

    def _ppe_status(self, z: dict[str, Any], reg: int) -> str:
        if z["step"] == 0:
            return B_PROGRESS[z["progress"]][reg]
        return ("done", "all on")[reg]

    def _status(self, z: dict[str, Any], i: int, reg: int) -> str:
        """Status mark of protocol step i; reg 0 = canonical wording, 1 = paraphrase."""
        step = z["step"]
        if self._complete(z) or i < step:
            text = self._fill(B_DONE[i][reg], z)
            if i in z["second_try"]:
                text += (" (second attempt)", " (on the second try)")[reg]
            return text
        if i > step:
            if z["redo"] and i in (2, 3):
                return ("not started; the first flask was poured away", "not begun, the first flask having been emptied")[reg]
            return ("not started", "not begun")[reg]
        prefix = ("current: ", "in hand, ")[reg]
        if i in self.TIMED and z["timer_s"] is not None:
            # Elapsed time, never a clock look-alike: '15 min 30 s' / '15:30 elapsed'.
            timer = (dur(z["timer_s"]), mmss(z["timer_s"]))[reg]
            if i == 5:
                return prefix + (f"gel in the casting tray with the comb in; set timer at {timer}", f"the gel in its casting tray round the comb, {timer} elapsed on the set timer")[reg]
            return prefix + (f"run under way, black lead in black and red in red; run timer at {timer}",
                              f"running with black cable to black and red to red, {timer} elapsed on the run timer")[reg]
        return prefix + self._fill(B_PROGRESS[z["progress"]][reg], z)

    @staticmethod
    def _date(z: dict[str, Any], reg: int) -> str:
        """Today's date from the latent: 'Fri 25 Sep 2026' or 'Friday 25 September 2026'."""
        return datetime.date.fromisoformat(z["today"]).strftime(("%a %d %b %Y", "%A %d %B %Y")[reg])

    def _stain_line(self, z: dict[str, Any], reg: int) -> str:
        old_lot, new_lot = self.LOTS["old"], self.LOTS["new"]
        old_label, new_label = (f"EXP {z['tube_expiry'][tube]}" for tube in ("old", "new"))
        if z["stain"] == "old":
            text = (f"SYBR Safe tube at hand: lot {old_lot}, label '{old_label}'; there is no other SYBR Safe tube at the bench.",
                    f"The only SYBR Safe on the bench is lot {old_lot}, printed '{old_label}'.")[reg]
            if z["approved"]:
                text += (" Dr. Adeyemi's note is taped round it.", " The supervisor's note is taped round it.")[reg]
            return text
        if z["stain"] == "both":
            return (f"SYBR Safe tubes at hand: the old one (lot {old_lot}, '{old_label}') and a sealed new one from the cold room (lot {new_lot}, '{new_label}').",
                    f"Two SYBR Safe tubes are on the bench now: the old lot {old_lot} ('{old_label}') and a sealed lot {new_lot} from the cold room ('{new_label}').")[reg]
        return (f"SYBR Safe tube in use: lot {new_lot}, label '{new_label}'.",
                f"The SYBR Safe in use is lot {new_lot}, printed '{new_label}'.")[reg]

    def _bench(self, z: dict[str, Any], t: int, extra: str | None, reg: int) -> str:
        step = z["step"]
        parts: list[str] = []
        if z["hazard"] == "hot_flask":
            parts.append(pick(
                [
                    ["Jonah is holding the flask straight from the microwave in nitrile gloves only; the heat-resistant glove hangs on its hook.",
                     "The just-microwaved flask is in Jonah's hand, and he is wearing only nitrile gloves; the heat-resistant glove is on its hook."],
                    ["Jonah has the flask fresh out of the microwave in his hand with nothing but nitrile gloves on; the heat-proof mitt is still on its hook."],
                ][reg], "b-hot", t))
        elif z["hazard"] == "spill_psu":
            # The power supply is off throughout the spill; the sentence says so.
            parts.append(pick(
                [
                    ["Water from the wash bottle has run under the switched-off power supply and is pooling round its plug and leads.",
                     "The spilled water has reached the power supply, which is switched off: its plug and leads are sitting in the puddle."],
                    ["The spilled water has crept under the power pack, which is off, and is pooling round its plug and cables."],
                ][reg], "b-spill", t))
        if z["power"] == "on":
            ma = 93 if z["volts"] == 210 else 52 + t % 4
            parts.append((f"Power supply display: {z['volts']} V, {ma} mA, run time {dur(z['timer_s'])}.",
                          f"The power pack's readout shows {z['volts']} V and {ma} mA with {mmss(z['timer_s'])} elapsed.")[reg])
            # While the power supply is on, a closed lid is stated at every
            # tick. A lifted lid is conveyed by the log (render checks that a
            # log line in view mentions the lid); the bench then gives a
            # neutral tank sentence in the lid sentence's place.
            if z["lid"] == "on":
                parts.append(pick([["Tank lid: closed.", "The tank lid is on.", "The lid is shut on the tank."],
                                   ["The tank's cover is in place.", "The cover sits shut on the tank."]][reg], "b-lidon", t))
            else:
                parts.append(("Tank: both leads plugged in, buffer over the gel.",
                              "Both cables are plugged into the tank, and buffer covers the gel.")[reg])
        elif z["hazard"] != "spill_psu":
            if step == 8:
                dial = (f"; voltage dial at {z['volts']} V", f", its dial turned to {z['volts']} V")[reg] if z["volts"] else ""
                parts.append((f"Power supply: off and dry{dial}.", f"The power pack is off and dry{dial}.")[reg])
            elif step == 9:
                parts.append(("Power supply: switched off and dry, display dark.", "The power pack is off and dry, its readout dark.")[reg])
            else:
                parts.append(pick(
                    [
                        ["Power supply: off, at the far end of the bench, and dry.",
                         "The power supply is switched off, and the bench around it is dry.",
                         "Power supply off and dry, its leads coiled beside it."],
                        ["The power pack sits switched off and dry at the far end of the bench.",
                         "The power pack is off, and the bench around it is dry."],
                    ][reg], "b-psu", t))
            if 6 <= step <= 8:
                parts.append((("Tank lid: closed.", "Tank lid: beside the tank.")[z["lid"] != "on"],
                              ("The tank's cover is on.", "The tank's cover lies on the bench beside the tank.")[z["lid"] != "on"])[reg])
        if step == 1:
            parts.append(("10x TAE stock on the shelf: about 700 mL left, label 'EXP 2027-01'.",
                          "The 10x TAE concentrate on the shelf has about 700 mL left and is printed 'EXP 2027-01'.")[reg])
        elif step == 2:
            parts.append(("Agarose jar: about 20 g left.", "The agarose jar still holds about 20 g.")[reg])
        elif step == 4:
            parts.append((f"Flask temperature: {z['temp_c']} °C.", f"The flask reads {z['temp_c']} degrees.")[reg])
            parts.append(self._stain_line(z, reg))
        if extra:
            parts.append(extra)
        return " ".join(parts)

    def _b_decoy_track(self, history: list[Tick]) -> list[tuple[list[str], list[str]]]:
        """Decoy lines of every tick so far, each split into (bench lines, log lines).

        A tick's lines never repeat a line of the two ticks before it, whose
        log entries appear in the same state. Tick k's lines depend only on
        ticks 0..k, so they stay the same as the history grows.
        """
        track: list[tuple[list[str], list[str]]] = []
        for k, tk in enumerate(history):
            gold = self.policy(tk.latent)["action"]
            felix = _b_felix_present(k)
            recent = {d for bench, log in track[-2:] for d in bench + log}
            lines, first_in_bench = _decoy_lines(B_DECOYS, gold, k, "b",
                                                 lambda d: (felix or "Felix" not in d) and d not in recent)
            track.append(([lines[0]], lines[1:]) if first_in_bench else (lines[1:], [lines[0]]))
        return track

    @staticmethod
    def _check_lid_in_view(history: list[Tick], lines: list[str]) -> None:
        """A lifted lid while the power supply is on is conveyed by the log (or,
        in the paraphrase, by the current and previous observation); refuse to
        render such a tick unless one of the observations in view mentions the lid."""
        z = history[-1].latent
        if z["power"] == "on" and z["lid"] != "on" and not any("lid" in line.lower() for line in lines):
            raise ValueError(f"t{len(history) - 1}: the lid is off while the power is on, but no observation in view mentions it")

    def _log(self, history: list[Tick], track: list[tuple[list[str], list[str]]] | None) -> list[str]:
        t = len(history) - 1
        self._check_lid_in_view(history, [history[k].surface["log"] for k in range(max(0, t - 2), t + 1)])
        out = []
        for k in range(max(0, t - 2), t + 1):
            line = history[k].surface["log"]
            if track is not None:
                line = " ".join([line] + track[k][1])
            stamp = clock(self.START, self.TICK_SECONDS * k + self.LOG_OFFSET_S.get(k, 0))
            out.append(f"{stamp} {line}")
        return out

    def render(self, history: list[Tick], variant: str) -> Any:
        tick = history[-1]
        z = tick.latent
        t = len(history) - 1
        if variant == "paraphrase":
            return self._render_paraphrase(history)
        protocol = [f"{B_PPE} [{self._ppe_status(z, 0)}]"]
        protocol += [f"{i}. {B_STEPS[i]} [{self._status(z, i, 0)}]" for i in B_STEPS]
        if self._complete(z):
            protocol.append("All nine steps are done.")
        track = self._b_decoy_track(history) if variant == "lexical_decoy" else None
        bench = self._bench(z, t, tick.surface.get("bench"), 0)
        if track is not None:
            bench = " ".join([bench] + track[t][0])
        return {
            "time": f"{self._date(z, 0)}, {clock(self.START, self.TICK_SECONDS * t)}",
            "protocol": protocol,
            "notes": f"{B_NOTES} {B_APPROVAL if z['approved'] else B_NO_APPROVAL}",
            "bench": bench,
            "log": self._log(history, track),
        }

    def _progress_p(self, z: dict[str, Any]) -> str:
        """Paraphrase register: one summary of the protective kit, completed stages, the stage in hand and the rest."""
        step = z["step"]
        if step == 0:
            return f"he is still getting his kit on ({self._ppe_status(z, 1)}), and no numbered stage has begun"
        complete = self._complete(z)
        last_done = self.LAST if complete else step - 1
        clauses = ["coat, gloves and goggles are on"]
        if last_done >= 1:
            recs = [self._fill(B_DONE_P[i], z) + (", on the second try" if i in z["second_try"] else "")
                    for i in range(1, last_done + 1) if i in B_DONE_P]
            head = {1: "stage 1 is complete", 2: "stages 1 and 2 are complete"}.get(last_done, f"stages 1 to {last_done} are complete")
            clauses.append(head + (" (" + "; ".join(recs) + ")" if recs else ""))
        elif not self._finished(z):
            # Stage 1 is in hand. Once it is finished (t8) the stage-in-hand
            # clause says so, and 'no stage is complete' would contradict it.
            clauses.append("no stage is complete yet")
        if complete:
            return "; ".join(clauses) + ", which is every stage on the printout"
        clauses.append(f"stage {step} is {self._status(z, step, 1)}")
        if step < self.LAST:
            if step == self.LAST - 1:
                rest = f"stage {self.LAST} has"
            elif step == self.LAST - 2:
                rest = f"stages {step + 1} and {self.LAST} have"
            else:
                rest = f"stages {step + 1} to {self.LAST} have"
            clauses.append(f"{rest} not begun" + (", the first flask having been emptied" if z["redo"] else ""))
        return "; ".join(clauses)

    def _render_paraphrase(self, history: list[Tick]) -> str:
        tick = history[-1]
        z = tick.latent
        t = len(history) - 1
        self._check_lid_in_view(history, [tk.surface["gist"] for tk in history[-2:]])
        parts = [f"Right now Jonah {tick.surface['gist']}."]
        if t >= 1:
            parts.append(f"(Previous update: Jonah {history[t - 1].surface['gist']}.)")
        parts.append(self._bench(z, t, tick.surface.get("bench_p"), 1))
        parts.append(f"The clock says {clock(self.START, self.TICK_SECONDS * t)} on {self._date(z, 1)}.")
        parts.append("Progress: " + self._progress_p(z) + ".")
        parts.append("For reference, the printout asks for " + B_PPE_P + ", and its nine stages read: "
                     + "; ".join(f"({i}) {B_STEPS_P[i]}" for i in B_STEPS_P) + ".")
        parts.append(B_NOTES_P)
        parts.append(B_APPROVAL_P if z["approved"] else B_NO_APPROVAL_P)
        return " ".join(parts)


SCENARIOS = [HomeRisotto, GelTrainee]
