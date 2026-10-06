# Anonymous manuscript artifacts

After regenerating the manuscript analysis and exhibits, build the two ARR
archives and validate a fresh extraction:

```sh
uv run python scripts/paper/build_submission.py --reproduce --latex
```

The default destination is `output/submission-2026-10-04/`. Use `--out PATH` for a
new destination after source changes. An existing validated extraction is never
overwritten. `--latex` compiles the extracted anonymous sources with `latexmk`
and exports `submission.pdf`. An author submission checklist is managed
separately and is not an input to the archives.

The builder selects the fixed manuscript cohort directly from its analysis
manifest: 15 settings, three complete recordings each. It copies the scorer,
analysis and manuscript dependencies into `software.zip`, and frozen states,
recordings, reports and native provenance into `data.zip`. Each ZIP is limited
to 200 MB. The reviewer README and full file-digest inventory are generated in
the software archive.

Identifying author, institution, host and local-cache metadata are transformed
only in the review copy. Frozen episodes, public states and 42 event logs are
preserved byte for byte. Three SemIf event logs require a narrow redaction of
native model-cache paths; an independent parsed comparison permits only that
diagnostic metadata field to change, preserving every measured value. Dependent SHA-256 receipts are updated
through the metadata dependency graph; source checks remain enabled. A source
change without regeneration, an identity in immutable measurements, an unresolved
checksum dependency or a missing required file stops the build.

`--verify` checks the extracted inventory, all 45 recordings, frozen requests and
answers, native input audits, and published scores. `--reproduce` additionally
regenerates the complete manuscript evidence and compares the rendered TeX
values with the supplied exhibits. Verification imports the extracted benchmark
code and blocks Python network connections. It makes no model calls and needs
no model weights or GPU. Logs and validation receipts remain beside the archives.

The builder is not part of the anonymous software archive because its redaction
rules necessarily contain identifying text. The reviewer verifier is included.
Original research files are never modified by packaging.
