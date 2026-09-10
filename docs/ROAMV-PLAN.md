# ROAMV Implementation and Validation Plan

The first deliverable should be a sealed mono-video package that resolves every
preview tile back to the correct source frame, reports its sampling gaps, and can
be read without an engine. Prove that contract before adding automatic semantic
analysis, synchronized capture, or live publication.

The [standalone specification](../spec/roamv/FORMAT.md) now defines the draft wire
contract; the [design research](ROAMV-DESIGN.md) explains its rationale. This plan
records the earlier baseline and the work needed to make the draft stable.

The self-contained [spec/roamv](../spec/roamv/) directory now supplies a schema,
checker for metadata, local integrity and text projection, negative tests, and
real reference media. Source-frame resolution, derivative reproduction, a general
encoder, and model-performance benchmarks remain unimplemented. Planned paths
and record names below are historical suggestions, not the current schema.
Legacy compositor and Unity repairs are an independent track, not gates for a
general-purpose format implementation.

## Current Evidence

The inspected baseline is commit `d7150bf`. At that baseline, the repository had
a standard-library Python compositor, a travel sampler, synthetic images, and
two Unity adapters, but no video demuxer, persistent frame identities, structured
manifests, package reader, or conformance suite. The standalone draft artifacts
listed above are subsequent work and do not fix the legacy counterexamples.

The Python probes below ran against that baseline. The media probe used local
FFmpeg `6.1.1-3ubuntu5`, encoding and inspecting a tiny H.264/Matroska fixture in
memory. These results demonstrate specific counterexamples, not model accuracy.
Unity observations are from source inspection; no Editor or capture test was run.

| Probe | Observed Result | Design Consequence |
| --- | --- | --- |
| Four identical camera positions | `select_by_travel` returns `[0]` | Translation alone cannot decide that a span has no visual, audio, or rotational activity |
| Positions `0,1,2,2,2` along one axis | Selected indexes `[0,1,2]` | The stationary tail is omitted even if an event happens there; selection needs independent coverage |
| Positions `0,0.1,3.1,3.2` along one axis | Selected indexes `[0,2]` | The sampler can omit the endpoint and leave capacity unused; record achieved spacing and endpoint policy |
| Unit square path returning to its start | Recorded path `4.0 m`; selected indexes `[0,2,4]`; selected chords `2.828427... m` | A manifest must not label selected chord distance as the complete recorded travel |
| One RGB frame followed by `pixels=None` | A sheet is composed; text does not mention missing data and claims frames are unaltered | Missing source pixels need an explicit failed selection and revised layout |
| Default four-tile geometry | `642x362`, about `0.870%` more pixels than `640x360` | Include separators in dimensions; equal image area does not establish equal token cost |
| VFR fixture, presentation timestamps | `0,100,400,900`, time base `1/1000` | Actual times are `0,0.1,0.4,0.9 s`; ordinal divided by nominal FPS is wrong |
| Same fixture, packet PTS order | `0,900,100,400` | Packet order must not become tile order |
| Periodic signal at integer-second samples | `sin(2*pi*t)` is zero at every sampled time but reaches one between samples | Identical sampled appearances cannot prove inactivity or establish a repetition count |

The relevant implementation locations are the
[Python sampler and manifest](../opsis.py),
[Unity capture and walk composition](../adapters/OpsisCapture.unity.cs), and
[Unity compositor and manifest](../adapters/RoamOpsis.unity.cs).

## Legacy Track: Make the Primitive Honest

Scope: `opsis.py`, the two existing adapters, focused regression fixtures, and
documentation of their behavior.

Validate dimensions, RGB buffer length, and supplied numerical metadata before
composing. Distinguish zero samples, one sample, missing pixels, invalid input,
and no detected activity. The compositor cannot infer scene inactivity merely
from sample count or position.

Make the stated sampling method come from selection metadata. An arbitrary list
of tiles must not automatically claim equal travel. Preserve the full recorded
path length when it is supplied, and otherwise label the computable selected
chord distance accurately. Replace the unconditional unaltered claim with the
actual resize and encoding description.

