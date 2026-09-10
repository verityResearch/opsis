# Opsis / ROAMV

**ROAMV is a standalone, general-purpose video package format.** It preserves
ordinary media and connects it to exact sample references, timed annotations,
and optional visual summaries. It is not a Unity asset, capture SDK, or new video
codec. No engine, camera pose, travel measurement, or model API is required.

## Standalone Draft

The current contract is **0.1.0-draft.1, sealed core**:

- [Format specification](spec/roamv/FORMAT.md): packaging, records, timing, source identity, coverage, and reader behavior.
- [JSON Schema](spec/roamv/manifest.schema.json): machine-readable structural contract.
- [Checker and tests](spec/roamv/README.md): validation commands and explicit limits.
- [Reference packages](spec/roamv/examples/README.md): real MP4/PNG assets, including minimal and linked examples.

The whole [spec/roamv](spec/roamv/) directory is self-contained and can be used
without the prototype or its adapters.

```text
recording.roamv/
  manifest.json
  media/source.mp4
  images/overview.png    optional visual summary
  text/overview.txt      summary identities and qualifications
```

Sources retain their existing encoding. Video, audio, still images, and data
streams share the same record model. Samples retain native presentation locators
and exact rational times; missing or uncertain evidence stays explicit. Sheets
are optional and use declared selection, transformations, and coverage rather
than a fixed tile count or travel-only rule.

![Generated two-frame reference sheet](spec/roamv/examples/summary/images/overview.png)

This is a draft with a schema, partial conformance checker, and fixtures, not an
end-to-end encoder or an established interoperability standard. The checker
reports source resolution and derivative reproduction as `not_checked`.

## Research and Legacy

[Research rationale](docs/ROAMV-DESIGN.md) and the
[implementation plan](docs/ROAMV-PLAN.md) preserve the evidence, alternatives, and
remaining work. The standalone specification takes precedence over earlier wire
sketches in those documents.

The original [opsis.py](opsis.py) compositor and [Unity adapters](adapters/)
remain separate legacy experiments. Their API and behavior have not changed and
they do not produce ROAMV packages. See the
[legacy explanation and provenance](docs/OPSIS-LEGACY.md) for their original
usage and known assumptions.
