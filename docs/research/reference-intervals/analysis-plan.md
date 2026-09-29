# Family reference-interval evidence review

- Date: 2026-09-29.
- Goal: assess whether literature supports different reference time-step intervals for the three SDB families of that date; recommend a reporting and aggregation policy.
- Research question: which time scales are measured, which are guidelines, and how far can they justify an environment time-step interval rather than a response-time budget?
- Initial paper set: introduction citations Murali et al. (2024), Dunay et al. (2024), Chen et al. (2017), Olguín Muñoz et al. (2021), Gergle et al. (2006), Miller (1968), and PCI SSC (2018). MacKenzie & Ware (1993) and Stuart et al. (2002) are contextual checks, not direct calibration sources.
- Comparison dimensions: task/consumer, timing origin and endpoint, manipulated variable, empirical result or guidance, reported percentiles, external validity to the current task, candidate interval, strength of the mapping.
- Required depth: inspect original methods and numerical results for the papers used to choose values; verify primary sources and record section/page pointers. Existing local research notes are leads, not substitutes for checking sources.
- Deliverable: Traditional Chinese evidence memo with a compact evidence matrix, candidate reference vector, aggregation formula, appendix figure specification, and explicit unresolved calibration gaps.
- Focus: evidence-backed operating points within 1–5 seconds, with no requirement that every family receive a distinct value.
- Artifacts: this directory; manuscript, bibliography, benchmark rules, and existing results remain outside the editing scope.
- Additional sources: record additions below before using them for deep analysis.

## Scope additions

- Roberts, Francis & Morgan (2006), Roberts & Francis (2013), and Stivers et al. (2009): inspect primary evidence for conversational timing because PCI SSC provides no numeric recorder-control latency threshold.
- Saff & Ernst (2004): inspect continuous testing as a closer IDE-debugging analogue if the code-completion studies do not establish an appropriate scale.
- Nielsen (1993) response-time guidance and O'Hara et al. (2002), NUREG-0700 Rev. 2: inspect only if needed to assess 1-second interaction guidance or a 5-second lenient comparison point.
- Scope clarification after repository inspection: current `data/lite/v1` also contains presenter voice control, while the manuscript and recorded results cover three families. Assess presenter separately using Miller's next-page guidance; do not fold it into the three-family aggregate.
- Source access: the accessible author dissertation reproduces Gergle et al. (2006) as Chapter 4 (explicit attribution on printed p. 41). It is used as an author-hosted primary version of the same study, not an independent replication.
- NUREG-0700 was not needed for the recommendation. The 5-second common comparison is a declared sensitivity endpoint, not an imported regulatory or HCI limit.
