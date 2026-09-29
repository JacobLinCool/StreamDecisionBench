# Historical audit of the original six scenarios

## Validity audit (LLM agents, not human validation)

| Fact | Value | Source |
|---|---|---|
| Blind re-derivations | 2 per scenario (an independent reimplementation of the public rules as a program and a release-by-release derivation by hand), 12 total, none reading generator or reference code; each agreed with the stored reference at 60/60 consumed decisions under its default reading | `paper/notes/audit_record.json` `checks` (roles `blind`, `walk`, field `agreement`) |
| Additional checks | per-family code-vs-text audit (3), structural/regeneration check (1) | `paper/notes/audit_record.json` `checks` (roles `audit`, `structural`) |
| Adversarial verification | each grouped finding judged by 3 lenses: literal reading, reference-code trace and alternative readings for the 31 findings about reference answers; reproduction, impact and counter-argument for the 26 others | `paper/notes/audit_record.json` `grouped_findings[].votes` |
| Outcome | 0 confirmed wrong reference answers; 3 rule ambiguities that could change a consumed decision (NO_READ scans in both assembly scenarios; glob `*` crossing `/` in one debugging scenario), affecting 16 consumed states (assembly A t55–59, assembly B t54–57 and t59, debugging B t39–40 and t44–47) | `paper/notes/audit_record.json` (confirmed findings g31, g32, g48 with majority verdict `ambiguous_text`, field `affected_t`) |
| Fix | two public rule sentences clarified; events, questions and reference answers unchanged | PROTOCOL |
