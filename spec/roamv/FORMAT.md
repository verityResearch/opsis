# ROAMV General-Purpose Video Format

ROAMV packages ordinary media with exact source references, timed annotations,
and optional visual summaries. It is designed for recordings, films, screen
captures, lectures, remote cameras, image sequences, and generated media. People,
media applications, search systems, and multimodal models can consume the same
package.

This document defines **0.1.0-draft.1, sealed core**. It is a standalone draft:
implementations need no game engine, camera rig, world coordinates, capture SDK,
or particular programming language. The companion
[JSON Schema](manifest.schema.json) defines its record shapes. Earlier research
documents are informative; this document defines this draft's wire contract.

The core preserves the media's existing encoding. It defines how to identify,
select, describe, and retrieve that media. A source file remains playable by an
ordinary player that supports its codec. A ROAMV package itself requires a reader
or extraction of the source file; no existing player support for `.roamv` is
assumed. The name and extension are provisional and no MIME registration is
claimed.

## 1. Conformance

In this draft, MUST, MUST NOT, SHOULD, and MAY express requirements,
prohibitions, recommendations, and optional behavior respectively.

Four roles can be implemented independently:

| Role | Required Behavior |
| --- | --- |
| Producer | Write a structurally and semantically valid manifest; identify source bytes; declare derivatives and unavailable evidence |
| Metadata reader | Parse the core, resolve internal references, preserve exact times, and reject unsupported required extensions |
| Media reader | Additionally resolve and decode media types it advertises; return an explicit unsupported or unavailable result otherwise |
| Validator | Identify which validation levels it performed, rather than treating schema validity as complete conformance |

The normative checks are JSON decoding, schema validation, semantic validation,
asset integrity, text projection, source resolution, and derivative reproduction.
Each has its own result: `pass`, `fail`, `unavailable`, `unsupported`, or
`not_checked`. Source resolution and derivative reproduction generally require
media decoders and the relevant processing implementation.

This directory includes a draft checker for the first five levels and portable
fixtures. It is not a video encoder or a complete source-resolution validator.
Passing it does not prove annotation accuracy or a claimed processing history.

## 2. Packaging

A sealed core package has one root file, `manifest.json`, and the local assets
referenced by that manifest. Directory names are arbitrary. The suffix `.roamv`
is a suggested directory convention.

```text
example.roamv/
  manifest.json
  media/source.mp4
  images/first.png               optional selected still
  images/last.png                optional selected still
  images/overview.png            optional sheet
  text/overview.txt              required when that sheet is present
```

All record collections in this draft are **inline maps in `manifest.json`**.
JSONL catalogues, binary indexes, archive embedding, and live publication are
future profiles; a core reader MUST NOT guess those dialects. An ordinary archive
can transport a sealed directory without changing its semantics.

Local asset paths are relative POSIX paths. They MUST have no empty, `.` or `..`
segments, leading slash, backslash, colon, or control characters. Paths are
literal strings, not percent-decoded URIs. Referenced local assets MUST be regular
files inside the package, with no symbolic links in their path. An asset MUST NOT
be `manifest.json`, which would introduce a self-referential checksum.

A manifest identifies a fixed revision. Producers SHOULD finish assets before
publishing the root manifest. Changing a referenced asset or record creates a
new revision. Unreferenced files are outside the sealed package's authority.

`source_mode` is `embedded` when all assets are local. In `linked` mode, source
assets MAY instead have a URI or an explicit unavailability reason. Their known
byte identities are still required. Derived assets MUST be local in this core
profile. A linked manifest can be valid while source access is unavailable.

The revision's content digest is SHA-256 over the exact `manifest.json` bytes,
including whitespace. That digest is exchanged externally; it is not a field in
the file it hashes. Root records contain the byte lengths and hashes of assets.
An external expected digest is necessary to identify a specific revision across
an untrusted transfer. Internal consistency alone does not establish authenticity.

## 3. JSON and Identifiers

Manifest bytes MUST be UTF-8 JSON without a byte-order mark. Duplicate object
keys, non-finite numbers, and invalid Unicode strings MUST be rejected. Core
record objects are closed: unknown core fields are invalid. Application data
belongs in a defined extension or an annotation's `data` value.

