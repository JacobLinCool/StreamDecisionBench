# Presenter voice control

The presenter task evaluates a stage controller that replaces the human slide operator at an AV desk. The presenter asks for slides out loud ("Next slide, please"), and the controller follows them from streaming ASR on four channels: the presenter's lapel microphone, the session chair (Host), the floor microphone (Audience) and the clip player's soundtrack (Clip). Each scenario exposes six choice questions. The mode is the route; the slide and the captions contribute in every mode; the active mode adds its own fields.

| Scenario | Consumer | Questions active in the composed decision | Timeline |
| --- | --- | --- | --- |
| Conference talk | Projector, clip player, caption bar, presenter's confidence monitor, chair's tablet | Mode + slide + captions; talk adds the host cue; questions adds the question card and host cue; clip adds the clip state | 60 observations, 2 seconds each, 120 seconds total |
| Flood-barrier briefing | Same outputs | Same composition | 60 observations, 2 seconds each, 120 seconds total |

These are two separately authored situations: a conference talk with a demo clip and floor questions, and a public briefing with an animation, a question taken mid-talk and a chair who relays online requests. They are development scenarios for one initial measurement, not a held-out test population.

## Why latency matters here

The presenter waits for the slide she asked for before talking about it, as she would wait for a human operator; a late slide leaves a pause in the hall and on the stream, then has her talking over the previous slide. She points at a frame when she asks to hold the clip, so a late pause freezes a frame she has already passed. The caption bar must follow the voice that is on; caption delay lowers rated quality and understanding, most for hard-of-hearing viewers. The question card tells her to repeat a floor question for the stream before answering, and the chair's stand-by avoids dead air after a handback. At the recorded interval the decisive windows last one to three time steps.

## Public evidence and timing

Every state contains the clock, the session (talk, presenter, host), the deck (slide numbers, lower-case names, which slides have a clip, and the slide in force at tick 0) and the transcript. All times are ticks. A transcript entry is `{utterance_id, at, final_at, speaker, text, final}`; `at` is the tick at which the utterance's first hypothesis appeared.

A partial holds the recogniser's current hypothesis: lower-case words, no punctuation or apostrophes, numbers spelled out. Each newer hypothesis replaces it under the same identifier, and earlier hypotheses are not kept. The final adds capitals, punctuation, apostrophes and digits, can still change words, and never changes again. Each speaker has at most one partial, and it is that speaker's newest utterance. The final writes slide numbers and numbers from 10 up as digits and has no quotation marks. The recogniser is biased toward slide names and command phrases, so a hypothesis can show a command that a later hypothesis or the final corrects ("go to slide seven" becomes "Go to slide 11.", "pause the demo" becomes "Because the demo runs on battery, ..."); a short command can also appear already final. Speakers can overlap: a final can arrive while another speaker's newer partial is on screen. Every utterance keeps its identifier, onset and speaker and ends in a final; the recordings contain no abandoned hypotheses, which is a simplification of real recognisers.

The rules name three evidence tiers, and every question cites one:

| Tier | What counts | Used by |
| --- | --- | --- |
| Onset | That an utterance exists, with its speaker and `at` | Captions; the listening card; the end of a stand-by |
| Current text | The text shown now, partial or final, following every revision including back | The early pause of a looping clip; the chair's stand-by |
| Final text | Final utterances only | Mode, slide, playing or closing the clip, repeat and answer cards |

Every start or move the room sees or hears waits for the final, because a hypothesis can still be revised; current text is used only where a late answer loses its value and a wrong one is cheap and undone by the next hypothesis. There is no displayed-slide field, operator log or pre-extracted command in the state; the reference replays final commands from `deck.start_slide`.

Commands have a closed public form: one whole sentence of a final utterance, lower-cased with commas, apostrophes and a closing run of "." and "!" removed, made of, in this order, an optional lead-in word, exactly one command phrase and an optional "please". Sentences with any other word or character, and sentences ending in "?", are talk. Play works only in talk and clip mode. The chair's stand-by is lexical by design: it follows a sentence that ends with "back to you", optionally followed by the chair's first name. Only the presenter moves slides and controls the clip; only the host opens questions or closes the session.

The first state becomes visible at zero seconds, the last at 118 seconds, and the observation horizon ends at 120 seconds. Reference state is constant between releases. A model's response can arrive between releases; the application keeps its previous complete decision until a new answer is accepted.

## Conference talk

Mira Castell presents a low-power voice-control system. She moves through the deck by voice, goes back to the demo slide, plays and holds the demo clip, closes it, hands back to the chair, and answers one floor question after repeating it.

| Public change | Expected effect |
| --- | --- |
| "next slide" partial grows into "Next slide shows the demo, ..." | No slide change at any tick |
| "go to slide seven" partial finalised as "Go to slide 11." | Slide 11 at the final; never slide 7 |
| Clip soundtrack says "Next slide." | Captions show the clip; slide and mode unchanged |
| "hold it" partial in clip mode | Clip paused at once; the final keeps it paused |
| The looping clip speaks again while "pause the demo" is revised to "because the demo runs on" | Captions follow the newest onset; early pause, then the clip plays again |
| "next slide" inside a longer sentence | No slide change |
| "back to you" in a partial revised to "back to your phone" | Stand-by, then listen |
| Floor question partial, then final ending in "?" | Listening, then repeat until she says "The question is ..." |

This trajectory has 24 changes to the composed reference decision.

## Flood-barrier briefing

Ines Harrow presents a flood barrier for a water board. She asks to play the animation on a slide without a clip, corrects herself, says "hold on to your seats" (an early pause that lapses at the final), then pauses the animation, and takes a question the chair opens mid-talk, answering it before repeating it. The chair relays an online request for a slide, which only the presenter can grant; she declines in a question.

| Public change | Expected effect |
| --- | --- |
| "Play the animation." on a slide without a clip | Nothing happens |
| "Oh, it's on the next one. Next slide, please." | The second sentence moves the slide |
| "hold" partial finalised as "Hold on to your seats." | Early pause, then the clip plays again |
| Slide command in clip mode | The clip closes and the slide moves |
| The chair starts speaking before her sentence is final | Captions switch to the chair at the chair's onset |
| Presenter answers before repeating the question | The card stays on repeat |
| Host relays "Go back to slide 3, please." | No slide change |
| "go back to slide three" finalises as "Go back to slide 3? Not today. ..." | No slide change |
| "the path back to you" revised to "the path back to union street" | Stand-by, then listen |

This trajectory has 22 changes to the composed reference decision.

## Composition and reference validation

The published `decision_spec` identifies the route question, globally required questions and active questions for each route. Both model and reference answers pass through that same composition. An incorrect mode remains an incorrect decision; a wrong inactive branch answer does not invalidate an otherwise correct applied decision.

The reference implementation recognises the published command form and the authored English sentences. It is an executable oracle for these controlled scenarios, not a general-purpose speech parser. Tests cover speaker roles, negated, question-form and malformed commands, slide numbers outside the deck, partial commands that must wait for the final, early pauses that lapse on a revised partial or at the final, commands ordered by the arrival of their finals, overlapping speakers, reopening and closing, the question card, the stand-by and the published transcript conventions (one partial per speaker, lower-case partials, finals that never change, utterances that keep their identity and are never dropped).
