# Test assets

Small **real** media clips for local/GPU and integration tests (interview decision:
commit small real clips rather than purely synthetic data).

Guidelines:
- Keep clips short (a few seconds) and small — they are committed to git.
- Use content you own or that is licensed for redistribution (e.g. CC0). Note the
  source/license here for each file.
- Unit tests do NOT use these (they generate synthetic audio); these are for the
  `@gpu` / `@integration` suites.

Expected files (referenced by tests):
- `sample_short.mp4` — a few seconds of Korean speech (single or multi speaker) for the e2e dub test.

| file | source | license | speakers | duration |
|------|--------|---------|----------|----------|
| _(add rows as you commit clips)_ | | | | |