For Unity, guard basename output paths and missing `Camera` components, restore
render targets and release temporary textures on every failure path, and apply
the same missing-frame and rotation qualification rules as the Python path.
`OpsisOfWalk` needs explicit bounded selection shared by both eyes. Simply wiring
in the current travel sampler would still discard turns and stationary events;
the selection policy must state which signals it handles and what it omits.

Keep compatible call sites where practical, but do not preserve misleading
manifest claims as a compatibility requirement. Keep a separately recognizable
legacy manifest when a wire-level change would otherwise be ambiguous.

Exit evidence: focused Python tests cover missing buffers, malformed input,
stationary motion, rotation-only marks, travel versus chord distance, and layout
orientation. Equivalent Unity tests need an actual host project with the
`RoamState` accessor supplied. Source inspection or a synthetic Python image
does not establish Unity capture correctness.

## Stage 1: Define and Read a Minimal Package

Current artifacts: `spec/roamv/FORMAT.md`, `manifest.schema.json`, `check.py`,
`examples/`, and `tests/`. The checker uses the pinned JSON Schema dependency in
that directory. It does not import the legacy compositor or any engine code.
Remaining scope: reusable reading and writing APIs plus the retrieval operations
below. A green draft checker is not yet the full stage's exit evidence.

Implement exact rational times, source and stream identity, samples, spans,
sheets, coverage, runs, and assets. Keep related logic together initially; split
modules once the implementation has actual boundaries worth preserving. The
image compositor remains usable without the package layer.

Start with one embedded source, one video stream, one clock epoch, and explicitly
provided sample selection. Include a sealed synthetic package small enough for
the repository. Its text manifests must be generated from its JSON records and
its images must resolve to source samples.

Implement `inspect`, `verify`, `frame`, and `clip` as distinct operations. At this
stage, `frame` resolves materialized stills and `clip` returns source-interval
descriptors; actual media extraction arrives in Stage 2. The reader must return
structured outcomes for unsupported features and unavailable evidence. The
initial implementation can reject unsupported source types without inventing
replacement media.

Exit evidence: the minimal package validates; a changed image, unknown required
feature, broken sample reference, duplicate ID, malformed rational, and
disagreeing text manifest each produce the expected scoped failure. An ordinary
PNG viewer and text reader can still inspect the supplied sheet independently.

## Stage 2: Add Real Media Ingestion

Scope: `adapters/ffmpeg.py`, package-writing integration, and media fixtures.
FFmpeg and ffprobe are explicit external dependencies; their versions and
invocations become part of the producing run.

Probe streams using structured JSON. Preserve source bytes and native timestamps,
and index decoded presentation samples. Use argument arrays for subprocesses and
bounded reads. First support a sequential decode path whose ordering is easy to
verify; add accelerated seeking only after it agrees with that reference path.

Record actual frame identifiers after decoding. Reconcile display rotation,
sample aspect ratio, color properties, and source gaps before rendering a tile.
The prototype may initially support only declared SDR input, reporting HDR or
unsupported transformations as such. Add those conversions with explicit recipes
and fixtures before claiming support.

Keep media processing incremental. One RGB24 1920x1080 frame occupies about
5.93 MiB; retaining an hour at 30 FPS would require about 626 GiB before metadata
or copies. Decode, measure, and discard intermediate buffers, materializing only
needed frames. Shard catalogues as necessary, and keep any interval-query cache
rebuildable from the authoritative records.

Clip export must distinguish requested boundaries from actual output boundaries.
A stream-copy clip can begin before the desired point; an accurately trimmed
transcode is a different derivative. Both must retain a mapping to the original
source. Never identify a returned frame from the requested `-ss` value alone.

Exit evidence: CFR, VFR, B-frame, nonzero-origin, repeated-timestamp,
discontinuity, missing-timestamp, rotated, portrait, and truncated-input fixtures
resolve correctly or fail explicitly. Seek-based retrieval matches sequential
retrieval by source locator, with pixel comparisons only under the pinned decode
pipeline. A longer local clip demonstrates bounded memory.

## Stage 3: Add Selection With Coverage

Scope: selection policies and coverage accounting in the package layer, plus an
optional adapter around an established shot detector.

First ship explicit selection, uniform-time coverage, and improved travel
selection. Add orientation and supplied event boundaries next. Use the same
frame inventory across these policies so differences can be traced to selection
rather than decoding. Record both analysis scope and output scope.

