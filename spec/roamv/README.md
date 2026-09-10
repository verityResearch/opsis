# ROAMV Standalone Draft

ROAMV packages video and related media without tying it to a capture system,
game engine, programming language, or model. This directory contains the complete
**0.1.0-draft.1 sealed core** draft and has no imports from the rest of the
repository.

- [FORMAT.md](FORMAT.md): normative behavior and semantic rules.
- [manifest.schema.json](manifest.schema.json): JSON Schema Draft 2020-12.
- [examples](examples/README.md): embedded, summary, and linked reference packages.
- [check.py](check.py): draft checker with per-level results.
- [tests/test_core.py](tests/test_core.py): valid and invalid conformance cases.
- [Optional media checks](tests/verify_reference_media.py): decode and pixel comparisons for the bundled fixture only.

## Check a Package

From this directory, with Python 3.10 or later:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -B check.py examples/summary
.venv/bin/python -B -m unittest discover -s tests -v
```

No media framework or network access is used by the checker. The schema has no
external references. FFmpeg is used only to make and independently inspect the
reference media, not to parse the format or run the core tests.

| Level | Supplied Checker |
| --- | --- |
| JSON | UTF-8, duplicate keys, finite numbers, valid Unicode |
| Schema | Required fields, types, closed core records |
| Semantics | References, exact timing, source lineage, layout, coverage |
| Integrity | Local file length, SHA-256, PNG header dimensions |
| Text | Exact projection of current sheet records |
| Source resolution | Not checked; requires stream and sample decoding |
| Derivative reproduction | Not checked; requires the recorded media pipeline |

Exit status is `0` for completed checks without failures, `1` for failure, and
`2` for an unsupported required extension. A linked source can be `unavailable`
with exit status `0`; callers MUST inspect the level results rather than equating
zero with complete verification. Integrity checks are not full PNG decoding.

This is not a hardened untrusted-input service. Readers still need resource
limits and safe media decoding. Annotation truth, synchronization measurements,
and processing-history claims cannot be established by structural validation.

## Remaining Scope

The sealed core is ready for implementation review, not a compatibility promise.
Independent readers, a general media writer, seek-versus-sequential decode tests,
and a broader codec/timing fixture corpus are needed before stabilization.
Live publication, archive-native indexing, editorial timelines, stereo, pose,
and other specialized media features need separately specified extensions.
