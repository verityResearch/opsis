from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check import (InvalidManifest, UnsupportedExtension, check_package, sheet_text,
                   strict_load, validate_schema, validate_semantics)


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "examples" / "summary"


class DraftContracts(unittest.TestCase):
    def setUp(self):
        self.manifest = strict_load(SUMMARY / "manifest.json")

    def validate(self, manifest=None):
        manifest = self.manifest if manifest is None else manifest
        validate_schema(manifest)
        validate_semantics(manifest)

    def assert_invalid(self, code):
        with self.assertRaises(InvalidManifest) as result:
            self.validate()
        self.assertEqual(result.exception.code, code)

    def test_embedded_examples_and_declared_limits(self):
        for name in ("minimal", "summary"):
            with self.subTest(name=name):
                report = check_package(ROOT / "examples" / name)
                self.assertEqual(report["errors"], [])
                for level in ("json", "schema", "semantics", "integrity", "text"):
                    self.assertEqual(report["levels"][level], "pass")
                for level in ("source_resolution", "derivative_reproduction"):
                    self.assertEqual(report["levels"][level], "not_checked")

    def test_linked_source_is_unavailable_not_verified(self):
        report = check_package(ROOT / "examples" / "linked")
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["levels"]["integrity"], "unavailable")
        self.assertEqual(report["unavailable_assets"], ["source"])

    def test_invalid_field_counterexamples(self):
        cases = [
            (("samples", "first", "stream"), "absent", "dangling_reference"),
            (("samples", "first", "native", "pts"), 0, "schema"),
            (("samples", "first", "native", "pts"), "0\n", "schema"),
            (("samples", "first", "time", "n"), "-0", "schema"),
            (("samples", "first", "time", "d"), "0", "schema"),
            (("samples", "first", "time", "d"), "2", "rational_not_reduced"),
            (("samples", "last", "time"), {"n": "1", "d": "2"}, "mapped_time"),
            (("samples", "last", "native", "ordinal"), "0", "duplicate_native_sample"),
            (("samples", "tone-window", "native", "count"), "-1", "schema"),
            (("time_maps", "video-time", "end_pts"), "12000", "mapping_outside_domain"),
            (("time_maps", "video-time", "uncertainty"), {"n": "1", "d": "100"}, "uncertainty_bound"),
            (("spans", "whole", "end"), {"n": "0", "d": "1"}, "interval_order"),
            (("spans", "whole", "children"), ["whole"], "span_cycle"),
            (("assets", "source", "location", "path"), "../source.mp4", "asset_path"),
            (("assets", "source", "location", "path"), "media/../source.mp4", "asset_path"),
            (("assets", "source", "location", "path"), "manifest.json", "self_hash"),
            (("assets", "source", "location"), {"uri": "https://example.invalid/\nsource.mp4"}, "schema"),
            (("assets", "first-image", "media_type"), "IMAGE/PNG", "schema"),
            (("processes", "render", "inputs"), ["sheet-image"], "asset_cycle"),
            (("assets", "sheet-text", "media_type"), "application/octet-stream", "sheet_assets"),
            (("sheets", "overview", "layout", "columns"), 3, "sheet_dimensions"),
            (("sheets", "overview", "tiles", 1, "cell"), 2, "tile_cell"),
            (("sheets", "overview", "tiles", 1, "content_rect"), [0, 0, 161, 90], "content_rect"),
            (("sheets", "overview", "tiles", 1, "source_rect"), [0, 0, 161, 90], "source_rect"),
            (("sheets", "overview", "selection", "tile_budget"), 1, "tile_budget"),
            (("sheets", "overview", "selection", "unmet"), ["event omitted"], "schema"),
            (("coverage", "video-preview", "max_selected_gap"), {"n": "1", "d": "100"}, "coverage_gap"),
            (("coverage", "video-preview", "analysis"), "sampled", "schema"),
        ]
        original = self.manifest
        for keys, value, code in cases:
            with self.subTest(path=keys, value=value):
                self.manifest = deepcopy(original)
                target = self.manifest
                for key in keys[:-1]:
                    target = target[key]
                target[keys[-1]] = value
                self.assert_invalid(code)

    def test_timestamp_precision_beyond_binary64(self):
        offset = 9007199254740993
        for mapping in self.manifest["time_maps"].values():
            mapping["offset"] = {"n": str(offset), "d": "1"}
        for sample in self.manifest["samples"].values():
            time = sample["time"]
            time["n"] = str(int(time["n"]) + offset * int(time["d"]))
        span = self.manifest["spans"]["whole"]
        span["start"] = {"n": str(offset), "d": "1"}
        span["end"] = {"n": str(offset + 1), "d": "1"}
        issue = self.manifest["coverage"]["video-preview"]["issues"][0]
        issue["interval"] = {"start": span["start"], "end": span["end"]}
        self.validate()

    def test_half_open_span_excludes_boundary_sample(self):
        self.manifest["time_maps"]["video-time"]["end_pts"] = None
        last = self.manifest["samples"]["last"]
        last["native"]["pts"] = "16384"
        last["time"] = {"n": "1", "d": "1"}
        self.assert_invalid("sample_outside_span")

    def test_overlapping_time_maps_are_ambiguous(self):
        self.manifest["time_maps"]["duplicate"] = deepcopy(self.manifest["time_maps"]["video-time"])
        self.assert_invalid("mapping_overlap")

    def test_sample_cannot_use_another_streams_time_map(self):
        self.manifest["samples"]["first"]["time_map"] = "audio-time"
        self.assert_invalid("mapping_source")

    def test_duplicate_pts_with_distinct_ordinals(self):
        last = self.manifest["samples"]["last"]
        last["native"]["pts"] = "0"
        last["time"] = {"n": "0", "d": "1"}
        self.manifest["coverage"]["video-preview"]["max_selected_gap"] = {"n": "1", "d": "1"}
        self.validate()
        tiles = self.manifest["sheets"]["overview"]["tiles"]
        tiles[0]["sample"], tiles[1]["sample"] = "last", "first"
        self.assert_invalid("tied_presentation_order")

    def test_packet_order_cannot_replace_tile_order(self):
        tiles = self.manifest["sheets"]["overview"]["tiles"]
        tiles[0]["sample"], tiles[1]["sample"] = "last", "first"
        self.assert_invalid("tile_time_order")

    def test_sheet_coverage_cannot_omit_a_displayed_frame(self):
        coverage = self.manifest["coverage"]["video-preview"]
        coverage["selected_samples"] = ["first"]
        coverage["max_selected_gap"] = {"n": "1", "d": "1"}
        self.assert_invalid("sheet_coverage")

    def test_unknown_time_is_valid_outside_chronological_views(self):
        last = self.manifest["samples"]["last"]
        last.update(time=None, time_basis="unknown", time_map=None, uncertainty=None)
        self.assert_invalid("unaligned_sample")
        self.manifest.pop("sheets")
        self.manifest.pop("coverage")
        self.validate()

    def test_unmeasured_mapping_does_not_become_exact(self):
        self.manifest["time_maps"]["video-time"]["uncertainty"] = None
        self.assert_invalid("uncertainty_bound")
        for name in ("first", "last"):
            self.manifest["samples"][name]["uncertainty"] = None
        self.validate()

    def test_analysis_intervals_are_scoped_and_disjoint(self):
        coverage = self.manifest["coverage"]["video-preview"]
        coverage.update(analysis="all_samples", analysis_process="index")
        coverage["analyzed_intervals"] = [
            {"start": {"n": "0", "d": "1"}, "end": {"n": "2", "d": "1"}}
        ]
        self.assert_invalid("analysis_outside_span")
        coverage["analyzed_intervals"][0]["end"] = {"n": "1", "d": "1"}
        self.validate()
        coverage["analyzed_intervals"].append(
            {"start": {"n": "1", "d": "2"}, "end": {"n": "1", "d": "1"}})
        self.assert_invalid("analysis_overlap")

    def test_extensions_do_not_silently_change_core(self):
        self.manifest["extensions"] = {"org.example.test.v1": {"axis": "alternate"}}
        self.validate()
        self.manifest["required_extensions"] = ["org.example.test.v1"]
        with self.assertRaises(UnsupportedExtension):
            self.validate()
        self.manifest["extensions"] = {}
        self.assert_invalid("extension_payload_missing")

    def test_arbitrary_annotation_data_is_not_a_core_rational(self):
        self.manifest["annotations"]["tone"]["data"] = {"n": 0, "d": 0}
        self.validate()

    def test_audio_only_package_needs_no_visual_samples(self):
        manifest = strict_load(ROOT / "examples" / "minimal" / "manifest.json")
        del manifest["streams"]["video"]
        self.validate(manifest)

    def test_image_only_package_needs_no_clock_or_pose(self):
        asset = deepcopy(self.manifest["assets"]["first-image"])
        asset.update(role="source", origin="generated")
        asset.pop("process")
        manifest = {key: self.manifest[key] for key in (
            "format", "version", "id", "revision", "time_unit", "source_mode", "required_extensions")}
        manifest["assets"] = {"still": asset}
        manifest["streams"] = {"image": {
            "asset": "still", "kind": "image", "locator": {"kind": "whole_asset"},
            "time_base": None, "dimensions": asset["dimensions"], "acquisition": "sparse", "process": "index",
        }}
        manifest["processes"] = {"index": {"name": "image-index", "version": "1", "inputs": ["still"], "parameters": {}}}
        manifest["samples"] = {"one": {
            "stream": "image", "native": {"kind": "image"}, "time": None,
            "time_basis": "unknown", "uncertainty": None, "process": "index", "image": "still",
        }}
        self.validate(manifest)

    def test_sample_qualifications_reach_text(self):
        self.manifest["samples"]["first"]["issues"] = [{
            "code": "timestamp_estimated", "detail": 'Qualification with "quotes" and\na newline.'
        }]
        self.validate()
        text = sheet_text(self.manifest, "overview")
        self.assertIn('sample_issue first timestamp_estimated "Qualification with \\"quotes\\" and\\na newline."', text)

    def test_strict_json_parsing(self):
        cases = [
            (b'{"a":1,"a":2}', "duplicate_key"),
            (b'{"nested":{"a":1,"a":2}}', "duplicate_key"),
            (b'{"value":NaN}', "nonfinite_number"),
            (b'{"value":Infinity}', "nonfinite_number"),
            (b'{"value":"\\ud800"}', "invalid_unicode"),
            (b'\xef\xbb\xbf{}', "byte_order_mark"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            for raw, code in cases:
                with self.subTest(raw=raw):
                    path.write_bytes(raw)
                    with self.assertRaises(InvalidManifest) as result:
                        strict_load(path)
                    self.assertEqual(result.exception.code, code)
            path.write_bytes(b'{"value":1e1000}')
            self.assertEqual(strict_load(path)["value"], Decimal("1e1000"))

    def test_integral_json_numbers_have_canonical_text(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / "package"
            shutil.copytree(SUMMARY, package)
            self.manifest["sheets"]["overview"]["layout"]["columns"] = 2.0
            self.manifest["sheets"]["overview"]["layout"]["background"] = [90.0, 90.0, 96.0]
            (package / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")
            report = check_package(package)
            self.assertEqual(report["errors"], [])
            self.assertEqual(report["levels"]["text"], "pass")

    def test_root_manifest_name_is_fixed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "alternate.json"
            path.write_text(json.dumps(self.manifest), encoding="utf-8")
            report = check_package(path)
            self.assertEqual(report["levels"]["semantics"], "fail")
            self.assertIn("manifest_name", report["errors"][0]["message"])

    def test_linked_uri_is_not_fetched(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = strict_load(ROOT / "examples" / "linked" / "manifest.json")
            manifest["assets"]["source"]["location"] = {"uri": "https://example.invalid/source.mp4"}
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            report = check_package(path)
            self.assertEqual(report["errors"], [])
            self.assertEqual(report["levels"]["integrity"], "unavailable")
            self.assertEqual(report["unavailable_assets"], ["source"])

    def test_asset_symlinks_are_not_followed(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / "package"
            shutil.copytree(SUMMARY, package)
            path = package / "media" / "source.mp4"
            path.unlink()
            path.symlink_to(SUMMARY / "media" / "source.mp4")
            report = check_package(package)
            self.assertEqual(report["levels"]["integrity"], "fail")
            self.assertIn("asset_symlink", report["errors"][0]["message"])

    def test_corrupt_media_fails_integrity(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / "package"
            shutil.copytree(SUMMARY, package)
            path = package / "media" / "source.mp4"
            raw = bytearray(path.read_bytes())
            raw[-1] ^= 1
            path.write_bytes(raw)
            report = check_package(package)
            self.assertEqual(report["levels"]["integrity"], "fail")
            self.assertIn("asset_hash", report["errors"][0]["message"])

    def test_missing_embedded_media_is_failure_not_linked(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / "package"
            shutil.copytree(SUMMARY, package)
            (package / "media" / "source.mp4").unlink()
            report = check_package(package)
            self.assertEqual(report["levels"]["integrity"], "fail")

    def test_rehashed_text_still_must_match_records(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / "package"
            shutil.copytree(SUMMARY, package)
            path = package / "text" / "overview.txt"
            raw = path.read_bytes().replace(b"analysis not_run", b"analysis all_samples")
            path.write_bytes(raw)
            asset = self.manifest["assets"]["sheet-text"]
            asset.update(bytes=str(len(raw)), sha256=hashlib.sha256(raw).hexdigest())
            (package / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")
            report = check_package(package)
            self.assertEqual(report["levels"]["integrity"], "pass")
            self.assertEqual(report["levels"]["text"], "fail")
            self.assertIn("text_projection", report["errors"][0]["message"])


if __name__ == "__main__":
    unittest.main()
