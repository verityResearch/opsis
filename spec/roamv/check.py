#!/usr/bin/env python3
"""Check the sealed ROAMV draft without importing a capture or media framework."""

from __future__ import annotations

import argparse
from collections import defaultdict
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import stat
import struct

from jsonschema import Draft202012Validator


COLLECTIONS = (
    "assets", "streams", "time_maps", "samples", "spans", "sheets", "coverage",
    "annotations", "processes",
)
SCHEMA_PATH = Path(__file__).with_name("manifest.schema.json")


class InvalidManifest(ValueError):
    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f"{code}: {detail}")


class UnsupportedExtension(InvalidManifest):
    pass


def require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise InvalidManifest(code, detail)


def strict_load(path: Path) -> dict:
    def object_pairs(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, "duplicate_key", key)
            value[key] = item
        return value

    def constant(value):
        raise InvalidManifest("nonfinite_number", value)

    def number(value):
        parsed = Decimal(value)
        # Core JSON integers fit this range; other numeric data stays exact.
        if parsed.copy_abs() <= 2147483647 and parsed == parsed.to_integral_value():
            return int(parsed)
        return parsed

    def strings(value):
        if isinstance(value, str):
            require(not any(0xD800 <= ord(c) <= 0xDFFF for c in value),
                    "invalid_unicode", "unpaired surrogate")
        elif isinstance(value, dict):
            for key, item in value.items():
                strings(key)
                strings(item)
        elif isinstance(value, list):
            for item in value:
                strings(item)

    raw = path.read_bytes()
    require(not raw.startswith(b"\xef\xbb\xbf"), "byte_order_mark", str(path))
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=object_pairs,
                       parse_constant=constant, parse_float=number)
    strings(value)
    return value


def rational(value: dict) -> Fraction:
    n, d = int(value["n"]), int(value["d"])
    require(d > 0 and math.gcd(n, d) == 1, "rational_not_reduced", str(value))
    return Fraction(n, d)


def interval(value: dict) -> tuple[Fraction, Fraction]:
    start, end = rational(value["start"]), rational(value["end"])
    require(start < end, "interval_order", str(value))
    return start, end


