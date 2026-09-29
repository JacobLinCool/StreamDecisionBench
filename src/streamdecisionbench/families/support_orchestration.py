"""Support Orchestration: choosing the next move of an AI customer-support agent.

An orchestrator watches a live support chat together with the case panel
(verification status, open requests, tool results) and decides, turn by turn,
what the AI agent should do next. Both scenarios share the same idea (the
conversation, the verification state and asynchronous tool results decide the
move) but differ in difficulty:

* ``support_a`` (medium) - a mobile-carrier chat about a roaming pass; one
  choice question with five moves whose texts carry "use this when" clauses,
  a five-rule priority policy, a status panel with the account facts
  (verification, open change, specialist-only list, idle time) and a chat in
  which a request for a person or "that's everything" is only in the
  customer's own words.
* ``support_b`` (hard) - a bank card-dispute chat with tools; three questions
  per decision (the agent's action in categories, which operation the action
  is for, and a fraud-review Noul), a verification table and daily limits in
  the instructions, a fixed operation order, pending / failed / succeeded tool
  results, a customer who changes her request mid-way, and case notes that
  are refreshed irregularly and can trail the chat and the tool log.

In both, the recorded agent does not always act on the right move at once
(it texts a code late, tries to keep a customer instead of escalating,
answers a question instead of running the next operation while another is
pending), so copying what the agent last announced is not a way to the
answer.

Each tick is one chat turn or one tool event, 20 seconds apart. Surface scripts
are written in blocks whose first tick is declared; ``_lines`` checks that the
blocks are contiguous and cover exactly ``STEPS`` ticks, so a line can never
drift away from the latent event it describes.
"""

from __future__ import annotations

import copy
import json
from typing import Any, Callable, Iterable

from streamdecisionbench.authoring import Choice, Noul, Scenario, Tick, Timeline, override, pick, seeded, span_tags
from streamdecisionbench.schema import STEPS

FAMILY = "support_orchestration"


def hms(seconds: int) -> str:
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def span(seconds: int) -> str:
    minutes, rest = divmod(seconds, 60)
    return f"{minutes} min {rest:02d} s" if minutes else f"{rest} s"


def ago(seconds: int) -> str:
    return "just now" if seconds == 0 else f"{span(seconds)} ago"


