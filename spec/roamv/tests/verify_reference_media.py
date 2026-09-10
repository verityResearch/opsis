"""Optional decoder checks for the bundled fixture, not a general ROAMV reader."""

from fractions import Fraction
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check import check_package, rational, strict_load


PACKAGE = Path(__file__).resolve().parents[1] / "examples" / "summary"


def command(args):
    return subprocess.run(args, check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=30).stdout


def rgb(path):
    return command([
        "ffmpeg", "-v", "error", "-nostdin", "-i", str(path), "-map", "0:v:0",
        "-vf", "format=rgb24", "-fps_mode", "passthrough", "-threads:v", "1",
        "-f", "rawvideo", "pipe:1",
    ])


class ReferenceMedia(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for tool in ("ffmpeg", "ffprobe"):
            if not shutil.which(tool):
                raise RuntimeError(f"{tool} is required for this optional fixture check")
        report = check_package(PACKAGE)
        if report["errors"]:
            raise RuntimeError(report["errors"])
        cls.manifest = strict_load(PACKAGE / "manifest.json")
        cls.source = PACKAGE / "media" / "source.mp4"
        cls.probe = json.loads(command([
            "ffprobe", "-v", "error", "-show_streams", "-show_frames", "-show_entries",
            "stream=index,codec_name,width,height,sample_aspect_ratio,sample_rate,channels,id,time_base:"
            "frame=stream_index,pts,pict_type,nb_samples", "-of", "json", str(cls.source),
        ]))
        cls.previews = {name: rgb(PACKAGE / "images" / f"frame-{index}.png")
                        for index, name in enumerate(("first", "last"), 1)}

    def test_streams_and_native_presentation_locators(self):
        streams = {stream["index"]: stream for stream in self.probe["streams"]}
        for stream in self.manifest["streams"].values():
            actual = streams[stream["locator"]["index"]]
            self.assertEqual(actual["id"], stream["locator"]["track_id"])
            self.assertEqual(actual["codec_name"], stream["codec"])
            self.assertEqual(Fraction(actual["time_base"]), rational(stream["time_base"]))
            if stream["kind"] == "video":
                self.assertEqual({key: actual[key] for key in ("width", "height")}, stream["dimensions"])
                self.assertEqual(actual["sample_aspect_ratio"], "1:1")
            else:
                self.assertEqual(int(actual["sample_rate"]), stream["sample_rate"])
                self.assertEqual(actual["channels"], stream["channels"])
        frames = [frame for frame in self.probe["frames"] if frame["stream_index"] == 0]
        self.assertEqual([frame["pts"] for frame in frames], [0, 4096, 8192, 12288])
        self.assertIn("B", [frame["pict_type"] for frame in frames])
        for sample_id in ("first", "last"):
            native = self.manifest["samples"][sample_id]["native"]
            self.assertEqual(frames[int(native["ordinal"])]["pts"], int(native["pts"]))

    def test_previews_equal_selected_decoded_rgb_frames(self):
        frames = rgb(self.source)
        frame_bytes = 160 * 90 * 3
        self.assertEqual(len(frames), frame_bytes * 4)
        for sample_id, preview in self.previews.items():
            ordinal = int(self.manifest["samples"][sample_id]["native"]["ordinal"])
            self.assertEqual(len(preview), frame_bytes)
            self.assertEqual(preview, frames[ordinal * frame_bytes:(ordinal + 1) * frame_bytes])

    def test_sheet_pixels_and_gap_equal_declared_layout(self):
        first, last = self.previews["first"], self.previews["last"]
        layout = self.manifest["sheets"]["overview"]["layout"]
        self.assertEqual((layout["columns"], layout["rows"], layout["tile_width"], layout["tile_height"]),
                         (2, 1, 160, 90))
        gap = bytes(layout["background"]) * layout["gap"]
        stride = layout["tile_width"] * 3
        expected = b"".join(first[y * stride:(y + 1) * stride] + gap
                            + last[y * stride:(y + 1) * stride] for y in range(90))
        self.assertEqual(rgb(PACKAGE / "images" / "overview.png"), expected)

    def test_audio_range_exists_after_priming_skip(self):
        native = self.manifest["samples"]["tone-window"]["native"]
        frames = [frame for frame in self.probe["frames"] if frame["stream_index"] == 1]
        self.assertEqual(frames[0]["pts"], int(native["pts"]))
        self.assertEqual(int(native["index"]), 0)
        for left, right in zip(frames, frames[1:]):
            self.assertEqual(left["pts"] + left["nb_samples"], right["pts"])
        pcm = command([
            "ffmpeg", "-v", "error", "-nostdin", "-i", str(self.source),
            "-map", "0:a:0", "-c:a", "pcm_s16le", "-f", "s16le", "pipe:1",
        ])
        channels = self.manifest["streams"]["audio"]["channels"]
        self.assertGreaterEqual(len(pcm) // (2 * channels), int(native["index"]) + int(native["count"]))


if __name__ == "__main__":
    unittest.main()