def validate_schema(manifest: dict) -> None:
    schema = strict_load(SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    error = next(Draft202012Validator(schema).iter_errors(manifest), None)
    if error:
        location = "/" + "/".join(map(str, error.absolute_path))
        raise InvalidManifest("schema", f"{location}: {error.message}")


def validate_semantics(manifest: dict, supported_extensions=()) -> None:
    tables = {name: manifest.get(name, {}) for name in COLLECTIONS}

    def ref(table, key):
        require(key in tables[table], "dangling_reference", f"{table}/{key}")
        return tables[table][key]

    def issues(items, bounds=None):
        for item in items:
            if "interval" in item:
                start, end = interval(item["interval"])
                if bounds:
                    require(bounds[0] <= start < end <= bounds[1],
                            "issue_outside_span", item["code"])

    records = [manifest] + [record for table in tables.values() for record in table.values()]
    extension_ids = {key for record in records for key in record.get("extensions", {})}
    for key in manifest["required_extensions"]:
        require(key in extension_ids, "extension_payload_missing", key)
    unknown = set(manifest["required_extensions"]) - set(supported_extensions)
    if unknown:
        raise UnsupportedExtension("unsupported_extension", ", ".join(sorted(unknown)))

    for asset_id, asset in tables["assets"].items():
        location = asset["location"]
        if manifest["source_mode"] == "embedded" or asset["role"] == "derived":
            require("path" in location, "local_asset_required", asset_id)
        if "path" in location:
            path = location["path"]
            require(not any(c in path for c in "\\:")
                    and not any(ord(c) < 32 or ord(c) == 127 for c in path)
                    and all(p not in ("", ".", "..") for p in path.split("/")),
                    "asset_path", path)
            require(path != "manifest.json", "self_hash", asset_id)
        if "process" in asset:
            ref("processes", asset["process"])

    for process in tables["processes"].values():
        for asset_id in process["inputs"]:
            ref("assets", asset_id)

    ancestors = {}
    active = set()

    def asset_ancestors(asset_id):
        if asset_id in ancestors:
            return ancestors[asset_id]
        require(asset_id not in active, "asset_cycle", asset_id)
        active.add(asset_id)
        asset = ref("assets", asset_id)
        parents = ref("processes", asset["process"])["inputs"] if "process" in asset else []
        result = set(parents)
        for parent in parents:
            result.update(asset_ancestors(parent))
        active.remove(asset_id)
        ancestors[asset_id] = result
        return result

    for asset_id in tables["assets"]:
        asset_ancestors(asset_id)

    for stream_id, stream in tables["streams"].items():
        asset = ref("assets", stream["asset"])
        process = ref("processes", stream["process"])
        require(stream["asset"] in process["inputs"], "index_input", stream_id)
        if stream["time_base"] is not None:
            rational(stream["time_base"])
        if stream["kind"] == "image":
            require(stream["locator"]["kind"] == "whole_asset"
                    and asset["media_type"].startswith("image/")
                    and stream["dimensions"] == asset["dimensions"],
                    "image_stream", stream_id)

    map_domains = defaultdict(list)
    for map_id, mapping in tables["time_maps"].items():
        stream = ref("streams", mapping["stream"])
        ref("processes", mapping["process"])
        require(stream["time_base"] is not None, "missing_time_base", map_id)
        rational(mapping["rate"])
        rational(mapping["offset"])
        if mapping["uncertainty"] is not None:
            rational(mapping["uncertainty"])
        start = None if mapping["start_pts"] is None else int(mapping["start_pts"])
        end = None if mapping["end_pts"] is None else int(mapping["end_pts"])
        require(start is None or end is None or start < end, "mapping_domain", map_id)
        map_domains[(mapping["stream"], mapping["epoch"])].append((start, end, map_id))
    for domains in map_domains.values():
        domains.sort(key=lambda d: (d[0] is not None, d[0] or 0))
        for left, right in zip(domains, domains[1:]):
            require(left[1] is not None and right[0] is not None and left[1] <= right[0],
                    "mapping_overlap", f"{left[2]}, {right[2]}")

    native_keys = set()
    frame_times = defaultdict(list)
    for sample_id, sample in tables["samples"].items():
        stream = ref("streams", sample["stream"])
        ref("processes", sample["process"])
        require(sample["process"] == stream["process"], "index_process", sample_id)
        native = sample["native"]
        expected = {"video": "frame", "audio": "audio", "image": "image", "data": "record"}
        require(native["kind"] == expected[stream["kind"]], "sample_kind", sample_id)
        key = (sample["stream"], native["kind"], native.get("epoch"),
               native.get("ordinal", native.get("index")), native.get("count"))
        require(key not in native_keys, "duplicate_native_sample", sample_id)
        native_keys.add(key)
        time = None if sample["time"] is None else rational(sample["time"])
        uncertainty = None if sample["uncertainty"] is None else rational(sample["uncertainty"])
        if sample["time_basis"] == "mapped":
            mapping = ref("time_maps", sample["time_map"])
            pts = native.get("pts")
            require(pts is not None and mapping["stream"] == sample["stream"]
                    and mapping["epoch"] == native.get("epoch"), "mapping_source", sample_id)
            pts = int(pts)
            require((mapping["start_pts"] is None or int(mapping["start_pts"]) <= pts)
                    and (mapping["end_pts"] is None or pts < int(mapping["end_pts"])),
                    "mapping_outside_domain", sample_id)
            expected_time = rational(mapping["offset"]) + rational(mapping["rate"]) * pts * rational(stream["time_base"])
            require(time == expected_time, "mapped_time", sample_id)
            bound = mapping["uncertainty"]
            require((bound is None and uncertainty is None)
                    or (bound is not None and (uncertainty is None or uncertainty >= rational(bound))),
                    "uncertainty_bound", sample_id)
        if native["kind"] == "frame" and time is not None:
            frame_times[(sample["stream"], native["epoch"])].append((int(native["ordinal"]), time))
        if "image" in sample:
            image = ref("assets", sample["image"])
            require(image["media_type"] == "image/png", "preview_encoding", sample_id)
            require(stream["asset"] == sample["image"] or stream["asset"] in ancestors[sample["image"]],
                    "preview_source", sample_id)
        issues(sample.get("issues", []))
    for times in frame_times.values():
        ordered = sorted(times)
        require(all(a[1] <= b[1] for a, b in zip(ordered, ordered[1:])),
                "presentation_order", str(ordered))

    span_bounds = {}
    for span_id, span in tables["spans"].items():
        span_bounds[span_id] = interval(span)
        ref("processes", span["process"])
        for stream_id in span["streams"]:
            ref("streams", stream_id)
        for related in span.get("related", []):
            ref("spans", related)
    for span_id in manifest.get("entrypoints", []):
        ref("spans", span_id)
    visited = set()
    active = set()

    def visit_span(span_id):
        require(span_id not in active, "span_cycle", span_id)
        if span_id in visited:
            return
        active.add(span_id)
        span = ref("spans", span_id)
        for child_id in span.get("children", []):
            child = ref("spans", child_id)
            a, b = span_bounds[span_id]
            c, d = span_bounds[child_id]
            require(a <= c < d <= b and set(child["streams"]) <= set(span["streams"]),
                    "child_containment", child_id)
            visit_span(child_id)
        active.remove(span_id)
        visited.add(span_id)

    for span_id in tables["spans"]:
        visit_span(span_id)

    def scoped_sample(sample_id, span_id, stream_id=None):
        sample = ref("samples", sample_id)
        span = ref("spans", span_id)
        require(sample["stream"] in span["streams"]
                and (stream_id is None or sample["stream"] == stream_id),
                "sample_scope", sample_id)
        require(sample["time"] is not None, "unaligned_sample", sample_id)
        time = rational(sample["time"])
        start, end = span_bounds[span_id]
        require(start <= time < end, "sample_outside_span", sample_id)
        return sample, time

    for coverage_id, coverage in tables["coverage"].items():
        span_id = coverage["span"]
        span = ref("spans", span_id)
        require(coverage["stream"] in span["streams"], "coverage_stream", coverage_id)
        bounds = span_bounds[span_id]
        times = []
        for sample_id in coverage["selected_samples"]:
            _, time = scoped_sample(sample_id, span_id, coverage["stream"])
            times.append(time)
        require(times == sorted(times), "selection_order", coverage_id)
        points = [bounds[0], *times, bounds[1]]
        gap = max(b - a for a, b in zip(points, points[1:]))
        require(gap == rational(coverage["max_selected_gap"]), "coverage_gap", coverage_id)
        if coverage["analysis_process"] is not None:
            ref("processes", coverage["analysis_process"])
        for sample_id in coverage["analyzed_samples"]:
            scoped_sample(sample_id, span_id, coverage["stream"])
        ranges = sorted(interval(item) for item in coverage["analyzed_intervals"])
        require(all(bounds[0] <= a < b <= bounds[1] for a, b in ranges),
                "analysis_outside_span", coverage_id)
        require(all(a[1] <= b[0] for a, b in zip(ranges, ranges[1:])),
                "analysis_overlap", coverage_id)
        issues(coverage["issues"], bounds)

    for sheet_id, sheet in tables["sheets"].items():
        ref("spans", sheet["span"])
        image, text_asset = ref("assets", sheet["image"]), ref("assets", sheet["text"])
        require(image["media_type"] == "image/png" and image["role"] == "derived"
                and text_asset["media_type"] == "text/plain" and text_asset["role"] == "derived",
                "sheet_assets", sheet_id)
        ref("processes", sheet["render_process"])
        require(image["process"] == sheet["render_process"], "render_process", sheet_id)
        layout = sheet["layout"]
        cols, rows = layout["columns"], layout["rows"]
        tw, th, gap = layout["tile_width"], layout["tile_height"], layout["gap"]
        size = {"width": cols * tw + (cols - 1) * gap, "height": rows * th + (rows - 1) * gap}
        require(image["dimensions"] == size, "sheet_dimensions", sheet_id)
        selection = sheet["selection"]
        ref("processes", selection["process"])
        require(len(sheet["tiles"]) <= selection["tile_budget"], "tile_budget", sheet_id)
        cells, sample_ids, times = [], [], []
        by_stream = defaultdict(list)
        tied_ordinals = {}
        for tile in sheet["tiles"]:
            sample_id = tile["sample"]
            sample, time = scoped_sample(sample_id, sheet["span"])
            require(sample["native"]["kind"] in ("frame", "image"), "visual_sample", sample_id)
            require(tile["cell"] < cols * rows, "tile_cell", sample_id)
            x, y, w, h = tile["content_rect"]
            require(x + w <= tw and y + h <= th, "content_rect", sample_id)
            base_asset = sample.get("image", ref("streams", sample["stream"])["asset"])
            require(base_asset in ancestors[sheet["image"]], "render_input", sample_id)
            if tile["source_rect"] is not None:
                require("image" in sample, "crop_requires_preview", sample_id)
                dims = ref("assets", sample["image"])["dimensions"]
                x, y, w, h = tile["source_rect"]
                require(x + w <= dims["width"] and y + h <= dims["height"], "source_rect", sample_id)
            native = sample["native"]
            if native["kind"] == "frame":
                tie = (sample["stream"], native["epoch"], time)
                ordinal = int(native["ordinal"])
                require(tie not in tied_ordinals or tied_ordinals[tie] < ordinal,
                        "tied_presentation_order", sample_id)
                tied_ordinals[tie] = ordinal
            cells.append(tile["cell"])
            sample_ids.append(sample_id)
            times.append(time)
            by_stream[sample["stream"]].append(sample_id)
        require(cells == sorted(set(cells)), "cell_order", sheet_id)
        require(len(sample_ids) == len(set(sample_ids)), "duplicate_tile_sample", sheet_id)
        require(times == sorted(times), "tile_time_order", sheet_id)
        covered = set()
        for coverage_id in selection["coverage"]:
            coverage = ref("coverage", coverage_id)
            require(coverage["span"] == sheet["span"] and coverage["stream"] not in covered
                    and coverage["stream"] in by_stream
                    and coverage["selected_samples"] == by_stream[coverage["stream"]],
                    "sheet_coverage", coverage_id)
            covered.add(coverage["stream"])
        require(covered == set(by_stream), "missing_sheet_coverage", sheet_id)
        issues(sheet["issues"], span_bounds[sheet["span"]])

    target_tables = {"asset": "assets", "stream": "streams", "sample": "samples", "span": "spans"}
    for annotation in tables["annotations"].values():
        ref("processes", annotation["process"])
        for target in annotation["targets"]:
            ref(target_tables[target["type"]], target["id"])


def sheet_text(manifest: dict, sheet_id: str) -> str:
    sheet = manifest["sheets"][sheet_id]
    span = manifest["spans"][sheet["span"]]
    layout, selection = sheet["layout"], sheet["selection"]

    def q(value):
        return f'{value["n"]}/{value["d"]}'

    def j(value):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)

    def issue_lines(items, prefix="issue"):
        for item in items:
            suffix = ""
            if "interval" in item:
                bounds = item["interval"]
                suffix = f' interval [{q(bounds["start"])},{q(bounds["end"])})'
            yield f'{prefix} {item["code"]} {j(item["detail"])}{suffix}'

    lines = [
        f'ROAMV {manifest["version"]} sheet {sheet_id}',
        f'package {manifest["id"]} revision {manifest["revision"]}',
        f'role {sheet["role"]} span {sheet["span"]} [{q(span["start"])},{q(span["end"])}) seconds',
        f'layout {layout["columns"]}x{layout["rows"]} tile {layout["tile_width"]}x{layout["tile_height"]} gap {layout["gap"]} background {j(layout["background"])} order row_major',
        f'selection {selection["method"]} status {selection["status"]} tiles {len(sheet["tiles"])} budget {selection["tile_budget"]}',
    ]
    for tile in sheet["tiles"]:
        sample = manifest["samples"][tile["sample"]]
        uncertainty = "unknown" if sample["uncertainty"] is None else q(sample["uncertainty"])
        lines.append(f'tile {tile["cell"]} sample {tile["sample"]} stream {sample["stream"]} time {q(sample["time"])} basis {sample["time_basis"]} uncertainty {uncertainty} content {j(tile["content_rect"])} source {j(tile["source_rect"])}')
        lines.extend(issue_lines(sample.get("issues", []), f'sample_issue {tile["sample"]}'))
    for coverage_id in selection["coverage"]:
        coverage = manifest["coverage"][coverage_id]
        lines.append(f'coverage {coverage_id} stream {coverage["stream"]} analysis {coverage["analysis"]} max_selected_gap {q(coverage["max_selected_gap"])}')
        lines.extend(issue_lines(coverage["issues"]))
    lines.extend(issue_lines(sheet["issues"]))
    lines.extend(f'unmet {j(item)}' for item in selection["unmet"])
    return "\n".join(lines) + "\n"