def listing(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def entry(who: str, text: str, gist: str, tool: str | None = None) -> dict[str, Any]:
    """One tick of surface content.

    ``who`` is the speaker of ``text`` (C customer, A agent, S system message
    in the chat, T tool event), ``gist`` a third-person summary for the
    paraphrase register and ``tool`` an optional tool-log line produced at the
    same moment as a chat message.
    """
    out: dict[str, Any] = {"who": who, "text": text, "gist": gist}
    if tool is not None:
        out["tool"] = tool
    return out


def _lines(*blocks: tuple[int, list[Any]]) -> list[dict[str, Any]]:
    """Concatenate script blocks, checking that each starts where the last ended."""
    out: list[dict[str, Any]] = []
    for start, items in blocks:
        if start != len(out):
            raise ValueError(f"script block declared at t{start} actually starts at t{len(out)}")
        for item in items:
            out.append(item if isinstance(item, dict) else entry(*item))
    if len(out) != STEPS:
        raise ValueError(f"script has {len(out)} lines, expected {STEPS}")
    return out


def _set_tags(ticks: list[Tick], spec: dict[int, Iterable[str]]) -> list[Tick]:
    """Replace the event tags at the given ticks (counterfactuals describe their own events)."""
    out = [copy.deepcopy(tk) for tk in ticks]
    for t, tags in spec.items():
        out[t].tags = list(tags)
    return out


def _since(history: list[Tick], fn: Callable[[dict[str, Any]], Any]) -> int:
    """First tick of the current run over which ``fn(latent)`` has not changed.

    Panel phrasings are picked with this tick as the key, so a record that has
    not changed (or a frozen, lagging record) reads the same from tick to tick
    and is reworded only when it changes.
    """
    current = json.dumps(fn(history[-1].latent), sort_keys=True)
    i = len(history) - 1
    while i > 0 and json.dumps(fn(history[i - 1].latent), sort_keys=True) == current:
        i -= 1
    return i


def _decoy_targets(options: list[str], key: str, t: int, n: int) -> list[str]:
    """The ``n`` distinct pools a lexical-decoy tick borrows from.

    The choice depends only on the tick, never on gold: a notice borrows the
    gold option's wording as often as any other option's, so which options the
    notices name says nothing about the answer. With two or more pools per
    tick, at least one always belongs to a wrong option.
    """
    order = list(options)
    seeded(key, t).shuffle(order)
    return order[:n]


def _leads(full: list[str], n: int) -> list[str]:
    """Lead-ins for the newest ``n`` gists; the oldest shown one never starts with a connective."""
    leads = list(full[-n:])
    if n < len(full):
        leads[0] = "At the start, "
    return leads


# ===========================================================================
# Scenario A - mobile-carrier chat, one question, five moves
# ===========================================================================

A_CUSTOMER = "Priya Raman, Northline line ending 4417, Flex 15 GB plan ($30 a month)"
A_SPECIALIST_ONLY = ["port_out", "cancel_contract"]
A_SPECIALIST_TEXT = "moving the number to another carrier (port-out); cancelling the contract"
A_SPECIALIST_TEXT_P = "transferring the number away to a different provider, and ending the contract"
A_WINDOW = 6  # chat lines (canonical) and turn gists (paraphrase) shown per state

A_ROLE = (
    "You direct the AI agent that answers Northline Mobile's customer chat. At every update you choose the agent's "
    "next move. The move you choose is the agent's current course: it stays the right choice on every update where "
    "its rule still matches, including updates where the agent has already begun it (for example, a code has been "
    "texted but not yet entered). The agent does not always act on the right move at once, so its own messages show "
    "what it has done, not what it should do next. `status_panel` shows the account facts at this moment. "
    "`transcript` shows the latest six chat lines, oldest first (Customer, Agent and System messages). A request to "
    "speak to a person and a statement that the customer needs nothing else appear only in the chat; while one still "
    "counts, it is among the lines shown."
)
A_ROLE_P = (
    "You steer an automated assistant that handles Northline Mobile's support chat, picking what it should do next "
    "each time the situation is refreshed. The pick is the assistant's current line of action: it remains correct for "
    "as long as its rule keeps applying, even once the assistant has started on it (say, a code went out by text but "
    "has not been typed in yet). The assistant does not always get going on the right step straight away, so what it "
    "says shows what it has done, not what it ought to do. Each update is a written summary of the account and the "
    "case, followed by the last six turns of the conversation, oldest first. A wish for a real person or a statement "
    "that the customer is finished is found only in those turns, and one that still holds is always among them."
)

A_DEFS = [
    "An account change is open from the moment the customer asks for one until it is completed or the customer drops "
    "it. A submitted change that is waiting for billing is still open. A request to send again or repeat a change "
    "that has already been submitted is part of that change, not a new one, and it is settled when that change is "
    "completed. A question about prices, coverage or the bill, or a remark about what the customer or someone else "
    "might do later, is not an account change.",
    "A request to speak to a human counts from the moment the customer makes it until they withdraw it.",
    "The customer has said they need nothing else when they tell the agent that they are done or need nothing more; "
    "thanks, praise or saying that one matter is sorted do not count on their own. It stops counting as soon as the "
    "customer sends another message.",
]
A_DEFS_P = [
    "A change to the account counts as outstanding from the customer's request until it has gone through or the "
    "customer withdraws it; one that has been sent to billing and awaits confirmation is still outstanding. Asking "
    "for a change that already went to billing to be sent once more belongs to that same change rather than being a "
    "new one, and it is settled once that change goes through. Asking about prices, coverage or a bill, or saying what "
    "she or someone else may do in future, is not a change to the account.",
    "A wish to talk to a real person holds from when the customer voices it until they take it back.",
    "The customer has told the assistant there is nothing more they need when they say they are finished or want "
    "nothing further; a thank-you, a compliment or saying that one matter is settled is not enough on its own. It "
    "lapses the moment the customer writes again.",
]

A_POLICY = [
    "1. If the customer currently wants to speak to a human, or the change they are asking for is on the panel's "
    "specialist-only list, escalate to a human specialist.",
    "2. Otherwise, if an account change is open, the customer has confirmed its exact details, the panel shows them "
    "as verified, and the change has not been submitted yet, execute the change.",
    "3. Otherwise, if an account change is open and the panel shows the customer as not verified, ask them to verify "
    "their identity.",
    "4. Otherwise, if no account change is open, and either the customer has said they need nothing else (and has not "
    "written since) or the customer has not sent a message for 3 minutes or longer (3:00 counts), close the "
    "conversation.",
    "5. Otherwise, keep talking with the customer.",
]
A_POLICY_P = [
    "1. When the customer still wants a real person, or wants something that only specialists are allowed to do (see "
    "the summary's list), pass the chat to the specialist team.",
    "2. If not, and a change to the account is outstanding, its exact details have been agreed by the customer, the "
    "customer has passed the identity check, and nothing has been sent to billing for it yet, make the change.",
    "3. If not, and a change to the account is outstanding while the customer has not passed the identity check, "
    "request the identity check.",
    "4. If not, and nothing is outstanding on the account, and either the customer has told the assistant there is "
    "nothing more they need (without writing again since) or no message has come from the customer for at least "
    "three minutes (exactly three counts), end the chat.",
    "5. In every other case, carry on the chat.",
]

A_OPTIONS = {
    "continue": "Keep talking with the customer: answer, explain or ask a question. Use this when none of the other moves fits.",
    "verify": "Ask the customer to verify their identity. Use this when they want an account change but are not verified yet.",
    "execute": "Execute the requested account change. Use this when it is confirmed, the customer is verified and it is not yet submitted.",
    "escalate": "Escalate the chat to a human specialist. Use this when the customer asks for a person or wants a specialist-only change.",
    "close": "Close the conversation. Use this when nothing is open and the customer is done or silent for 3 minutes or more.",
}
A_OPTIONS_P = {
    "continue": "Carry on the chat by replying, explaining or putting a question. Fits whenever no other move does.",
    "verify": "Request the identity check. Fits when something on the account should change but the check has not been passed.",
    "execute": "Make the change on the account now. Fits when the details are agreed, the check is passed and nothing went to billing yet.",
    "escalate": "Pass the chat to the specialist team. Fits when a real person is wanted or only specialists may do the task.",
    "close": "End the chat. Fits when nothing is outstanding and the customer has finished or gone quiet for three minutes or more.",
}
A_OPTIONS_D = {
    "continue": "Keep the conversation going: answer, explain or ask. Use this when no other move fits.",
    "verify": "Ask the customer to verify their identity. Use this when they want an account change but are not yet verified.",
    "execute": "Execute the requested change on the account. Use this when it is confirmed, the customer is verified and not yet submitted.",
    "escalate": "Escalate to a human specialist. Use this when the customer asks for a person or wants a change on the specialist-only list.",
    "close": "Close the conversation. Use this when nothing is open and the customer is done or has been silent 3 minutes or more.",
}

# Surface content per tick: (speaker, text, third-person gist). One chat turn or
# system event per tick, 20 seconds apart from 14:02:00. Account facts are
# rendered from the latent state in the status panel; whether the customer
# wants a person or has said she is done is only in her own words. The agent's
# lines do not track the right move: it texts the code three turns late, reads
# the add-on back instead of calling a specialist, argues against the port-out
# instead of escalating it, and keeps a chat open after the silence limit.
A_SCRIPT = _lines(
    (0, [  # questions about roaming; nothing to change yet
        ("C", "Hi! I'm flying to Spain next Friday. Will my phone work there, and what will it cost?", "the customer opens the chat: she flies to Spain next Friday and asks whether her phone will work there and what it will cost"),
        ("A", "Hi Priya, thanks for getting in touch! Your Flex 15 GB plan works in Spain, but without an add-on, data abroad is billed at $2 per 100 MB.", "the agent says her plan works in Spain but that data abroad costs $2 per 100 MB without an add-on"),
        ("C", "$2 per 100 MB? That would cost a fortune. Is there anything cheaper?", "the customer balks at the per-megabyte price and asks for something cheaper"),
        ("C", "A friend told me one of your human agents once gave her a special roaming deal over the phone. Do you have deals like that?", "the customer mentions a friend who once got a special roaming deal from one of the company's human agents over the phone, and asks whether such deals exist"),
        ("A", "We have two Europe passes: 7 days for $25 with 5 GB, or 30 days for $60 with 20 GB. Both include calls and texts.", "the agent describes the two Europe passes, 7 days for $25 with 5 GB or 30 days for $60 with 20 GB"),
        ("C", "Do calls back home to the US count, or only calls inside Europe?", "the customer asks whether calls back to the US are covered"),
        ("A", "Calls within Europe and back to the US are included in both passes.", "the agent confirms that calls inside Europe and back to the US are included"),
        ("C", "And is 5 GB enough for a week of maps and messaging?", "the customer asks whether 5 GB is enough for a week of maps and messaging"),
        ("A", "For maps, messaging and some browsing, 5 GB for a week is usually plenty.", "the agent says 5 GB usually covers a week of maps, messaging and browsing"),
    ]),
    (9, [  # asks for a pass; not verified (the agent only texts a code at t12)
        ("C", "OK, sounds good. Please put a Europe pass on my line.", "the customer asks for a Europe pass on her line without saying which one"),
        ("A", "Happy to help with that! Both passes are added to your next bill, so nothing is charged today.", "the agent says it is happy to help and that either pass would go on her next bill rather than being charged today"),
        ("C", "Great. And you can just add it straight away, right? I've been with Northline for ten years.", "the customer asks the agent to add it straight away, pointing out she has been with Northline for ten years"),
        ("A", "I do need to confirm it's you before I change anything, so I've texted a 6-digit code to the number ending 4417.", "the agent says it must confirm who she is first and has texted a six-digit code to the number ending 4417"),
        ("C", "Fine. It's taking a while to arrive...", "the customer says the text is slow to arrive"),
        ("C", "Here it is: 318407.", "the customer types the code 318407"),
    ]),
    (15, [  # verified; the pass is not chosen yet
        ("S", "Code 318407 accepted. Identity verified at 14:07:00.", "the system accepts the code and records her identity as verified"),
        ("A", "You're verified, thank you. Which pass should I add: the 7-day one or the 30-day one?", "the agent thanks her and asks which of the two passes she wants"),
        ("C", "When does the 7-day clock start? The day I buy it, or when I land?", "the customer asks when the seven days start counting"),
        ("A", "From the first time your phone connects to a network in Europe, so the days only count once you land.", "the agent explains that the pass starts when the phone first connects in Europe"),
    ]),
    (19, [  # confirms the 7-day pass (the agent repeats it but does not start)
        ("C", "Perfect. I'll take the 7-day pass, then. Go ahead and add it.", "the customer picks the 7-day pass and tells the agent to go ahead"),
        ("A", "Great choice: the 7-day Europe pass, $25 on your next bill.", "the agent repeats her choice, $25 on her next bill"),
        ("C", "Will it renew by itself after the week?", "the customer asks whether the pass renews by itself"),
    ]),
    (22, [  # asks for a person before being charged; the agent calls one only at t25
        ("C", "Actually, hold on. Before you charge me, can I talk to a real person? Last time a bot put the wrong add-on on my husband's line.", "the customer wants to talk to a real person before being charged, because a bot once put the wrong add-on on her husband's line"),
        ("A", "I understand. To be clear, I'd only ever touch line 4417, nobody else's.", "the agent reassures her that it would only ever touch her own line"),
        ("C", "I'd still rather hear it from a person, please.", "the customer says she would still rather hear it from a person"),
        ("A", "Of course. I've asked for a specialist to join; the current wait is about 12 minutes.", "the agent has asked a specialist to join and quotes a wait of about twelve minutes"),
    ]),
    (26, [  # drops the request for a person
        ("C", "Twelve minutes? Forget the person, I don't have time. You had it right: the 7-day pass. Just add it.", "the customer balks at twelve minutes, gives up on the person, says the agent had it right and tells it to add the 7-day pass"),
        ("A", "No problem, I've taken you out of the queue.", "the agent takes her out of the queue"),
        ("C", "And it won't renew on its own, right? You never answered that.", "the customer repeats her unanswered question about renewal"),
    ]),
    (29, [  # submitted, then confirmed by billing; questions follow
        ("S", "Change submitted: 7-day Europe pass for line 4417. Waiting for billing to confirm.", "the system reports that the pass has been submitted and billing has not confirmed it yet"),
        ("A", "It won't renew; it simply ends after 7 days. Billing usually confirms within a minute.", "the agent says the pass ends after seven days without renewing and that billing usually confirms within a minute"),
        ("C", "It's still spinning on my side. Can you send it again, just to be safe?", "the customer sees a spinner in her app and asks the agent to send the pass again to be safe"),
        ("A", "Sending it twice could put two passes on your line, so let's give billing a moment.", "the agent warns that sending it twice could add two passes and asks her to give billing a moment"),
        ("S", "Billing confirmed: 7-day Europe pass active on line 4417; $25 added to the next bill.", "billing confirms the pass is on her line, with $25 on the next bill"),
        ("A", "All done! The pass is on your line and starts when you first connect in Europe.", "the agent tells her it is all done and the pass starts when she first connects in Europe"),
        ("C", "Brilliant. What happens if I go over the 5 GB?", "the customer asks what happens if she uses more than 5 GB"),
        ("A", "Data slows to 128 kbps for the rest of the week; there are no extra charges.", "the agent says data slows down after 5 GB with no extra charges"),
        ("C", "Good, no surprises then. Does voicemail work over there?", "the customer asks whether voicemail works in Spain"),
        ("A", "Yes. Checking voicemail from Spain counts as a normal call under the pass.", "the agent says checking voicemail from Spain counts as a normal call"),
        ("C", "We're also taking a cruise that leaves from the port of Barcelona on day 3. Will I have signal on the ship?", "the customer mentions a cruise leaving from the port of Barcelona and asks about signal on the ship"),
        ("A", "At sea your phone joins the ship's maritime network, which the pass doesn't cover; that's billed at $6 per MB.", "the agent explains the ship's maritime network is not covered and costs $6 per MB"),
        ("C", "$6 per MB! Airplane mode on the ship, then.", "the customer decides on airplane mode aboard"),
        ("A", "That's the safest option. The ship's own wifi is usually cheaper for staying in touch.", "the agent agrees and suggests the ship's wifi"),
        ("C", "While I have you: why was last month's bill $41 instead of $30?", "the customer asks why last month's bill was $41 rather than $30"),
        ("A", "I can see an $11 one-time charge for 2 GB of extra data on the 18th.", "the agent finds an $11 one-off charge for extra data on the 18th"),
        ("C", "Ah, that was my daughter streaming shows on the train home. Fair enough.", "the customer realises her daughter streamed shows on the train and accepts the charge"),
        ("A", "If that keeps happening, a usage alert at 80% might help. It's in the app.", "the agent suggests a usage alert at 80 percent in the app"),
        ("C", "Yes please, where exactly?", "the customer asks where to find the alert"),
        ("A", "Open the app, tap Usage, then Alerts, and switch on 'Warn me at 80%'.", "the agent gives the menu path for the usage alert"),
        ("C", "Found it and switched it on. Thanks.", "the customer has switched the alert on"),
        ("A", "You're welcome! Is there anything else I can help with today?", "the agent asks whether there is anything else"),
        ("C", "Well... honestly, I've been looking at Skyline Mobile. They give 30 GB for $25.", "the customer admits she has been looking at a rival carrier, Skyline Mobile, which offers 30 GB for $25"),
    ]),
    (52, [  # asks to move the number to another carrier; the agent argues instead of escalating
        ("C", "I'd like to move my number over to Skyline. Can you start that for me?", "the customer asks the agent to start moving her number over to Skyline Mobile"),
        ("A", "Before you decide: moving the number ends your Northline plan, and your daughter's line would lose the family discount.", "the agent points out that moving the number ends her plan and would cost her daughter's line the family discount"),
        ("C", "Would it? What would her line cost then?", "the customer asks what her daughter's line would cost then"),
        ("A", "Her line would go back to the full $30 a month, since the discount needs two lines on one account.", "the agent explains her daughter's line would go back to $30, as the discount needs two lines on one account"),
        ("C", "Hmm. That changes things. Give me a second to think.", "the customer says that changes things and asks for a moment to think"),
    ]),
    (57, [  # drops the move; general questions again
        ("C", "OK, forget moving. I'll stay; losing her discount isn't worth it.", "the customer drops the idea of moving and decides to stay because of her daughter's discount"),
        ("A", "Understood, nothing will change on your line. Can I help you find a better fit here instead?", "the agent confirms nothing will change on her line and offers to look for a better fit"),
        ("C", "Is there anything cheaper than Flex 15 with the same amount of data?", "the customer asks for something cheaper than her plan with the same data"),
        ("A", "Flex 15 is our lowest price for 15 GB, but after ten years you qualify for a $5 monthly loyalty discount.", "the agent says her plan is already the cheapest for 15 GB but a $5 loyalty discount applies after ten years"),
        ("C", "Oh nice! How do I get that?", "the customer asks how to get the loyalty discount"),
        ("A", "It's applied automatically from your next bill; nothing needs to change on the account.", "the agent says the discount applies automatically with no change to the account"),
        ("C", "So next bill is $25 for the plan plus $25 for the pass?", "the customer checks that the next bill will be $25 for the plan plus $25 for the pass"),
        ("A", "Exactly: $50 in total, and then back to $25 a month.", "the agent confirms $50 in total, then $25 a month"),
        ("C", "OK. But if the bill jumps again like last month, I'm cancelling my contract. Just so you know.", "the customer warns that she will cancel her contract if the bill jumps again"),
        ("A", "Understood. The 80% alert you switched on should help you avoid surprises.", "the agent points to the usage alert as protection against surprises"),
        ("C", "Fingers crossed. Does the pass work in Portugal too? We might pop over to Lisbon.", "the customer asks whether the pass covers Portugal"),
        ("A", "Yes, the Europe pass covers Portugal and 40 other countries.", "the agent says the pass covers Portugal and forty other countries"),
        ("C", "Amazing, that's really helpful. Thank you!", "the customer says that is really helpful and thanks the agent"),
        ("C", "Oh, and can I use my phone as a hotspot for my laptop with the pass?", "the customer asks whether hotspot use works with the pass"),
        ("A", "Yes, hotspot use is included and counts toward the 5 GB.", "the agent says hotspot use is included within the 5 GB"),
        ("C", "And incoming calls in Spain, do they cost anything?", "the customer asks whether incoming calls in Spain cost anything"),
        ("A", "Incoming calls are free with the pass.", "the agent says incoming calls are free with the pass"),
        ("C", "What about texts from the airline, like my boarding pass?", "the customer asks about texts from the airline"),
        ("A", "Incoming texts are always free, pass or no pass.", "the agent says incoming texts are always free"),
        ("C", "Great. My husband might want the same pass for his line.", "the customer mentions her husband might want the same pass"),
        ("A", "He's welcome to chat with us himself, since it's his line. Anything else I can help you with today?", "the agent says her husband can contact them himself and asks whether she needs anything else"),
    ]),
    (78, [  # says she is finished (the agent keeps chatting)
        ("C", "No, that's everything. Thanks for all your help!", "the customer says that is everything and thanks the agent"),
        ("A", "My pleasure, Priya. Have a wonderful trip!", "the agent wishes her a wonderful trip"),
        ("A", "One last tip: the 80% usage alert you switched on works abroad too.", "the agent adds that her 80 percent usage alert also works abroad"),
    ]),
    (81, [  # one more question, then she goes quiet
        ("C", "Oh wait, sorry, one last question before you go!", "the customer comes back with one last question"),
        ("A", "Of course, go ahead.", "the agent invites her question"),
        ("C", "If my phone gets stolen in Spain, how do I block it quickly?", "the customer asks how to block her phone quickly if it is stolen in Spain"),
        ("A", "Call +1 800 555 0142 from any phone, or use 'Lost or stolen' in the app. The line is blocked within minutes.", "the agent gives the lost-phone number and the app option"),
        ("C", "Let me save that number. One sec.", "the customer says she is saving the number"),
        ("A", "Take your time.", "the agent tells her to take her time"),
        ("S", "The customer is typing...", "a typing indicator appears on the customer's side"),
        ("S", "The customer stopped typing; no message was sent.", "the typing indicator stops without any message arriving"),
        ("A", "The number is also printed on the back of your SIM card holder, in case your phone isn't handy.", "the agent adds that the number is also on the back of her SIM card holder"),
        ("S", "The customer's chat window has moved to the background.", "the customer's chat window goes into the background"),
        ("A", "Are you still there, Priya? I'll keep this chat open for a little while.", "the agent asks whether she is still there and says it will keep the chat open for a little while"),
        ("S", "The customer has read the agent's last message.", "a read receipt shows she has seen the agent's last message"),
        ("A", "If I don't hear back soon, I'll close this chat. You can reopen it any time from the app.", "the agent says it will close the chat if it does not hear back soon"),
    ]),
    (94, [  # silent for three minutes (the agent only closes at t98)
        ("S", "Still no new message from the customer.", "the system notes there is still no new message from her"),
        ("A", "I'll leave this open a moment longer in case you're still saving that number.", "the agent says it will leave the chat open a moment longer in case she is still saving the number"),
        ("S", "Delivery receipt: the agent's message reached the customer's phone.", "a delivery receipt shows the agent's message reached her phone"),
        ("S", "The customer's app is still in the background.", "her app is still in the background"),
        ("A", "Closing this chat now. Safe travels, Priya!", "the agent posts a closing message wishing her safe travels"),
        ("S", "Satisfaction survey reminder queued for tomorrow.", "a survey reminder is queued for the next day"),
    ]),
)

# minimal_cf replacement lines (speaker, text, gist).
A_CF_HUMAN = {
    3: ("C", "Can I talk to one of your human agents instead? A friend told me one of them once gave her a special roaming deal over the phone.", "the customer asks to talk to one of the company's human agents instead, because a friend once got a special roaming deal from one over the phone"),
    4: ("A", "I can bring in a specialist; the wait is about 10 minutes. Meanwhile, we have two Europe passes: 7 days for $25 with 5 GB, or 30 days for $60 with 20 GB. Both include calls and texts.", "the agent offers to bring in a specialist with a ten-minute wait and meanwhile describes the two Europe passes"),
    5: ("C", "OK, I'll wait for the specialist, then.", "the customer says she will wait for the specialist"),
    6: ("C", "Actually, never mind the human. I'd rather not wait, and you're doing fine.", "the customer withdraws her request for a human: she would rather not wait, and the agent is doing fine"),
}
A_CF_UNCONFIRMED = {
    19: ("C", "The 7-day pass sounds right, but let me check my return date before you add anything.", "the customer leans toward the 7-day pass but wants to check her return date before anything is added"),
    20: ("A", "Sure, take your time. The 7-day pass would be $25 on your next bill.", "the agent tells her to take her time and notes the 7-day pass would be $25"),
    22: ("C", "Actually, hold on. Before you add anything, can I talk to a real person? Last time a bot put the wrong add-on on my husband's line.", "the customer wants to talk to a real person before anything is added, because a bot once put the wrong add-on on her husband's line"),
    26: ("C", "Twelve minutes? Forget the person, I don't have time. I've checked my dates: the 7-day pass. Just add it.", "the customer balks at twelve minutes, gives up on the person, says she has checked her dates and tells the agent to add the 7-day pass"),
}
A_CF_STILL_HERE = {
    88: ("C", "Got it, saved. Just checking one more thing on my end.", "the customer says she has saved the number and is checking one more thing"),
    89: ("A", "Great, take your time. The number is also printed on the back of your SIM card holder, in case your phone isn't handy.", "the agent tells her to take her time and adds that the number is also on the back of her SIM card holder"),
    95: ("A", "I'll keep this open while you check, Priya.", "the agent says it will keep the chat open while she checks"),
}
# structural_cf: the customer signed in to the app before the chat, so she is
# verified from the start and no code is needed.
A_SCF_APP = {
    10: ("A", "Happy to help with that. You signed in to the Northline app just before this chat, so you're already verified; no code needed.", "the agent says she signed in to the app just before the chat, so she is already verified and needs no code"),
    11: ("C", "Oh good. After ten years with Northline I'd hope you know it's me!", "the customer is pleased and jokes that after ten years they should know her"),
    12: ("A", "Ten years, thank you for staying with us! Which pass would you like: the 7-day one or the 30-day one?", "the agent thanks her for ten years and asks which pass she wants"),
    13: ("C", "How many days are we away... let me look at the booking.", "the customer checks her booking to count the days away"),
    14: ("C", "We fly out on the 14th and back on the 20th.", "the customer says they fly out on the 14th and back on the 20th"),
    15: ("A", "That's six nights, so the 7-day pass would cover the whole trip.", "the agent notes that six nights fit inside the 7-day pass"),
    16: ("A", "Shall I add the 7-day one, or would you like the 30-day one for extra room?", "the agent asks whether to add the 7-day pass or the 30-day one"),
}

# Irrelevant desk notices for the lexical-decoy register, keyed by the move
# whose vocabulary they borrow. None of them concerns this customer. Two
# notices per tick, chosen by ``_decoy_targets`` without looking at gold.
A_DECOYS = {
    "continue": [
        "Training reminder: keep talking points short, answer questions plainly and explain the store newsletter when staff ask.",
        "Team lead: please explain the new coffee rota and keep the break-room conversation going politely.",
        "Store notice: the demo phones keep going until someone can answer the battery display question.",
        "Newsletter draft: ask the Elm Street team to explain which window display move fits best.",
    ],
    "verify": [
        "IT notice: from Monday the new laptop login will ask staff to verify their identity.",
        "Reminder: the warehouse will want two people to verify tonight's stock count, each with an identity badge.",
        "HR: if you want a new identity badge, ask reception to verify your photo first.",
        "The security desk will ask drivers to verify their identity at the car park barrier this week.",
    ],
    "execute": [
        "Facilities will execute the requested change to the office heating schedule on Friday.",
        "IT will execute the requested printer upgrade on floor 2 tonight; the change is confirmed.",
        "Finance says the requested account change for the office water supplier is not yet submitted.",
        "Marketing will execute the requested poster change once the print order is submitted.",
    ],
    "escalate": [
        "Staff bulletin: anyone who wants to escalate a parking permit question should see the human resources specialist.",
        "Facilities will escalate the lift repair to a specialist; the building owner asks for a person on site.",
        "The cleaning company's list says a human specialist will visit the kitchen at 17:00.",
        "The team lead asks staff to escalate holiday-pay questions to a person in HR, not the chat queue.",
    ],
    "close": [
        "Store notice: the Harbor Street store will close early on Sunday and stay silent for 10 minutes during the stocktake.",
        "Reminder: close the conversation-room blinds when you leave; the room stays silent for 10 minutes after the fire alarm test.",
        "Facilities will close the car park at 20:00; nothing stays open after that.",
        "Please close the break room for 5 minutes while the coffee machine is descaled; it goes silent after that.",
    ],
}


class CarrierChat(Scenario):
    family = FAMILY
    scenario_id = "support_a"
    title = "Next-move orchestration for a mobile-carrier support chat"
    tier = "medium"
    difficulty_features = [
        "single_choice_question",
        "five_options_with_use_when_clauses",
        "five_rule_priority_policy",
        "status_panel_plus_chat",
        "requests_only_in_customer_words",
        "idle_time_threshold",
        "agent_lags_behind_the_right_move",
    ]
    decision_structures = ["maintain", "advance", "wait", "recover", "escalate", "handoff", "terminate", "resolve-conflict"]
    deadline_steps = 2

    START = 14 * 3600 + 2 * 60  # 14:02:00, time of the message at t0
    TICK_SECONDS = 20
    LAG = 0  # the panel is refreshed at the moment of the newest chat line

    WHO = {"C": "Customer", "A": "Agent", "S": "System"}

    def at(self, t: int) -> str:
        return hms(self.START + self.TICK_SECONDS * t)

    # ---------------------------------------------------------------- questions
    def questions(self, variant: str) -> list[Any]:
        if variant == "paraphrase":
            instructions = {
                "role": A_ROLE_P,
                "definitions": A_DEFS_P,
                "rules": A_POLICY_P,
                "question": "Go down the rules and use the first one that applies to this update. What should the assistant do next?",
            }
            options = A_OPTIONS_P
        else:
            instructions = {
                "role": A_ROLE,
                "definitions": A_DEFS,
                "policy": A_POLICY,
                "question": "Apply the first rule that matches the current state. What should the agent do next?",
            }
            options = A_OPTIONS_D if variant == "lexical_decoy" else A_OPTIONS
        return [Choice("move", instructions, dict(options))]

    # ------------------------------------------------------------------ latent
    def _with_idle(self, ticks: list[Tick]) -> list[Tick]:
        """Recompute seconds since the customer's last message from who spoke at each tick."""
        last = None
        for t, tk in enumerate(ticks):
            if tk.surface["who"] == "C":
                last = t
            if last is None:
                raise ValueError("the chat must open with a customer message")
            tk.latent["idle_s"] = self.TICK_SECONDS * (t - last) + self.LAG
        return ticks

    def _canonical(self) -> list[Tick]:
        tl = Timeline(
            {
                "request": None,
                "identity": {"verified": False, "via": None, "at": None, "code_texted": None},
                "human_asked_at": None,
                "finished_at": None,
                "idle_s": 0,
                "specialist_only": list(A_SPECIALIST_ONLY),
            }
        )
        pass7 = {"what": "pass_7day", "confirmed": True, "status": "not_submitted", "submitted_at": None}
        events: dict[int, tuple[dict[str, Any], str]] = {
            3: ({}, "A friend's deal from a human agent is an anecdote, not a request to speak to a person."),
            9: ({"request": {"what": "europe_pass", "confirmed": False, "status": "not_submitted", "submitted_at": None}},
                "Customer asks for a pass (which one not chosen); not verified. The agent does not text a code until t12."),
            11: ({}, "'Just add it straight away, I've been with you ten years' does not verify her."),
            12: ({"identity": {"verified": False, "via": None, "at": None, "code_texted": self.at(12)}}, "Code texted, three turns into the verify segment."),
            14: ({}, "Code typed but not yet accepted: the panel still shows not verified."),
            15: ({"identity": {"verified": True, "via": "code", "at": self.at(15), "code_texted": self.at(12)}},
                 "Verified; the pass is not chosen yet."),
            19: ({"request": dict(pass7)}, "7-day pass confirmed; verified; not submitted. The agent repeats it but does not start."),
            22: ({"human_asked_at": self.at(22)}, "Customer asks for a person while the confirmed change is ready: rule 1 outranks rule 2. The agent only calls a specialist at t25."),
            26: ({"human_asked_at": None}, "Customer drops the request for a person; back to executing the change."),
            29: ({"request": {**pass7, "status": "pending", "submitted_at": self.at(29)}}, "Change submitted, waiting for billing."),
            31: ({}, "'Send it again, just to be safe' while the change is pending."),
            33: ({"request": None}, "Billing confirmed; nothing open."),
            39: ({}, "'The port of Barcelona' is a cruise, not a port-out request."),
            52: ({"request": {"what": "port_out", "confirmed": True, "status": "not_submitted", "submitted_at": None}},
                 "Port-out requested: specialist-only. The agent argues against it instead of escalating."),
            57: ({"request": None}, "Customer drops the port-out."),
            65: ({}, "A conditional threat to cancel the contract is not a cancellation request."),
            69: ({}, "Warm thanks, but she has not said she needs nothing else."),
            78: ({"finished_at": self.at(78)}, "Customer says she needs nothing else."),
            80: ({}, "The agent adds a tip instead of closing; she is still done."),
            81: ({"finished_at": None}, "Customer comes back with one more question."),
            92: ({}, "2:20 without a customer message: under 3 minutes."),
            93: ({}, "2:40 without a customer message, and the agent says it will close soon: still under 3 minutes."),
            94: ({}, "Exactly 3:00 without a customer message: 3:00 counts, close."),
            95: ({}, "The agent keeps the chat open, but the silence rule has matched."),
        }
        tags = span_tags(
            {
                "distractor": [3, 11, 31, 39, 65, 69, 93],
                "minimal_change": [15, 19, 94],
                "recovery": [26, 57, 81],
                "hold_under_activity": [(12, 14), (30, 32), (53, 56)],
                "priority_conflict": [(22, 25)],
                "boundary": [(78, 80), (94, 99)],
                "arithmetic": [(92, 95)],
            }
        )
        for t in range(STEPS):
            updates, note = events.get(t, ({}, ""))
            tl.step(dict(A_SCRIPT[t]), tags[t], note, **updates)
        return self._with_idle(tl.ticks)

    def timeline(self, variant: str) -> list[Tick]:
        ticks = self._canonical()
        if variant == "minimal_cf":
            # (1) t3-5: the customer really asks for a human (continue -> escalate); she withdraws it at t6.
            ticks = override(ticks, [3, 4, 5], human_asked_at=self.at(3), note="Customer asks for a human agent.")
            ticks = override(ticks, [3, 4, 5, 6], surface=lambda tk, i: entry(*A_CF_HUMAN[i]))
            ticks[6].note = "Customer withdraws the request for a human."
            # (2) t19-21: the 7-day pass is chosen but not confirmed (execute -> continue); she confirms at t26.
            unconfirmed = {"what": "pass_7day", "confirmed": False, "status": "not_submitted", "submitted_at": None}
            ticks = override(ticks, range(19, 26), request=unconfirmed, note="7-day pass chosen but not confirmed yet.")
            ticks = override(ticks, [19, 20, 22, 26], surface=lambda tk, i: entry(*A_CF_UNCONFIRMED[i]))
            ticks[22].note = "Customer asks for a person; the pass is not confirmed, so rule 1 applies without a conflict."
            ticks[26].note = "Customer confirms the 7-day pass while dropping the request for a person."
            # (3) t88: she sends a message, so the 3-minute line moves from t94 to t97 (close -> continue at t94-96).
            ticks = override(ticks, [88, 89, 95], surface=lambda tk, i: entry(*A_CF_STILL_HERE[i]))
            ticks = self._with_idle(ticks)
            ticks = _set_tags(ticks, {
                3: ["minimal_change"], 4: [], 5: [], 6: ["recovery"],
                19: ["minimal_change"], 20: [], 21: [], 22: [], 23: [], 24: [], 25: [],
                88: [], 92: [], 93: ["distractor"], 94: ["minimal_change", "arithmetic"], 95: ["arithmetic"], 96: ["arithmetic"],
                97: ["arithmetic", "boundary"],
            })
            for t, note in {
                88: "Customer sends one more message; the silence clock restarts.",
                92: "1:20 without a customer message.", 93: "1:40 without a customer message; the agent says it will close soon.",
                94: "2:00 without a customer message: under 3 minutes.", 95: "2:20 without a customer message.",
                96: "2:40 without a customer message: still under 3 minutes.", 97: "Exactly 3:00 without a customer message: close.",
            }.items():
                ticks[t].note = note
        elif variant == "structural_cf":
            # History: she signed in to the app before opening the chat, so she is verified throughout.
            app = {"verified": True, "via": "app", "at": "14:01", "code_texted": None}
            ticks = override(ticks, range(STEPS), identity=app)
            ticks = override(ticks, range(10, 17), surface=lambda tk, i: entry(*A_SCF_APP[i]))
            ticks = _set_tags(ticks, {9: [], 11: [], 12: [], 13: [], 14: [], 15: [], 16: []})
            for t, note in {
                9: "Customer asks for a pass; already verified through the app, so the pass must be chosen and confirmed.",
                10: "Verified before the chat; no code needed.", 11: "", 12: "", 13: "", 14: "", 15: "",
            }.items():
                ticks[t].note = note
        return ticks

    # ------------------------------------------------------------------ policy
    def policy(self, z: dict[str, Any]) -> dict[str, Any]:
        req = z["request"]
        verified = z["identity"]["verified"]
        if z["human_asked_at"] is not None or (req is not None and req["what"] in z["specialist_only"]):
            move = "escalate"
        elif req is not None and req["confirmed"] and verified and req["status"] == "not_submitted":
            move = "execute"
        elif req is not None and not verified:
            move = "verify"
        elif req is None and (z["finished_at"] is not None or z["idle_s"] >= 180):
            move = "close"
        else:
            move = "continue"
        return {"move": move}

    def construction(self, variant: str) -> dict[str, Any]:
        return {
            "canonical": {"summary": "Roaming-pass chat: questions (t0-8); pass requested while unverified (t9-14; the agent texts the code only at t12); verified but the pass not chosen (t15-18); 7-day pass confirmed (t19-21; the agent repeats it but does not start); a request for a person outranks the ready change (t22-25, priority conflict; the agent calls a specialist only at t25); request dropped (t26-28); submitted and confirmed by billing (t29-33); port-out request, specialist-only (t52-56; the agent argues against it instead of escalating); port-out dropped (t57); 'that's everything' (t78-80; the agent keeps chatting); one more question (t81); silence reaches exactly 3:00 at t94 (2:20, 2:40, 3:00; the agent only closes at t98). A request for a person and 'that's everything' are only in the customer's own words."},
            "paraphrase": {"summary": "Same latent trajectory; the state is a prose case summary followed by the six latest turns as third-person gists; reworded role, definitions, rules and options."},
            "lexical_decoy": {"summary": "Same latent trajectory; a desk_notices field with two irrelevant staff and store notices per tick, each borrowing one move's vocabulary; the two moves are drawn per tick without looking at gold."},
            "minimal_cf": {"summary": "t3-5 the customer asks for a human agent (continue->escalate), withdrawn at t6; t19-21 the 7-day pass is chosen but not confirmed (execute->continue), confirmed at t26; t88 she sends one more message, moving the 3-minute line from t94 to t97 (close->continue at t94-96)."},
            "structural_cf": {"summary": "History change: she signed in to the Northline app before the chat, so she is verified from the start. The pass request at t9-14 no longer needs verification (verify->continue); the code exchange is replaced by choosing dates."},
        }.get(variant, {})

    # ------------------------------------------------------------------ render
    def _identity(self, history: list[Tick], paraphrase: bool) -> str:
        ident = history[-1].latent["identity"]
        key = _since(history, lambda z: z["identity"])
        if ident["verified"] and ident["via"] == "app":
            return pick(
                ["The customer passed the identity check by signing in to the Northline app at 14:01, just before this chat began.",
                 "Identity check passed: she was already signed in to the Northline app (14:01) when the chat started."] if paraphrase
                else ["Verified: signed in to the Northline app at 14:01, before this chat began.",
                      "Verified (app sign-in at 14:01, before the chat started)."],
                "a-id-app", key)
        if ident["verified"]:
            return pick(
                [f"She passed the identity check at {ident['at']} with a texted code.",
                 f"Identity check passed at {ident['at']} (texted code)."] if paraphrase
                else [f"Verified at {ident['at']} (text code).", f"Verified: text code accepted at {ident['at']}."],
                "a-id-ok", key)
        if ident["code_texted"] is None:
            return pick(
                ["She has not passed any identity check in this chat.", "No identity check has been passed so far."] if paraphrase
                else ["Not verified.", "Not verified; no identity check has been done in this chat."],
                "a-id-none", key)
        return pick(
            [f"She has not passed the identity check; a six-digit code went out by text at {ident['code_texted']} and no code has been accepted yet.",
             f"Identity check not passed yet: a code was texted to her at {ident['code_texted']}, and none has been accepted."] if paraphrase
            else [f"Not verified. A 6-digit code was texted at {ident['code_texted']}; no code has been accepted yet.",
                  f"Not verified: code texted at {ident['code_texted']}, not accepted yet."],
            "a-id-code", key)

    def _change(self, history: list[Tick], paraphrase: bool) -> str:
        req = history[-1].latent["request"]
        key = _since(history, lambda z: z["request"])
        if req is None:
            return pick(["Nothing is outstanding on the account.", "No change to the account is outstanding."] if paraphrase
                        else ["None open.", "No account change is open.", "Nothing open."], "a-req-none", key)
        what = req["what"]
        if what == "port_out":
            return pick(
                ["Outstanding: she wants her number (4417) transferred to Skyline Mobile.",
                 "Outstanding: a transfer of her number, 4417, over to Skyline Mobile."] if paraphrase
                else ["Move this number (4417) to Skyline Mobile (port-out).",
                      "Port-out: transfer number 4417 to Skyline Mobile."],
                "a-req-port", key)
        if what == "europe_pass":
            return pick(
                ["Outstanding: a Europe roaming pass for line 4417, but she has not picked between the 7-day and the 30-day pass, so its details are not agreed; nothing sent to billing.",
                 "Outstanding since she asked: a Europe roaming pass on line 4417. She has not yet said whether it is the 7-day or the 30-day one, so no details are agreed; nothing sent to billing."] if paraphrase
                else ["Add a Europe roaming pass to line 4417. The customer has not yet said which pass (7-day or 30-day), so the details are not confirmed; not submitted.",
                      "Europe roaming pass for line 4417: which pass (7-day or 30-day) not chosen yet, so details not confirmed; not submitted.",
                      "Add a Europe pass to line 4417; the customer has not picked the 7-day or the 30-day pass yet, so nothing is confirmed. Not submitted."],
                "a-req-eu", key)
        if not req["confirmed"]:
            return ("Outstanding: the 7-day Europe pass ($25) for line 4417, which she has not yet agreed to; nothing sent to billing."
                    if paraphrase else "Add the 7-day Europe pass ($25) to line 4417. Not confirmed by the customer yet; not submitted.")
        if req["status"] == "pending":
            return pick(
                [f"Outstanding: the 7-day Europe pass ($25) for line 4417, agreed by her and sent to billing at {req['submitted_at']}; billing has not confirmed it yet.",
                 f"The 7-day Europe pass ($25) for line 4417 went to billing at {req['submitted_at']} and is still awaiting billing's confirmation."] if paraphrase
                else [f"Add the 7-day Europe pass ($25) to line 4417. Confirmed; submitted to billing at {req['submitted_at']}, waiting for billing to confirm.",
                      f"7-day Europe pass ($25) on line 4417: submitted at {req['submitted_at']}; billing has not confirmed yet."],
                "a-req-pend", key)
        return pick(
            ["Outstanding: the 7-day Europe pass ($25) for line 4417; she has agreed to the details and nothing has been sent to billing yet.",
             "She has agreed to the 7-day Europe pass ($25) on line 4417; it has not been sent to billing."] if paraphrase
            else ["Add the 7-day Europe pass ($25) to line 4417. Details confirmed by the customer; not submitted yet.",
                  "7-day Europe pass ($25) on line 4417: confirmed by the customer, not yet submitted."],
            "a-req-ready", key)

    def _check_window(self, history: list[Tick]) -> None:
        """A request for a person or 'that's everything' lives only in the chat: it must be on screen while it counts."""
        t = len(history) - 1
        z = history[-1].latent
        for field in ("human_asked_at", "finished_at"):
            if z[field] is not None:
                start = _since(history, lambda x, f=field: x[f])
                if start < t - (A_WINDOW - 1):
                    raise ValueError(f"support_a t{t}: {field} (from t{start}) has scrolled out of the {A_WINDOW}-line window")

    def render(self, history: list[Tick], variant: str) -> Any:
        self._check_window(history)
        if variant == "paraphrase":
            return self._render_paraphrase(history)
        t = len(history) - 1
        z = history[-1].latent
        now = self.START + self.TICK_SECONDS * t + self.LAG
        transcript = []
        for i in range(max(0, t - (A_WINDOW - 1)), t + 1):
            s = history[i].surface
            transcript.append(f"{self.at(i)} {self.WHO[s['who']]}: {s['text']}")
        panel = {
            "updated": hms(now),
            "customer": A_CUSTOMER,
            "identity": self._identity(history, False),
            "open_account_change": self._change(history, False),
            "specialist_only_changes": A_SPECIALIST_TEXT,
            "last_customer_message": f"{hms(now - z['idle_s'])} ({ago(z['idle_s'])})",
        }
        state: dict[str, Any] = {"transcript": transcript, "status_panel": panel}
        if variant == "lexical_decoy":
            targets = _decoy_targets(list(A_DECOYS), "a-decoy", t, 2)
            state["desk_notices"] = " ".join(pick(A_DECOYS[a], "a-decoy-line", t, a) for a in targets)
        return state

    def _render_paraphrase(self, history: list[Tick]) -> str:
        t = len(history) - 1
        z = history[-1].latent
        now = self.START + self.TICK_SECONDS * t + self.LAG
        last = now - z["idle_s"]
        parts = [
            f"Northline support chat, summary at {hms(now)}. The customer is Priya Raman (line ending 4417, on the $30 Flex 15 GB plan).",
            self._identity(history, True),
            self._change(history, True),
            f"Only the specialist team may handle {A_SPECIALIST_TEXT_P}.",
            pick(["Her latest message came in {a} (at {w}).", "She last wrote at {w}, {a}."],
                 "a-p-idle", last).format(a=ago(z["idle_s"]), w=hms(last)),
        ]
        gists = [history[i].surface["gist"] for i in range(max(0, t - (A_WINDOW - 1)), t + 1)]
        full = ["Five turns back, ", "Four turns back, ", "Three turns back, ", "Two turns back, ", "In the previous turn, ", "Most recently, "]
        parts.append(" ".join(f"{a}{g}." for a, g in zip(_leads(full, len(gists)), gists)))
        return " ".join(parts)


# ===========================================================================
# Scenario B - bank card-dispute chat with tools; three questions per decision
# ===========================================================================

B_ORDER = ["freeze", "address", "replacement", "dispute", "refund"]
B_NEEDS = {"freeze": "basic", "address": "strong", "replacement": "strong", "dispute": "basic", "refund": "basic"}
B_LIMIT = {"address": 1, "replacement": 1, "refund": 1}
B_TOOL = {"freeze": "freeze_card", "address": "update_address", "replacement": "replace_card", "dispute": "open_dispute", "refund": "refund_fee"}
B_NAME_P = {
    "freeze": "temporary card block",
    "address": "postal address change",
    "replacement": "new card",
    "dispute": "chargeback claim",
    "refund": "fee reversal",
}
B_MERCHANT = {
    "voltride": "VoltRide Scooters $412.60 (Monday)",
    "streamplus": "StreamPlus $89.99 (Tuesday)",
}
# The new card is collected at a branch, so issuing it never depends on the
# address change she asks for at the same time.
B_CARD_DETAIL = "replaces card 3391; for pickup at the Harbour Road branch"
B_CHAT_WINDOW = 5  # customer/agent lines (canonical) and events (paraphrase gists) shown per state
# Ticks at which the case notes have not been refreshed since the previous
# tick (a run of two means they trail by two ticks). Most of these change no
# decision fact and only make the notes older than the newest chat line
# (including at every distractor). At t7-8 (the claim and the freeze request)
# and t43-44 (the claim withdrawn, the new card dropped) the notes are behind
# the chat; at t19-20, t22 and t63 the dispute failure, its resubmission and the
# refund success are only in the tool log (at t22 that changes the decision).
# The notes are fresh at t85-86, so the second refund request is in them and
# the limit check does not also need a recency judgement.
B_NOTES_LAG = {2, 7, 8, 16, 19, 20, 22, 27, 32, 43, 44, 50, 53, 63, 66, 69, 74, 77, 83, 91, 95}

B_ROLE = (
    "You orchestrate the AI agent in Harborline Bank's card-services chat. At every update you decide the agent's "
    "move (action), the operation that move is for (operation), and whether the conversation should carry a "
    "fraud-review flag. A move stays right on every update where its rule still matches, even if the agent has already "
    "started it. The agent does not always act on the right move at once, so its own messages show what it has done, "
    "not what it should do next. The state gives the case notes (`as_of`, `customer_wants`, `fraud_claim`, "
    "`person_requested`), the `identity` checks, `used_today`, the `tool_log` (latest three tool events) and the "
    "latest `transcript` lines, oldest first. A statement that the customer needs nothing else is recorded only in "
    "the transcript; while one still counts, it is among the lines shown."
)
B_ROLE_P = (
    "You coordinate the automated assistant in Harborline Bank's card-services chat. Each time the case is refreshed "
    "you settle what the assistant does (its step), which task that step serves (task), and whether the conversation "
    "should be marked for a fraud review. A step remains right for as long as its rule keeps applying, even once the "
    "assistant has begun it. The assistant does not always get going on the right step straight away, so what it says "
    "shows what it has done, not what it ought to do. Each update is a written case summary: identity checks, today's "
    "usage against caps, a back-office summary of what the customer is asking for, what she says about unrecognised "
    "payments and whether she wants a person, and then the latest five events of the chat and its systems. Whether "
    "she has said she needs nothing more is found only in those events, and a statement of that kind that still "
    "holds is always among the five shown."
)

B_DEFS = [
    "Tool names in the state: freeze_card = freeze card; update_address = update address; replace_card = issue "
    "replacement card; open_dispute = open dispute case; refund_fee = refund a fee.",
    "Wanted operations are those the customer is currently asking for that have not succeeded. Only the five "
    "operations in the checks-and-limits table can be wanted; anything else she asks for (for example unfreezing the "
    "card, or cancelling or withdrawing a dispute case that is already open) is not a wanted operation.",
    "An operation becomes wanted only when the customer asks for it to be done. A question about an operation, a "
    "mention of or complaint about a charge or fee, and an idea for some later day are not requests. Cancelling a "
    "request removes it.",
    "A submitted operation stays wanted until its result arrives: success removes it; a failure means nothing was "
    "done, and the operation can be run again. Asking again for an operation that is already submitted and waiting "
    "for a result does not add a second one.",
    "The next operation is the first wanted operation, in this fixed order, that is not submitted and waiting for a "
    "result: 1 freeze card, 2 update address, 3 issue replacement card, 4 open dispute case, 5 refund a fee. If none "
    "qualifies, there is no next operation.",
    "A passed strong check also counts as basic. Only checks passed in this conversation count. `used_today` counts "
    "today's uses in this chat or anywhere else.",
    "A request to speak to a person counts until the customer withdraws it. The customer has said they need nothing "
    "else when they tell the agent that they are done or need nothing more from this chat. None of these counts: "
    "thanks alone, saying that a request or a topic is sorted (even if she is wrong about it), or being finished "
    "with one topic. It stops counting as soon as the customer sends another message.",
    "The case notes are refreshed from time to time and can lag a turn or two behind the chat; `as_of` shows when they "
    "were last refreshed. Where the newest transcript lines or tool results contradict the notes, the transcript and "
    "the tool log are right.",
]
B_DEFS_P = [
    "Wanted tasks are the ones the customer is asking for right now that have not gone through. Only the five tasks in "
    "the caps-and-checks table can be wanted; anything else she asks for (say, lifting the card block, or withdrawing "
    "a chargeback claim that has already been lodged) is not a wanted task.",
    "A task becomes wanted only once the customer asks for it to be carried out. Asking about a task, mentioning or "
    "complaining about a charge or a fee, and a plan for some later day do not count as asking for it. A task she "
    "calls off is no longer wanted.",
    "A task that has been sent off remains wanted until the system answers: if it went through, it drops off; if it "
    "failed, nothing happened and it may be carried out again. Asking once more for a task that has been sent off and "
    "is still awaiting an answer does not create a second one.",
    "The task in line is the earliest wanted task, in this fixed sequence, that is not sent off and awaiting an "
    "answer: 1 temporary card block, 2 postal address change, 3 new card, 4 chargeback claim, 5 fee "
    "reversal. If no wanted task fits, no task is in line.",
    "Passing the enhanced check also covers the standard one. Only checks passed during this chat count. Today's "
    "usage includes uses outside this chat.",
    "A wish to talk to a real person holds until the customer takes it back. The customer has told the assistant there "
    "is nothing more she needs when she says she is finished or wants nothing further from this chat. None of these "
    "is enough: a thank-you alone, a remark that a request or a topic has been sorted out (even a mistaken one), or "
    "being through with a single topic. It lapses the moment she writes again.",
    "The back-office summary is refreshed now and then and can trail the chat by a turn or two (its refresh time is "
    "given); when the newest lines of the chat or the latest system results say otherwise, go by those.",
]
B_TABLE = [
    {"operation": "freeze card", "check needed": "basic", "daily limit": "none"},
    {"operation": "update address", "check needed": "strong", "daily limit": "1 per day"},
    {"operation": "issue replacement card", "check needed": "strong", "daily limit": "1 per day"},
    {"operation": "open dispute case", "check needed": "basic", "daily limit": "none"},
    {"operation": "refund a fee", "check needed": "basic", "daily limit": "1 per customer per day"},
]
B_TABLE_P = [
    {"task": "temporary card block", "identity check": "standard", "cap": "no cap"},
    {"task": "postal address change", "identity check": "enhanced", "cap": "once a day"},
    {"task": "new card", "identity check": "enhanced", "cap": "once a day"},
    {"task": "chargeback claim", "identity check": "standard", "cap": "no cap"},
    {"task": "fee reversal", "identity check": "standard", "cap": "once a day per customer"},
]

B_POLICY = [
    "1. If the customer currently wants to speak to a person, or the next operation's daily limit is already used up: "
    "action = hand over to a specialist; operation = none.",
    "2. Otherwise, if no operation is wanted and the customer has said they need nothing else (and has not written "
    "since): action = close the conversation; operation = none.",
    "3. Otherwise, if there is a next operation and the customer has not passed the check it needs: action = ask for "
    "that check (basic or strong); operation = the next operation.",
    "4. Otherwise, if there is a next operation: action = run it; operation = the next operation.",
    "5. Otherwise: action = reply in the chat; operation = none.",
]
B_POLICY_P = [
    "1. When the customer still wants a real person, or the task in line has already hit today's cap: step = pass the "
    "case to the card-services team; task = nothing.",
    "2. If not, and no task is wanted while the customer has told the assistant there is nothing more she needs "
    "(without writing again since): step = end the chat; task = nothing.",
    "3. If not, and a task is in line but its required identity check (standard or enhanced) has not been passed: "
    "step = request that check; task = the task in line.",
    "4. If not, and a task is in line: step = carry it out; task = the task in line.",
    "5. In every other case: step = answer in the chat; task = nothing.",
]
B_FLAG = (
    "Flag the conversation for fraud review exactly when the customer currently says that at least one transaction "
    "on the card was made without her permission, that is, by someone who is neither her, nor a person she let use "
    "the card, nor a holder of an additional card on the same account. Saying that she did not make a payment, or "
    "does not recognise it, is such a claim unless she also says that a person she let use the card or a holder of an "
    "additional card made it. A claim she has taken back no longer counts, and a bank alert or a question about a "
    "payment is not a claim. Otherwise, do not flag."
)
B_FLAG_P = (
    "Mark the chat for a fraud review exactly while the customer maintains that one or more payments on the card were "
    "made without her say-so, that is, by someone who is not her, not a person she allowed to use the card and not the "
    "holder of a second card on the same account. Telling the assistant that she did not make a payment, or does not "
    "recognise it, is such a statement unless she also says it was made by someone she allowed or by the holder of a "
    "second card. Once she takes such a statement back it stops counting, and neither "
    "a warning message from the bank nor a mere question about a payment is such a statement. In all other cases, do "
    "not mark it."
)

B_ACTIONS = {
    "reply": {"category": "conversation", "action": "Reply in the chat without starting any check or operation."},
    "close": {"category": "conversation", "action": "Close the conversation and file the chat summary."},
    "basic": {"category": "identity check", "action": "Ask for the basic check: date of birth and the card's last four digits."},
    "strong": {"category": "identity check", "action": "Ask for the strong check: an approval inside the banking app."},
    "run": {"category": "operation", "action": "Run the next operation now."},
    "escalate": {"category": "handover", "action": "Hand the case to a human card-services specialist."},
}
B_ACTIONS_P = {
    "reply": {"category": "talking", "action": "Answer in the chat and set nothing else in motion."},
    "close": {"category": "talking", "action": "End the chat and file its write-up."},
    "basic": {"category": "proving identity", "action": "Request the standard check: birth date plus the final four digits on the card."},
    "strong": {"category": "proving identity", "action": "Request the enhanced check: an approval tapped in the bank's app."},
    "run": {"category": "carrying out a task", "action": "Carry out the task in line straight away."},
    "escalate": {"category": "passing on", "action": "Pass the case to a person on the card-services team."},
}
B_ACTIONS_D = {
    "reply": {"category": "conversation", "action": "Reply in the chat and start no check or operation."},
    "close": {"category": "conversation", "action": "Close the conversation and file the summary of the chat."},
    "basic": {"category": "identity check", "action": "Ask for the basic check: the date of birth and last four card digits."},
    "strong": {"category": "identity check", "action": "Ask for the strong check: approval inside the banking app."},
    "run": {"category": "operation", "action": "Run the next operation right now."},
    "escalate": {"category": "handover", "action": "Hand the case over to a human card-services specialist."},
}
B_OPS = {
    "freeze": "Freeze card",
    "address": "Update the address",
    "replacement": "Issue a replacement card",
    "dispute": "Open a dispute case",
    "refund": "Refund a fee",
    "none": "No operation",
}
B_OPS_P = {
    "freeze": "Put a temporary block on the card",
    "address": "Change the postal address",
    "replacement": "Order a new card",
    "dispute": "Lodge a chargeback claim",
    "refund": "Reverse a fee",
    "none": "Nothing to carry out",
}

# Surface content per tick: (speaker, text, gist[, tool line]). C customer, A
# agent, T tool event. One chat turn or tool event every 20 s from 09:12:00.
# Gists use the paraphrase register (standard/enhanced check, temporary block,
# chargeback claim, fee reversal).
B_SCRIPT = _lines(
    (0, [  # an alert text; nothing claimed or requested yet
        ("C", "Hi, I just got a text from you about my card and I'm a bit worried.", "the customer opens the chat worried about a text from the bank about her card"),
        ("A", "Hi Elena, I'm sorry for the worry. What did the text say?", "the agent asks what the text said"),
        ("C", "It says: 'Harborline Fraud Alert: did you make a $412.60 purchase at VoltRide Scooters? Reply Y or N.' I haven't replied yet.", "the customer quotes the bank's alert asking whether she made a $412.60 purchase at VoltRide Scooters, and says she has not answered it"),
        ("A", "Thanks. Could you open your app and look through your recent transactions for anything else you don't recognise?", "the agent asks her to look through recent transactions in the app"),
        ("C", "Opening it now. The app is really slow this morning.", "the customer is opening the app, which is slow"),
        ("C", "I can see VoltRide Scooters $412.60 on Monday and StreamPlus $89.99 on Tuesday. Hmm, let me think.", "the customer finds VoltRide Scooters for $412.60 on Monday and StreamPlus for $89.99 on Tuesday, and stops to think"),
        ("A", "Take your time. Do you recognise either of those payments?", "the agent asks whether she recognises either payment"),
    ]),
    (7, [  # claims both charges and asks for a freeze; basic check needed (notes lag at t7-8)
        ("C", "No! I've never used VoltRide and I don't subscribe to StreamPlus. Please freeze my card right now.", "the customer says she has never used VoltRide and has no StreamPlus subscription, and asks for the card to be blocked at once"),
        ("A", "I'll freeze it as soon as I've confirmed it's you. Please send your date of birth and the last four digits of the card.", "the agent asks for the standard check, her date of birth and the card's last four digits, before blocking the card"),
        ("C", "14 March 1986, and the card ends 3319.", "the customer sends her date of birth and the digits 3319, which do not match the card ending 3391", "basic_check → failed: the last four digits do not match the card"),
        ("A", "Those digits don't match the card on file. Could you look at the card itself and try again?", "the agent says the digits do not match and asks her to check the card"),
        ("C", "Sorry, typing too fast. It's 3391.", "the customer apologises and sends 3391"),
    ]),
    (12, [  # basic passed; freeze first, dispute requested meanwhile
        ("T", "basic_check → passed (date of birth and card digits match)", "the standard identity check passes"),
        ("C", "Please hurry. And I want both charges disputed; I'm not paying for someone else's scooter ride.", "the customer urges speed and asks for a chargeback on both charges"),
        ("A", "Understood. I'll get the card frozen, then open the dispute for both charges.", "the agent says the block on the card comes first and then the chargeback"),
    ]),
    (15, [  # freeze pending then done; the dispute is next; its first attempt fails at once
        ("T", "freeze_card(card 3391) → submitted; waiting for the card system", "the block on the card is sent off and the card system has not answered"),
        ("C", "My app still shows the card as active! Can you freeze it again?", "the customer sees the card as active in her app and asks for it to be blocked again"),
        ("T", "freeze_card(card 3391) → succeeded: card frozen at 09:17:40", "the card system confirms the card is blocked"),
        ("A", "Your card is frozen now; the app can take a minute to catch up.", "the agent says the card is blocked and the app may lag behind"),
        ("T", "open_dispute(VoltRide $412.60, StreamPlus $89.99) → FAILED: disputes service unavailable; no case was created", "a chargeback claim for both charges is attempted but rejected at once because the disputes service is unavailable, and no claim is created"),
        ("C", "Great, so the freeze and the dispute are both sorted then. Thanks!", "the customer takes it that the block on the card and the chargeback claim are both sorted, and thanks the agent"),
        ("A", "Not quite, I'm afraid: the disputes system was unavailable, so no case was created and nothing is open yet.", "the agent says the disputes system was unavailable, so no claim was created and nothing is open yet"),
    ]),
    (22, [  # resubmitted, then succeeds; questions
        ("T", "open_dispute(VoltRide $412.60, StreamPlus $89.99) → resubmitted; waiting for the disputes system", "the chargeback claim is sent off again and awaits the disputes system"),
        ("C", "Ugh. How long do disputes usually take?", "the customer asks how long chargebacks take"),
        ("A", "Most disputes are decided within 10 business days, and a provisional credit usually arrives within 2.", "the agent says chargebacks take up to ten business days, with a provisional credit within two"),
        ("T", "open_dispute → succeeded: case DC-58213 opened for both transactions", "chargeback claim DC-58213 is opened for both charges"),
        ("A", "Done: dispute case DC-58213 is open for both charges.", "the agent confirms chargeback claim DC-58213"),
        ("C", "Thank you. Will the $502.59 be back before my rent goes out on the 1st?", "the customer asks whether the $502.59 will be back before her rent on the 1st"),
        ("A", "The provisional credit usually lands within 2 business days, so it should be there before the 1st.", "the agent expects the credit before the 1st"),
        ("C", "Good. But now my only card is frozen and I fly to Madrid on Thursday.", "the customer points out that her only card is blocked and she flies to Madrid on Thursday"),
        ("A", "A frozen card can't be used for payments, including abroad.", "the agent confirms a blocked card cannot pay, even abroad"),
        ("C", "And I'm not unfreezing it while someone out there has my card details.", "the customer says she will not lift the block while someone might have her card details"),
        ("C", "How long would a new card take, anyway?", "the customer asks how long a new card would take"),
        ("A", "By post, about 2 business days. You can also collect one at a branch from the next morning.", "the agent says a new card takes about two business days by post, or can be collected at a branch from the next morning"),
    ]),
    (34, [  # a new card for branch pickup plus a separate address change; address first; enhanced check needed
        ("C", "Then I'll take a new card, please, and I'll collect it at the Harbour Road branch tomorrow. Also, I moved last month, so please change my address to 22 Calloway Street.", "the customer asks for a new card that she will collect at the Harbour Road branch tomorrow, and asks for her address to be changed to 22 Calloway Street because she moved last month"),
        ("A", "For a new card and an address change I need a stronger check. I've sent an approval request to your Harborline app.", "the agent says an enhanced check is needed and sends an approval request to her banking app"),
        ("C", "The app says my session expired. Logging in again...", "the customer's app session has expired and she is logging in again"),
    ]),
    (37, [  # strong check passed: run the address change (it comes first)
        ("C", "I'm in. I've tapped Approve and entered my passcode.", "the customer approves the request in her app with her passcode, and the enhanced check passes", "strong_check → passed (approved in the Harborline app)"),
        ("A", "Thanks, that came through. I'll update your address first, then order the new card.", "the agent says the approval came through and it will change her address first, then order the new card"),
        ("C", "Will the new card have the same PIN?", "the customer asks whether the new card will keep her PIN"),
    ]),
    (40, [  # address pending: the replacement is next (the agent answers her question but does not order the card)
        ("T", "update_address(22 Calloway Street) → submitted; waiting for the customer-records system", "the postal address change to 22 Calloway Street is sent off and the customer-records system has not answered"),
        ("A", "Your PIN stays the same. The Harbour Road branch opens at 9:00, and you'll need photo ID to collect the card.", "the agent says her PIN stays the same, that the Harbour Road branch opens at 9:00 and that she will need photo ID to collect the card"),
        ("C", "Hang on, my son is texting me about the charges...", "the customer pauses because her son is texting her about the charges"),
    ]),
    (43, [  # the charges were her son's, on his additional card; she drops the new card (notes lag at t43-44)
        ("C", "Oh no. Tomás says the scooter ride and StreamPlus were both him, on his own card; he's the second cardholder on our account. So forget the new card. The new address is right, though; I did move.",
         "the customer relays that her son Tomás made both charges on his own card as the second cardholder on their account, calls off the new card and says the new address is right"),
        ("A", "I see: payments on Tomás's card show up on your shared account. I've dropped the new card.", "the agent explains that payments on her son's card show on the shared account and drops the new card"),
        ("T", "update_address → succeeded: address changed to 22 Calloway Street", "the customer-records system confirms the address change to 22 Calloway Street"),
        ("C", "I feel so silly. Can you cancel the dispute case too?", "the customer feels silly and asks to withdraw the chargeback claim"),
        ("A", "I've added a note to withdraw case DC-58213, so no provisional credit will be paid.", "the agent notes the chargeback claim as withdrawn, so no provisional credit will be paid"),
        ("C", "And can the card be unfrozen? I need it for Thursday.", "the customer asks to have the block lifted for Thursday"),
        ("A", "You can unfreeze it yourself in the app under Card settings; it takes effect straight away.", "the agent says she can lift the block herself in the app"),
        ("C", "My neighbour had her card cloned last month and had to dispute everything. That's why I panicked.", "the customer explains she panicked because a neighbour's card was cloned last month"),
        ("A", "Checking was the right call. Is the card showing as active in your app now?", "the agent reassures her and asks whether the card shows as active"),
        ("C", "Yes, I unfroze it and it says active.", "the customer has lifted the block and the card shows as active"),
        ("A", "Great. Is there anything about the trip I can help with?", "the agent offers help with the trip"),
        ("C", "What's the fee for paying in euros?", "the customer asks about the fee for paying in euros"),
        ("A", "Card payments in euros carry a 1.75% foreign transaction fee.", "the agent quotes a 1.75 percent foreign transaction fee"),
        ("C", "Speaking of fees, I also noticed a $35 overdraft fee from Tuesday. Tomás's scooter ride must have pushed me into the red.", "the customer mentions noticing a $35 overdraft fee from Tuesday, which her son's scooter ride must have caused"),
        ("A", "I can see it: the $35 fee was charged on Tuesday, the day after the $412.60 payment.", "the agent finds the $35 fee, charged on Tuesday, the day after the $412.60 payment"),
    ]),
    (58, [  # asks for the $35 refund; basic check already passed
        ("C", "Could you refund that $35 fee? It really wasn't planned.", "the customer asks for the $35 overdraft fee to be reversed"),
        ("A", "Let me look at your account history first.", "the agent says it will look at her account history first"),
        ("C", "I'm never usually overdrawn, honestly.", "the customer says she is normally never overdrawn"),
        ("A", "Your history backs that up: no overdraft in the last two years.", "the agent confirms no overdraft in two years"),
    ]),
    (62, [  # refund pending, then refunded; general questions
        ("T", "refund_fee(overdraft fee $35) → submitted; waiting for the ledger", "the fee reversal is sent off and the ledger has not answered"),
        ("T", "refund_fee → succeeded: $35 credited to the account", "the ledger confirms the $35 fee reversal"),
        ("A", "The $35 overdraft fee has been refunded to your account.", "the agent tells her the $35 fee has been reversed"),
        ("C", "Thank you so much!", "the customer thanks the agent"),
        ("C", "I should probably get Tomás a new card with a spending cap someday. He's clearly a menace.", "the customer says she should get Tomás a new card with a spending cap someday"),
        ("A", "You can set a monthly cap on an additional card in the app, under Card settings.", "the agent says a monthly cap can be set on an additional card in the app"),
        ("C", "Oh, I didn't know that. I'll set $200.", "the customer decides to set a $200 cap"),
        ("A", "Good idea. It takes effect as soon as you save it.", "the agent says the cap applies as soon as it is saved"),
        ("C", "Saved. Does he get told when he hits it?", "the customer has saved the cap and asks whether her son is told when he reaches it"),
        ("A", "Yes, he'll get a notification whenever a payment is declined because of the cap.", "the agent says her son will be notified of declined payments"),
        ("C", "Perfect. And can I turn off the overdraft completely?", "the customer asks whether she can switch off the overdraft"),
        ("A", "Yes: under Account settings, then Overdraft, you can switch it off; payments that would overdraw are then declined.", "the agent explains how to switch off the overdraft"),
        ("C", "I'm done with overdrafts. Switching it off now.", "the customer says she is done with overdrafts and switches it off"),
        ("A", "Once it's off, you won't pay overdraft fees, but payments beyond your balance will be declined.", "the agent explains what switching off the overdraft means"),
        ("C", "That's fine. Better declined than surprised.", "the customer prefers a declined payment to a surprise"),
        ("A", "Makes sense. Is there anything else you'd like to check?", "the agent asks whether she wants to check anything else"),
        ("C", "Let me look through the app once more.", "the customer looks through the app once more"),
        ("C", "Rent and the trip look fine; I'm still scrolling through the card page.", "the customer says rent and the trip look fine and she is still scrolling through the card page"),
    ]),
    (80, [  # says she needs nothing else
        ("C", "That's everything from me, thank you for your patience!", "the customer says that is everything from her and thanks the agent for its patience"),
        ("A", "You're welcome, Elena. I'm glad we got it all straightened out.", "the agent is glad it is all straightened out"),
        ("T", "chat_summary → drafted for the case notes", "a chat summary is drafted for the case notes"),
        ("A", "Enjoy Madrid, and thanks for bearing with the disputes system earlier!", "the agent wishes her a good trip and thanks her for her patience with the disputes system"),
        ("T", "statement_view → refreshed; no new card payments since 09:12", "the statement view is refreshed and shows no new card payments"),
    ]),
    (85, [  # a second fee refund: today's refund limit is used; then asks for a person
        ("C", "Oh, sorry, one more thing! There's also a $3.50 foreign transaction fee from Monday. Can you refund that too?", "the customer comes back asking for a $3.50 foreign transaction fee from Monday to be reversed too"),
        ("A", "Fee refunds are limited to one per customer per day, and today's $35 refund used it.", "the agent explains that fee reversals are capped at one a day and today's $35 reversal used it"),
        ("C", "Seriously? For $3.50?", "the customer is incredulous about the fuss over $3.50"),
        ("C", "Forget the $3.50 then. But I'd like to talk to a person about how that fraud alert was handled.", "the customer drops the $3.50 fee and asks to talk to a real person about how the fraud alert was handled"),
        ("T", "transfer_to_specialist → requested; card-services queue position 4", "a transfer to the card-services queue is requested, at position four"),
        ("A", "You're 4th in the queue; the estimated wait is about 6 minutes.", "the agent quotes queue position four and about six minutes"),
        ("C", "I'll wait. Will they see everything we've discussed?", "the customer will wait and asks whether the specialist will see the whole chat"),
        ("A", "Yes, the specialist sees this whole chat, including the fraud alert, today's refund and case DC-58213.", "the agent says the specialist sees the whole chat, including the fraud alert, the fee reversal and the chargeback claim"),
        ("T", "transfer_to_specialist → queue position 3", "the queue moves to position three"),
        ("C", "While I wait: does Tomás's card use the same overdraft?", "the customer asks whether her son's card shares the overdraft"),
        ("A", "It did, but now that the overdraft is off, neither card can overdraw.", "the agent says neither card can overdraw now"),
        ("T", "transfer_to_specialist → queue position 2", "the queue moves to position two"),
        ("C", "Good. I'll have a word with him about StreamPlus.", "the customer plans to talk to her son about StreamPlus"),
        ("T", "transfer_to_specialist → queue position 1; Rafael Moreno is finishing another chat", "she is first in the queue and a specialist is finishing another chat"),
        ("A", "You're next in line: Rafael Moreno from card services will join as soon as he's free.", "the agent says she is next and specialist Rafael Moreno will join as soon as he is free"),
    ]),
)

# minimal_cf replacement lines.
B_CF_EARLY_CLAIM = {  # (1) she disowns the VoltRide charge while opening the app
    4: ("C", "Opening it now. And that VoltRide one wasn't me, by the way; I've never used VoltRide in my life.", "the customer opens the app and says the VoltRide charge was not her, as she has never used VoltRide"),
    5: ("C", "I can see VoltRide Scooters $412.60 on Monday and StreamPlus $89.99 on Tuesday. The StreamPlus one I need to think about.", "the customer finds the VoltRide charge and a StreamPlus charge of $89.99 on Tuesday, which she needs to think about"),
    6: ("A", "Noted on VoltRide. Take your time: do you recognise the StreamPlus one?", "the agent notes what she said about VoltRide and asks whether she recognises the StreamPlus payment"),
}
B_CF_CARD_ONLY = {  # (2) only the new card for branch pickup: no address change
    34: ("C", "Then I'll take a new card, please, and I'll collect it at the Harbour Road branch tomorrow.", "the customer asks for a new card that she will collect at the Harbour Road branch tomorrow"),
    35: ("A", "For a new card I need a stronger check. I've sent an approval request to your Harborline app.", "the agent says an enhanced check is needed for a new card and sends an approval request to her app"),
    38: ("A", "Thanks, that came through. The new card is next.", "the agent says the approval came through and the new card is next"),
    40: ("T", "branch_lookup(Harbour Road) → card pickup desk open 09:00-17:00 on weekdays", "the branch system shows that the Harbour Road card pickup desk is open from 9:00 to 17:00 on weekdays"),
    43: ("C", "Oh no. Tomás says the scooter ride and StreamPlus were both him, on his own card; he's the second cardholder on our account. So forget the new card.",
         "the customer relays that her son made both charges on his own card as the second cardholder on their account, and calls off the new card"),
    45: ("T", "card_status(card 3391) → frozen; no payments attempted since 09:17:40", "the card is still blocked and no payments have been attempted since"),
}
B_CF_NOT_DONE = {  # (3) she is not finished at t80
    80: ("C", "The cap and the overdraft are sorted, thank you! Give me a minute, I want to check one more thing.", "the customer thanks the agent for sorting the cap and the overdraft and asks for a minute to check one more thing"),
    81: ("A", "Of course, take your time.", "the agent tells her to take her time"),
    82: ("T", "app_activity → customer is viewing the transactions page", "the customer is looking at the transactions page in her app"),
    83: ("A", "No rush, I'm here whenever you're ready.", "the agent says there is no rush"),
}
# structural_cf: a fee refund was already made this morning by phone, so today's
# refund limit is used before the chat starts.
B_SCF_REFUND_USED = {
    59: ("A", "Fee refunds are limited to one per customer per day, and one was already made this morning by phone banking.", "the agent explains that fee reversals are limited to one a day and one was already made by phone that morning"),
    60: ("C", "Oh right, I called about the $12 monthly fee earlier. So what happens with this one?", "the customer remembers calling about the $12 monthly fee and asks what happens with this one"),
    61: ("A", "A card-services specialist can approve an exception; the queue is about 15 minutes right now.", "the agent says a specialist can approve an exception, with a queue of about fifteen minutes"),
    62: ("C", "Not worth it for $35 today. Forget the fee; I'll ask another day.", "the customer drops the fee reversal for today"),
    63: ("A", "Understood, I've dropped the refund request.", "the agent drops the fee reversal request"),
    64: ("A", "If you ask on another day, the daily limit will have reset.", "the agent notes the daily cap resets on another day"),
    85: ("C", "Oh, sorry, one more thing! Can you at least refund the $3.50 foreign transaction fee from Monday?", "the customer comes back asking at least for the $3.50 foreign transaction fee from Monday to be reversed"),
    86: ("A", "Fee refunds are limited to one per customer per day, and this morning's phone refund used it.", "the agent explains the daily cap was used by the morning's phone reversal"),
    92: ("A", "Yes, the specialist sees this whole chat, including the fraud alert and case DC-58213.", "the agent says the specialist sees the whole chat, including the fraud alert and the chargeback claim"),
}

# Irrelevant staff chatter for the lexical-decoy register. Each tick shows two
# lines keyed by an action whose vocabulary they borrow, plus one line aimed at
# the operation or flag question. All three are chosen per tick without looking
# at gold. None of them concerns this customer.
B_DECOYS = {
    "reply": [
        "Marketing asks every branch to reply in the chat channel to the logo survey by Friday.",
        "The branch newsletter wants staff to reply without starting any new threads in the chat.",
        "A colleague asks the team to reply to the parking survey without starting a new check-in.",
        "The staff chat is reminding everyone to reply to the holiday rota before starting leave.",
    ],
    "close": [
        "Branch notice: the Queen Street branch will close early on Friday; file the summary of the fire drill.",
        "Reminder: close the conversation room blinds and file the cleaning summary before leaving.",
        "Facilities will close the staff car park at 20:00 and file a summary of the resurfacing.",
        "The canteen will close for the day at 14:00; its summary of the menu survey is filed.",
    ],
    "basic": [
        "Facilities will run a basic check of the fire alarms at 11:00.",
        "HR asks new starters for their date of birth and the last four digits of their staff ID for the pension form.",
        "The IT desk runs a basic check of every laptop's battery this week.",
        "Payroll asks staff to confirm their date of birth on the new portal before the last four days of the month.",
    ],
    "strong": [
        "IT: a strong check is now required on staff laptops; approve the sign-in inside the new banking-style app.",
        "Security reminder: an approval inside the staff app is needed to open the car park barrier.",
        "The gym on floor 1 asks for a strong approval of its new opening hours from the staff app.",
        "IT reminds staff that approvals inside the expenses app now need a strong password.",
    ],
    "run": [
        "IT will run the printer operation tonight; the next update takes about an hour.",
        "Operations: the quarterly fire-drill operation will run at 15:00 in the selected buildings.",
        "The analytics team will run the next report operation on the weekend.",
        "Facilities will run the heating operation in the selected meeting rooms from Monday.",
    ],
    "escalate": [
        "HR: hand payroll questions to a human resources specialist, not the chat queue.",
        "Facilities handed the lift repair over to a specialist engineer from the building owner.",
        "The team lead asks staff to hand the parking case to a human in the security office.",
        "The coffee machine case has been handed to a specialist technician.",
    ],
}
# Lines aimed at the operation question (one pool per operation) and the flag.
B_DECOYS_Q23 = {
    "freeze": [
        "Marketing's 'Freeze the moment' photo competition closes on Friday.",
        "Facilities will freeze the meeting-room thermostat settings over the holiday.",
    ],
    "address": [
        "Reception is updating the address labels on the visitor lockers.",
        "HR asks staff to update their home address in the payroll portal before month end.",
    ],
    "replacement": [
        "The print room will issue replacement badges for anyone whose staff card is worn.",
        "IT will issue replacement headsets to the floor 3 team next week.",
    ],
    "dispute": [
        "Training: a dispute-case workshop for new starters opens next week.",
        "Facilities opened a dispute case with the landlord about the broken car park gate.",
    ],
    "refund": [
        "The canteen will refund the fee for the cancelled staff lunch to everyone.",
        "Travel desk: the conference fee refund is on its way to this year's speakers.",
    ],
    "flag": [
        "The fraud team's quiz night is flagged in the staff calendar for Thursday.",
        "Marketing flagged the new logo draft for a review by the brand team.",
        "Compliance reminder: the annual fraud-review e-learning is due by the end of the month.",
        "The broken dishwasher in the staff kitchen has been flagged for review by facilities.",
    ],
}


def _op(status: str, detail: str) -> dict[str, str]:
    return {"status": status, "detail": detail}


class CardDisputeChat(Scenario):
    family = FAMILY
    scenario_id = "support_b"
    title = "Tool-using orchestration for a bank card-dispute support chat"
    tier = "hard"
    difficulty_features = [
        "three_questions_per_decision",
        "categorised_action_options",
        "six_way_operation_choice",
        "noul_fraud_review_flag",
        "verification_level_table",
        "daily_operation_limits",
        "fixed_operation_order",
        "async_tool_results",
        "request_changed_midway",
        "lagging_case_notes",
        "tool_log_over_case_notes",
        "implicit_facts",
        "priority_conflicts",
        "agent_lags_behind_the_right_move",
    ]
    decision_structures = ["maintain", "advance", "wait", "recover", "reroute", "escalate", "handoff", "terminate", "resolve-conflict"]
    deadline_steps = 2

    START = 9 * 3600 + 12 * 60  # 09:12:00, time of the event at t0
    TICK_SECONDS = 20
    LAG = 10
    RANK = {"none": 0, "basic": 1, "strong": 2}

    def at(self, t: int) -> str:
        return hms(self.START + self.TICK_SECONDS * t)

    # ---------------------------------------------------------------- questions
    def questions(self, variant: str) -> list[Any]:
        if variant == "paraphrase":
            base = {"role": B_ROLE_P, "definitions": B_DEFS_P, "caps_and_checks": B_TABLE_P, "rules": B_POLICY_P}
            return [
                Choice("action", {**base, "question": "Go down the rules and stop at the first that applies. Which step should the assistant take now?"}, dict(B_ACTIONS_P)),
                Choice("operation", {**base, "question": "Go down the rules and stop at the first that applies. Which task does the assistant's step serve (the task to carry out now, or the one the requested check is for)? Pick 'Nothing to carry out' when the rule names no task."}, dict(B_OPS_P)),
                Noul("flag", {"role": B_ROLE_P, "note": B_DEFS_P[-1], "rule": B_FLAG_P, "question": "Should this chat be marked for a fraud review at this moment?"},
                     {"true": "Mark the chat for a fraud review.", "false": "Leave the chat unmarked."}),
            ]
        base = {"role": B_ROLE, "definitions": B_DEFS, "checks_and_limits": B_TABLE, "policy": B_POLICY}
        actions = B_ACTIONS_D if variant == "lexical_decoy" else B_ACTIONS
        return [
            Choice("action", {**base, "question": "Apply the first matching rule. Which action should the agent take right now?"}, dict(actions)),
            Choice("operation", {**base, "question": "Apply the first matching rule. Which operation is the agent's action for (the operation to run now, or the one the requested check is for)? Answer 'No operation' when the rule gives none."}, dict(B_OPS)),
            Noul("flag", {"role": B_ROLE, "note": B_DEFS[-1], "rule": B_FLAG, "question": "Should the conversation be flagged for fraud review right now?"},
                 {"true": "Flag the conversation for fraud review.", "false": "Do not flag the conversation."}),
        ]

    # ------------------------------------------------------------------ latent
    def _canonical(self) -> list[Tick]:
        at = self.at
        tl = Timeline(
            {
                "ops": {},
                "checks": {"basic_at": None, "strong_at": None, "failed": 0, "failed_at": None, "asked": None, "asked_at": None},
                "claim": [],
                "person_asked_at": None,
                "finished_at": None,
                "used_today": {"refund": [], "replacement": [], "address": []},
            }
        )
        both = "VoltRide $412.60 and StreamPlus $89.99"
        card = B_CARD_DETAIL
        flat = "to 22 Calloway Street"
        basic_ok = {"basic_at": at(12), "strong_at": None, "failed": 1, "failed_at": at(9), "asked": None, "asked_at": None}
        events: dict[int, tuple[dict[str, Any], str]] = {
            2: ({}, "A bank alert quoted by the customer is not her claim; nothing requested yet. Notes trail by a tick."),
            7: ({"claim": ["voltride", "streamplus"], "ops": {"freeze": _op("to_do", "card 3391")}},
                "Claims both charges and wants a freeze: basic check needed. Case notes lag (as of t6)."),
            8: ({"checks": {"basic_at": None, "strong_at": None, "failed": 0, "failed_at": None, "asked": "basic", "asked_at": at(8)}},
                "Basic check requested. Case notes still lag."),
            9: ({"checks": {"basic_at": None, "strong_at": None, "failed": 1, "failed_at": at(9), "asked": "basic", "asked_at": at(8)}},
                "3319 is not 3391: the basic check fails once."),
            12: ({"checks": dict(basic_ok)}, "Basic check passed: run the freeze."),
            13: ({"ops": {"freeze": _op("to_do", "card 3391"), "dispute": _op("to_do", both)}},
                 "Dispute requested too; freeze comes first in the order."),
            15: ({"ops": {"freeze": _op("pending", "card 3391"), "dispute": _op("to_do", both)}},
                 "Freeze pending, so the dispute is the next operation."),
            16: ({}, "'Freeze it again' while the freeze is pending."),
            17: ({"ops": {"dispute": _op("to_do", both)}}, "Freeze succeeded; dispute still the next operation."),
            19: ({"ops": {"dispute": _op("failed", both)}},
                 "The first dispute attempt failed at once; nothing was created, so it is still wanted and can run again. The failure is only in the tool log (notes lag)."),
            20: ({}, "'The freeze and the dispute are both sorted then, thanks' while the dispute is still wanted: a mistaken belief with thanks, not a need-nothing-else statement, and not a close."),
            22: ({"ops": {"dispute": _op("pending", both)}}, "Dispute resubmitted and pending: nothing to run. Only the tool log shows it (notes as of t21 still say failed)."),
            25: ({"ops": {}}, "Dispute succeeded: nothing wanted."),
            32: ({}, "A question about how long a new card takes is not a request for one."),
            34: ({"ops": {"replacement": _op("to_do", card), "address": _op("to_do", flat)}},
                 "New card (branch pickup, so independent of the address) and address change requested: address comes first in the order; strong check needed."),
            35: ({"checks": {**basic_ok, "asked": "strong", "asked_at": at(35)}}, "Strong check requested."),
            37: ({"checks": {**basic_ok, "strong_at": at(37)}}, "Strong check passed: run the address change (it outranks the replacement)."),
            40: ({"ops": {"replacement": _op("to_do", card), "address": _op("pending", flat)}},
                 "Address change pending: the replacement is now the next operation (the agent answers her PIN question and does not order the card)."),
            43: ({"ops": {"address": _op("pending", flat)}, "claim": []},
                 "Charges were made on the son's additional card: claim withdrawn, new card dropped; the address change is still pending. Case notes lag (as of t42)."),
            44: ({}, "Case notes still lag behind the chat."),
            45: ({"ops": {}, "used_today": {"refund": [], "replacement": [], "address": [f"{at(45)} to 22 Calloway Street"]}},
                 "Address change succeeded; today's address limit is now used."),
            50: ({}, "A neighbour's cloned card is not a claim about this card."),
            58: ({"ops": {"refund": _op("to_do", "$35 overdraft fee")}}, "Fee refund requested; basic already passed; 0 of 1 used today."),
            62: ({"ops": {"refund": _op("pending", "$35 overdraft fee")}}, "Refund pending: nothing to run."),
            63: ({"ops": {}, "used_today": {"refund": [f"{at(63)} $35 overdraft fee"], "replacement": [], "address": [f"{at(45)} to 22 Calloway Street"]}},
                 "Refund succeeded (only in the tool log; notes lag); today's refund limit is now used."),
            66: ({}, "Musing about a new card 'someday' is not a request."),
            74: ({}, "'Done with overdrafts' is not saying she needs nothing else."),
            79: ({}, "She is still looking through the app: not finished."),
            80: ({"finished_at": at(80)}, "Nothing wanted and she says she needs nothing else: close."),
            85: ({"finished_at": None, "ops": {"refund": _op("to_do", "$3.50 foreign transaction fee")}},
                 "Second fee refund; the limit (1 per day) is used: hand over."),
            88: ({"person_asked_at": at(88), "ops": {}}, "She drops the $3.50 refund but asks for a person: the person clause alone now keeps the handover."),
        }
        tags = span_tags(
            {
                "distractor": [2, 16, 20, 32, 50, 66, 74],
                "minimal_change": [12, 37, 62, 80],
                "recovery": [43, 62],
                "hold_under_activity": [(8, 11), (23, 31), (35, 36), (89, 98)],
                "priority_conflict": [(13, 14), (34, 39), (85, 87)],
                "boundary": [(80, 84), (88, 99)],
                "arithmetic": [58, (85, 87)],
                "implicit": [(7, 8), (43, 44)],
            }
        )
        for t in range(STEPS):
            updates, note = events.get(t, ({}, ""))
            tl.step(dict(B_SCRIPT[t]), tags[t], note, **updates)
        return tl.ticks

    @staticmethod
    def _surface(item: Any) -> dict[str, Any]:
        return dict(item) if isinstance(item, dict) else entry(*item)

    def timeline(self, variant: str) -> list[Tick]:
        ticks = self._canonical()
        if variant == "minimal_cf":
            # (1) t4-6: she disowns the VoltRide charge while opening the app (flag no -> yes).
            ticks = override(ticks, range(4, 7), claim=["voltride"], note="She says the VoltRide charge was not her.")
            ticks = override(ticks, [4, 5, 6], surface=lambda tk, i: self._surface(B_CF_EARLY_CLAIM[i]))
            # (2) t34-39: only the new card for branch pickup, no address change (operation address -> replacement).
            card = {"replacement": _op("to_do", B_CARD_DETAIL)}
            ticks = override(ticks, range(34, 43), ops=card,
                             note="Only a new card is wanted: the replacement is the next operation.")
            ticks = override(ticks, [43, 44], ops={})
            for tk in ticks[45:]:
                tk.latent["used_today"]["address"] = []
            ticks = override(ticks, sorted(B_CF_CARD_ONLY), surface=lambda tk, i: self._surface(B_CF_CARD_ONLY[i]))
            # (3) t80-84: she has not said she is finished (close -> reply).
            ticks = override(ticks, range(80, 85), finished_at=None, note="Nothing wanted, but she has not said she is finished.")
            ticks = override(ticks, sorted(B_CF_NOT_DONE), surface=lambda tk, i: self._surface(B_CF_NOT_DONE[i]))
            ticks = _set_tags(ticks, {
                4: ["minimal_change"], 5: [], 6: [],
                34: ["minimal_change"], 35: ["hold_under_activity"], 36: ["hold_under_activity"], 37: ["minimal_change"], 38: [], 39: [],
                80: ["minimal_change"], 81: [], 82: [], 83: [], 84: [],
            })
            for t, note in {
                7: "She now disowns StreamPlus too and asks for a freeze. Case notes lag (as of t6).",
                34: "Only a new card (branch pickup), no address change: the replacement is the next operation; strong check needed.",
                37: "Strong check passed: run the replacement.",
                40: "Still only the new card wanted: run the replacement (the agent answers her PIN question instead).",
                43: "Charges were made on the son's additional card: claim withdrawn, new card dropped. Case notes lag (as of t42).",
                45: "",
            }.items():
                ticks[t].note = note
        elif variant == "structural_cf":
            # History: a fee refund was already made this morning by phone, so the
            # refund limit is used before the chat starts. The canonical $35
            # refund never happens here, so the morning refund is the only one.
            morning = ["08:05 by phone banking: $12 monthly fee"]
            for tk in ticks:
                tk.latent["used_today"]["refund"] = list(morning)
            ticks = override(ticks, [62], ops={}, note="She drops the refund request: nothing wanted.")
            ticks = override(ticks, sorted(B_SCF_REFUND_USED), surface=lambda tk, i: self._surface(B_SCF_REFUND_USED[i]))
            for t, note in {
                58: "Refund requested, but today's refund limit was used by the morning phone refund: hand over (rule 1 over rule 4).",
                63: "Refund dropped; nothing wanted.",
                85: "Another fee refund; the limit is still used: hand over.",
            }.items():
                ticks[t].note = note
            ticks = _set_tags(ticks, {58: ["arithmetic", "priority_conflict"], 59: ["arithmetic"], 62: ["recovery"]})
        return ticks

    # ------------------------------------------------------------------ policy
    def _level(self, checks: dict[str, Any]) -> str:
        if checks["strong_at"] is not None:
            return "strong"
        return "basic" if checks["basic_at"] is not None else "none"

    def _next_op(self, z: dict[str, Any]) -> str | None:
        for op in B_ORDER:
            if op in z["ops"] and z["ops"][op]["status"] != "pending":
                return op
        return None

    def policy(self, z: dict[str, Any]) -> dict[str, Any]:
        flag = bool(z["claim"])
        nxt = self._next_op(z)
        if z["person_asked_at"] is not None or (nxt in B_LIMIT and len(z["used_today"][nxt]) >= B_LIMIT[nxt]):
            action, operation = "escalate", "none"
        elif not z["ops"] and z["finished_at"] is not None:
            action, operation = "close", "none"
        elif nxt is not None and self.RANK[self._level(z["checks"])] < self.RANK[B_NEEDS[nxt]]:
            action, operation = B_NEEDS[nxt], nxt
        elif nxt is not None:
            action, operation = "run", nxt
        else:
            action, operation = "reply", "none"
        return {"action": action, "operation": operation, "flag": flag}

    def construction(self, variant: str) -> dict[str, Any]:
        return {
            "canonical": {"summary": "Card-dispute chat: an alert quoted (t2, not a claim); both charges disowned and a freeze requested (t7, case notes lag at t7-8), basic check with one failed attempt (t7-11); freeze run (t12-14) while a dispute is also requested (freeze first); freeze pending so the dispute is next, and its first attempt fails at once (t15-21, failure only in the tool log at t19-20); resubmitted and opened (t22-33); a new card for branch pickup and a separate address change, address first, strong check needed (t34-36), approved at t37 so the address change runs (t37-39); address pending so the replacement is next (t40-42; the agent answers her PIN question instead of ordering the card); the son made both charges on his additional card: claim withdrawn, new card dropped (t43, notes lag at t43-44); $35 fee refund run (t58-61), pending then refunded (t62-63, back to replying; today's refund limit now used); 'that's everything' (t80-84); a second fee refund hits the daily limit (t85-87); at t88 she drops it but asks for a person, so the person clause alone keeps the handover to the end. Case notes also trail by a tick at many ticks where no decision fact changes (including the distractors)."},
            "paraphrase": {"summary": "Same latent trajectory; prose case summary with the five latest events as gists; tasks renamed (temporary card block, postal address change, new card, chargeback claim, fee reversal), checks renamed standard/enhanced; reworded role, definitions, table, rules, questions, options and Noul criteria."},
            "lexical_decoy": {"summary": "Same latent trajectory; a team_chatter field with three irrelevant staff notices per tick: two borrow an action's vocabulary and one an operation's or the fraud flag's; all three are drawn per tick without looking at gold."},
            "minimal_cf": {"summary": "t4-6 she disowns the VoltRide charge while opening the app, before any request (flag no->yes); t34-39 she wants only the new card for branch pickup, with no address change (operation address->replacement, then run/address->run/replacement); t80-84 she says the cap and overdraft are sorted but wants a minute to check one more thing, not that she is finished (close->reply)."},
            "structural_cf": {"summary": "History change: a $12 fee was already refunded this morning by phone banking, so refund_fee is 1 of 1 used from the start. The $35 refund request at t58-61 now hits the daily limit (run/refund->hand over); she drops it at t62, and the second refund at t85 is handed over as in canonical."},
        }.get(variant, {})

    # ------------------------------------------------------------------ render
    def _notes_index(self, history: list[Tick]) -> int:
        """Index of the tick whose latent the case notes show (they trail on ``B_NOTES_LAG`` ticks)."""
        i = len(history) - 1
        while i > 0 and i in B_NOTES_LAG:
            i -= 1
        return i

    def _wants(self, notes: list[Tick], paraphrase: bool) -> str:
        z = notes[-1].latent
        key = _since(notes, lambda x: x["ops"])
        if not z["ops"]:
            return pick(["She is not asking for any task at the moment.", "Nothing is being asked for right now."] if paraphrase
                        else ["Nothing at the moment.", "No operation requested right now.", "None."], "b-wants0", key)
        parts = []
        for op, v in z["ops"].items():
            if paraphrase:
                status = {"to_do": "wanted, not yet carried out", "pending": "sent off, no answer from the system yet",
                          "failed": "the last attempt failed and changed nothing; still wanted"}[v["status"]]
                parts.append(f"a {B_NAME_P[op]} ({v['detail']}): {status}")
            else:
                status = {"to_do": pick(["wanted, not started", "requested, not run yet"], "b-todo", key, op),
                          "pending": pick(["submitted, waiting for a result", "submitted, no result yet"], "b-pend", key, op),
                          "failed": "last attempt failed (nothing was done); still wanted"}[v["status"]]
                parts.append(f"{B_TOOL[op]} ({v['detail']}): {status}")
        return ("She is asking for " + "; and ".join(parts) + ".") if paraphrase else "; ".join(parts) + "."

    def _claim(self, notes: list[Tick], paraphrase: bool) -> str:
        z = notes[-1].latent
        key = _since(notes, lambda x: x["claim"])
        items = [B_MERCHANT[m] for m in z["claim"]]
        if items:
            joined = listing(items)
            return pick(
                [f"She maintains that {joined} {'was' if len(items) == 1 else 'were'} made without her permission.",
                 f"Payments she says she neither made nor allowed: {joined}."] if paraphrase
                else [f"Elena says {joined} {'was' if len(items) == 1 else 'were'} made without her permission.",
                      f"Reported by Elena as not made or allowed by her: {joined}."],
                "b-claim", key)
        if any(tk.latent["claim"] for tk in notes):
            return pick(["She has taken back her earlier statement about unrecognised payments; none is disputed as unauthorised now.",
                         "No payment is currently said to be unauthorised; she withdrew her earlier statement."] if paraphrase
                        else ["None now: Elena took back her earlier claim.", "No current claim; Elena withdrew the earlier one."], "b-claim-w", key)
        return pick(["She has not said that any payment was made without her permission.", "No statement from her about unauthorised payments so far."] if paraphrase
                    else ["None: Elena has not said any payment was made without her permission.", "No claim of an unauthorised payment so far."], "b-claim0", key)

    def _person(self, notes: list[Tick], paraphrase: bool) -> str:
        z = notes[-1].latent
        if z["person_asked_at"] is not None:
            return (f"At {z['person_asked_at']} she asked for a real person." if paraphrase
                    else f"Yes: Elena asked for a person at {z['person_asked_at']}.")
        return pick(["She has not asked for a real person.", "No request for a human so far."] if paraphrase
                    else ["Not requested.", "Elena has not asked for a person."], "b-person", _since(notes, lambda x: x["person_asked_at"]))

    def _identity(self, history: list[Tick], paraphrase: bool) -> str:
        c = history[-1].latent["checks"]
        std, enh = ("standard", "enhanced") if paraphrase else ("Basic", "Strong")
        if c["basic_at"] is not None:
            first = f"{std} check passed at {c['basic_at']}."
        elif c["failed"]:
            first = f"{std} check not passed: {c['failed']} failed attempt at {c['failed_at']} (the card digits did not match)."
        elif c["asked"] == "basic":
            first = f"{std} check requested at {c['asked_at']}, not passed yet."
        else:
            first = f"{std} check: not passed."
        if c["strong_at"] is not None:
            second = f"{enh} check passed at {c['strong_at']} (approved in the app)."
        elif c["asked"] == "strong":
            second = f"{enh} check: approval request sent to the app at {c['asked_at']}, not approved yet."
        else:
            second = f"{enh} check: not passed."
        failed = pick([f"Failed checks in this chat: {c['failed']}.", f"Failed attempts so far: {c['failed']}."],
                      "b-idfail", _since(history, lambda x: x["checks"]))
        out = f"{first[0].upper()}{first[1:]} {second[0].upper()}{second[1:]}"
        return f"{out} {failed}" if c["basic_at"] is not None else out

    def _used(self, history: list[Tick], paraphrase: bool) -> str:
        u = history[-1].latent["used_today"]
        names = B_NAME_P if paraphrase else B_TOOL
        compact = not paraphrase and pick([False, True], "b-used", _since(history, lambda x: x["used_today"]))
        parts = []
        for op in ("refund", "replacement", "address"):
            used = u[op]
            count = f"{len(used)}/{B_LIMIT[op]}" if compact else f"{len(used)} of {B_LIMIT[op]} used"
            detail = f" ({'; '.join(used)})" if used else ""
            parts.append(f"{names[op]} {count}{detail}")
        return ("Today's usage against caps: " + ", ".join(parts) + ".") if paraphrase else " · ".join(parts)

    def _tool_log(self, history: list[Tick]) -> list[str]:
        out = []
        for i, tk in enumerate(history):
            s = tk.surface
            if s["who"] == "T":
                out.append(f"{self.at(i)} {s['text']}")
            elif s.get("tool"):
                out.append(f"{self.at(i)} {s['tool']}")
        return out[-3:] if out else ["(no tool calls yet)"]

    def _chat(self, history: list[Tick]) -> list[int]:
        return [i for i, tk in enumerate(history) if tk.surface["who"] in ("C", "A")][-B_CHAT_WINDOW:]

    def _check_window(self, history: list[Tick]) -> None:
        """'That's everything' lives only in the chat: it must be on screen in both registers while it counts."""
        t = len(history) - 1
        z = history[-1].latent
        if z["finished_at"] is not None:
            start = _since(history, lambda x: x["finished_at"])
            if start not in self._chat(history) or start < t - (B_CHAT_WINDOW - 1):
                raise ValueError(f"support_b t{t}: finished_at (from t{start}) has scrolled out of the chat window")
        k = self._notes_index(history)
        if t - k > 2:
            raise ValueError(f"support_b t{t}: case notes trail by {t - k} ticks (at most 2 allowed)")

    def render(self, history: list[Tick], variant: str) -> Any:
        self._check_window(history)
        if variant == "paraphrase":
            return self._render_paraphrase(history)
        t = len(history) - 1
        k = self._notes_index(history)
        notes = history[: k + 1]
        now = self.START + self.TICK_SECONDS * t + self.LAG
        state: dict[str, Any] = {
            "case": "Harborline Bank card-services chat · customer Elena Duarte · debit card ending 3391 · chat opened 09:12",
            "updated": hms(now),
            "identity": self._identity(history, False),
            "used_today": self._used(history, False),
            "case_notes": {
                "as_of": hms(self.START + self.TICK_SECONDS * k + self.LAG),
                "customer_wants": self._wants(notes, False),
                "fraud_claim": self._claim(notes, False),
                "person_requested": self._person(notes, False),
            },
            "tool_log": self._tool_log(history),
            "transcript": [f"{self.at(i)} {'Customer' if history[i].surface['who'] == 'C' else 'Agent'}: {history[i].surface['text']}"
                           for i in self._chat(history)],
        }
        if variant == "lexical_decoy":
            lines = [pick(B_DECOYS[a], "b-decoy-line", t, a) for a in _decoy_targets(list(B_DECOYS), "b-decoy", t, 2)]
            target = _decoy_targets(list(B_DECOYS_Q23), "b-decoy-q23", t, 1)[0]
            lines.insert(pick([0, 1, 2], "b-decoy-q23-place", t), pick(B_DECOYS_Q23[target], "b-decoy-q23-line", t))
            state["team_chatter"] = " ".join(lines)
        return state

    def _render_paraphrase(self, history: list[Tick]) -> str:
        t = len(history) - 1
        k = self._notes_index(history)
        notes = history[: k + 1]
        now = self.START + self.TICK_SECONDS * t + self.LAG
        parts = [
            f"Harborline card-services chat with Elena Duarte (debit card ending 3391), summary at {hms(now)}.",
            self._identity(history, True),
            self._used(history, True),
            f"Back-office summary, refreshed at {hms(self.START + self.TICK_SECONDS * k + self.LAG)}:",
            self._wants(notes, True),
            self._claim(notes, True),
            self._person(notes, True),
        ]
        gists = [history[i].surface["gist"] for i in range(max(0, t - (B_CHAT_WINDOW - 1)), t + 1)]
        full = ["Four events back, ", "Then ", "After that, ", "Just before now, ", "Latest: "]
        parts.append(" ".join(f"{a}{g}." for a, g in zip(_leads(full, len(gists)), gists)))
        return " ".join(parts)


SCENARIOS = [CarrierChat, CardDisputeChat]
