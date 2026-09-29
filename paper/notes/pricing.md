# List prices used for the cost rows (retrieved 2026-09-29)

These prices were read from the providers' official pages, and an independent second pass checked each one against the live page. They are applied in `paper/analysis/lite_numbers.py` (`PRICES`), and the results appear in the appendix token table.

| Setting | Input | Cached input | Output | Unit | Source |
|---|---:|---:|---:|---|---|
| GPT-5.6-Luna (low, none) | $0.20 | $0.02 | $1.20 | per 1M tokens | https://developers.openai.com/api/docs/pricing and https://developers.openai.com/api/docs/models/gpt-5.6-luna |
| GPT-5.6-Terra (low, none) | $2.00 | $0.20 | $12.00 | per 1M tokens | https://developers.openai.com/api/docs/pricing and https://developers.openai.com/api/docs/models/gpt-5.6-terra |
| Jev (`jev-latest`) | $0.042 | — | free | per 1M tokens | https://docs.typesafe.ai/models ("Output tokens are free.") |
| GPT-6 Astra (low) | $10.00 | $1.00 | $50.00 | per 1M tokens | https://developers.openai.com/api/docs/pricing and https://developers.openai.com/api/docs/models/gpt-6-astra (read 2026-09-30) |

## OpenAI

- **Tier.** The prices are Standard tier, short context (up to 272K input tokens). Every request here is about 2K tokens.
- **Reasoning tokens.** They are billed as output. The reasoning guide says: "While reasoning tokens are not visible via the API, they still occupy space in the model's context window and are billed as output tokens." `usage.output_tokens` already includes `reasoning_tokens`, and the generator checks this.
- **Fees.** No per-request fee applies to text tokens.
- **Effective date.** The prices took effect on July 30, 2026. The changelog says: "Starting July 30, GPT-5.6 Luna costs 80% less, while GPT-5.6 Terra costs 20% less." All passes were recorded after that date.
- **What is not modelled.** Cache writes ($0.25 and $2.50 per 1M) are not modelled. No pass reported cached tokens.

## TypeSafe

- **Billing.** Jev bills input tokens only.
- **Other prices.** No cached-input price, batch tier or per-request fee is published.
- **Caveat.** https://typesafe.ai/pricing returned 404, so the Models page is the official source.

## Caveat

These costs are list-price estimates. The amounts actually billed can differ, for example through account discounts or through a data-residency or regional uplift. Superseded, legacy and incomplete passes are not included.

## GPT-6 Astra low

The model page states "reasoning.effort supports low, medium, high, xhigh, and max"; a request with effort `none` was rejected with HTTP 400 (`unsupported_value`, not billed), so the recorded setting is `low`. Usage over the 480 requests: 1,476,489 input tokens (0 cached), 22,305 output tokens of which 773 were reasoning. At the list prices above that is $14.76 input + $1.12 output = $15.88. The paper reports Astra low as its sixth setting; the appendix token table and the total in the Reproducibility appendix include this pass.