def check_package(path: Path) -> dict:
    levels = {key: "not_checked" for key in (
        "json", "schema", "semantics", "integrity", "text",
        "source_resolution", "derivative_reproduction",
    )}
    report = {"levels": levels, "unavailable_assets": [], "errors": []}
    manifest_path = path / "manifest.json" if path.is_dir() else path
    level = "json"
    try:
        manifest = strict_load(manifest_path)
        levels[level] = "pass"
        level = "schema"
        validate_schema(manifest)
        levels[level] = "pass"
        level = "semantics"
        require(manifest_path.name == "manifest.json", "manifest_name", str(manifest_path))
        validate_semantics(manifest)
        levels[level] = "pass"
        level = "integrity"
        root = manifest_path.parent.resolve()
        local = {}
        for asset_id, asset in manifest["assets"].items():
            location = asset["location"]
            if "path" not in location:
                report["unavailable_assets"].append(asset_id)
                continue
            asset_path = root
            for part in location["path"].split("/"):
                asset_path /= part
                require(not asset_path.is_symlink(), "asset_symlink", asset_id)
            info = asset_path.stat()
            require(stat.S_ISREG(info.st_mode), "asset_not_file", asset_id)
            require(info.st_size == int(asset["bytes"]), "asset_size", asset_id)
            digest = hashlib.sha256()
            with asset_path.open("rb") as handle:
                header = handle.read(24)
                digest.update(header)
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(block)
            require(digest.hexdigest() == asset["sha256"], "asset_hash", asset_id)
            if asset["media_type"] == "image/png":
                require(len(header) == 24 and header[:16] == b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR",
                        "png_header", asset_id)
                width, height = struct.unpack(">II", header[16:24])
                require(asset["dimensions"] == {"width": width, "height": height},
                        "image_dimensions", asset_id)
            local[asset_id] = asset_path
        levels[level] = "unavailable" if report["unavailable_assets"] else "pass"
        level = "text"
        for sheet_id, sheet in manifest.get("sheets", {}).items():
            require(local[sheet["text"]].read_bytes() == sheet_text(manifest, sheet_id).encode("utf-8"),
                    "text_projection", sheet_id)
        levels[level] = "pass"
    except UnsupportedExtension as error:
        levels[level] = "unsupported"
        report["errors"].append({"level": level, "message": str(error)})
    except (ValueError, OSError, RecursionError) as error:
        levels[level] = "fail"
        report["errors"].append({"level": level, "message": str(error)})
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path, help="package directory or manifest path")
    args = parser.parse_args()
    report = check_package(args.package)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if "unsupported" in report["levels"].values():
        return 2
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