Keep the first adaptive policy deterministic: named signal priorities, stable
tie-breaking, configurable temporal anchors, and explicit overflow behavior.
Every selected sample has a reason. Every required obligation is represented or
listed as unmet. Splitting a span must account for the total output budget, not
only the limit on each individual sheet.

Evaluate PySceneDetect as an optional shot-boundary producer. Pin and record its
version when integrating it; the rolling documentation cited in the design is
not itself a tested version constraint. Treat its boundaries as detector output
with parameters and uncertainty. Do not introduce object tracking, ASR, or a
learned ranking model until the simpler policies have measured deficiencies.

Exit evidence: a stationary crossing, turn-in-place, event during a walk's pause,
one-frame change, repeated action, flash without a cut, true cut, and dense event
span all retain appropriate coverage or explicitly report insufficiency. Travel
sampling no longer misreports full path length. Mandatory evidence exceeding the
budget cannot result in a falsely complete output.

## Stage 4: Evaluate the Reader Experience

Build a small retrieval harness that can serve identical evidence as a sheet,
separate stills, or a clip. Record exactly what reaches the reader, including
text, image dimensions, timestamps, audio, tool calls, and measured usage.
Version model and preprocessing configuration alongside results.

Begin with at least 24 deterministic synthetic cases, covering the failure
families below with positive and adversarial variants. Add a pilot of at least
12 real clips across embodied walks, fixed-camera actions, and screen or lecture
content. The existing example JPEGs are useful image fixtures but cannot replace
continuous video with audio and timing ground truth.

| Test Family | Example Question | Failure to Detect |
| --- | --- | --- |
| Observer versus object motion | Did the object move, or did the camera turn? | Apparent movement mislabeled as subject movement |
| Repetition and reversal | How many complete cycles occurred, and in which direction? | Aliasing, reversed order, or guessed counts |
| Pause and brief activity | What happened after walking stopped? | Travel-based omission or missed short events |
| Fine detail | Which control or value changed? | Tile downsampling removes decisive evidence |
| Cuts and transitions | Is this continuous motion or a new shot? | Montage interpreted as a trajectory |
| Audio and overlapping speech | Which event was audible but not visible? | Static imagery erases audio evidence |
| Source gaps and uncertainty | Can the event's order be determined? | Confident answer despite missing evidence |
| Long-range context | Which earlier state explains the later change? | Navigation loses source context or exhausts the budget |

Separate layout, sample count, and selection experiments. For layout, compare the
same four samples as individual images and a 2x2 sheet, then repeat with six
samples and a 3x2 sheet. For sample count, compare four versus six at fixed total
pixel budget, then at fixed per-frame resolution while measuring the extra cost.
For selection, hold output layout and nominal evidence budget constant while
comparing uniform, travel, and adaptive policies. Include native video as another
reader condition, accounting for its different internal sampling and actual cost.

Ground-truth annotations are held out from selection unless the experiment is
explicitly an oracle upper bound. Keep captions and audio identical across paired
conditions, and run a visual-only condition. Use paired question results and
confidence intervals, with session-separated calibration and evaluation sets.
The pilot is for debugging and estimating variance, not proving small differences.

Before the held-out comparison, set acceptable error margins for each task and a
minimum useful reduction in total measured cost or latency. Promote a default
only if it meets those criteria without unacceptable increases in missed events
or unsupported claims. A format can be useful for one task even when native
video wins another; the reader should retain both delivery paths.

Exit evidence: publish the corpus identities, split, questions, configurations,
per-question results, usage, timing, and failure analysis. Until those results
exist, describe cost and accuracy benefits as hypotheses.

## Stage 5: Add Multimodal and Capture Profiles

Scope: audio and annotation integrations; independently, an optional stereo
capture extension with shared selection. Stereo is not a core release gate.

Import supplied captions and events before adding automatic inference. Retain
the original audio and source references. Validate cue timing, language and
speaker fields, overlap, resampling offsets, and WebVTT export losses. An absent
transcript does not imply absent audio or silence.

