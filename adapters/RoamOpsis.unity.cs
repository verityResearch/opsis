#if UNITY_EDITOR
using System.Collections.Generic;
using System.IO;
using System.Text;
using UnityEngine;

// ROAM/1 opsis — the shape of what happened.
//
//   stigme (στιγμή)  a point without extension — one look, full resolution
//   kairos (καιρός)  the span between two looks, as lived — structure, in text
//   opsis  (ὄψις)    the SEEING of that span — its shape, as one image
//
// WHAT THIS IS FOR, stated narrowly because v1 overclaimed.
//
// An opsis is NOT a substitute for looking. Two full-resolution looks cost ~3,000
// tokens and carry bark grain, leaf veins, the fork in a trunk. A four-tile sheet
// costs ~1,500 and carries none of that — each tile arrives at a quarter of a
// look's resolution before the vision encoder even sees it. Anyone reaching for
// this to SEE a place has chosen the wrong tool.
//
// What it is good for is the one question a still cannot answer: what CHANGED
// across the span, and in what shape.
//   - a mover crossing        -> a streak walking across tiles
//   - cairn's own turning     -> the whole field sliding, nothing moving against it
//   - approach                -> something growing in place
//   - a static span           -> tiles that differ only by parallax
// Those are distinguishable at a glance and nearly indistinguishable as tables of
// numbers. That is the entire claim.
//
// THREE CORRECTIONS FROM v1, each one a rule this file had already written down:
//
// 1. NOTHING IS ENCODED INTO PIXELS. v1 marked unmeasurable frames by dimming and
//    cross-ruling them — destroying frame content to carry one bit that was
//    already in the manifest. Data in pixels is invisible to this reader by
//    construction; that is the founding constraint of the whole format family,
//    and v1 violated it three functions below stating it. Frames are now shown
//    unaltered or not shown at all.
//
// 2. SAMPLED BY TRAVEL, NOT BY TIME. On a real walk — 4.9 m covered, then two
//    seconds standing still — an even time sample produced two informative tiles
//    and seven identical ones. Seven-ninths of the budget spent on a stationary
//    body. The project's own thesis is that the baseline that matters is travel;
//    the sheet is now sampled the same way, at roughly equal displacement.
//
// 3. FEWER TILES. Four by default. A 2x2 of 320x180 is exactly the pixel budget
//    of one 640x360 look, which makes the trade legible: one look's worth of
//    attention, spent on four moments instead of one.
public static class RoamOpsis
{
    public class Tile
    {
        public Texture2D image;
        public float elapsed;        // world-seconds from span start
        public Vector3 pos;
        public float yaw;
        public string note = "";
    }

    const int Rule = 2;

    /// Pick frames at roughly equal TRAVEL, not equal time. Returns indices into
    /// `poses`. A frame that adds no displacement adds no information, so the
    /// stationary tail of a span is simply not sampled.
    public static List<int> SelectByTravel(IList<Vector3> poses, int maxTiles, float minStep = 0.15f)
    {
        var chosen = new List<int>();
        if (poses == null || poses.Count == 0) return chosen;
        chosen.Add(0);
        if (poses.Count == 1 || maxTiles <= 1) return chosen;

        // total path length, then aim for evenly spaced arc-length stops
        float total = 0f;
        for (int i = 1; i < poses.Count; i++) total += Vector3.Distance(poses[i - 1], poses[i]);
        if (total < minStep) return chosen;                 // never really moved

        float target = total / (maxTiles - 1);
        float acc = 0f, since = 0f;
        for (int i = 1; i < poses.Count && chosen.Count < maxTiles; i++)
        {
            float d = Vector3.Distance(poses[i - 1], poses[i]);
            acc += d; since += d;
            bool last = (i == poses.Count - 1);
            if (since >= target - 1e-4f || (last && since >= minStep))
            {
                chosen.Add(i);
                since = 0f;
            }
        }
        return chosen;
    }

