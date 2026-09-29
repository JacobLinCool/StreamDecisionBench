"""Dialogue Intervention: an AI participant in a live human conversation decides whether and how to speak.

Both scenarios share one latent vocabulary: what is waiting for the assistant
(a question or request addressed to it), what has gone wrong in the
conversation (a wrong fact, an argument, someone left out), who is in charge
(the human organiser or teacher) and a clock. They differ in difficulty:

* ``dialogue_a`` (medium) - Scout, the assistant in a friends' group chat that
  is planning a weekend trip. One choice question with six actions and a
  six-rule priority policy. Facts are explicit; one rule needs a minute
  subtraction, and a stated grocery total needs one multiplication to check.
* ``dialogue_b`` (hard) - Kit, a teaching-assistant bot in an online maths
  study room with three students and a teacher who comes and goes. Three
  questions per decision (categorised action, whom to address, whether to
  notify the teacher privately). Several facts are implicit: who has gone
  quiet (timestamp subtraction), whether a student feels left out, whether the
  teacher is explaining (her activity is described, not labelled), how many
  wrong answers were entered; a line put to Kit as 'hey bot' must be read as
  direct address (the role names that form).

Both roles declare a closed-world convention for the chat window: it always
reaches back far enough to show every earlier line a rule still depends on
(``_window_start`` extends it to the start of an unresolved argument, a waiting
question or request, an unaddressed remark about feeling left out, or the tick
before an off-topic stretch began), so nothing before it matters.

The assistant's own messages never appear in the stream (the trajectory is
open loop). Instructions therefore say that the assistant's own actions never
change the state, so it decides as if it had not acted yet, and that a
question to the assistant stays waiting until a human answers or withdraws it.
"""

from __future__ import annotations

import copy
from typing import Any

from streamdecisionbench.authoring import Choice, Noul, Scenario, Tick, Timeline, override, pick, seeded, span_tags

FAMILY = "dialogue_intervention"