This draft uses [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12/json-schema-core)
for structural constraints. JSON parsing and the cross-record rules below are
additional requirements. In particular, a schema cannot by itself compare a tile
timestamp against its referenced span or verify a file digest.

IDs are case-sensitive strings matching the schema's `id` definition. A record's
ID is its key in its collection, not an embedded `id` field. IDs need only be
unique within their collection. Reference field definitions determine the target
collection; arbitrary objects in annotation data are not implicitly references.

Missing optional collections mean empty collections. Missing optional `children`,
`related`, `entrypoints`, and `issues` arrays mean empty arrays. All other absent
optional data is unspecified. `null` is accepted only where the schema permits
it and means unknown, unavailable, or an explicitly unbounded mapping boundary
as defined below. It never implies zero.

## 4. Root Manifest

| Field | Requirement | Meaning |
| --- | --- | --- |
| `format` | Required | Literal `ROAMV` |
| `version` | Required | Literal `0.1.0-draft.1` |
| `id`, `revision` | Required | Logical package and revision identifiers; not content digests |
| `time_unit` | Required | Literal `second` |
| `source_mode` | Required | `embedded` or `linked` |
| `required_extensions` | Required | Extension identifiers required for correct interpretation; empty for the unextended core |
| `assets`, `streams` | Required, nonempty | Byte objects and logical media streams |
| `time_maps`, `samples`, `spans` | Optional | Native-time correspondence, identified observations, and intervals |
| `sheets`, `coverage`, `annotations` | Optional | Visual summaries, selection accounting, and descriptions or measurements |
| `processes` | Optional | Named, versioned producing or indexing procedures; required whenever referenced |
| `entrypoints` | Optional | Span IDs, in preferred navigation order |
| `title`, `extensions` | Optional | Display title and extension payloads |

A basic package needs only media assets, stream descriptions, and the process
records those streams reference. Sheets, annotations, poses, transcripts, and
automatic selection are not prerequisites. Audio-only and image-only packages
are valid. Continuous source video is retained even when a sheet selects sparse
frames from it.

## 5. Assets, Streams, and Processes

An asset describes one byte object using `role`, `media_type`, `bytes`, `sha256`,
and `location`. `bytes` is a canonical decimal integer string; `sha256` is exactly
64 lowercase hexadecimal characters. The location is exactly one of
`{"path": "..."}`, `{"uri": "..."}`, or `{"unavailable": "reason"}`.
Media types use the schema's lowercase `type/subtype` spelling, without parameters.
URI locations have an explicit scheme and no raw whitespace or control characters.
A URI identifies an external resource; it neither grants access nor guarantees
that a reader supports its scheme. Scheme-specific resolution is a media-reader
responsibility, not a consequence of passing this schema.

A `source` asset MUST state its `origin`: `recorded`, `screen_capture`,
`generated`, `imported`, or `unknown`. Source means an input to this package; it
does not certify camera capture or absence of earlier edits. A `derived` asset
MUST name its producing `process`. Image assets also declare their decoded raster
`dimensions` and `color_space`; use `unspecified` when the latter is not known.

A stream references one asset and has kind `video`, `audio`, `image`, or `data`.
Its locator is a `container_track` with an index and optional container track ID,
or `whole_asset`. Its `process` identifies how that locator was interpreted.
The indexing process MUST list the stream's asset among its inputs.
Video and image streams declare raster dimensions; audio declares sample rate
and channel count. Codec labels are descriptive and do not require every reader
to implement every codec.

`time_base` is a positive rational number of seconds per native timestamp tick,
or `null` when unavailable. It is not frame rate. Acquisition is `continuous`,
`sparse`, or `unknown`, and describes the source stream, not the summary sampler.
An image sequence can use one image stream per source file with timed samples.
Combining sparse captures into a video creates a derivative; it does not change
the capture coverage of the originals.

