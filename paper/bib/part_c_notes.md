# Part C bibliography notes: entries added or corrected during revision

Checked on 2026-09-28 with WebFetch. The entries are at the end of `references.bib`, except the two corrections, which are edited in place.

| Key | Work | Version cited | Metadata source | Content checked |
|---|---|---|---|---|
| `li2020towards` | Towards Streaming Perception | ECCV 2020, LNCS, Part II | Crossref chapter record 10.1007/978-3-030-58536-5_28 (title, authors, pages 473–488, publisher, year) and Crossref book record 10.1007/978-3-030-58536-5 (book title, "Proceedings, Part II", editors); arXiv:2005.10420 abstract page (ECCV 2020 Oral) | arXiv v2 PDF, §3.1 and §3.3 |
| `ramstedt2019real` | Real-Time Reinforcement Learning | NeurIPS 2019 (Advances in Neural Information Processing Systems 32) | NeurIPS proceedings page and BibTeX export (papers.nips.cc, hash `54e36c5ff5f6a1802925ca009f3ebb68`): authors, editors, volume, publisher; arXiv:1911.04448 abstract page | abstract |
| `achenchabe2021early` | Early and Revocable Time Series Classification | arXiv v2 | arXiv:2109.10285 abstract page (title, four authors, primary class cs.AI, no journal reference) | format only |
| `jimenez2024swebench` | SWE-bench | ICLR 2024 | unchanged; title casing corrected to "GitHub" | none |

## Notes

- **`li2020towards`.** The Crossref chapter record does not give the LNCS volume number, so the entry has no `volume` field; the book subtitle identifies it as Part II. The paper's claims rest on §3.1: "We benchmark the algorithm f by comparing its most recent output at time t_i to the ground-truth y_i", which "is equivalent to the benchmark applying a zero-order hold for the algorithm's outputs", and "the streaming loss above can be applied to any single-frame task". §3.3 states that "our evaluation is hardware dependent — the same algorithm on different hardware may yield different streaming performance". Ground truth is evaluated at annotated frame times, so the score is a discrete-time sum; SDB integrates over continuous time.
- **`ramstedt2019real`.** The abstract states that MDPs are "often used in a way that wrongfully assumes that the state of an agent's environment does not change during action selection" and proposes a framework in which states and actions evolve simultaneously. The proceedings export has an empty `pages` field, so the entry has none.
- **`achenchabe2021early`.** Converted from `@article` with `journal = {arXiv preprint ...}` to the `@misc` eprint form the other preprints use, so every arXiv item renders as "Preprint, arXiv:…".
- **`jimenez2024swebench`.** The ICLR proceedings export spells the title "Github"; the entry now uses the product's spelling, "GitHub", as noted in `part_b_notes.md` item 5.

## Jaynes (1968), Prior Probabilities

Verified against the IEEE publisher entry (https://doi.org/10.1109/TSSC.1968.300117) and original paper (https://bayes.wustl.edu/etj/articles/prior.pdf), Section VII, published pp. 236--237. Volume 4, issue 3, pp. 227--241. Cited only for the multiplicative-invariance argument for scale measures, not empirical deployment weights, HCI tolerance or the benchmark's endpoints. The manuscript derives its own interval-weighting rule explicitly.

## OpenAI, GPT-6 Astra model page (`openai2026astra`)

Read on 2026-09-30 at https://developers.openai.com/api/docs/models/gpt-6-astra. Cited only for the reasoning efforts the model accepts; the page states "reasoning.effort supports low, medium, high, xhigh, and max", and an API request with effort `none` returned HTTP 400 `unsupported_value` (see `paper/notes/pricing.md`). The pricing entry `openai2026pricing` now records both access dates, because Astra's price was read on 2026-09-30.