For the optional stereo extension, define per-eye records, capture clock maps,
frame/capture IDs, calibration references, and explicit synchronization quality.
A hardware capture tool or simulator can produce these records. Measure or
guarantee the timing basis before declaring a synchronized pair. Use the same
selected pairs for both eyes and retain explicit failures for missing eye data.
Simulation clocks belong to an adapter, not the general media core.

Exit evidence: a moving test target exposes a swapped eye, unequal selection,
skewed pair, and missing eye. Pausing or changing simulation time does not corrupt
capture ordering. Validate resource cleanup during induced capture errors in the
actual capture environment. An engine adapter needs its own runtime validation;
it is not a dependency of ordinary video or audio readers.

## Stage 6: Stabilize Interoperability and Scale

Add a second independent reader before freezing version 1. It can be a minimal
JavaScript reader using exact integer arithmetic, without any engine integration.
Compare semantic interpretation and source resolution; do not demand byte-equal
PNG and JPEG outputs from different adapters.

Next evaluate linked-source delivery, archival export, and dense telemetry.
Add OTIO and Web Annotation exports only with round-trip tests for supported
fields and explicit reports for losses. Preserve source credentials without
claiming that ROAMV's hash verification validates a C2PA signature.

Live publication follows sealed-package reliability. Define immutable chunks,
manifest generations, progress markers, late events, crash recovery, and
resumption. Fault injection must demonstrate that readers continue using the last
complete generation after an interrupted publication. Partial records or media
chunks must never appear as complete evidence.

Exit evidence: two readers agree on normative fixtures, sealed packages survive
transport and integrity checks, and every advertised extension has its own
capability and failure tests. Do not label unimplemented extensions as part of
version 1 merely because this document describes them.

## Reproducing the Counterexamples

Run these from the repository root. They use no source-media files and make no
repository changes.

```bash
python3 -B - <<'PY'
import math
import opsis

paths = {
    "stationary": [(0, 0, 0)] * 4,
    "pause": [(x, 0, 0) for x in (0, 1, 2, 2, 2)],
    "sparse": [(x, 0, 0) for x in (0, 0.1, 3.1, 3.2)],
    "square": [(0, 0, 0), (1, 0, 0), (1, 1, 0),
               (0, 1, 0), (0, 0, 0)],
}
for name, path in paths.items():
    keep = opsis.select_by_travel(path, 4)
    selected = [path[i] for i in keep]
    distance = lambda p: sum(math.dist(a, b) for a, b in zip(p, p[1:]))
    print(name, keep, distance(path), distance(selected))

result = opsis.compose([
    opsis.Tile(bytes(8 * 8 * 3), 8, 8),
    opsis.Tile(None, 8, 8, elapsed=1),
], tile_w=8, tile_h=8)
print("missing", result.composed, "missing" in result.manifest.lower())
print("sheet", 642, 362, (642 * 362 / (640 * 360) - 1) * 100)
print("periodic", [round(math.sin(2 * math.pi * t), 10) for t in range(4)],
      math.sin(2 * math.pi * 0.25))
PY
```

The media probe requires an FFmpeg build with `libx264` and the Matroska muxer:

```bash
python3 -B - <<'PY'
import json
import subprocess

video = subprocess.run([
    "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
    "testsrc2=size=64x36:rate=10:duration=1",
    "-vf", r"select=eq(n\,0)+eq(n\,1)+eq(n\,4)+eq(n\,9)",
    "-fps_mode", "passthrough", "-c:v", "libx264", "-threads", "1",
    "-x264-params", "b-adapt=0:keyint=30:min-keyint=30:scenecut=0",
    "-bf", "2", "-f", "matroska", "pipe:1",
], capture_output=True, check=True, timeout=20).stdout

for kind in ("frames", "packets"):
    result = subprocess.run([
        "ffprobe", "-v", "error", "-show_streams", "-show_" + kind,
        "-select_streams", "v:0", "-of", "json", "pipe:0",
    ], input=video, capture_output=True, check=True, timeout=20)
    data = json.loads(result.stdout)
    print(kind, data["streams"][0]["time_base"],
          [row["pts"] for row in data[kind]])
PY
```

These commands establish the current behavior recorded above. They are not
regression expectations for the corrected sampler or compositor; implementation
tests should encode the intended contracts instead.