A process declares `name`, `version`, input **asset IDs**, and a `parameters`
object. Optional description and extension data can add context. Parameters
describe the procedure; readers do not execute them. Ordered transformations
belong in an ordered array inside those parameters. A process can describe a
human selection, decoder, recorder, transcoder, detector, or supplied metadata.
No process name or executable is mandated.

Asset dependencies, found through their producing processes' input
assets, MUST be acyclic. An asset MUST NOT appear among its own transitive
inputs. A process with no input assets is permitted for authored text or generated
content; it does not establish a link to unseen source media.

## 6. Time

All normalized times use one package-relative time axis. Its origin is chosen by
the producer and established by the time maps or supplied sample times. Zero does
not imply UTC, recording start, or a physical clock epoch. Negative times are
valid, including preroll. Independent source clocks retain separate time maps.

Exact values use a reduced rational:

```json
{"n": "1001", "d": "30000"}
```

The numerator is a canonical signed decimal integer string; the denominator is
a positive canonical decimal integer string. Leading zeros, plus signs, negative
zero, and common factors are invalid. Zero is always `{"n":"0","d":"1"}`.
PTS, frame ordinals, audio sample indexes, and byte lengths are also integer
strings. This avoids depending on all JSON implementations preserving large
numeric literals exactly. [RFC 8259, section 6](https://www.rfc-editor.org/rfc/rfc8259#section-6)

Every interval is half-open, `[start,end)`, with `start < end`. A boundary frame
at `end` belongs to the next interval. This follows the temporal interval
convention of [Media Fragments](https://www.w3.org/TR/media-frags/#naming-time).
Point events can target a sample; they do not require an invalid zero-length span.

A time map names a stream, discontinuity `epoch`, native PTS domain, rate,
offset, uncertainty, and producing process. Within that domain:

```text
package_time = offset + rate * native_pts * stream.time_base
```

`rate` MUST be positive. The mapping domain is `[start_pts,end_pts)`; a `null`
boundary is unbounded on that side within the named source epoch. Mappings for
the same stream and epoch MUST NOT overlap. An epoch changes when resets or
discontinuities invalidate native ordering. Piecewise maps can describe measured
offset and clock drift. Editing operations such as reverse playback, speed ramps,
or compositing multiple clips require a future editorial profile.

Uncertainty is a nonnegative rational bound in package seconds, or `null` if
unmeasured. An exact PTS-to-presentation-time mapping can have zero uncertainty
without making any claim about physical exposure time. An unknown bound cannot
establish cross-camera synchronization. Unaligned observations remain valid
samples with unknown normalized time; they cannot enter a chronological sheet.

## 7. Samples and Spans

A sample has a stream, native locator, normalized time, `time_basis`, uncertainty,
and indexing process. The optional `image` references a materialized PNG preview.
The source remains the stream's asset, even when that preview is available.
The preview MUST be that image asset itself or have that source asset among its
transitive processing inputs.

| Native Kind | Required Locator | Meaning |
| --- | --- | --- |
| `frame` | Epoch, zero-based presentation ordinal, PTS or `null` | One displayed video frame; not a packet index |
| `image` | Kind only | The image stream's entire asset |
| `audio` | Epoch, zero-based decoded sample index, sample count, PTS or `null` | A contiguous range of decoded audio sample frames across all channels |
| `record` | Epoch, zero-based record index, PTS or `null` | An observation in a data stream |

Native kind MUST agree with stream kind. Native ordinals and sample indexes are
defined by the stream's indexing process, with any decoder delay, trimming, and
error policy recorded in its parameters. Repeated PTS values are distinguished
by native ordinal or index. Reuse an existing sample ID when referencing the same
native observation; do not create contradictory duplicate locators.
`sample.process` MUST equal `stream.process`. Alternative indexing interpretations
use distinct stream IDs. Known frame times MUST be nondecreasing with presentation
ordinal within a stream and epoch.
An audio sample's time identifies the first decoded sample frame in its range,
not its midpoint or end. The count remains a native duration measure; a range
crossing a time-map boundary requires the applicable maps to interpret its end.

For `time_basis: mapped`, `time_map` is required. The map's stream and epoch MUST
match the sample, its domain MUST contain the sample's non-null PTS, and `time`
MUST equal the exact mapping result. Sample uncertainty MUST be unknown when the
map's uncertainty is unknown. Otherwise it may be unknown, but any stated bound
MUST be no smaller than the map's bound.

For `provided`, the time is supplied by the indexing process and `time_map` is
absent or null. That process MUST describe the timing basis, including estimation
when applicable. For `unknown`, time, uncertainty, and any `time_map` are null.
An ordinal divided by nominal FPS MUST NOT be represented as an observed PTS.

A span has kind `segment`, `shot`, `chapter`, or `event`, exact start and end,
stream membership, and its producing process. Children MUST be temporally
contained, use a subset of the parent's streams, and form an acyclic graph.
`related` references permit cross-links, overlap, and shared context. They carry
no containment or causal implication. Any number of annotation spans can overlap.

No duration or physical motion is inferred from absent samples. Audio ranges
retain their native count even when they share a timestamp with a video frame.

## 8. Sheets and Text

A sheet is optional. It contains at least two visual samples, an image asset,
a UTF-8 text asset, span, role, layout, selection record, render process, and
issues. A single sample is delivered as a still; zero samples yields an explicit
unavailable or insufficient response by the consuming application.

Core sheet images and materialized sample previews use `image/png`. Other image
types can exist as sources. Additional preview encodings require an extension.
Both sheet image and text are derived assets. The image's producing process MUST
equal the sheet's `render_process`.
For each tile, the sheet image's transitive processing inputs MUST include the
sample's preview asset if supplied, or its stream asset otherwise.

Layout has columns `C`, rows `R`, tile width `w`, tile height `h`, gap `g`, and an
RGB background. Its image dimensions MUST be:

```text
width  = C*w + (C-1)*g
height = R*h + (R-1)*g
```

Cells are indexed from zero, left to right, then top to bottom. Cell `i` begins
at `((i % C)*(w+g), floor(i/C)*(h+g))`. Tiles explicitly identify occupied cells;
unlisted cells are empty background and MUST NOT be counted as observations.
Every cell is occupied at most once. Tile arrays MUST be in strictly increasing
cell order, and samples MUST be nondecreasing in normalized time. Repeated times
retain source presentation order within a stream and epoch.

The role `sequence` states temporal ordering, not continuous observation, a single
shot, or causation. `overview` describes a broader summary. Neither role implies
uniform sampling. A four-tile default is a reader choice, not a format limit.

`content_rect` is `[x,y,width,height]` relative to the tile cell, and fits inside
it. `source_rect` is null for the complete input raster or a rectangle within a
materialized sample preview. An explicit source crop requires `sample.image`,
which fixes the coordinate space independently of video decoder orientation.
Coordinates have a top-left origin and half-open pixel edges. Outside content
rectangles, gaps, and empty cells use the declared background.

The render process MUST declare applicable decoding, orientation, color,
cropping, resampling, padding, and encoding steps. Scaling SHOULD preserve
display aspect ratio. Any deliberate distortion MUST be declared as a sheet
issue. Unknown color interpretation stays unspecified; a metadata label alone
does not establish a color conversion. Source text remains part of the image.
Core source tiles MUST NOT be annotated, dimmed, synthesized, or patched to
represent missing evidence. Such imagery can be a separately declared derivative.

A missing selected frame causes omission and revised selection accounting, or
an insufficient result. A black rectangle MUST NOT stand for a missing source
sample. A genuinely black source frame is an ordinary identified sample.

### Text Projection

Text files use UTF-8, LF endings, and a final LF. The following lines are emitted
in order, with single spaces between tokens. Values that are arrays or free text
use compact JSON, preserving Unicode and escaping control characters. Fractions
use `n/d`. The logical revision is used rather than the root digest.
Integer-valued layout fields and rectangle/background elements are rendered as
base-10 integers without a decimal point or exponent.

```text
ROAMV 0.1.0-draft.1 sheet SHEET_ID
package PACKAGE_ID revision REVISION
role ROLE span SPAN_ID [START,END) seconds
layout CxR tile WxH gap G background [r,g,b] order row_major
selection METHOD status STATUS tiles N budget B
tile CELL sample SAMPLE_ID stream STREAM_ID time N/D basis BASIS uncertainty VALUE content [x,y,w,h] source VALUE
sample_issue SAMPLE_ID CODE "DETAIL"
coverage COVERAGE_ID stream STREAM_ID analysis MODE max_selected_gap N/D
issue CODE "DETAIL"
unmet "OBLIGATION"
```

Emit one tile line per tile, followed by that sample's issues, and one coverage
line per selection coverage ID, in their declared order. Uncertainty is a fraction
or the literal `unknown`; source is the JSON rectangle or `null`. Emit coverage
issues immediately after their coverage line, then sheet issues, then unmet
obligations. An issue with an
interval appends ` interval [START,END)` to its line. When a list is empty, emit
no lines for it. Absent crop and unknown uncertainty do not omit their tokens.

The draft checker's `sheet_text` function is an executable rendering of this
template. The serialized text MUST agree with the current records exactly.
Readers can also display a richer presentation, but that presentation cannot
override the manifest's source identity or qualifications.

## 9. Selection and Coverage

Every sheet states its selection method, parameters, process, tile budget, status,
unmet obligations, and coverage IDs. The format mandates no detector or selection
algorithm. Explicit selection, uniform time, scene boundaries, local visual
change, audio events, and observer travel can all be represented. There is no
requirement to record observer travel or pose.

The tile count MUST NOT exceed its declared budget. `satisfied` means the named
policy's declared obligations were met and `unmet` is empty. It does not mean
all events were captured. `insufficient` requires at least one stated unmet
obligation. More sheets can be produced, but applications must also account for
any overall delivery budget.

Coverage is recorded per span and per stream, avoiding the implication that one
camera's samples cover another. Each sheet references exactly one coverage record
for each stream it displays. Each coverage record's `selected_samples` MUST
equal that sheet's samples for the stream, in presentation order. Shared coverage
records are permitted only when that equality holds for every referencing sheet.

`analysis` has the following meaning:

| Value | Required Data | Claim |
| --- | --- | --- |
| `not_run` | Null process, empty analyzed sample and interval lists | No analysis procedure is claimed |
| `sampled` | Process and nonempty analyzed sample IDs; empty interval list | Procedure inspected those identified samples |
| `all_samples` | Process and nonempty disjoint intervals; empty sample list | Procedure inspected every available source sample in those intervals |

These claims describe the named procedure's inputs, not its semantic accuracy or
activity between source captures. An interval in `all_samples` can still contain
a source acquisition gap; that gap MUST be reported as an issue. No-change
observations must identify their method and scope. None of these analysis modes
means that no event occurred.

Every selected and analyzed sample MUST belong to the coverage stream and lie
inside the span. Analysis intervals MUST be contained by the span and not overlap.
The `max_selected_gap` is exactly the greatest difference between consecutive
values in the sorted list consisting of span start, selected sample times, and
span end. With no selected samples it is the span duration. This is a measure
of presented timestamp spacing, not a bound on missed events or exposure time.

Issues contain a code, detail, and optional interval. Codes are extensible labels,
not instructions. Useful labels include `not_analyzed`, `source_gap`,
`decode_failure`, `timestamp_estimated`, `budget_exhausted`, and `color_unspecified`.
Unknown codes MUST remain visible. Issue intervals associated with a coverage
record MUST be inside its span.

## 10. Annotations and Audio

Annotations hold captions, transcripts, events, measurements, or notes. Each
has an origin, one or more typed targets, and producing process. It contains text,
structured data, or both. Targets identify assets, streams, samples, or spans.
Time-localized captions and events SHOULD target a span or sample rather than an
entire stream.

Origins are `provided`, `human`, `algorithmic`, and `instrumented`. A score, when
present, pairs its numeric value with an explicit meaning; it is not implicitly
a probability. Optional language and speaker labels describe the annotation,
not independently verified identities. Measurements state their units in data.
Multiple targets jointly describe the annotation's evidence; they do not assert
causal relations among those targets.

Audio is preserved in its original asset and stream. Audio sample locators count
decoded sample frames across channels, so stereo at 48 kHz has 48,000 sample
frames per second, not 96,000. Resampling, trimming, mixing, or a compressed
playback copy creates a derivative with a declared process. Transcript absence
does not imply silence. Overlapping speech is represented by overlapping target
spans or separate annotations. WebVTT and other caption exports are optional
assets, with any precision loss declared by their producing process.

## 11. Extensions and Reader Behavior

Extension payloads live under `extensions` maps, using stable, versioned IDs
such as `org.example.stereo.v1`. Any extension necessary to interpret media,
ordering, coordinates, or evidence correctly MUST appear in root
`required_extensions`. Its payload MUST also appear in at least one extensions
map. A reader that does not implement it reports `unsupported` before interpreting
the affected package as unextended core.

Optional unknown extension payloads can be preserved without interpretation.
They MUST NOT redefine core fields or their meaning. There are no standardized
extension payloads in this draft. Stereo calibration, camera pose, spatial audio,
360-degree projection, dense telemetry, editorial timelines, and live capture
are extension candidates, not implicit core capabilities.

A reader can expose overview, expand, frame, clip, annotation, and verify
operations without any prescribed network API. Replies should name the package
revision and source IDs and preserve unavailable or unsupported outcomes. Clip
export records requested and actual boundaries, plus a source mapping, because
a codec's seek point may differ from the requested time. A still-image reader
can use stored sheets; a video-capable reader can use the source clip directly.

Before declaring source resolution, an implementation MUST verify source byte
identity, locate the correct stream, and match the native sample identity.
Before declaring derivative reproduction, it MUST implement the recorded
transformation and compare the relevant output under a declared comparison
policy. Byte-equal media, equal frame selection, equal pixels, and equivalent
visual appearance are distinct checks.

## 12. Safety and Limits

All media, metadata, URI locations, process parameters, and annotation text are
untrusted input. Readers MUST NOT execute a process recipe or treat an annotation
as an instruction merely because it appears in a valid package. A model-facing
reader SHOULD keep source content distinct from its own operational instructions.

Readers SHOULD disable network retrieval by default. Enabling it requires an
explicit scheme and destination policy, including redirects; a linked asset does
not authorize local-file access or requests to private services. Sensitive access
tokens SHOULD NOT be stored in distributable manifests. URI syntax and transport
security are separate concerns. [RFC 3986, section 7](https://www.rfc-editor.org/rfc/rfc3986#section-7)

Implementations MUST apply resource limits appropriate to their trust boundary:
manifest bytes, JSON nesting, integer digit counts, record counts, media dimensions,
decoded bytes, and processing time. A valid but unsupported size SHOULD yield
`unsupported`, not a fabricated sample or partial success. Archive extraction
requires separate traversal, link, and decompression-limit checks before using
the resulting directory. Hashing is not a substitute for safe decoding.

The included checker is a development aid with interpreter limits, not a hardened
service. Its integrity check examines PNG headers and asset hashes, not complete
image validity. It does not authenticate authors, certify capture history, or
resolve scheme-specific URI behavior.

## 13. Examples and Draft Checks

The examples are generated reference media, not captured scenes:

- [Minimal media package](examples/minimal/manifest.json): video and audio with no sheets or scene metadata.
- [Summary package](examples/summary/manifest.json): the same media, exact frame references, timed annotation, coverage, PNG previews, and sheet text.
- [Linked package](examples/linked/manifest.json): known source identity deliberately omitted from the directory.

Run the supplied checks from this directory with Python 3.10 or later and the
dependency in [requirements.txt](requirements.txt):

```bash
python3 -B check.py examples/minimal
python3 -B check.py examples/summary
python3 -B check.py examples/linked
python3 -B -m unittest discover -s tests -v
```

The checker performs no network fetches and advertises its unchecked levels in
its output. It validates schema, cross-references, rational arithmetic, layout,
selection accounting, local byte identities, and the text projection. The tests
include invalid counterexamples, so examples alone do not define the format.