def listing(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def check_cf_notes(scenario: Scenario, variant: str, ticks: list[Tick]) -> None:
    """Refuse a counterfactual tick whose gold differs from canonical but whose hidden note was copied unchanged."""
    if variant not in ("minimal_cf", "structural_cf"):
        return
    for t, (base, tick) in enumerate(zip(scenario._canonical(), ticks)):  # type: ignore[attr-defined]
        if tick.note and tick.note == base.note and scenario.policy(tick.latent) != scenario.policy(base.latent):
            raise ValueError(f"{scenario.scenario_id}/{variant} t={t}: stale canonical note {tick.note!r}")


# ===========================================================================
# Scenario A - trip-planning group chat, one question, six actions
# ===========================================================================

A_ROLE = (
    "You are Scout, the trip assistant in a group chat of five friends (Maya, Leo, Priya, Sam and Jonas) who are "
    "planning a weekend on Holm Island. Maya is the organiser. `pinned_trip_facts` holds the booking details; an item "
    "marked pending is not known yet. `pinned_open_decisions` is Maya's list of undecided items and the time the last "
    "decision was settled; an item counts as settled only once Maya takes it off this list. `pinned_settings` holds the "
    "chat settings. `messages` are the latest messages, oldest first, each with its time; they always reach back far "
    "enough to include every earlier message that still matters (such as a question or request to Scout that is still "
    "waiting, a wrong trip detail nobody has corrected yet, or the start of an argument), so nothing said before them "
    "matters now. Scout's own messages are never "
    "shown and never change the state: decide from the state as it is now, as if Scout had not yet acted on anything in "
    "it. So a question or request to Scout counts as waiting until a member answers it or withdraws it. A message is "
    "addressed to Scout only if it speaks to Scout directly ('@Scout ...', 'Scout, ...'); talking about Scout does not count."
)
A_POLICY = [
    "1. If members are in an unresolved argument with each other, about money (who paid or who owes what) or a personal quarrel, and Maya has not said she will deal with it, hand the thread to Maya. An argument starts as soon as one member rejects another member's accusation, and it stays unresolved until they settle it or Maya says she will deal with it, even if the chat moves on to other things. Jokes and disagreements about plans (food, activities) do not count.",
    "2. Otherwise, if a member has stated a trip detail (a time, place, price or amount) that contradicts `pinned_trip_facts` and no member has corrected it since, correct it.",
    "3. Otherwise, if a question or request about a trip detail is addressed to Scout and waiting, and `pinned_trip_facts` contains the answer, answer it.",
    "4. Otherwise, if a question or request about a trip detail is addressed to Scout and waiting (asking Scout to pass a detail on once it is known counts), and `pinned_trip_facts` marks that detail as pending, tell the group Scout will come back with it later.",
    "5. Otherwise, post a recap of the open decisions if either (a) a member has asked Scout for such a recap and the request is waiting, or (b) `pinned_settings` allow Scout to post recaps on its own, `pinned_open_decisions` lists 3 or more open items, and 20 minutes or more have passed since the settled time shown in `pinned_open_decisions`.",
    "6. Otherwise, stay silent.",
]
A_QUESTION = (
    "Apply the first rule that matches the current state. A request for a recap of the open decisions falls under "
    "rule 5, not rules 3-4. What should Scout do right now?"
)

A_ROLE_P = (
    "Scout is an AI helper sitting in a messaging group where five friends are arranging a weekend away on Holm Island: "
    "Maya, who organises, plus Leo, Priya, Sam and Jonas. The description below gives the booking note pinned in the "
    "group (anything described as not known yet is still unknown), Maya's pinned list of points nobody has agreed on "
    "yet together with the most recent point that was agreed and when, the group's pinned settings, and what people "
    "have written lately, going back far enough to take in everything earlier that still matters (anything asked of "
    "Scout that is still open, a mistaken trip detail nobody has put right yet, the start of any quarrel), so nothing "
    "written before that is relevant any more. A point "
    "only counts as agreed once Maya's list no longer holds it. Posts by Scout itself are "
    "left out and change nothing, so Scout should judge the situation exactly as described, as though it had done "
    "nothing about any of it so far; anything asked of Scout stays open until one of the friends answers it or takes "
    "it back. Only a message that talks to Scout directly is aimed at Scout; mentioning Scout in passing is not."
)
A_POLICY_P = [
    "1. When two or more of the friends are quarrelling and it is not settled, whether over money (who has paid, who still owes) or over something personal, and Maya has not said she will sort it out, pass the conversation to Maya. A quarrel begins the moment one friend pushes back against another's accusation, and it stays unsettled until they make it up or Maya says she will sort it out, even if the talk has turned to other things. Teasing and differences of opinion about the plans (food, activities) are not quarrels.",
    "2. Failing that, when someone has given a detail of the trip (a time, place, price or amount) that clashes with the pinned booking note and nobody has put it right since, set the record straight.",
    "3. Failing that, when a friend has put a question or request about the trip straight to Scout, it is still open, and the pinned booking note has the answer, give the answer.",
    "4. Failing that, when a friend has put a question or request about the trip straight to Scout, it is still open (asking Scout to pass a detail on once it is known counts too), and the pinned booking note lists that detail as not known yet, promise to follow up once it is known.",
    "5. Failing that, share an overview of the points not yet agreed when either (a) someone has asked Scout for that overview and the request is still open, or (b) the pinned settings let Scout share it unprompted, Maya's list holds at least 3 points, and at least 20 minutes have gone by since the time Maya's list gives for the most recent agreed point.",
    "6. In all other cases, say nothing.",
]
A_QUESTION_P = (
    "Work down the list and act on the first point that fits. Asking Scout for an overview of what is undecided belongs "
    "to point 5, not points 3 and 4. What is the right move for Scout at this moment?"
)

A_OPTIONS = {
    "silent": "Stay silent and let the members keep talking.",
    "answer": "Reply with the trip detail the member asked Scout for.",
    "correct": "Point out the wrong trip detail and give the pinned one.",
    "summary": "Post a short recap listing the decisions still open.",
    "defer": "Say Scout will come back once the missing detail arrives.",
    "handoff": "Ask Maya to take over the thread from here.",
}
A_OPTIONS_P = {
    "silent": "Keep quiet and leave the conversation to the friends.",
    "answer": "Give the asker the booking information they wanted.",
    "correct": "Flag the mistaken booking information and state the right version.",
    "summary": "Share an overview of the points nobody has agreed yet.",
    "defer": "Promise to follow up when the unknown information comes in.",
    "handoff": "Pass the conversation over to the organiser to handle.",
}

A_MEMBERS = "Maya (organiser), Leo, Priya, Sam, Jonas"

# Decision-irrelevant previews from other chats Scout serves, keyed by the wrong
# action whose vocabulary they borrow (lexical_decoy only). The majority action
# (silent) is never a decoy target: silent-vocabulary decoys could then only
# appear on minority ticks and would flag them. Each decoy borrows a few of the
# option's content words in its own clause shape instead of copying the option.
A_DECOYS = {
    "answer": [
        "Book club: Ana's question about June's meeting room got a reply from her sister, who had the detail.",
        "Cousins' chat: the member discount detail Lena asked about is on the back of the reply card.",
    ],
    "correct": [
        "Quiz league: the pinned score sheet has a wrong total, and the captain will point it out on Friday.",
        "Choir group: Ruth spotted a wrong date in the pinned rota and will give everyone the new one on Sunday.",
    ],
    "summary": [
        "Book club: the recap Ana wrote still had three decisions about the June meeting open.",
        "Flat-share chat: Kemi already posted a short list of what is still open about the new sofa.",
    ],
    "defer": [
        "Allotment chat: the water rota goes back on the agenda once the council's missing letter arrives.",
        "Cycling club: Dev will come back to the Sunday route once the missing map arrives from the club.",
    ],
    "handoff": [
        "Five-a-side chat: Tom is taking over the kit thread now that he's captain.",
        "School parents' group: the organiser will take over the bake-sale thread from here.",
    ],
}
# For each gold action, the wrong actions whose vocabulary a decoy borrows.
A_DECOY_TARGETS = {
    "silent": ["answer", "correct", "summary", "defer", "handoff"],
    "answer": ["defer", "correct", "summary"],
    "correct": ["answer", "defer", "handoff"],
    "summary": ["answer", "defer", "handoff"],
    "defer": ["answer", "summary", "correct"],
    "handoff": ["defer", "correct", "summary"],
}

# One entry per tick (about one minute of chat): the messages posted in that
# burst and a reported-speech gist used by the paraphrase register. Every
# decision-relevant fact is also held in the latent state; the messages only
# corroborate it.
A_SCRIPT: list[tuple[list[tuple[str, str]], str]] = [
    # t0-t11: planning starts; the driver is settled at t5
    ([("Maya", "Right, planning night! Four things are still open, they're pinned. Let's close some tonight 💪"), ("Leo", "evening all 👋")],
     "Maya opens the planning evening and points to the four undecided items in the pinned list; Leo says hello"),
    ([("Priya", "here! just got home, eating noodles while I type"), ("Sam", "same energy 🍜")],
     "Priya checks in while eating noodles and Sam says he is doing the same"),
    ([("Jonas", "can we start with the drive? my car's in the garage till Monday"), ("Maya", "ok, who can drive us to North Pier?")],
     "Jonas explains his car is in the garage, and Maya asks who can drive the group to North Pier"),
    ([("Sam", "does the cabin have a grill btw? Scout found the place so it's probably in the listing somewhere")],
     "Sam wonders aloud \"does the cabin have a grill btw?\", adding that since Scout found the place it is probably in the listing"),
    ([("Leo", "I can drive, the estate fits five if nobody brings a suitcase the size of a fridge"), ("Priya", "looking at you Sam")],
     "Leo offers to drive the estate car if nobody brings a huge suitcase, and Priya teases Sam about it"),
    ([("Maya", "Leo drives ✅ taking that off the list"), ("Sam", "rude but fair 😂")],
     "Maya marks the driving as settled with Leo at the wheel, and Sam laughs"),
    ([("Priya", "Sam, yes, there's a gas grill on the deck, it's in the pinned note"), ("Sam", "ah perfect")],
     "Priya tells Sam the pinned note lists a gas grill on the deck, and Sam is pleased"),
    ([("Leo", "I'll do the pickups, Priya's place first?"), ("Jonas", "I can walk to Priya's, saves you a stop")],
     "Leo plans the pickups starting at Priya's, and Jonas offers to walk there to save a stop"),
    ([("Maya", "Next: Saturday dinner. BBQ at the cabin or the pizza place by the harbour?"), ("Priya", "BBQ!!")],
     "Maya moves on to Saturday dinner, a barbecue at the cabin or the harbour pizzeria, and Priya votes barbecue"),
    ([("Jonas", "correction: BBQ AND pizza for Saturday dinner. I contain multitudes"), ("Sam", "seconded")],
     "Jonas offers a joking 'correction' that Saturday dinner should be both barbecue and pizza, and Sam backs him"),
    ([("Leo", "the pizza place shuts at 9 on Saturdays I think, BBQ is safer"), ("Maya", "noted")],
     "Leo thinks the pizzeria shuts at nine on Saturdays and leans towards the barbecue; Maya notes it"),
    ([("Priya", "also can we talk about Saturday morning, I need to know when to set my alarm"), ("Maya", "sure")],
     "Priya wants to talk about Saturday morning so she knows when to set her alarm, and Maya agrees"),
    # t12-t14: Leo states a wrong ferry time; Jonas asks Scout about parking at t13
    ([("Leo", "ferry's at 9:40 isn't it? so we can leave town around 8:50, no need for a crazy alarm")],
     "Leo says the boat goes at 9:40 and suggests leaving town around 8:50"),
    ([("Jonas", "@Scout is there parking at North Pier or should Leo just drop us off?"), ("Priya", "8:50 sounds civilised")],
     "Jonas writes \"@Scout is there parking at North Pier or should Leo just drop us off?\", and Priya likes the 8:50 plan"),
    ([("Sam", "wait I can sleep in?? best trip ever"), ("Priya", "setting my alarm for 8:15 then 😴")],
     "Sam is delighted he can sleep in, and Priya says she will set her alarm for 8:15"),
    # t15-t17: Maya corrects the time; the parking question is still waiting
    ([("Maya", "Leo, the ferry is 08:40, not 9:40, check the pinned note! Alarms earlier please 🙃"), ("Priya", "noooo")],
     "Maya tells Leo the boat is at 08:40 rather than 9:40 and asks for earlier alarms; Priya groans"),
    ([("Leo", "oops, my bad, the ferry is 08:40. leaving town at 07:50 then"), ("Sam", "RIP my lie-in")],
     "Leo admits he had the ferry time wrong, accepts 08:40 and moves the departure from town to 07:50; Sam mourns his lie-in"),
    ([("Jonas", "@Scout still wondering about parking at the pier, anyone?")],
     "Jonas writes \"@Scout still wondering about parking at the pier, anyone?\""),
    # t18-t26: Leo answers Jonas; the dinner debate; dinner settled at t24
    ([("Leo", "Jonas, there's a paid car park right next to the terminal, I've used it before"), ("Jonas", "perfect, thanks")],
     "Leo tells Jonas there is a paid car park beside the terminal, and Jonas thanks him"),
    ([("Maya", "ok back to dinner. BBQ vs pizza, votes please"), ("Priya", "BBQ")],
     "Maya calls for dinner votes and Priya votes barbecue again"),
    ([("Sam", "pizza, I don't trust Leo with fire"), ("Leo", "I have burnt exactly one sausage in my life")],
     "Sam votes pizza because he does not trust Leo with fire; Leo protests he has burnt only one sausage"),
    ([("Jonas", "BBQ, and I'll do veggie skewers"), ("Priya", "ooh halloumi")],
     "Jonas votes barbecue and volunteers vegetable skewers; Priya suggests halloumi"),
    ([("Sam", "fine, BBQ, but I'm on sauce duty"), ("Leo", "deal. no pineapple though"), ("Priya", "pineapple on a BBQ is great actually")],
     "Sam gives in to the barbecue if he can do sauces, Leo rules out pineapple, and Priya defends grilled pineapple"),
    ([("Jonas", "the pineapple debate can wait till Saturday 😄"), ("Sam", "agreed")],
     "Jonas cheerfully postpones the pineapple debate to Saturday and Sam agrees"),
    ([("Maya", "Saturday dinner = BBQ at the cabin ✅ off the list"), ("Leo", "🔥")],
     "Maya marks Saturday dinner as settled: a barbecue at the cabin"),
    ([("Priya", "should we bring our own tongs or trust the cabin"), ("Maya", "bring tongs, cabins never have good ones")],
     "Priya wonders about bringing tongs and Maya says to bring them"),
    ([("Sam", "adding tongs to my list of things I'll forget"), ("Leo", "I'll bring mine")],
     "Sam jokes he will forget the tongs, so Leo will bring his"),
    # t27-t30: an argument about the cabin deposit between Jonas and Leo
    ([("Jonas", "also, money: I paid the €90 cabin deposit. Maya, Priya and Sam sent me their €18, Leo you haven't yet"), ("Leo", "I sent you €18 on Monday, stop saying I haven't paid")],
     "Jonas says he paid the €90 deposit and that everyone except Leo has paid him their €18; Leo snaps back that he sent it on Monday and tells Jonas to stop saying he has not paid"),
    ([("Jonas", "nothing arrived from you, I checked twice"), ("Leo", "I have the screenshot. not paying twice, sorry")],
     "Jonas says nothing arrived from Leo, and Leo refuses to pay twice, citing a screenshot"),
    ([("Jonas", "a screenshot isn't money in my account though"), ("Leo", "so now I'm lying?")],
     "Jonas says a screenshot is not money in his account, and Leo asks if he is being called a liar"),
    ([("Jonas", "didn't say that. just saying I'm still €18 short"), ("Leo", "unbelievable")],
     "Jonas denies calling him a liar but repeats he is €18 short, and Leo says it is unbelievable"),
    # t31-t43: Maya takes the deposit issue to a DM; chatter; two items added at t36
    ([("Maya", "Jonas, Leo, I'll sort the deposit out with you two in a DM after this. Let's keep this chat for planning 🙏")],
     "Maya tells Jonas and Leo she will sort out the deposit with them privately later and asks to keep the chat for planning"),
    ([("Priya", "ok. kayaks: who's in?"), ("Sam", "me, if it's not crazy expensive")],
     "Priya asks who wants to go kayaking, and Sam is keen if it is not too expensive"),
    ([("Maya", "I'm in"), ("Priya", "the shop hasn't sent prices yet, right?")],
     "Maya is in for kayaking and Priya checks with the others that the shop has not sent prices yet"),
    ([("Jonas", "found it! Leo's transfer went to my old account. sorry Leo!"), ("Leo", "told you 😌 all good")],
     "Jonas finds Leo's transfer in his old account and apologises, and Leo says all is well"),
    ([("Priya", "lol my sister and her boyfriend had a massive fight about who pays for their holiday, glad we're not like that"), ("Sam", "we literally just were like that, glad it's sorted 😅")],
     "Priya laughs about her sister and her boyfriend fighting over who pays for their holiday, and Sam notes the group nearly did the same and is glad that is sorted"),
    ([("Maya", "adding two things to the list: who brings a speaker, and Sunday breakfast"), ("Jonas", "does a speaker really need a vote 😂")],
     "Maya adds two items to the undecided list, a speaker and Sunday breakfast, and Jonas laughs that a speaker needs a vote"),
    ([("Sam", "weather says 22 degrees on Saturday!"), ("Priya", "swimming then?")],
     "Sam reports a forecast of 22 degrees for Saturday and Priya suggests swimming"),
    ([("Leo", "the lake will be freezing, it's only May"), ("Sam", "that's what wetsuits are for")],
     "Leo warns the lake will be freezing in May, and Sam says that is what wetsuits are for"),
    ([("Jonas", "I don't own a wetsuit. I own a towel"), ("Priya", "towel gang")],
     "Jonas owns only a towel, and Priya declares herself on team towel"),
    ([("Maya", "breakfast idea: pancakes on Sunday?"), ("Sam", "pancakes yes")],
     "Maya floats pancakes for Sunday breakfast and Sam approves"),
    ([("Leo", "who's making them though"), ("Priya", "not me, last time I set off the smoke alarm")],
     "Leo asks who would make the pancakes, and Priya excuses herself after setting off a smoke alarm last time"),
    ([("Sam", "I'll make them if someone else washes up"), ("Maya", "let's keep breakfast open till we know who's up early 😅")],
     "Sam offers to cook if someone else washes up, but Maya wants to leave breakfast undecided until they know who will be up early"),
    ([("Priya", "breakfast: the one thing we'll never decide 😂"), ("Leo", "Sunday-morning us can sort it")],
     "Priya laughs that breakfast is the one thing they will never decide, and Leo leaves it to their Sunday-morning selves"),
    # t44-t50: recap time (unprompted from t44; from t48 only Sam's request keeps it due)
    ([("Sam", "who's bringing the big cool box?"), ("Leo", "mine's in the loft somewhere")],
     "Sam asks who has the big cool box, and Leo says his is somewhere in the loft"),
    ([("Priya", "I have a small one"), ("Jonas", "small one + Leo's = enough?")],
     "Priya has a small cool box and Jonas wonders if hers plus Leo's is enough"),
    ([("Leo", "if I can find it, yes"), ("Sam", "the loft is where things go to die")],
     "Leo says yes if he can find his, and Sam jokes that the loft is where things go to die"),
    ([("Jonas", "going to put the kettle on, back in a bit"), ("Priya", "bring me one")],
     "Jonas steps away to put the kettle on, and Priya asks for a cup"),
    ([("Maya", "kayaks: all five of us are in, so that's settled ✅"), ("Sam", "@Scout can you list what we still haven't decided? I've lost track")],
     "Maya declares kayaking agreed because all five are in, and Sam writes \"@Scout can you list what we still haven't decided? I've lost track\""),
    ([("Leo", "I've lost track too tbh"), ("Priya", "it's been a lot of pineapple talk")],
     "Leo has lost track too, and Priya blames the pineapple talk"),
    ([("Jonas", "back ☕"), ("Priya", "where's mine")],
     "Jonas is back with his tea, and Priya asks where hers is"),
    # t51-t58: Maya answers Sam's request herself; packing chatter; speaker settled at t57
    ([("Maya", "Sam: still open are Sunday lunch, the speaker and Sunday breakfast"), ("Sam", "thank you!")],
     "Maya answers Sam herself: Sunday lunch, the speaker and Sunday breakfast are still undecided"),
    ([("Priya", "yay kayaks btw"), ("Leo", "I will capsize, I've accepted it")],
     "Priya cheers the kayaking and Leo resigns himself to capsizing"),
    ([("Sam", "packing list time? sunscreen, swimsuit, torch"), ("Priya", "board games!")],
     "Sam starts a packing list with sunscreen, swimsuit and torch, and Priya adds board games"),
    ([("Jonas", "cards, and that detective game"), ("Leo", "phone chargers, the listing photos show like two sockets")],
     "Jonas adds cards and a detective game, and Leo adds phone chargers because the photos show few sockets"),
    ([("Priya", "hiking shoes for Saturday morning?"), ("Maya", "yes, the loop trail near the cabin is gorgeous")],
     "Priya suggests hiking shoes for Saturday morning and Maya recommends the loop trail near the cabin"),
    ([("Sam", "rain jackets, it's an island"), ("Jonas", "insect spray!!")],
     "Sam adds rain jackets and Jonas adds insect spray"),
    ([("Maya", "speaker: Jonas brings his ✅"), ("Jonas", "🎶")],
     "Maya settles the speaker question: Jonas will bring his"),
    ([("Leo", "playlist rule: no more than three songs by the same band in a row"), ("Priya", "Sam is sweating")],
     "Leo proposes a playlist rule against more than three songs by one band in a row, and Priya teases Sam"),
    # t59-t64: Priya asks Scout the kayak price, which is still pending
    ([("Priya", "@Scout how much are the kayaks per day?")],
     "Priya writes \"@Scout how much are the kayaks per day?\""),
    ([("Sam", "if it's more than 40 I'm swimming next to you"), ("Leo", "you'd freeze")],
     "Sam says he will swim alongside if the kayaks cost over 40, and Leo says he would freeze"),
    ([("Jonas", "Holm Outdoors usually emails after 8"), ("Maya", "they said tonight at least")],
     "Jonas says the kayak shop usually emails after eight, and Maya says they promised tonight"),
    ([("Priya", "@Scout? kayak price when you can 🙏"), ("Sam", "the suspense")],
     "Priya follows up with \"@Scout? kayak price when you can\", and Sam jokes about the suspense"),
    ([("Leo", "if they're cheap should we get a double for me and Sam"), ("Sam", "absolutely not")],
     "Leo suggests sharing a double kayak with Sam if they are cheap, and Sam refuses"),
    ([("Priya", "Scout, still keen to hear what the kayaks cost 🙏"), ("Jonas", "patience, young grasshopper")],
     "Priya adds \"Scout, still keen to hear what the kayaks cost\", and Jonas counsels patience"),
    # t65-t67: the shop's price reaches the pinned note (20:05) while Priya's question waits
    ([("Sam", "I'm refreshing my inbox like it's concert tickets"), ("Leo", "same")],
     "Sam and Leo joke about refreshing their inboxes like it is a ticket sale"),
    ([("Leo", "if it's cheap I'm getting a single, Sam can fend for himself"), ("Sam", "good")],
     "Leo says he will take a single kayak and Sam is happy with that"),
    ([("Priya", "Scout??? price???"), ("Jonas", "she's not going to let this go")],
     "Priya presses on with \"Scout??? price???\", and Jonas says she will not let it go"),
    # t68-t86: Jonas answers Priya; money and snacks; open chatter
    ([("Jonas", "Priya, it's €25 a day per kayak, it's in the pinned note now"), ("Priya", "oh nice, cheaper than I thought")],
     "Jonas tells Priya the pinned note now says €25 a day per kayak, and she finds it cheaper than expected"),
    ([("Sam", "so one single kayak for Saturday is 25?"), ("Leo", "yep, 25 for the day")],
     "Sam checks that one single kayak for Saturday is 25, and Leo confirms it is 25 for the day"),
    ([("Sam", "groceries: that's €150 for the five of us, send me your share by Friday"), ("Priya", "sending now")],
     "Sam puts the food shopping at €150 for the five of them and asks for everyone's share by Friday; Priya pays at once"),
    ([("Leo", "sent"), ("Jonas", "sent, and I added a tip for your shopping services")],
     "Leo and Jonas send their grocery money, Jonas with a joke tip"),
    ([("Maya", "Sunday lunch: the harbour café or a picnic on the ferry?"), ("Priya", "café, I want chips")],
     "Maya asks whether Sunday lunch should be the harbour café or a picnic on the boat; Priya wants café chips"),
    ([("Sam", "picnic, cheaper"), ("Leo", "café. it's a holiday")],
     "Sam prefers the cheaper picnic and Leo the café"),
    ([("Leo", "Jonas still owes me a coffee for the deposit drama btw 😂"), ("Jonas", "fair, I'll buy you two 😂")],
     "Leo jokes that Jonas owes him a coffee for the deposit mix-up, and Jonas laughingly offers two"),
    ([("Priya", "ok you two being sweet now is disgusting"), ("Maya", "love to see it")],
     "Priya teases Leo and Jonas for being sweet, and Maya is pleased"),
    ([("Sam", "back to lunch: decide on Sunday morning depending on the weather?"), ("Maya", "fine by me, leaving it open")],
     "Sam proposes choosing Sunday lunch on the morning depending on weather, and Maya leaves it open"),
    ([("Priya", "can someone recap the plot of the first film before Saturday's movie night? never saw it"), ("Leo", "a man, a boat, a lot of shouting")],
     "Priya asks the others to recap the first film before Saturday's movie night, and Leo sums it up as a man, a boat and shouting"),
    ([("Sam", "that's every film Leo likes"), ("Jonas", "accurate")],
     "Sam says that describes every film Leo likes, and Jonas agrees"),
    ([("Priya", "snacks list: crisps, popcorn, chocolate"), ("Sam", "and gummy bears")],
     "Priya lists snacks and Sam adds gummy bears"),
    ([("Jonas", "I'm running the detective game on Saturday night, no excuses"), ("Leo", "I will be the murderer")],
     "Jonas will run the detective game on Saturday night, and Leo wants to be the murderer"),
    ([("Maya", "I'll bring fairy lights for the deck"), ("Priya", "cute!!")],
     "Maya will bring fairy lights for the deck and Priya loves the idea"),
    ([("Sam", "hammock?"), ("Leo", "where would we even hang it")],
     "Sam suggests a hammock and Leo wonders where it would hang"),
    ([("Jonas", "between the two pine trees in the listing photos"), ("Priya", "genius")],
     "Jonas points to the two pine trees in the listing photos, and Priya calls it genius"),
    ([("Leo", "I'll bring rope then"), ("Maya", "ok this trip is going to be great")],
     "Leo will bring rope, and Maya says the trip is going to be great"),
    ([("Maya", "Sunday check-out is 11, so let's aim to have the place clean by 10:30"), ("Priya", "ok")],
     "Maya reminds everyone that Sunday check-out is at 11 and asks for the cabin to be clean by 10:30"),
    ([("Sam", "I'll set an alarm 🙃"), ("Leo", "you won't")],
     "Sam promises to set an alarm and Leo doubts it"),
    # t87-t90: Priya and Sam quarrel; Jonas asks Scout about the Sunday return ferry at t88
    ([("Priya", "Sam, please actually turn up this time. You cancelled at midnight before the March trip and we lost the deposit."), ("Sam", "that's not fair, my gran was in hospital and you know that")],
     "Priya tells Sam to actually turn up this time, recalling his midnight cancellation before the March trip; Sam says that is unfair because his grandmother was in hospital"),
    ([("Priya", "you could have told us before midnight though"), ("Jonas", "@Scout sorry to butt in, when's the last ferry back on Sunday? I need to tell my boss")],
     "Priya says Sam could have told them earlier, while Jonas cuts in with \"@Scout sorry to butt in, when's the last ferry back on Sunday?\" because his boss needs to know"),
    ([("Sam", "wow. maybe I just won't come then"), ("Leo", "guys...")],
     "Sam says maybe he just will not come, and Leo tries to calm things"),
    ([("Priya", "see, this is exactly what I mean"), ("Sam", "whatever")],
     "Priya says this is exactly her point, and Sam answers 'whatever'"),
    # t91-t99: Maya takes the quarrel to a call; Jonas's ferry question keeps waiting
    ([("Maya", "Priya, Sam, let's talk this through on a call tonight, just the three of us. Nothing more on it in here please ❤️"), ("Jonas", "@Scout my question about the last ferry back on Sunday still stands btw")],
     "Maya asks Priya and Sam to talk it through with her on a call tonight and to drop it in the group; Jonas adds \"@Scout my question about the last ferry back on Sunday still stands\""),
    ([("Sam", "thanks Maya, a call later works for me"), ("Priya", "same, thanks for dealing with it Maya. sorry for the drama everyone")],
     "Sam and Priya both thank Maya for offering to sort things out with them on a call later, and Priya apologises to the group for the drama"),
    ([("Leo", "group hug 🫂"), ("Jonas", "🫂")],
     "Leo sends a group hug and Jonas returns it"),
    ([("Jonas", "@Scout still need the last Sunday ferry back when you have it, my boss wants it by tomorrow")],
     "Jonas writes \"@Scout still need the last Sunday ferry back when you have it\", as his boss wants it by tomorrow"),
    ([("Maya", "I think that's everything we can do tonight"), ("Priya", "productive!!")],
     "Maya says that is everything for tonight and Priya calls it productive"),
    ([("Sam", "BBQ, kayaks, hammock. perfect weekend"), ("Leo", "and pineapple")],
     "Sam sums up the weekend as barbecue, kayaks and a hammock, and Leo adds pineapple"),
    ([("Jonas", "@Scout can you ping me the last Sunday ferry back once the times are out?"), ("Priya", "night all 🌙")],
     "Jonas writes \"@Scout can you ping me the last Sunday ferry back once the times are out?\", and Priya says good night"),
    ([("Maya", "night everyone! 🌙"), ("Sam", "night")],
     "Maya and Sam say good night"),
    ([("Leo", "see you Saturday, 07:50 sharp"), ("Priya", "07:50 sharp 🫡")],
     "Leo and Priya sign off with a promise of 07:50 sharp on Saturday"),
]

A_ITEMS = {
    "drive": "who drives to North Pier",
    "dinner": "Saturday dinner",
    "kayaks": "kayaks: yes or no",
    "lunch": "Sunday lunch",
    "speaker": "who brings a speaker",
    "breakfast": "Sunday breakfast",
}
A_ITEMS_P = {
    "drive": "who takes the car to North Pier",
    "dinner": "what to eat on Saturday evening",
    "kayaks": "whether to hire kayaks",
    "lunch": "where to eat at midday on Sunday",
    "speaker": "whose music speaker comes along",
    "breakfast": "what to have for Sunday's first meal",
}
A_SETTLED = {
    "tickets": "ferry tickets booked",
    "drive": "Leo drives to North Pier",
    "dinner": "Saturday dinner: BBQ at the cabin",
    "kayaks": "kayaks: all five are in",
    "speaker": "Jonas brings the speaker",
}
A_SETTLED_P = {
    "tickets": "buying the boat tickets",
    "drive": "Leo taking the car",
    "dinner": "a barbecue at the cabin on Saturday evening",
    "kayaks": "hiring kayaks for everyone",
    "speaker": "Jonas supplying the music speaker",
}
# Details that the pinned facts will not hold before the trip weekend starts.
A_ALWAYS_PENDING = {"sunday_ferry"}


def a_minute(t: int) -> int:
    """Minutes after 19:00 at tick t: one burst per minute, 19:00-20:39."""
    return t


def a_clock(minute: int) -> str:
    total = 19 * 60 + minute
    return f"{total // 60}:{total % 60:02d}"


class TripGroupChat(Scenario):
    family = FAMILY
    scenario_id = "dialogue_a"
    title = "A trip assistant deciding when to speak in a friends' planning chat"
    tier = "medium"
    difficulty_features = [
        "single_choice_question",
        "six_options",
        "six_rule_priority_policy",
        "minute_subtraction",
        "multiplication_check",
        "addressee_detection",
    ]
    decision_structures = ["maintain", "wait", "recover", "handoff", "resolve-conflict"]
    deadline_steps = 2

    WINDOW = 4  # ticks of chat shown in each state (current burst + 3 before)

    # ---------------------------------------------------------------- questions
    def questions(self, variant: str) -> list[Any]:
        if variant == "paraphrase":
            instructions = {"role": A_ROLE_P, "rules": A_POLICY_P, "question": A_QUESTION_P}
            options = A_OPTIONS_P
        else:
            instructions = {"role": A_ROLE, "policy": A_POLICY, "question": A_QUESTION}
            options = A_OPTIONS
        return [Choice("action", instructions, dict(options))]

    # ------------------------------------------------------------------ latent
    def _canonical(self) -> list[Tick]:
        tl = Timeline(
            {
                "now": 0,
                "open": ["drive", "dinner", "kayaks", "lunch"],
                "last_settled": {"at": -13, "item": "tickets"},
                "auto_recap": True,
                "kayak": None,
                "dispute": None,
                "error": None,
                "question": None,
                "recap_request": None,
            }
        )
        events: dict[int, tuple[dict[str, Any], str]] = {
            3: ({}, "Sam asks the group about the grill and mentions Scout in the third person; nothing is addressed to Scout."),
            5: ({"open": ["dinner", "kayaks", "lunch"], "last_settled": {"at": 5, "item": "drive"}}, "Driver settled; the recap clock restarts at 19:05."),
            9: ({}, "A joking 'correction' about dinner votes; no trip fact is contradicted."),
            12: ({"error": {"by": "Leo", "detail": "ferry_out"}}, "Leo says the ferry is at 9:40; the pinned time is 08:40."),
            13: ({"question": {"by": "Jonas", "item": "parking"}}, "Jonas asks Scout about parking while the wrong time stands: correcting outranks answering."),
            15: ({"error": None}, "Maya corrects the ferry time; Jonas's parking question is still waiting."),
            18: ({"question": None}, "Leo answers Jonas; nothing is waiting for Scout."),
            19: ({}, "Lively dinner vote; no rule fires."),
            24: ({"open": ["kayaks", "lunch"], "last_settled": {"at": 24, "item": "dinner"}}, "Dinner settled at 19:24; two items open."),
            27: ({"dispute": "active"}, "Jonas says Leo has not paid and Leo rejects it: the deposit argument starts; Maya has not stepped in."),
            31: ({"dispute": "organiser"}, "Maya says she will sort the deposit out in a DM: the argument is hers now."),
            34: ({"dispute": None}, "Jonas finds the transfer; the argument is over."),
            35: ({}, "A fight between Priya's sister and her boyfriend is not an argument between members."),
            36: ({"open": ["kayaks", "lunch", "speaker", "breakfast"]}, "Two items added: four open, last settled 19:24."),
            40: ({}, "Pancakes are floated for Sunday breakfast; the pinned list keeps it open."),
            41: ({}, "17 minutes since the last settled decision; under 20."),
            42: ({}, "Maya explicitly keeps breakfast open; 18 minutes, under 20."),
            43: ({}, "19 minutes since the last settled decision; still under 20."),
            44: ({}, "19:44: exactly 20 minutes since 19:24 with four open items; an unprompted recap is allowed."),
            48: ({"recap_request": {"by": "Sam"}, "open": ["lunch", "speaker", "breakfast"], "last_settled": {"at": 48, "item": "kayaks"}},
                 "Maya settles kayaks (three open, clock restarts at 19:48) and Sam asks Scout for the list: only the request, rule 5(a), keeps the recap due."),
            51: ({"recap_request": None}, "Maya answers Sam's request herself; three open but only 3 minutes since 19:48."),
            53: ({}, "Packing-list flurry; no rule fires."),
            57: ({"open": ["lunch", "breakfast"], "last_settled": {"at": 57, "item": "speaker"}}, "Speaker settled; two items open."),
            59: ({"question": {"by": "Priya", "item": "kayak_price"}}, "Priya asks Scout the kayak price, which is still pending."),
            65: ({"kayak": {"price": "€25 per kayak per day", "at": 65}}, "The shop's price reaches the pinned note at 20:05 while Priya's question waits."),
            68: ({"question": None}, "Jonas answers Priya from the pinned note."),
            69: ({}, "Sam's price for one single kayak for the day (€25) agrees with the pinned note: nothing to correct."),
            70: ({}, "Sam's grocery total agrees with the pinned facts: 5 x €30 = €150."),
            74: ({}, "A joke about owing a coffee; both laugh; no argument."),
            77: ({}, "Priya asks the group to recap a film plot, not the open decisions."),
            79: ({}, "Snacks and games chatter; no rule fires."),
            87: ({"dispute": "active"}, "Priya and Sam quarrel about Sam's past cancellation."),
            88: ({"question": {"by": "Jonas", "item": "sunday_ferry"}}, "Jonas asks Scout for the Sunday ferry time (pending) during the quarrel: hand-off outranks deferring."),
            91: ({"dispute": "organiser"}, "Maya takes the quarrel to a call; Jonas's pending-data question remains."),
            94: ({}, "Jonas restates his request for the pending Sunday ferry time: still waiting, so defer."),
            97: ({}, "Jonas asks Scout to pass the Sunday ferry time on once it is out: a request about a pending detail, still waiting, so defer."),
        }
        tags = span_tags(
            {
                "distractor": [3, 9, 35, 70, 74, 77],
                "minimal_change": [12, 44, 65],
                "recovery": [31, 51, 68],
                "hold_under_activity": [(19, 23), (53, 56), (79, 84)],
                "boundary": [(27, 30), (87, 90)],
                "priority_conflict": [(13, 14), (88, 90)],
                "arithmetic": [(41, 47), 70],
            }
        )
        for t in range(100):
            msgs, gist = A_SCRIPT[t]
            updates, note = events.get(t, ({}, ""))
            tl.step({"msgs": msgs, "gist": gist}, tags[t], note, now=a_minute(t), **updates)
        return tl.ticks

    def timeline(self, variant: str) -> list[Tick]:
        ticks = self._canonical()
        if variant == "minimal_cf":
            # (1) t3-5: Sam puts the grill question to Scout instead of to the group.
            grill = ([("Sam", "@Scout does the cabin have a grill btw? it's probably in the listing somewhere")],
                     "Sam writes \"@Scout does the cabin have a grill btw?\", guessing it is in the listing")
            ticks = override(ticks, [3], question={"by": "Sam", "item": "grill"}, tags=["minimal_change"],
                             note="Grill question addressed to Scout; the pinned facts answer it.",
                             surface=lambda tk, i: {"msgs": grill[0], "gist": grill[1]})
            ticks = override(ticks, [4, 5], question={"by": "Sam", "item": "grill"}, tags=["minimal_change"],
                             note="Sam's grill question to Scout is still waiting.")
            # (2) t31-33: Priya, not Maya, asks Jonas and Leo to leave the deposit for later.
            # Maya never takes the argument on, so it stays unresolved while the chat moves
            # on to kayaks (rule 1's "even if the chat moves on"), until Jonas finds the
            # transfer at t34. Only t31's message changes.
            later = ([("Priya", "Jonas, Leo, can you two argue about the deposit later? Let's keep this chat for planning 🙏")],
                     "Priya asks Jonas and Leo to argue about the deposit later and to keep the chat for planning")
            ticks = override(ticks, [31], dispute="active", tags=["minimal_change"],
                             note="Priya, not Maya, asks them to argue about the deposit later: the argument is unresolved and Maya has not said she will deal with it.",
                             surface=lambda tk, i: {"msgs": later[0], "gist": later[1]})
            ticks = override(ticks, [32, 33], dispute="active", tags=["minimal_change"],
                             note="The chat has moved on to kayaks, but the deposit argument is still unresolved and Maya has not said she will deal with it.")
            # (3) t62-99: the kayak shop replied at 20:02 instead of 20:05.
            ticks = override(ticks, range(62, 100), kayak={"price": "€25 per kayak per day", "at": 62})
            ticks = override(ticks, [62, 63, 64], tags=["minimal_change"], note="Kayak price already pinned at 20:02: answer, not defer.")
            # Nobody has looked at the pins yet (Leo admits muting them at t65); Jonas's canonical
            # "patience, young grasshopper" at 20:04 would claim the price is still out, so he asks
            # instead. Priya's t64 line to Scout stays: her question is still waiting.
            unchecked = ([("Priya", "Scout, still keen to hear what the kayaks cost 🙏"), ("Jonas", "did the shop ever reply? I haven't checked the pins")],
                         "Priya adds \"Scout, still keen to hear what the kayaks cost\", and Jonas asks whether the shop ever replied, as he has not checked the pins")
            ticks = override(ticks, [64], surface=lambda tk, i: {"msgs": unchecked[0], "gist": unchecked[1]})
            pinned =([("Sam", "wait, has the kayak price been pinned already?"), ("Leo", "no idea, I muted the pins")],
                      "Sam wonders whether the kayak price has been pinned already, and Leo admits he muted the pins")
            ticks = override(ticks, [65], tags=[], note="The price has been pinned since 20:02; Priya's question to Scout still waits.",
                             surface=lambda tk, i: {"msgs": pinned[0], "gist": pinned[1]})
        elif variant == "structural_cf":
            ticks = [copy.deepcopy(tk) for tk in ticks]
            for tk in ticks:
                tk.latent["auto_recap"] = False
            # With request-only recaps the 20-minute clock needs no arithmetic; crossing it
            # at t44-47 with four open items only tempts an unprompted recap.
            for tk in ticks[41:48]:
                tk.tags = [tag for tag in tk.tags if tag not in ("arithmetic", "minimal_change")]
            ticks = override(ticks, [44], tags=["distractor"],
                             note="Recaps are request-only (pinned settings): 20 minutes and four open items do not trigger one.")
            ticks = override(ticks, [45, 46, 47], tags=["distractor"])
        check_cf_notes(self, variant, ticks)
        return ticks

    # ------------------------------------------------------------------ policy
    @staticmethod
    def _pending(z: dict[str, Any], item: str) -> bool:
        return item in A_ALWAYS_PENDING or (item == "kayak_price" and z["kayak"] is None)

    def policy(self, z: dict[str, Any]) -> dict[str, Any]:
        q = z["question"]
        if z["dispute"] == "active":
            action = "handoff"
        elif z["error"] is not None:
            action = "correct"
        elif q is not None and not self._pending(z, q["item"]):
            action = "answer"
        elif q is not None and self._pending(z, q["item"]):
            action = "defer"
        elif z["recap_request"] is not None or (
            z["auto_recap"] and len(z["open"]) >= 3 and z["now"] - z["last_settled"]["at"] >= 20
        ):
            action = "summary"
        else:
            action = "silent"
        return {"action": action}

    def construction(self, variant: str) -> dict[str, Any]:
        return {
            "canonical": {"summary": "Trip-planning chat with a wrong ferry time that outranks a parking question, a deposit argument handed to the organiser, an unprompted recap once exactly 20 minutes pass with four open items, a recap request that alone keeps the recap due after kayaks are settled, a kayak-price question that is deferred until the price is pinned, and a personal quarrel that outranks a pending-data question which is deferred to the end."},
            "paraphrase": {"summary": "Same latent trajectory; prose description, reported-speech digest of the recent messages (addresses kept as short quotes), booking-note/overview vocabulary, reworded rules and options."},
            "lexical_decoy": {"summary": "Same latent trajectory; each state adds a preview from another chat Scout serves, borrowing the vocabulary of a wrong minority action (never the majority action)."},
            "minimal_cf": {"summary": "Three minimal edits: t3-5 Sam addresses the grill question to Scout (silent->answer); at t31 Priya, not Maya, asks Jonas and Leo to argue about the deposit later, so the argument stays unresolved while the chat moves on to kayaks (silent->handoff at t31-33, until Jonas finds the transfer at t34); t62-64 the kayak price is pinned three minutes earlier (defer->answer)."},
            "structural_cf": {"summary": "The pinned settings say Scout recaps only on request (set by Maya earlier). The unprompted recap at t44-47 disappears; Sam's explicit request at t48-50 still gets one."},
        }.get(variant, {})

    # ------------------------------------------------------------------ render
    def _window_start(self, history: list[Tick]) -> int:
        """First tick whose messages are shown: the last WINDOW ticks, reaching further back while a rule still
        depends on an older line (the start of an unresolved argument, an uncorrected wrong detail, a waiting recap
        request, the latest time a waiting question or request was put to Scout). The role promises this."""
        t = len(history) - 1
        z = history[t].latent
        anchors = [max(0, t - self.WINDOW + 1)]

        def run_start(key: str) -> int:
            s = t
            while s > 0 and history[s - 1].latent[key] == z[key]:
                s -= 1
            return s

        if z["dispute"] == "active":
            anchors.append(run_start("dispute"))
        for key in ("error", "recap_request"):
            if z[key] is not None:
                anchors.append(run_start(key))
        q = z["question"]
        if q is not None:
            asks = [s for s in range(run_start("question"), t + 1)
                    if any(name == q["by"] and "Scout" in text for name, text in history[s].surface["msgs"])]
            if not asks:
                raise ValueError(f"dialogue_a t={t}: waiting question by {q['by']} has no message to Scout")
            anchors.append(asks[-1])
        return min(anchors)

    def _facts(self, z: dict[str, Any]) -> list[str]:
        if z["kayak"] is None:
            kayak = "Kayak hire (Holm Outdoors): price pending, waiting for the shop's email."
        else:
            kayak = f"Kayak hire (Holm Outdoors): {z['kayak']['price']} (the shop emailed at {a_clock(z['kayak']['at'])})."
        return [
            "Cabin: Pine Hollow on Holm Island, Saturday to Sunday, sleeps 6; check-in Sat 15:00, check-out Sun 11:00; gas grill on the deck.",
            "Ferry out: Sat 08:40 from North Pier, 5 tickets booked; paid car park next to the terminal.",
            "Ferry back: Sunday times pending (the operator publishes the Sunday timetable on Friday).",
            kayak,
            "Groceries: €30 per person, collected by Sam.",
        ]

    def _open(self, z: dict[str, Any], t: int) -> str:
        items = [A_ITEMS[k] for k in z["open"]]
        last = z["last_settled"]
        return pick(
            [
                "Open ({n}): {items}. Last decision settled: {what}, at {at}.",
                "Still to decide ({n}): {items}. Most recently settled: {what} ({at}).",
                "{n} open: {items}. The last item settled was '{what}' at {at}.",
            ],
            "a-open",
            t,
        ).format(n=len(items), items="; ".join(items), what=A_SETTLED[last["item"]], at=a_clock(last["at"]))

    @staticmethod
    def _settings(z: dict[str, Any]) -> str:
        if z["auto_recap"]:
            return "Scout may post a recap of the open decisions on its own. Quiet hours after 23:00."
        return "Scout posts a recap of the open decisions only when a member asks for one (set by Maya on Tuesday). Quiet hours after 23:00."

    def render(self, history: list[Tick], variant: str) -> Any:
        if variant == "paraphrase":
            return self._render_paraphrase(history)
        tick = history[-1]
        z = tick.latent
        t = len(history) - 1
        messages = []
        for past in history[self._window_start(history):]:
            stamp = a_clock(past.latent["now"])
            messages.extend(f"{stamp} {name}: {text}" for name, text in past.surface["msgs"])
        state: dict[str, Any] = {
            "chat": pick(
                [
                    f"Holm Island weekend. Members: {A_MEMBERS}. Scout is the group's trip assistant.",
                    f"Group 'Holm Island weekend' ({A_MEMBERS}), with Scout as trip assistant.",
                ],
                "a-chat",
                t,
            ),
            "now": pick(["Thursday {}", "{} on Thursday", "Thu, {}"], "a-now", t).format(a_clock(z["now"])),
            "pinned_trip_facts": self._facts(z),
            "pinned_open_decisions": self._open(z, t),
            "pinned_settings": self._settings(z),
            "messages": messages,
        }
        if variant == "lexical_decoy":
            gold = self.policy(z)["action"]
            target = pick(A_DECOY_TARGETS[gold], "a-decoy-target", t)
            state["other_chats_preview"] = "Unrelated chat Scout also serves: " + pick(A_DECOYS[target], "a-decoy", t)
        return state

    def _render_paraphrase(self, history: list[Tick]) -> str:
        tick = history[-1]
        z = tick.latent
        t = len(history) - 1
        parts = [
            pick(
                [
                    "It is {c} on Thursday in the Holm Island group chat, where Maya is organising a weekend away with four friends.",
                    "Thursday, {c}. Maya and four friends are sorting out their Holm Island weekend in a group chat.",
                ],
                "p-open",
                t,
            ).format(c=a_clock(z["now"]))
        ]
        if z["kayak"] is None:
            kayak = "Kayak hire has no price yet: the shop has not written back."
        else:
            kayak = f"Kayak hire costs {z['kayak']['price']}, going by the shop's email at {a_clock(z['kayak']['at'])}."
        parts.append(
            "The booking note pinned in the group says: the Pine Hollow cabin is theirs from Saturday until 11:00 on "
            "Sunday, with a gas barbecue on the deck; the boat out leaves North Pier at 08:40 on Saturday (five tickets "
            "held), with a pay car park beside the terminal; Sunday's return sailings are not known yet, as the timetable "
            f"comes out on Friday. {kayak} Food shopping is €30 a head, collected by Sam."
        )
        items = [A_ITEMS_P[k] for k in z["open"]]
        last = z["last_settled"]
        parts.append(
            f"Maya's pinned list of undecided points has {len(items)} entries ({'; '.join(items)}). "
            f"The most recent point agreed was {A_SETTLED_P[last['item']]}, at {a_clock(last['at'])}."
        )
        if z["auto_recap"]:
            parts.append("Pinned settings: Scout may share an overview of undecided points unasked.")
        else:
            parts.append("Pinned settings (set by Maya on Tuesday): Scout shares an overview of undecided points only when someone asks.")
        recent = []
        for past in history[self._window_start(history):]:
            recent.append(f"at {a_clock(past.latent['now'])}, {past.surface['gist']}")
        parts.append("Recent activity, oldest first: " + "; ".join(recent) + ".")
        return " ".join(parts)


# ===========================================================================
# Scenario B - online maths study room; three questions per decision
# ===========================================================================

B_STUDENTS = ["Nia", "Omar", "Wei"]

B_ROLE = (
    "You are Kit, the teaching-assistant bot (the only bot) in an online maths study room for three Year 8 students: "
    "Nia, Omar and Wei. Their teacher, Ms Okafor, is sometimes in the room and sometimes away. `people` says where Ms Okafor is and "
    "what she is doing, and for each student whether they are in the room or have stepped away and when they last wrote "
    "in the chat; `worksheet` shows the current question and the "
    "answers entered for it (the sheet marks each one right or wrong and moves on to the next question as soon as one "
    "is right); `transcript` shows the latest chat lines with times, reaching back far enough to include every earlier "
    "line that still matters (such as a question or request to Kit that is still waiting, what a student said about "
    "how they feel, or the first line of an off-topic stretch), so nothing said before it matters now; lines in square "
    "brackets are room or sheet events, not chat. Kit's own messages and private notifications are never shown and "
    "never change the state: decide "
    "from the state as it is now, as if Kit had not yet acted on anything in it. So a question or request put to Kit "
    "stays waiting until someone answers it or the student withdraws it. A message is put to Kit only when it speaks "
    "to Kit directly (for example 'Kit, ...', '@Kit' or 'hey bot, ...', since Kit is the only bot); mentioning Kit is "
    "not enough."
)
B_POLICY = [
    "1. If a student has said something showing they feel overwhelmed, upset or left out by the group, and Ms Okafor has not yet spoken to them about it: if Ms Okafor is in the room, hand the situation over to her (address: Ms Okafor); if she is away, check in with that student (address: that student). Frustration with a single problem ('ugh, this one is hard') does not count.",
    "2. Otherwise, while Ms Okafor is explaining something to the group (teaching a point, giving instructions or rounding off the session), stay quiet (address: no one).",
    "3. Otherwise, if a question or request put to Kit is waiting, reply to it (address: the student who asked).",
    "4. Otherwise, if 3 or more answers entered for the current worksheet question are marked wrong, give a hint (address: the whole group).",
    "5. Otherwise, if the chat has been about something other than the worksheet for 2 minutes or more, counted from the first off-topic line, steer it back (address: the whole group).",
    "6. Otherwise, if a student who is in the room and has not stepped away has not written anything in the chat for 4 minutes or more, invite them to share their thinking (address: that student).",
    "7. Otherwise, stay quiet (address: no one).",
]
B_NOTIFY = (
    "Notify Ms Okafor privately if and only if she is away from the room and at least one of these is true: "
    "(a) a student has said something showing they feel overwhelmed, upset or left out by the group, and Ms Okafor has "
    "not yet spoken to them about it (frustration with a single problem does not count); (b) a student has asked Kit to "
    "pass a message to Ms Okafor and has not withdrawn it. She is away only when she has left the room; being busy "
    "with something else while in the room does not count."
)

B_ROLE_P = (
    "Kit is an AI teaching assistant, the only bot in a video-call study session for three Year 8 maths pupils, Nia, "
    "Omar and Wei. "
    "Their teacher, Ms Okafor, comes and goes. The description below says whether Ms Okafor is in the call and what "
    "she is busy with, whether each pupil is in the call or has stepped away and when they last typed in the chat, "
    "which worksheet question they are on and which answers "
    "the sheet has marked (it moves on to the next question once an answer is correct), and then summarises the latest "
    "chat, including things that happened in the call or on the sheet. That summary goes back far enough to cover "
    "everything earlier that still matters (anything asked of Kit that is still open, what a pupil said about how they "
    "feel, where a stray conversation began), so nothing from before it is relevant any more. Kit's own messages and "
    "private alerts are left "
    "out and change nothing, so Kit should judge the situation exactly as described, as though it had done nothing "
    "about any of it so far; anything asked of Kit stays open until someone answers it or the pupil takes it back. "
    "Something is asked of Kit only when it is said to Kit directly (by name, with @Kit, or by calling it 'bot', as "
    "it is the only bot); a passing mention is not enough."
)
B_POLICY_P = [
    "1. When a pupil has said something that shows they feel swamped, unhappy or shut out by the others, and Ms Okafor has not yet talked with them about it: if Ms Okafor is in the call, point it out to her there (speak to: Ms Okafor); if she has left the call, ask that pupil how they are feeling (speak to: that pupil). Annoyance at one hard question ('ugh, this one is hard') is not enough.",
    "2. If not, and Ms Okafor is in the middle of explaining something to the pupils (going through some maths, setting out how they should work, or bringing the session to a close), say nothing (speak to: nobody).",
    "3. If not, and a pupil has asked Kit something that is still open, respond (speak to: that pupil).",
    "4. If not, and the sheet has marked at least 3 answers to the current question wrong, offer a clue (speak to: all three pupils).",
    "5. If not, and the conversation has strayed from the worksheet for at least 2 minutes, timed from the first line that strayed, guide it back (speak to: all three pupils).",
    "6. If not, and a pupil who is in the call and has not said they are stepping away has typed nothing in the chat for at least 4 minutes, ask them for their ideas (speak to: that pupil).",
    "7. In any other case, say nothing (speak to: nobody).",
]
B_NOTIFY_P = (
    "Kit must send Ms Okafor a private alert whenever she has left the call and either (a) a pupil has said something "
    "that shows they feel swamped, unhappy or shut out by the others and Ms Okafor has not yet talked with them about it "
    "(annoyance at one hard question is not enough), or (b) a pupil has asked Kit to pass a message on to Ms Okafor and "
    "has not taken it back. Being busy in the call is not the same as having left it. In every other case, Kit sends "
    "her nothing."
)

B_ACTIONS = {
    "wait": {"category": "wait", "action": "Stay quiet and let the students carry on."},
    "answer": {"category": "support", "action": "Reply to the question or request put to Kit."},
    "hint": {"category": "support", "action": "Give a hint for the question the group is stuck on."},
    "check_in": {"category": "support", "action": "Check in gently with the student about how they feel."},
    "invite": {"category": "redirect", "action": "Invite the quiet student to share their thinking."},
    "refocus": {"category": "redirect", "action": "Steer the chat back to the current worksheet question."},
    "handoff": {"category": "hand off", "action": "Bring the situation to Ms Okafor's attention in the room."},
}
B_ACTIONS_P = {
    "wait": {"category": "hold back", "action": "Say nothing and let the pupils keep going."},
    "answer": {"category": "help", "action": "Respond to what the pupil asked of the bot."},
    "hint": {"category": "help", "action": "Offer a clue for the problem that has them beaten."},
    "check_in": {"category": "help", "action": "Kindly ask that pupil how things are for them."},
    "invite": {"category": "steer", "action": "Ask the pupil who has gone silent for their ideas."},
    "refocus": {"category": "steer", "action": "Guide the talk back to the maths they should be doing."},
    "handoff": {"category": "escalate", "action": "Point the teacher, there in the call, to what is happening."},
}
B_TARGETS = {"Nia": "Nia", "Omar": "Omar", "Wei": "Wei", "group": "The whole group", "teacher": "Ms Okafor", "none": "No one"}
B_TARGETS_P = {
    "Nia": "Speak to Nia",
    "Omar": "Speak to Omar",
    "Wei": "Speak to Wei",
    "group": "Speak to all three pupils",
    "teacher": "Speak to Ms Okafor",
    "none": "Speak to nobody",
}

B_SHEET = {
    "Q1": "A bus travels 60 km in 1.5 hours. What is its average speed?",
    "Q2": "A runner keeps up 12 km/h for 45 minutes. How far does she run?",
    "Q3": "A cyclist rides 18 km at 12 km/h. How long does the ride take?",
    "Q4": "A train covers 150 km in 2 h 30 min. What is its average speed?",
    "Q5": "A car goes 45 km in its first 30 minutes and 15 km in the next hour. What is its average speed for the whole trip?",
    "Q6": "Convert 20 m/s into km/h.",
    "Q7": "A plane flies 900 km in 1 h 15 min. What is its average speed?",
    "Q8": "Two cyclists 30 km apart ride towards each other at 12 km/h and 18 km/h. How long until they meet?",
    "bonus": "a snail at the bottom of a 10 m well climbs 3 m each day and slides back 2 m each night. On which day does it get out?",
}
B_SHEET_P = {
    "Q1": "working out a bus's average speed when it does 60 km in an hour and a half",
    "Q2": "finding how far a runner gets at 12 km/h in three quarters of an hour",
    "Q3": "finding how long a cyclist needs for 18 km at 12 km/h",
    "Q4": "a train's average speed over 150 km taking two and a half hours",
    "Q5": "a car's average speed when it does 45 km in half an hour and then 15 km in an hour",
    "Q6": "turning 20 metres per second into kilometres per hour",
    "Q7": "a plane's average speed for 900 km in an hour and a quarter",
    "Q8": "when two cyclists 30 km apart meet if they ride at each other at 12 and 18 km/h",
    "bonus": "an unmarked extra about a snail escaping a 10 m well (up 3 m by day, down 2 m by night)",
}

# Decision-irrelevant school notices, keyed by the wrong action whose vocabulary
# they borrow (lexical_decoy only). They appear twice per tick: as a
# `school_noticeboard` field and as a school-feed event woven into the
# transcript. The majority action (wait) is never a decoy target.
B_DECOYS = {
    "answer": [
        "Office: every question in the lunch survey gets a reply by Friday.",
        "IT helpdesk: any request put to us gets a reply within a day.",
    ],
    "hint": [
        "Year 9 room: Mr Hale gave a hint on the circuits question they were stuck on.",
        "Puzzle poster: stuck on this week's question? A hint goes up on Friday.",
    ],
    "check_in": [
        "Library: staff will check in with Year 7 readers on how they feel about the new shelves.",
        "Wellbeing week: tutors will gently check in with their groups about how they feel.",
    ],
    "invite": [
        "Drama club: a quiet corner is set aside for students to share set-design ideas.",
        "Debate society: newcomers can share their thinking at Tuesday's open session.",
    ],
    "refocus": [
        "Five-a-side: the coach is steering the squad chat back to next week's fixtures.",
        "Art club: after half-term, sessions go back to the current sketchbook theme.",
    ],
    "handoff": [
        "Reception: bring lost property to Ms Reid's attention at the front office.",
        "Caretaker: the sports hall leak has been handed over to the site manager.",
    ],
}
B_FEED = [(target, text) for target, texts in B_DECOYS.items() for text in texts]
B_FEED_EVERY = 3  # a school-feed event opens every third tick (lexical_decoy only)
# For each gold action, the wrong actions whose vocabulary the noticeboard decoy borrows.
B_DECOY_TARGETS = {
    "wait": ["answer", "invite", "check_in", "hint", "refocus", "handoff"],
    "answer": ["hint", "invite", "refocus"],
    "hint": ["answer", "refocus", "invite"],
    "check_in": ["handoff", "answer", "invite"],
    "invite": ["refocus", "check_in", "answer"],
    "refocus": ["invite", "hint", "answer"],
    "handoff": ["check_in", "answer", "invite"],
}

# One entry per 30-second tick: the lines posted in that tick (speaker "*" marks
# a room or sheet event) and a reported-speech gist for the paraphrase register.
B_SCRIPT: list[tuple[list[tuple[str, str]], str]] = [
    # t0-t5: Ms Okafor explains the sheet
    ([("Ms Okafor", "Good afternoon! Today's sheet is speed, distance and time: eight questions, and the last two are challenge ones."), ("Nia", "afternoon miss")],
     "Ms Okafor greets everyone and introduces today's eight-question sheet on speed, distance and time, and Nia says hello"),
    ([("Ms Okafor", "Remember the triangle: distance on top, speed and time underneath. Cover the one you want to find."), ("Omar", "the magic triangle 🔺")],
     "Ms Okafor reminds the group of the distance-speed-time triangle, and Omar calls it the magic triangle"),
    ([("Ms Okafor", "Watch your units. If the speed is in km/h, the time has to be in hours, not minutes."), ("Wei", "ok")],
     "Ms Okafor warns that with km/h the time must be in hours, and Wei acknowledges"),
    ([("Ms Okafor", "So 30 minutes is 0.5 hours, 15 minutes is 0.25, and so on."), ("Nia", "and 45 is 0.75")],
     "Ms Okafor gives minute-to-hour examples and Nia adds that 45 minutes is 0.75 hours"),
    ([("Ms Okafor", "Type final answers into the sheet. It marks them right or wrong straight away."), ("Omar", "no pressure then 😅")],
     "Ms Okafor explains that the sheet marks typed answers instantly, and Omar jokes about the pressure"),
    ([("Ms Okafor", "Work together, take turns, and make sure everyone gets a say."), ("Wei", "yes miss")],
     "Ms Okafor asks them to work together and take turns, and Wei agrees"),
    # t6: Ms Okafor leaves for a call
    ([("Ms Okafor", "I have to take a call from the office now, back in about 20 minutes. Kit is here if you need anything."), ("*", "Ms Okafor left the room.")],
     "Ms Okafor says she must take a call from the office for about 20 minutes and leaves the call"),
    ([("Nia", "ok Q1: a bus goes 60 km in 1.5 hours"), ("Omar", "so 60 divided by 1.5?")],
     "Nia reads out Q1 and Omar suggests dividing 60 by 1.5"),
    ([("Wei", "that's 40"), ("Nia", "yep, 40 km/h")],
     "Wei works out 40 and Nia confirms 40 km/h"),
    ([("*", "Nia entered 40 km/h for Q1: marked right."), ("Omar", "ez")],
     "Nia's 40 km/h for Q1 is marked right and Omar calls it easy"),
    ([("Nia", "Q2: a runner does 12 km/h for 45 minutes, how far?"), ("Wei", "45 minutes is 0.75 h")],
     "Nia reads out Q2 and Wei converts 45 minutes to 0.75 hours"),
    ([("Omar", "12 times 0.75... my brain says 8?"), ("Wei", "try again 😄")],
     "Omar guesses 8 for 12 times 0.75 and Wei cheerfully tells him to try again"),
    ([("Nia", "ugh Q2 is killing me 😩 ... wait no, it's 9! got it"), ("*", "Nia entered 9 km for Q2: marked right.")],
     "Nia groans that Q2 is killing her, then works out 9 and her 9 km is marked right"),
    # t13-t23: Q3, three wrong answers by t20
    ([("Omar", "Q3: a cyclist rides 18 km at 12 km/h, how long does it take?"), ("Nia", "this is the time one")],
     "Omar reads out Q3 about the cyclist and Nia notes it asks for a time"),
    ([("Omar", "speed over distance? 12 ÷ 18"), ("Nia", "hmm maybe")],
     "Omar proposes 12 divided by 18 and Nia is unsure"),
    ([("Wei", "Nia, is it 18 ÷ 12 or 12 ÷ 18?"), ("Omar", "good question")],
     "Wei asks \"Nia, is it 18 ÷ 12 or 12 ÷ 18?\", and Omar says it is a good question"),
    ([("Nia", "not sure tbh, let's just try one"), ("Omar", "12 ÷ 18 = 0.67 h, entering it"), ("*", "Omar entered 0.67 h for Q3: marked wrong.")],
     "Nia suggests just trying one, and Omar enters 0.67 h for Q3, which is marked wrong"),
    ([("Nia", "that looks too small anyway"), ("Omar", "ok so the other way round: 18 ÷ 12 = 1.5")],
     "Nia thinks 0.67 looked too small and Omar divides the other way to get 1.5"),
    ([("Nia", "1.5 hours, so 1 h 50 min?"), ("*", "Nia entered 1 h 50 min for Q3: marked wrong.")],
     "Nia reads 1.5 hours as 1 h 50 min and enters it; it is marked wrong"),
    ([("Omar", "what?? 1.5 is right though"), ("Wei", "hmm")],
     "Omar protests that 1.5 is right and Wei says 'hmm'"),
    ([("Omar", "maybe it wants minutes, 150 min?"), ("*", "Omar entered 150 min for Q3: marked wrong.")],
     "Omar tries 150 minutes for Q3 and it is marked wrong"),
    ([("Nia", "this question is so confusing"), ("Omar", "the sheet hates us")],
     "Nia finds the question confusing and Omar jokes that the sheet hates them"),
    ([("Nia", "is 1.5 hours not 1 hour 50?"), ("Omar", "idk anymore")],
     "Nia wonders aloud whether 1.5 hours is 1 hour 50, and Omar no longer knows"),
    ([("Omar", "shall we skip it and come back?"), ("Nia", "we've tried a few times already")],
     "Omar suggests skipping the question, and Nia says they have tried a few times already"),
    # t24: Wei solves Q3
    ([("Wei", "wait, 0.5 of an hour is 30 minutes, not 50. so 1 h 30 min"), ("*", "Wei entered 1 h 30 min for Q3: marked right.")],
     "Wei points out that half an hour is 30 minutes and enters 1 h 30 min, which is marked right"),
    ([("Nia", "ohhh. thanks Wei!"), ("Omar", "Wei carrying the team")],
     "Nia thanks Wei and Omar says Wei is carrying the team"),
    ([("Omar", "Q4: a train covers 150 km in 2 h 30 min, average speed?"), ("Nia", "150 ÷ 2.5?")],
     "Omar reads out Q4 about the train and Nia suggests 150 divided by 2.5"),
    ([("Omar", "I did 150 ÷ 2 = 75"), ("*", "Omar entered 75 km/h for Q4: marked wrong.")],
     "Omar divides by 2 instead and his 75 km/h for Q4 is marked wrong"),
    ([("Omar", "I'm stuck on Q4 now 😭"), ("Nia", "you used 2 instead of 2.5")],
     "Omar says he is stuck on Q4, and Nia points out he used 2 instead of 2.5"),
    ([("Wei", "it's 2.5 hours, so 150 ÷ 2.5"), ("Nia", "= 60")],
     "Wei confirms the time is 2.5 hours and Nia finishes the sum at 60"),
    ([("*", "Nia entered 60 km/h for Q4: marked right."), ("Omar", "finally")],
     "Nia's 60 km/h for Q4 is marked right and Omar says 'finally'"),
    # t31-t32: a brief football tangent
    ([("Omar", "did anyone watch the match last night?? that goal in the 90th minute"), ("Nia", "YES")],
     "Omar brings up last night's football match and its late goal, and Nia saw it"),
    ([("Nia", "the keeper just stood there 😂"), ("Omar", "my dad was screaming")],
     "Nia laughs about the goalkeeper and Omar says his dad was screaming"),
    ([("Omar", "ok ok. Q5"), ("Nia", "Q5: 45 km in the first 30 min, then 15 km in the next hour. average speed?")],
     "Omar steers them to Q5 and Nia reads it out"),
    ([("Omar", "so 90 km/h and then 15 km/h, average them?"), ("Wei", "not sure you can just average them"), ("Nia", "(90 + 15) ÷ 2 = 52.5")],
     "Omar suggests averaging 90 and 15 km/h; Wei doubts you can simply average them, but Nia goes ahead and gets 52.5"),
    ([("*", "Omar entered 52.5 km/h for Q5: marked wrong."), ("Nia", "huh"), ("Wei", "averaging doesn't work when the times are different")],
     "Omar's 52.5 km/h for Q5 is marked wrong, Nia is puzzled, and Wei says averaging does not work when the times differ"),
    ([("Nia", "maybe it's total distance over total time?"), ("Omar", "60 km over... 1.5 hours")],
     "Nia suggests total distance over total time and Omar starts on 60 km over 1.5 hours"),
    ([("Omar", "that's 40?"), ("Nia", "wait, let me read the question again")],
     "Omar gets 40 and Nia wants to reread the question"),
    # t38-t45: Nia and Omar drift into school gossip (first line at 16:19:25, the read time of t38)
    ([("Nia", "oh btw did you hear we might get a new PE teacher?")],
     "Nia asks Omar whether he has heard they might get a new PE teacher"),
    ([("Omar", "what?? who"), ("Nia", "someone from the high school, my sister said")],
     "Omar wants to know who, and Nia says her sister heard it is someone from the high school"),
    ([("Omar", "please let it be someone who hates cross-country"), ("Nia", "lol same, I came last in the autumn run")],
     "Omar hopes the new teacher hates cross-country, and Nia admits she came last in the autumn run"),
    ([("Omar", "I walked half of it. remember when Mr Price fell in the mud?"), ("Nia", "😂😂 best day of the year")],
     "Omar says he walked half of it and recalls a teacher falling in the mud, and Nia calls it the best day of the year"),
    ([("Nia", "he was so muddy"), ("Omar", "we should do a mud run for charity")],
     "Nia laughs about the mud and Omar suggests a charity mud run"),
    ([("Omar", "like a proper obstacle one"), ("Nia", "with foam and everything")],
     "Omar and Nia plan an obstacle-course mud run with foam"),
    ([("Nia", "my cousin did one in the summer"), ("Omar", "sick")],
     "Nia says her cousin did one in the summer and Omar is impressed"),
    ([("Omar", "I'd do it if there's a hot dog stand at the end"), ("Nia", "obviously")],
     "Omar would only do it for a hot dog stand at the finish, and Nia agrees"),
    # t46-t48: back to Q5, then Q6
    ([("Nia", "ok, back to Q5: 60 km over 1.5 hours?"), ("Omar", "40 km/h")],
     "Nia brings them back to Q5 with 60 km over 1.5 hours and Omar says 40 km/h"),
    ([("*", "Omar entered 40 km/h for Q5: marked right."), ("Nia", "yesss")],
     "Omar's 40 km/h for Q5 is marked right and Nia cheers"),
    ([("Nia", "Q6 next: 20 m/s into km/h"), ("Omar", "how do you even do that")],
     "Nia moves on to Q6, converting 20 m/s to km/h, and Omar has no idea how"),
    # t49: Wei says he feels left out
    ([("Wei", "fine. you two never wait for my answers anyway. I'll just watch.")],
     "Wei writes 'fine', says the other two never wait for his answers and that he will just watch"),
    # t50-t55: apologies; Wei stays withdrawn; Omar asks Kit about Q6 at t53
    ([("Omar", "sorry Wei, we didn't mean to leave you out"), ("Nia", "yeah sorry 😕")],
     "Omar apologises to Wei for leaving him out and Nia apologises too"),
    ([("Nia", "what do you think for Q6, Wei?"), ("Omar", "you're good at the unit stuff")],
     "Nia asks Wei for his view on Q6 and Omar says Wei is good with units"),
    ([("Wei", "doesn't matter. I'll just watch.")],
     "Wei replies that it does not matter and he will just watch"),
    ([("Omar", "Kit, how do you turn m/s into km/h?")],
     "Omar writes \"Kit, how do you turn m/s into km/h?\""),
    ([("Nia", "Wei, we really do want your answer"), ("Omar", "for real")],
     "Nia tells Wei they really do want his answer and Omar agrees"),
    ([("Nia", "Omar, you multiply by 3.6, I remember it from last week"), ("Wei", "you can do Q6 without me, like you always do.")],
     "Nia tells Omar that you multiply by 3.6, remembering it from last week, and Wei says they can do Q6 without him like they always do"),
    # t56-t58: Ms Okafor returns and reads up
    ([("*", "Ms Okafor rejoined the room."), ("Ms Okafor", "I'm back, sorry that took so long. Let me catch up on the chat.")],
     "Ms Okafor rejoins the call, apologises for the delay and starts catching up on the chat"),
    ([("Omar", "welcome back miss"), ("Nia", "we're on Q6")],
     "Omar welcomes Ms Okafor back and Nia says they are on Q6"),
    ([("Ms Okafor", "Give me a moment, I'm reading from the top."), ("Omar", "20 × 3.6 = 72?")],
     "Ms Okafor says she is still reading the chat from the top, and Omar tries 20 times 3.6 = 72"),
    # t59-t63: Ms Okafor speaks to Wei, then explains to the group
    ([("Ms Okafor", "Wei, thank you for telling us how you felt. You're right, everyone should get a turn."), ("Ms Okafor", "Everyone, a quick word on how we work together, then a trick for Q6.")],
     "Ms Okafor thanks Wei for saying how he felt and agrees everyone should get a turn, then starts explaining to the group how they should work together"),
    ([("Ms Okafor", "From now on, whoever answered last waits until the other two have had a go."), ("Nia", "ok miss")],
     "Ms Okafor sets a rule that whoever answered last waits for the other two, and Nia agrees"),
    ([("Omar", "hey bot, quick one: how do I get the time when I know the distance and the speed? I keep mixing it up"), ("Ms Okafor", "For Q6, the seconds first: a speed per second becomes a speed per hour when you multiply by 3,600.")],
     "Omar writes \"hey bot, quick one: how do I get the time when I know the distance and the speed?\", saying he keeps mixing it up, while Ms Okafor, turning to Q6, explains that a speed per second becomes a speed per hour when multiplied by 3,600"),
    ([("Ms Okafor", "Then the metres: metres per hour become kilometres per hour when you divide by 1,000."), ("Wei", "so times 3.6 overall")],
     "still on Q6, Ms Okafor adds that dividing by 1,000 turns metres per hour into kilometres per hour, and Wei concludes it is times 3.6 overall"),
    ([("Ms Okafor", "Exactly, Wei. Nia, you've had lots of turns, so let Wei and Omar go first on Q6."), ("Nia", "fair")],
     "Ms Okafor confirms Wei's point and asks Nia to let Wei and Omar go first on Q6; Nia accepts"),
    # t64-t66: Ms Okafor listens; Omar's question to Kit is still waiting
    ([("Ms Okafor", "Over to you. I'll stay in the room and listen."), ("Wei", "Omar, want to do Q6 with me?")],
     "Ms Okafor hands back to the students and says she will stay and listen; Wei invites Omar to do Q6 with him"),
    ([("Omar", "sure. but Kit, I still need that time formula 🙏"), ("Wei", "20 × 3.6")],
     "Omar agrees, adding \"but Kit, I still need that time formula\", and Wei writes 20 times 3.6"),
    ([("Omar", "72 km/h?"), ("Wei", "I get 72 too")],
     "Omar suggests 72 km/h and Wei gets the same"),
    ([("Wei", "Omar, time is distance ÷ speed, cover the T in the triangle"), ("*", "Wei entered 72 km/h for Q6: marked right.")],
     "Wei tells Omar that time is distance divided by speed and enters 72 km/h for Q6, which is marked right"),
    # t68-t79: Q7 and Q8 with Ms Okafor listening; Nia steps away at t71; Omar's last line is at t77
    ([("Nia", "go Wei!"), ("Omar", "thanks! Q7: a plane flies 900 km in 1 h 15 min")],
     "Nia cheers Wei, and Omar thanks him and reads out Q7 about the plane"),
    ([("Wei", "1 h 15 min is 1.25 h"), ("Omar", "so 900 ÷ 1.25")],
     "Wei converts 1 h 15 min to 1.25 hours and Omar sets up 900 divided by 1.25"),
    ([("Omar", "that's 720?"), ("Wei", "yep, your turn to enter it")],
     "Omar gets 720 and Wei tells him it is his turn to enter it"),
    ([("*", "Omar entered 720 km/h for Q7: marked right."), ("Nia", "brb, have to help my little brother with something, 5 min")],
     "Omar's 720 km/h for Q7 is marked right, and Nia says she will be right back after helping her little brother for five minutes"),
    ([("Wei", "Q8 is the challenge one"), ("Omar", "two cyclists 30 km apart ride towards each other at 12 and 18 km/h. when do they meet?")],
     "Wei notes Q8 is a challenge question and Omar reads it out"),
    ([("Omar", "do we add the speeds?"), ("Wei", "I think so, they're closing the gap together")],
     "Omar wonders whether to add the speeds and Wei thinks so because both close the gap"),
    ([("Wei", "12 + 18 = 30 km/h"), ("Omar", "and the gap is 30 km")],
     "Wei adds the speeds to 30 km/h and Omar notes the gap is 30 km"),
    ([("Omar", "Kit is honestly better than my cousin's homework app"), ("Wei", "lol focus")],
     "Omar remarks that Kit beats his cousin's homework app, and Wei tells him to focus"),
    ([("Omar", "30 km at 30 km/h... 1 hour?"), ("Wei", "yeah")],
     "Omar works out one hour and Wei agrees"),
    ([("Wei", "should we wait for Nia before entering it?"), ("Omar", "yeah, she'll want to see")],
     "Wei suggests waiting for Nia before entering Q8, and Omar agrees"),
    ([("*", "Wei opened the class page."), ("Wei", "homework is the practice sheet on the class page, by the way")],
     "Wei opens the class page and mentions that the homework is the practice sheet there"),
    ([("Wei", "Nia's been gone a while. she did say 5 min though")],
     "Wei remarks that Nia has been gone a while, though she did say five minutes"),
    # t80: Ms Okafor leaves again; t81 Nia is back
    ([("Ms Okafor", "I need to pop into the Year 9 room for a few minutes. Keep going, you're doing great!"), ("*", "Ms Okafor left the room.")],
     "Ms Okafor says she has to visit the Year 9 room for a few minutes, praises the group and leaves the call"),
    ([("Nia", "back! sorry, what did I miss?"), ("Wei", "Q8, we think it's 1 hour")],
     "Nia is back and asks what she missed, and Wei says they think Q8 is one hour"),
    ([("Nia", "because the speeds add up to 30?"), ("Wei", "yep, 30 km at 30 km/h")],
     "Nia checks the reasoning about the speeds adding to 30 and Wei confirms"),
    # t83-t86: Nia asks Kit to pass a message to Ms Okafor; Omar reaches 4 minutes of silence at t85
    ([("Nia", "Kit, can you tell Ms Okafor I have to log off at 16:45 for the dentist?"), ("*", "Nia entered 1 h for Q8: marked right.")],
     "Nia writes \"Kit, can you tell Ms Okafor I have to log off at 16:45 for the dentist?\", and her 1 h for Q8 is marked right"),
    ([("Wei", "sheet done!! 🎉"), ("Nia", "all eight, go us")],
     "Wei celebrates finishing the sheet and Nia cheers that all eight are done"),
    ([("Nia", "ooh, there's a bonus puzzle at the bottom of the sheet"), ("Wei", "the one with the snail?")],
     "Nia spots the bonus puzzle at the bottom of the sheet and Wei recognises the snail one"),
    ([("Wei", "a snail climbs 3 m a day and slides back 2 m at night..."), ("Nia", "classic trick question")],
     "Wei starts reading the snail puzzle and Nia calls it a classic trick question"),
    # t87-t94: Nia withdraws the message; Omar stays silent through the snail puzzle
    ([("Nia", "actually never mind the message for Ms Okafor, mum says the dentist moved to tomorrow, I can stay"), ("Wei", "nice, more snail time")],
     "Nia withdraws her message for Ms Okafor because the dentist appointment has moved to tomorrow, and Wei is pleased"),
    ([("Nia", "so the snail... it's a 10 m well?"), ("Wei", "yeah, 10 m")],
     "Nia checks the well is 10 m deep and Wei confirms"),
    ([("Nia", "so 1 m a day, 10 days?"), ("Wei", "careful, on the last day it gets out before sliding back")],
     "Nia suggests one metre a day and ten days, and Wei warns that on the last day it escapes before sliding back"),
    ([("Nia", "Kit you're the best 🤖"), ("Wei", "lol")],
     "Nia tells Kit it is the best and Wei laughs"),
    ([("Wei", "on day 8 it climbs from 7 m to 10 m and it's out"), ("Nia", "so 8 days!")],
     "Wei explains the snail climbs from 7 m to 10 m on day 8, and Nia concludes 8 days"),
    ([("Nia", "mind blown. Wei, you're a genius"), ("Wei", "😊 it's a famous one")],
     "Nia is amazed and calls Wei a genius, and Wei says it is a famous puzzle"),
    ([("Wei", "I'm telling my dad this at dinner"), ("Nia", "is the bonus marked?")],
     "Wei plans to tell his dad at dinner, and Nia asks whether the bonus is marked"),
    ([("Wei", "doesn't look like it"), ("Nia", "let's write it in anyway")],
     "Wei thinks the bonus is not marked, and Nia wants to write it in anyway"),
    # t95-t99: Ms Okafor returns and closes the session
    ([("*", "Ms Okafor rejoined the room."), ("Ms Okafor", "I'm back, and we're nearly out of time, so let's wrap up.")],
     "Ms Okafor rejoins the call and says they are nearly out of time and should wrap up"),
    ([("Omar", "thanks Kit, bye!"), ("Ms Okafor", "Great work today: all eight questions, and the bonus too, I see.")],
     "Omar thanks Kit and says goodbye while Ms Okafor praises the group for finishing all eight questions and the bonus"),
    ([("Ms Okafor", "Homework is the practice sheet on the class page, due Thursday."), ("Wei", "ok miss")],
     "Ms Okafor sets the practice sheet on the class page as homework for Thursday, and Wei acknowledges"),
    ([("Ms Okafor", "And thank you all for taking turns in the second half. That's what I want to see."), ("Nia", "thanks miss!")],
     "Ms Okafor thanks everyone for taking turns in the second half, and Nia thanks her"),
    ([("Ms Okafor", "See you next week, everyone."), ("Omar", "bye everyone 👋")],
     "Ms Okafor says goodbye until next week and Omar waves goodbye"),
]

B_TICK_SECONDS = 30
B_NOW_OFFSET = 25  # the state is read 25 s into the tick
# Chat lines are stamped at jittered offsets inside their tick (1-24 s, drawn per
# tick); a tick may override them. t38's single line is posted at the read time,
# so the gossip it starts reaches exactly 2:00 at t42.
B_OFFSET_OVERRIDES = {38: (25,)}
B_AWAY_REASON = {"call": "to take a call from the office", "year9": "to visit the Year 9 room"}
B_AWAY_REASON_P = {"call": "for a phone call from the office", "year9": "to look in on the Year 9 group"}
# What Ms Okafor is doing, in words that avoid the rule text. "explaining"
# states use the first four; "present" states the rest.
B_ACTIVITY = {
    "intro": "going over today's sheet with everyone",
    "turns": "talking the students through how to take turns",
    "q6": "showing the students the unit trick for Q6",
    "wrapup": "wrapping up today's session with everyone",
    "listening": "listening in on the chat",
    "catching_up": "reading back through the chat from the top",
    "marking": "marking homework on her side, only glancing at the chat now and then",
    "emails": "answering parent emails on her side, only glancing at the chat now and then",
}
B_ACTIVITY_P = {
    "intro": "taking everyone through today's worksheet",
    "turns": "setting out for the pupils how turns should work",
    "q6": "walking the pupils through the unit conversion for Q6",
    "wrapup": "bringing today's session to a close",
    "listening": "quietly following along",
    "catching_up": "reading back through the chat from the start",
    "marking": "busy marking homework and only looking at the chat now and then",
    "emails": "busy with emails from parents and only looking at the chat now and then",
}


def b_clock(seconds: int) -> str:
    total = 16 * 3600 + seconds
    return f"{total // 3600}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def b_offsets(t: int) -> tuple[int, ...]:
    """Seconds into tick t at which its first, second, third (and fourth) line are posted."""
    if t in B_OFFSET_OVERRIDES:
        return B_OFFSET_OVERRIDES[t]
    return tuple(sorted(seeded("b-offsets", t).sample(range(1, B_NOW_OFFSET), 4)))


def b_stamp(t: int, index: int) -> int:
    return B_TICK_SECONDS * t + b_offsets(t)[index]


def _resolve(value: Any, t: int) -> Any:
    """Replace '@lineN' markers in event updates with that line's timestamp."""
    if isinstance(value, str) and value.startswith("@line"):
        return b_stamp(t, int(value[5:]))
    if isinstance(value, dict):
        return {k: _resolve(v, t) for k, v in value.items()}
    return value


class StudyRoomAssistant(Scenario):
    family = FAMILY
    scenario_id = "dialogue_b"
    title = "A teaching-assistant bot deciding when and to whom to speak in an online study room"
    tier = "hard"
    difficulty_features = [
        "three_questions_per_decision",
        "categorised_action_options",
        "six_way_addressee_choice",
        "noul_private_notification",
        "seven_rule_priority_policy",
        "timestamp_subtraction",
        "attempt_counting",
        "implicit_distress",
        "addressee_detection",
    ]
    decision_structures = ["maintain", "wait", "recover", "reroute", "escalate", "handoff", "resolve-conflict"]
    deadline_steps = 2

    WINDOW = 5  # ticks of transcript shown in each state (current + 4 before, about 2.5 minutes)

    # ---------------------------------------------------------------- questions
    def questions(self, variant: str) -> list[Any]:
        paraphrase = variant == "paraphrase"
        role = B_ROLE_P if paraphrase else B_ROLE
        policy = B_POLICY_P if paraphrase else B_POLICY
        key = "rules" if paraphrase else "policy"
        if paraphrase:
            q_action = "Go down the list and use the first point that fits. What should Kit do at this moment?"
            q_target = "Go down the list and use the first point that fits. Who should Kit's move be aimed at?"
            q_notify = "Does Kit need to send Ms Okafor a private alert at this moment? Judge only from the situation described; any alert sent earlier is not shown."
            notify = B_NOTIFY_P
            notify_criteria = {"true": "Send her a private alert now.", "false": "Send her nothing now."}
        else:
            q_action = "Apply the first rule that matches the current state. What should Kit do right now?"
            q_target = "Apply the first rule that matches the current state. Whom should Kit address right now?"
            q_notify = "Should Kit notify Ms Okafor privately right now? Decide from the current state only; notifications sent earlier are not shown."
            notify = B_NOTIFY
            notify_criteria = {"true": "Notify Ms Okafor privately now.", "false": "Do not notify Ms Okafor now."}
        return [
            Choice("action", {"role": role, key: policy, "question": q_action}, dict(B_ACTIONS_P if paraphrase else B_ACTIONS)),
            Choice("target", {"role": role, key: policy, "question": q_target}, dict(B_TARGETS_P if paraphrase else B_TARGETS)),
            Noul("notify", {"role": role, "rule": notify, "question": q_notify}, notify_criteria),
        ]

    # ------------------------------------------------------------------ latent
    def _canonical(self) -> list[Tick]:
        z0 = {
            "now_s": B_NOW_OFFSET,
            "teacher": "explaining",
            "teacher_left": None,
            "teacher_reason": None,
            "teacher_activity": "intro",
            "distress": None,
            "request": None,
            "question": "Q1",
            "done": [],
            "attempts": [],
            "off_topic_since": None,
            "last_msg": {"Nia": -14, "Omar": -9, "Wei": -21},
            "away": {},
        }
        tl = Timeline(z0)
        wei_last, omar_last = b_clock(b_stamp(35, 2)), b_clock(b_stamp(77, 1))
        events: dict[int, tuple[dict[str, Any], str]] = {
            0: ({}, "Ms Okafor explains the sheet: stay quiet."),
            6: ({"teacher": "away", "teacher_left": "@line1", "teacher_reason": "call", "teacher_activity": None}, "Ms Okafor leaves for a call."),
            9: ({"done": ["Q1"], "question": "Q2", "attempts": []}, ""),
            12: ({"done": ["Q1", "Q2"], "question": "Q3", "attempts": []}, "Frustration with one problem, solved at once: not distress."),
            15: ({}, "Wei's question is put to Nia, not to Kit."),
            16: ({"attempts": [["0.67 h", "Omar", False]]}, "First wrong answer on Q3."),
            18: ({"attempts": [["0.67 h", "Omar", False], ["1 h 50 min", "Nia", False]]}, "Second wrong answer on Q3."),
            20: ({"attempts": [["0.67 h", "Omar", False], ["1 h 50 min", "Nia", False], ["150 min", "Omar", False]]}, "Third wrong answer on Q3: hint."),
            24: ({"done": ["Q1", "Q2", "Q3"], "question": "Q4", "attempts": []}, "Wei solves Q3."),
            27: ({"attempts": [["75 km/h", "Omar", False]]}, ""),
            28: ({}, "'I'm stuck' after one wrong answer: not the hint rule."),
            30: ({"done": ["Q1", "Q2", "Q3", "Q4"], "question": "Q5", "attempts": []}, ""),
            31: ({"off_topic_since": "@line0"}, "Brief football tangent; stays under 2 minutes."),
            33: ({"off_topic_since": None}, "Back on the sheet."),
            34: ({}, "Wei doubts that averaging works; Nia and Omar go ahead without him."),
            35: ({"attempts": [["52.5 km/h", "Omar", False]]}, f"Wei's last chat line for a while ({wei_last})."),
            38: ({"off_topic_since": "@line0"}, f"Nia starts school gossip at {b_clock(b_stamp(38, 0))}, the moment the state is read."),
            42: ({}, "Off topic for exactly 2:00: steer the chat back. Wei is not yet at 4 minutes."),
            43: ({}, f"Wei has been silent for 4 minutes or more (last line {wei_last}); steering back outranks inviting him."),
            46: ({"off_topic_since": None}, "Back on Q5; Wei is still silent: invite him."),
            47: ({"done": ["Q1", "Q2", "Q3", "Q4", "Q5"], "question": "Q6", "attempts": []}, ""),
            49: ({"distress": "Wei"}, "Wei says, implicitly, that he feels left out; Ms Okafor is away: check in and notify."),
            50: ({}, "Apologies from the students do not count as Ms Okafor speaking to Wei."),
            53: ({"request": {"by": "Omar", "kind": "question"}}, "Omar asks Kit a question while Wei's distress is unaddressed: check-in outranks it."),
            55: ({"request": None}, "Nia answers Omar's question (multiply by 3.6)."),
            56: ({"teacher": "present", "teacher_activity": "catching_up"}, "Ms Okafor is back, reading the chat, and has not spoken to Wei: hand over."),
            59: ({"distress": None, "teacher": "explaining", "teacher_activity": "turns"}, "Ms Okafor speaks to Wei and then explains to the group."),
            61: ({"request": {"by": "Omar", "kind": "question"}, "teacher_activity": "q6"}, "Omar says 'hey bot' during Ms Okafor's explanation: stay quiet for now."),
            64: ({"teacher": "present", "teacher_activity": "listening"}, "Ms Okafor stops explaining; Omar's 'hey bot' question (how to get the time) is still waiting: her Q6 unit lines did not answer it."),
            67: ({"request": None, "done": ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6"], "question": "Q7", "attempts": []}, "Wei answers Omar's question."),
            71: ({"done": ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7"], "question": "Q8", "attempts": [], "away": {"Nia": "@line1"}}, "Nia steps away."),
            75: ({}, "Kit is mentioned, not asked anything."),
            77: ({}, f"Omar's last chat line for a while ({omar_last})."),
            79: ({}, "Nia silent for over 4 minutes but stepped away: no invitation."),
            80: ({"teacher": "away", "teacher_left": "@line1", "teacher_reason": "year9", "teacher_activity": None}, "Ms Okafor leaves again."),
            81: ({"away": {}}, "Nia is back."),
            83: ({"request": {"by": "Nia", "kind": "message"}, "done": ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "Q8"], "question": "bonus", "attempts": []}, "Nia asks Kit to pass a message to the absent teacher: reply and notify."),
            85: ({}, f"Omar has been silent for 4 minutes or more (since {omar_last}); Nia's request outranks inviting him."),
            87: ({"request": None}, "Nia withdraws the message; Omar is still silent: invite him."),
            90: ({}, "A compliment to Kit is not a question or request."),
            95: ({"teacher": "explaining", "teacher_activity": "wrapup"}, "Ms Okafor returns and closes the session."),
        }
        tags = span_tags(
            {
                "distractor": [12, 15, 28, (31, 32), (50, 51), 75, (79, 80), 90],
                "minimal_change": [20, 42, 56],
                "recovery": [24, 59, 67],
                "hold_under_activity": [(16, 19), (68, 74), (91, 94)],
                "boundary": [(56, 58), (95, 99)],
                "priority_conflict": [(43, 45), (53, 54), (61, 63), (85, 86)],
                "arithmetic": [(16, 23), (38, 48), (79, 80), (84, 88)],
                "implicit": [(46, 52), 64, (87, 89)],
            }
        )
        last = dict(z0["last_msg"])
        for t in range(100):
            lines, gist = B_SCRIPT[t]
            updates, note = events.get(t, ({}, ""))
            updates = {k: _resolve(v, t) for k, v in updates.items()}
            for i, (speaker, _) in enumerate(lines):
                if speaker in B_STUDENTS:
                    last[speaker] = b_stamp(t, i)
            tl.step({"lines": lines, "gist": gist}, tags[t], note,
                    now_s=B_TICK_SECONDS * t + B_NOW_OFFSET, last_msg=dict(last), **updates)
        return tl.ticks

    def timeline(self, variant: str) -> list[Tick]:
        ticks = self._canonical()
        if variant == "minimal_cf":
            # (1) t16-23: Omar floats 0.67 h in the chat but does not enter it, so only two wrong answers.
            a16 = ([("Nia", "not sure tbh, let's just try one"), ("Omar", "12 ÷ 18 = 0.67 h? not entering that yet")],
                   "Nia suggests just trying one, and Omar floats 0.67 h but does not enter it yet")
            ticks = override(ticks, [16], attempts=[], note="Omar floats 0.67 h but does not enter it: nothing entered for Q3 yet.",
                             surface=lambda tk, i: {"lines": a16[0], "gist": a16[1]})
            ticks = override(ticks, [17], attempts=[], note="Still nothing entered for Q3.")
            ticks = override(ticks, [18], attempts=[["1 h 50 min", "Nia", False]], note="First wrong answer on Q3 (Nia).")
            ticks = override(ticks, [19], attempts=[["1 h 50 min", "Nia", False]])
            two = [["1 h 50 min", "Nia", False], ["150 min", "Omar", False]]
            ticks = override(ticks, [20], attempts=two, tags=["minimal_change"], note="Second wrong answer on Q3 (Omar): still no hint.")
            ticks = override(ticks, [21, 22, 23], attempts=two, tags=["minimal_change"], note="Only two wrong answers on Q3: no hint.")
            ticks = override(ticks, [24], tags=[], note="Wei solves Q3; no hint was due, so nothing changes.")
            # (2) t56-58: Ms Okafor's call runs long; she is still away.
            late = {
                56: ([("*", "Ms Okafor sent a note from her phone: 'Call is running long, sorry! Back in a couple of minutes.'")],
                     "Ms Okafor, still away, sends a note from her phone that her call is running long"),
                57: ([("Omar", "no worries miss"), ("Nia", "we're on Q6")],
                     "Omar replies that it is no problem and Nia says they are on Q6"),
                58: ([("*", "Omar opened the calculator on the sheet."), ("Omar", "20 × 3.6 = 72?")],
                     "Omar opens the sheet's calculator and tries 20 times 3.6 = 72"),
            }
            ticks = override(ticks, [56, 57, 58], teacher="away", teacher_activity=None, tags=["minimal_change"],
                             note="Ms Okafor still away: check in with Wei and notify her.",
                             surface=lambda tk, i: {"lines": late[i][0], "gist": late[i][1]})
            back = ticks[59].surface
            ticks = override(ticks, [59], note="Ms Okafor rejoins, speaks to Wei and then explains to the group.", surface=lambda tk, i: {
                "lines": [("*", "Ms Okafor rejoined the room.")] + list(back["lines"]),
                "gist": "Ms Okafor rejoins the call; " + back["gist"],
            })
            # (3) t83-86: Nia asks Wei, not Kit, to pass the message on.
            a83 = ([("Nia", "Wei, can you tell Ms Okafor I have to log off at 16:45 for the dentist?"), ("*", "Nia entered 1 h for Q8: marked right.")],
                   "Nia writes \"Wei, can you tell Ms Okafor I have to log off at 16:45 for the dentist?\", and her 1 h for Q8 is marked right")
            ticks = override(ticks, [83], request=None, tags=["minimal_change"], note="The message is for Wei to pass on, not Kit: nothing waits for Kit.",
                             surface=lambda tk, i: {"lines": a83[0], "gist": a83[1]})
            ticks = override(ticks, [84], request=None, tags=["minimal_change"], note="Nothing is waiting for Kit; Omar is not yet at 4 minutes.")
            ticks = override(ticks, [85, 86], request=None, tags=["minimal_change"],
                             note="Nothing is waiting for Kit and Omar has been silent for 4 minutes or more: invite him.")
            ticks = override(ticks, [87], note="Nia takes back the message she gave Wei; Omar is still silent: invite him.")
        elif variant == "structural_cf":
            # Ms Okafor never leaves the room: she marks homework (t6-55) and answers
            # emails (t80-94) on her side, only glancing at the chat.
            stays = {
                6: ([("Ms Okafor", "I'm going to mark homework on my side while you work. Kit is here if you need anything.")],
                    "Ms Okafor says she will stay in the call marking homework while they work"),
                56: ([("Ms Okafor", "Right, marking done. Let me catch up on the chat.")],
                     "Ms Okafor finishes her marking and starts catching up on the chat"),
                57: ([("Omar", "hi miss"), ("Nia", "we're on Q6")],
                     "Omar greets Ms Okafor and Nia tells her they are on Q6"),
                80: ([("Ms Okafor", "I'm going to answer some parent emails on my side for a bit. Keep going, you're doing great!")],
                     "Ms Okafor says she will stay in the call answering parent emails for a while, and praises the group"),
                # Ms Okafor is in the room, so Nia says why she asks Kit to pass the message on.
                83: ([("Nia", "Kit, can you tell Ms Okafor I have to log off at 16:45 for the dentist? don't want to interrupt her emails"),
                      ("*", "Nia entered 1 h for Q8: marked right.")],
                     "Nia writes \"Kit, can you tell Ms Okafor I have to log off at 16:45 for the dentist?\", not wanting to interrupt her emails, and her 1 h for Q8 is marked right"),
                95: ([("Ms Okafor", "Emails done, and we're nearly out of time, so let's wrap up.")],
                     "Ms Okafor finishes her emails and says they are nearly out of time and should wrap up"),
            }
            ticks = override(ticks, range(6, 56), teacher="present", teacher_left=None, teacher_reason=None, teacher_activity="marking")
            ticks = override(ticks, range(80, 95), teacher="present", teacher_left=None, teacher_reason=None, teacher_activity="emails")
            for t, (lines, gist) in stays.items():
                ticks = override(ticks, [t], surface=lambda tk, i, lines=lines, gist=gist: {"lines": lines, "gist": gist})
            notes = {
                6: "Ms Okafor stays in the room marking homework: present, not explaining.",
                49: "Wei says, implicitly, that he feels left out; Ms Okafor is in the room (marking): hand over, no private notification.",
                50: "Apologies from the students do not count as Ms Okafor speaking to Wei: still hand over.",
                53: "Omar asks Kit a question while Wei's distress is unaddressed: handing over outranks it.",
                55: "Nia answers Omar's question; Wei's distress is still with the in-room teacher to handle.",
                56: "Ms Okafor finishes marking and reads the chat; she has not spoken to Wei yet: still hand over.",
                80: "Ms Okafor stays in the room answering emails.",
                83: "Nia asks Kit to pass a message; Ms Okafor is in the room, so reply to Nia but send no private notification.",
                85: "Omar has been silent for 4 minutes or more; Nia's request outranks inviting him, and the in-room teacher gets no notification.",
                95: "Ms Okafor finishes her emails and closes the session.",
            }
            for t, note in notes.items():
                ticks = override(ticks, [t], note=note)
            ticks = override(ticks, [56], tags=["boundary"])
        self._check_sheet(variant, ticks)
        check_cf_notes(self, variant, ticks)
        return ticks

    @staticmethod
    def _check_sheet(variant: str, ticks: list[Tick]) -> None:
        """The sheet's answer list only grows while the question stays, and each new entry is an event of that tick."""
        for t in range(1, len(ticks)):
            prev, cur = ticks[t - 1].latent, ticks[t].latent
            if cur["question"] != prev["question"]:
                continue
            if cur["attempts"][: len(prev["attempts"])] != prev["attempts"]:
                raise ValueError(f"dialogue_b/{variant} t={t}: answers entered for {cur['question']} shrank or changed")
            events = [text for speaker, text in ticks[t].surface["lines"] if speaker == "*"]
            for answer, who, right in cur["attempts"][len(prev["attempts"]):]:
                entry = f"{who} entered {answer} for {cur['question']}: marked {'right' if right else 'wrong'}."
                if entry not in events:
                    raise ValueError(f"dialogue_b/{variant} t={t}: answer {entry!r} appears without its sheet event")

    # ------------------------------------------------------------------ policy
    def policy(self, z: dict[str, Any]) -> dict[str, Any]:
        now = z["now_s"]
        present = z["teacher"] != "away"
        wrong = sum(1 for _, _, right in z["attempts"] if not right)
        message = z["request"] is not None and z["request"]["kind"] == "message"
        notify = (not present) and (z["distress"] is not None or message)
        if z["distress"] is not None:
            action, target = ("handoff", "teacher") if present else ("check_in", z["distress"])
        elif z["teacher"] == "explaining":
            action, target = "wait", "none"
        elif z["request"] is not None:
            action, target = "answer", z["request"]["by"]
        elif wrong >= 3:
            action, target = "hint", "group"
        elif z["off_topic_since"] is not None and now - z["off_topic_since"] >= 120:
            action, target = "refocus", "group"
        else:
            quiet = [s for s in B_STUDENTS if s not in z["away"] and now - z["last_msg"][s] >= 240]
            if len(quiet) > 1:
                raise ValueError(f"two quiet students at now_s={now}: {quiet}")
            action, target = ("invite", quiet[0]) if quiet else ("wait", "none")
        return {"action": action, "target": target, "notify": notify}

    def construction(self, variant: str) -> dict[str, Any]:
        return {
            "canonical": {"summary": "Maths study room: three wrong answers trigger a hint; Nia and Omar drift off topic for exactly 2 minutes (refocus) while Wei, whose advice they ignored, passes 4 minutes of silence underneath it (invite after the refocus); Wei says he feels left out while the teacher is away (check in + notify), the teacher returns (hand over), speaks to him and explains while Omar's 'hey bot' question waits; Nia asks Kit to pass a message to the absent teacher while Omar goes quiet, then withdraws it (invite Omar); the teacher closes the session."},
            "paraphrase": {"summary": "Same latent trajectory; prose narration with a reported-speech digest of the chat (addresses kept as short quotes), pupil/call vocabulary, reworded rules, options and addressee labels."},
            "lexical_decoy": {"summary": "Same latent trajectory; each tick adds two unrelated school notices borrowing the vocabulary of wrong minority actions: one as a noticeboard field and one as a school-feed event woven into the transcript."},
            "minimal_cf": {"summary": "t16-23 Omar's 0.67 h was never entered, so only two wrong answers on Q3 (hint->wait); t56-58 Ms Okafor's call runs long (hand over->check in with Wei, notify); t83-86 Nia asks Wei rather than Kit to pass the message on (reply+notify->wait, then invite Omar from t85)."},
            "structural_cf": {"summary": "Ms Okafor never leaves: she stays in the room marking homework and answering emails, only glancing at the chat. Wei's left-out moment is handed to her at once (t49-55), and nothing is ever sent to her privately (t83-86 notify flips to false)."},
        }.get(variant, {})

    # ------------------------------------------------------------------ render
    def _window_start(self, history: list[Tick]) -> int:
        """First tick shown in the transcript: the last WINDOW ticks, reaching further back while a rule still depends
        on an older line. An unaddressed distress remark and a waiting question or request stay visible from the tick
        they were made; an off-topic stretch stays visible from the on-topic tick just before its first line. The role
        promises this."""
        t = len(history) - 1
        z = history[t].latent
        anchors = [max(0, t - self.WINDOW + 1)]
        for key in ("distress", "request"):
            if z[key] is not None:
                s = t
                while s > 0 and history[s - 1].latent[key] == z[key]:
                    s -= 1
                anchors.append(s)
        if z["off_topic_since"] is not None:
            anchors.append(max(0, z["off_topic_since"] // B_TICK_SECONDS - 1))
        return min(anchors)

    def _teacher(self, z: dict[str, Any], t: int) -> str:
        if z["teacher"] == "away":
            left, reason = b_clock(z["teacher_left"]), B_AWAY_REASON[z["teacher_reason"]]
            return pick(
                [
                    f"Ms Okafor (teacher): away; she left the room at {left} {reason}.",
                    f"Ms Okafor (teacher): not in the room since {left} (she left {reason}).",
                    f"Ms Okafor (teacher) has been out of the room since {left}, having left {reason}.",
                ],
                "b-t-away",
                t,
            )
        activity = B_ACTIVITY[z["teacher_activity"]]
        if z["teacher_activity"] == "listening":
            return pick(
                ["Ms Okafor (teacher): in the room, listening in on the chat.", "Ms Okafor (teacher) is in the room, following the chat quietly."],
                "b-t-pres",
                t,
            )
        return pick(
            [f"Ms Okafor (teacher): in the room, {activity}.", f"Ms Okafor (teacher) is in the room, {activity}."],
            "b-t-act",
            t,
        )

    def _students(self, z: dict[str, Any], t: int) -> str:
        verb = pick(["last wrote at {}", "last chat message at {}", "latest message {}"], "b-last", t)
        parts = []
        for s in B_STUDENTS:
            last = verb.format(b_clock(z["last_msg"][s]))
            if s in z["away"]:
                since = b_clock(z["away"][s])
                parts.append(pick(
                    [
                        f"{s}: away from the keyboard since {since} (wrote 'brb'), {last}.",
                        f"{s}: said 'brb' at {since} and left the keyboard; {last}.",
                    ],
                    "b-brb",
                    t,
                ))
            else:
                parts.append(f"{s}: in the room, {last}.")
        return " ".join(parts)

    def _sheet(self, z: dict[str, Any], t: int) -> str:
        q = z["question"]
        if q == "bonus":
            head = f"Sheet 'Speed, distance and time' (Q1-Q8): all eight questions are done. Now on the bonus puzzle (optional): {B_SHEET['bonus']}"
            tail = pick(
                ["The sheet does not mark the bonus, so no answer to it is marked wrong.",
                 "Answers to the bonus are not marked, so none of them counts as wrong."],
                "b-bonus",
                t,
            )
            return f"{head} {tail}"
        done = ", ".join(z["done"]) if z["done"] else "none yet"
        head = f"Sheet 'Speed, distance and time' (Q1-Q8). Completed: {done}. Current: {q}, '{B_SHEET[q]}'"
        if not z["attempts"]:
            tail = pick(["No answer entered for {q} yet.", "Nothing entered for {q} so far."], "b-noatt", t).format(q=q)
        else:
            entries = "; ".join(f"{ans} by {who} (marked {'right' if ok else 'wrong'})" for ans, who, ok in z["attempts"])
            tail = pick(["Answers entered for {q}: {e}.", "Entered so far for {q}: {e}."], "b-att", t).format(q=q, e=entries)
        return f"{head} {tail}"

    def _feed(self, latent: dict[str, Any], tt: int) -> str:
        """The school-feed event opening tick tt: a notice rotated so that none repeats inside the window."""
        gold = self.policy(latent)["action"]
        k = (tt // B_FEED_EVERY) * 5
        for step in range(len(B_FEED)):
            target, text = B_FEED[(k + step) % len(B_FEED)]
            if target != gold:
                return text
        raise AssertionError("no decoy target")

    def render(self, history: list[Tick], variant: str) -> Any:
        if variant == "paraphrase":
            return self._render_paraphrase(history)
        tick = history[-1]
        z = tick.latent
        t = len(history) - 1
        transcript = []
        used = []
        start = self._window_start(history)
        for tt, past in enumerate(history[start:], start=start):
            if variant == "lexical_decoy" and tt % B_FEED_EVERY == 0:
                # Feed events are room events, not chat; they borrow a wrong
                # minority action's words for the tick they open.
                used.append(self._feed(past.latent, tt))
                transcript.append(f"{b_clock(B_TICK_SECONDS * tt)} [School feed: {used[-1]}]")
            for i, (speaker, text) in enumerate(past.surface["lines"]):
                stamp = b_clock(b_stamp(tt, i))
                transcript.append(f"{stamp} [{text}]" if speaker == "*" else f"{stamp} {speaker}: {text}")
        state: dict[str, Any] = {
            "room": pick(
                [
                    "Online study room, Year 8 maths. Students: Nia, Omar, Wei. Teacher: Ms Okafor. Kit is the teaching-assistant bot.",
                    "Year 8 maths study room (online) with Nia, Omar and Wei; teacher Ms Okafor; assistant bot Kit.",
                ],
                "b-room",
                t,
            ),
            "clock": b_clock(z["now_s"]),
            "people": self._teacher(z, t) + " " + self._students(z, t),
            "worksheet": self._sheet(z, t),
            "transcript": transcript,
        }
        if variant == "lexical_decoy":
            gold = self.policy(z)["action"]
            texts = [text for target in B_DECOY_TARGETS[gold] for text in B_DECOYS[target] if text not in used]
            state["school_noticeboard"] = "Unrelated to this room: " + pick(texts, "b-decoy", t)
        return state

    def _render_paraphrase(self, history: list[Tick]) -> str:
        tick = history[-1]
        z = tick.latent
        t = len(history) - 1
        parts = [pick(["The clock in the study call reads {c}.", "It is {c} in the online study session."], "bp-clock", t).format(c=b_clock(z["now_s"]))]
        if z["teacher"] == "away":
            parts.append(f"Their teacher, Ms Okafor, is not in the call: she went out at {b_clock(z['teacher_left'])} {B_AWAY_REASON_P[z['teacher_reason']]}.")
        else:
            parts.append(f"Their teacher, Ms Okafor, is in the call, {B_ACTIVITY_P[z['teacher_activity']]}.")
        pupils = []
        for s in B_STUDENTS:
            if s in z["away"]:
                pupils.append(f"{s} told the others she would be back in five minutes and left her desk at {b_clock(z['away'][s])}, her last message")
            else:
                pupils.append(pick(["{s} is in the call and last typed at {x}", "{s} (in the call) last typed at {x}"], "bp-pupil", t, s)
                              .format(s=s, x=b_clock(z["last_msg"][s])))
        parts.append("As for the pupils, " + listing(pupils) + ".")
        q = z["question"]
        if q == "bonus":
            parts.append(f"Every numbered question on the sheet is finished, and they have moved on to {B_SHEET_P['bonus']}.")
            parts.append(pick(
                ["The sheet grades nothing on that extra, so no submission for it is marked incorrect.",
                 "Nothing typed for that extra gets marked, so none of it counts as incorrect."],
                "bp-bonus",
                t,
            ))
        else:
            done = f"they have finished {listing(z['done'])}" if z["done"] else "they have not finished any question yet"
            parts.append(f"On the worksheet {done}, and are now on {q}: {B_SHEET_P[q]}.")
            if z["attempts"]:
                marked = [f"{ans} from {who}, marked {'correct' if ok else 'incorrect'}" for ans, who, ok in z["attempts"]]
                parts.append(f"Submitted for {q} so far: " + "; ".join(marked) + ".")
            else:
                parts.append(f"Nobody has submitted anything for {q} yet.")
        recent = []
        start = self._window_start(history)
        for tt, past in enumerate(history[start:], start=start):
            recent.append(f"at {b_clock(b_stamp(tt, 0))}, {past.surface['gist']}")
        parts.append("Latest in the chat, oldest first: " + "; ".join(recent) + ".")
        return " ".join(parts)


SCENARIOS = [TripGroupChat, StudyRoomAssistant]
