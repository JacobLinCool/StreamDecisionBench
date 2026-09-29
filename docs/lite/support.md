# Support workflows

The support task evaluates the complete guidance currently consumed by an application. Each scenario exposes seven choice questions. A route selects the applicable branch questions, while a global question contributes in every branch. All questions receive the same public snapshot; no question sees another question's generated answer. The application composes the answers after they arrive.

| Scenario | Consumer | Questions active in the composed decision | Timeline |
| --- | --- | --- | --- |
| Payment and reconnection | Payment/service guidance plus recorder control | Route + recorder + payment stage and card; or service target and action; or hold action | 60 observations, 2 seconds each, 120 seconds total |
| Intercom service | Parcel, cancellation or repair guidance plus follow-up preference | Route + contact channel + delivery target and action; or delivery target and cancellation action; or repair target and action | 60 observations, 2 seconds each, 120 seconds total |

These are two separately authored situations, rather than variants of one script. Their shared domain is customer support; their decisions, branch structure and tool observations differ. They are development scenarios for one initial measurement, not a held-out test population.

## Public evidence and timing

Every state contains the elapsed clock, telephone connection/hold status and its change time, a transcript with utterance identifiers, timestamps, speaker roles and finality, and actual application/tool fields. Both scenarios include their complete rules in `prepared.rules`. A final revision replaces the earlier partial with the same utterance identifier. Earlier final utterances remain visible. Role labels identify the verified customer, the agent and a background speaker; only the customer can request a workflow, select its target or grant consent.

There are no pre-extracted customer-intent, route, scam or desired-action labels in the state. Fields such as a diagnostic callback, spare inventory, carrier status and payment-form completion are normal structured application observations. The generated gold and evidence list remain outside the state given to the model. The reference function reads the state alone and has no episode index or hidden event annotation.

The first state becomes visible at zero seconds, the last at 118 seconds, and the observation horizon ends at 120 seconds. Reference state is constant between releases. Hold thresholds and delivery deadlines in these scenarios fall on releases, so their changes have unambiguous boundaries. A model's response can still arrive between releases; the application continues using its previous complete decision until a new answer is accepted.

## Payment and reconnection

The customer moves between paying a broadband balance and investigating the connection. Route precedence is call ended, customer on hold, then the most recent final customer request. Card selection, permission changes and acknowledgements alone preserve the current route. Partial customer instructions do not change it. On returning from hold, the last requested workflow resumes.

The payment branch uses both payment stage and selected card. An approved or declined tool callback selects result guidance; a pending submission selects wait. For a draft, authorisation is required before card selection and collection. The customer can withdraw and later grant authorisation. Completed fields only count for the currently selected card: changing from debit to credit leaves the previous card's form insufficient. A form that is complete and correctly matched permits submit guidance. These are recommendations in synthetic observations; the benchmark does not submit a payment.

The recorder is global: a service request can become active while capture remains open, producing service guidance with a paused recorder. Capture begins with an agent's final request for the long card number, ends with an explicit stop or submission, and is independent of the selected route. A current partial customer utterance containing card-number, expiry or code digits also pauses recording; account numbers and old final card speech do not. Call termination stops the recorder. The transcript uses a short fictional test-card prefix rather than a usable payment credential.

Connection guidance follows the line-test callback; router guidance follows the router's online/offline observation. Hold guidance uses the published eight-second threshold, including equality, even when the agent claims a different elapsed duration. The synthetic threshold is a task rule, not a claimed contact-centre standard.

| Public change | Expected effect |
| --- | --- |
| Authorisation granted, card not selected | Payment stage becomes choose card |
| Background speaker recommends credit | Customer's debit selection remains |
| Customer asks for service during open capture | Route becomes service; recorder remains paused |
| Agent explicitly stops capture | Recorder resumes without changing service route |
| Hold reaches eight seconds | Hold action becomes return to customer |
| Partial card correction becomes final | Selected card changes; mismatched form stays incomplete |
| Customer withdraws authorisation | Ask for authorisation even though card data remains |
| Tool submission followed by a new partial expiry utterance | Wait for result; temporarily pause recording again |

This trajectory has 22 changes to the composed reference decision. It includes stable spans with irrelevant speech as well as changes affecting only the global recorder or one active branch field.

## Intercom delivery and repair

The customer first asks about an original and a replacement parcel, then switches to two intercom components. Route precedence is call ended, an overdue or shorter hold, then the most recent final customer request. Delivery and cancellation share the selected parcel question; repair instead uses the selected device. Customer corrections replace earlier choices only when final. Other speakers' statements and partial corrections remain observations without authorising a new branch.

Delivery guidance combines the selected parcel's carrier status with its promised time. Address mismatch has priority, followed by confirmed delivery or cancellation; an otherwise incomplete parcel becomes late at the exact promised time. Before that deadline, a label-only parcel requires a tracking check and an in-transit parcel requires waiting. Cancellation guidance also uses the selected parcel: a carrier cancellation callback confirms completion, while dispatched or delivered parcels are locked. The agent's statement that a button was clicked does not substitute for the callback.

Repair guidance uses the selected component's diagnostic status, result and spare availability. A running diagnostic requires waiting. A power fault calls for a spare when available, otherwise a visit. A network fault requires current remote-access consent before remote-check guidance. A no-fault result selects an explanation. Results and stock for the other component cannot substitute.

Follow-up contact is a global decision with independent permission: email, text message or none. Withdrawing messaging consent does not revoke remote-access consent, and permission changes alone do not change the workflow. The preference remains part of the applied decision during hold and after the call ends. No shipment, cancellation or remote-access action is executed by the benchmark.

| Public change | Expected effect |
| --- | --- |
| Partial cancellation request | Continue existing delivery guidance |
| Request becomes final | Select cancellation and the requested parcel |
| Agent says cancellation is done; no callback | Continue requesting cancellation |
| Cancellation callback arrives | Confirm cancellation |
| Original parcel reaches its deadline | Open a late-parcel case despite agent's estimate |
| Customer corrects base unit to handset | Use handset diagnostics and stock after finality |
| Matching spare becomes available | Change from visit guidance to spare guidance |
| Customer withdraws contact permission | Contact becomes none; permitted remote check continues |

This trajectory has 24 changes to the composed reference decision.

## Composition and reference validation

The published `decision_spec` identifies the route question, globally required questions and active questions for each route. Both model and reference answers must pass through that same composition. An incorrect route remains an incorrect decision; a wrong inactive branch answer does not invalidate an otherwise correct applied decision. Reference segments are formed from changes to this composed decision.

The reference implementation recognises the authored English instruction forms, including role, finality, explicit corrections, quoted distractors and negated requests. It is an executable oracle for these controlled scenarios, not a general-purpose dialogue parser. Any added wording must be checked against the public rules and the reference implementation. Counterfactual tests cover speaker changes, partial/final revisions, withdrawal and regrant, mismatched card fields, exact timing equality, authoritative callbacks, device-specific evidence and independent permissions. These tests verify specified cases; model scores and broader task validity require the measured runs and additional independent situations.