    public static void GridFor(int n, out int cols, out int rows)
    {
        if (n <= 1) { cols = 1; rows = 1; return; }
        if (n == 2) { cols = 2; rows = 1; return; }
        cols = Mathf.CeilToInt(Mathf.Sqrt(n));
        if (cols > 3) cols = 3;
        rows = Mathf.CeilToInt((float)n / cols);
    }

    /// Compose the sheet. Frames are drawn unaltered; every qualification lives in
    /// the manifest, which is the half of the channel that arrives intact.
    public static string Compose(List<Tile> tiles, string path, int tileW = 320, int tileH = 180)
    {
        if (tiles == null || tiles.Count == 0)
            return "ROAM/1  opsis\n  unavailable: no frames";
        if (tiles.Count == 1)
            return "ROAM/1  opsis\n  not composed: only one distinct position in this span — "
                 + "nothing changed to have a shape. Use a stigme instead.";

        int cols, rows;
        GridFor(tiles.Count, out cols, out rows);
        int W = cols * tileW + (cols - 1) * Rule;
        int H = rows * tileH + (rows - 1) * Rule;

        var sheet = new Texture2D(W, H, TextureFormat.RGB24, false);
        var px = new Color32[W * H];
        var ruleCol = new Color32(90, 90, 96, 255);
        for (int i = 0; i < px.Length; i++) px[i] = ruleCol;

        for (int i = 0; i < tiles.Count; i++)
        {
            int c = i % cols, r = i / cols;
            // Texture2D is bottom-origin; rows laid out top-first so the sheet reads
            // the way it is written. Reversing this would silently reverse time.
            Blit(px, W, H, tiles[i], c * (tileW + Rule), (rows - 1 - r) * (tileH + Rule), tileW, tileH);
        }

        sheet.SetPixels32(px); sheet.Apply();
        var bytes = sheet.EncodeToJPG(90);
        Object.DestroyImmediate(sheet);
        Directory.CreateDirectory(Path.GetDirectoryName(path));
        File.WriteAllBytes(path, bytes);
        return Manifest(tiles, cols, rows, tileW, tileH, path, bytes.Length);
    }

    static void Blit(Color32[] dst, int W, int H, Tile tile, int x0, int y0, int tw, int th)
    {
        Color32[] src = null; int sw = 0, sh = 0;
        if (tile.image != null)
        {
            try { src = tile.image.GetPixels32(); sw = tile.image.width; sh = tile.image.height; }
            catch { src = null; }
        }
        for (int y = 0; y < th; y++)
        for (int x = 0; x < tw; x++)
        {
            Color32 c;
            if (src == null) c = new Color32(24, 24, 28, 255);
            else
            {
                int sx = sw == tw ? x : Mathf.Clamp(x * sw / tw, 0, sw - 1);
                int sy = sh == th ? y : Mathf.Clamp(y * sh / th, 0, sh - 1);
                c = src[sy * sw + sx];
            }
            int dx = x0 + x, dy = y0 + y;
            if (dx >= 0 && dx < W && dy >= 0 && dy < H) dst[dy * W + dx] = c;
        }
    }

    static string Manifest(List<Tile> tiles, int cols, int rows, int tw, int th, string path, int bytes)
    {
        var sb = new StringBuilder();
        sb.AppendLine("ROAM/1  opsis   (the shape of what happened — NOT a substitute for looking)");
        sb.Append("grid ").Append(cols).Append("x").Append(rows)
          .Append("  tiles ").Append(tw).Append("x").Append(th)
          .Append("  ").Append(tiles.Count).Append(" frames  ").Append(bytes / 1024).AppendLine(" KB");
        sb.AppendLine("reading order: left to right, top to bottom — the layout IS the ordering.");
        sb.AppendLine("frames are UNALTERED; every qualification is here in text, never in pixels.");
        sb.AppendLine("sampled at equal TRAVEL, so tiles are not equally spaced in time.");

        float span = tiles[tiles.Count - 1].elapsed - tiles[0].elapsed;
        float dist = 0f;
        for (int i = 1; i < tiles.Count; i++) dist += Vector3.Distance(tiles[i - 1].pos, tiles[i].pos);
        sb.Append("span ").Append(span.ToString("F2")).Append(" world-s, ")
          .Append(dist.ToString("F2")).Append(" m travelled");
        if (tiles.Count > 1) sb.Append(", ~").Append((dist / (tiles.Count - 1)).ToString("F2")).Append(" m per tile");
        sb.AppendLine();

        for (int i = 0; i < tiles.Count; i++)
        {
            var t = tiles[i];
            sb.Append("  tile ").Append(i.ToString().PadLeft(2))
              .Append("  +").Append(t.elapsed.ToString("F2")).Append("s");
            if (i > 0) sb.Append("  +").Append(Vector3.Distance(tiles[i-1].pos, t.pos).ToString("F2")).Append("m");
            else sb.Append("   start ");
            sb.Append("  (").Append(t.pos.x.ToString("F2")).Append(",")
              .Append(t.pos.y.ToString("F2")).Append(",").Append(t.pos.z.ToString("F2")).Append(")")
              .Append("  yaw ").Append(t.yaw.ToString("F0").PadLeft(3));
            if (!string.IsNullOrEmpty(t.note)) sb.Append("  ").Append(t.note);
            sb.AppendLine();
        }
        sb.Append("written: ").Append(path);
        return sb.ToString();
    }

    // ---- standalone verification -------------------------------------------
    public enum Motion { Still, Sweep, Crossing, Approach }

    public static string SelfTest(Motion motion, string path, int frames = 4)
    {
        var tiles = new List<Tile>();
        for (int i = 0; i < frames; i++)
        {
            tiles.Add(new Tile {
                image = Synth(motion, i, frames, 320, 180),
                elapsed = i * 0.45f,
                pos = new Vector3(i * 0.5f, 0.75f, 0f),
                yaw = motion == Motion.Sweep ? 320f + i * 8f : 355f,
            });
        }
        string m = Compose(tiles, path);
        foreach (var t in tiles) if (t.image != null) Object.DestroyImmediate(t.image);
        return "self-test: " + motion + "\n" + m;
    }

    static Texture2D Synth(Motion m, int i, int n, int w, int h)
    {
        var tex = new Texture2D(w, h, TextureFormat.RGB24, false);
        var px = new Color32[w * h];
        float f = (float)i / Mathf.Max(1, n - 1);
        for (int y = 0; y < h; y++)
        for (int x = 0; x < w; x++)
        {
            int band = ((x + (m == Motion.Sweep ? (int)(f * 120f) : 0)) / 26) % 2;
            byte g = (byte)Mathf.Clamp((band == 0 ? 70 : 105) + (y * 40 / h), 0, 255);
            px[y * w + x] = new Color32(g, (byte)(g + 12), (byte)(g + 4), 255);
        }
        if (m == Motion.Crossing) Disc(px, w, h, (int)(34 + f * (w - 78)), h / 2, 18);
        else if (m == Motion.Approach) Disc(px, w, h, w / 2, h / 2, (int)(7 + f * 52));
        tex.SetPixels32(px); tex.Apply();
        return tex;
    }

    static void Disc(Color32[] px, int w, int h, int cx, int cy, int r)
    {
        for (int y = cy - r; y <= cy + r; y++)
        for (int x = cx - r; x <= cx + r; x++)
        {
            if (x < 0 || x >= w || y < 0 || y >= h) continue;
            int dx = x - cx, dy = y - cy;
            if (dx * dx + dy * dy <= r * r) px[y * w + x] = new Color32(230, 215, 120, 255);
        }
    }
}
#endif
