#if UNITY_EDITOR
using System.Collections.Generic;
using System.Text;
using UnityEngine;

// The capture half of ROAM/1 opsis: take a stereo look, keep it, and compose the
// span's sheets from the looks actually taken.
//
// Extracted from cairn's CairnStereo so the format can be used without the rest of
// the roam rig. It needs only two things from a host project: a head transform with
// child cameras named EyeL and EyeR. Replace RoamState.Head with your own accessor.
public static class OpsisCapture
{
    // ---- the walk's looks, kept for an opsis ---------------------------------
    //
    // An opsis was originally composed from PeripheryEye's ring: 320x180 gist frames
    // at quality 60, shot through the 100 deg periphery lens, then downsampled again
    // into the sheet. Loss compounded on loss, while the EYES — 55 deg, matched,
    // 640x360 — sat unused. A walk is a sequence of LOOKS; the sheet should be made
    // of those.
    //
    // Marks are taken deliberately, one per move, which is also the walk's own rhythm:
    // step, look, attend. Nothing samples on a timer, so a mark always corresponds to
    // a moment cairn actually chose to see.
    public class Mark
    {
        public byte[] left, right;
        public Vector3 pos;
        public float yaw, worldTime;
    }

    static readonly List<Mark> marks = new List<Mark>();
    public static int MarkCount { get { return marks.Count; } }
    public static string ClearMarks() { int n = marks.Count; marks.Clear(); return "cleared " + n + " marks"; }

    /// Capture both eyes now and keep them. Returns what was taken.
    public static string MarkLook()
    {
        var head = RoamState.Head;
        if (head == null) return RoamState.Tag() + "no head";
        var L = head.Find("EyeL"); var R = head.Find("EyeR");
        if (L == null || R == null) return RoamState.Tag() + "eyes missing";

        var m = new Mark {
            left = GrabJpg(L.GetComponent<Camera>()),
            right = GrabJpg(R.GetComponent<Camera>()),
            pos = head.position,
            yaw = head.eulerAngles.y,
            worldTime = Time.time,
        };
        marks.Add(m);
        string turn = "";
        if (marks.Count > 1)
        {
            float dYaw = Mathf.Abs(Mathf.DeltaAngle(marks[marks.Count-2].yaw, m.yaw));
            float step = Vector3.Distance(marks[marks.Count-2].pos, m.pos);
            turn = "  (+" + step.ToString("F2") + "m, " + dYaw.ToString("F0") + " deg since last)";
        }
        return RoamState.Tag() + "mark " + (marks.Count-1) + " at " + m.pos.ToString("F2")
             + " yaw " + m.yaw.ToString("F0") + turn;
    }

    static byte[] GrabJpg(Camera cam)
    {
        var rt = new RenderTexture(640, 360, 24);
        var tex = new Texture2D(640, 360, TextureFormat.RGB24, false);
        var prevActive = RenderTexture.active; var prevTarget = cam.targetTexture;
        cam.targetTexture = rt; cam.Render(); RenderTexture.active = rt;
        tex.ReadPixels(new Rect(0, 0, 640, 360), 0, 0); tex.Apply();
        cam.targetTexture = prevTarget; RenderTexture.active = prevActive;
        var bytes = tex.EncodeToJPG(92);
        Object.DestroyImmediate(rt); Object.DestroyImmediate(tex);
        return bytes;
    }

    /// Compose one sheet per eye from the marks taken so far.
    public static string OpsisOfWalk(string dir = "Library/Roam")
    {
        if (marks.Count < 2)
            return RoamState.Tag() + "opsis: need at least 2 marks, have " + marks.Count
                 + " — a walk with one look has no shape yet.";

        var sb = new System.Text.StringBuilder();
        // Rotation makes consecutive tiles show DIFFERENT PARTS of the world, which
        // reads as motion when it is really cairn pivoting. Say so rather than let the
        // sheet imply the world moved.
        float maxTurn = 0f;
        for (int i = 1; i < marks.Count; i++)
            maxTurn = Mathf.Max(maxTurn, Mathf.Abs(Mathf.DeltaAngle(marks[i-1].yaw, marks[i].yaw)));

        float t0 = marks[0].worldTime;
        foreach (var eye in new[]{ "L", "R" })
        {
            var tiles = new List<RoamOpsis.Tile>();
            var made = new List<Texture2D>();
            foreach (var m in marks)
            {
                var bytes = eye == "L" ? m.left : m.right;
                Texture2D tex = null;
                if (bytes != null && bytes.Length > 0)
                {
                    tex = new Texture2D(2, 2, TextureFormat.RGB24, false);
                    if (!tex.LoadImage(bytes)) { Object.DestroyImmediate(tex); tex = null; }
                    else made.Add(tex);
                }
                tiles.Add(new RoamOpsis.Tile {
                    image = tex, elapsed = m.worldTime - t0,
                    pos = m.pos, yaw = m.yaw,
                });
            }
            string man = RoamOpsis.Compose(tiles, dir + "/opsis-" + eye + ".jpg");
            foreach (var t in made) Object.DestroyImmediate(t);
            if (eye == "L") sb.AppendLine(man);
            else sb.AppendLine("right eye written: " + dir + "/opsis-R.jpg");
        }
        sb.AppendLine("source: EYE frames at 640x360 q92 (not periphery gist)");
        if (maxTurn > 8f)
            sb.AppendLine("** cairn TURNED up to " + maxTurn.ToString("F0")
                        + " deg between marks — tiles show different directions, so apparent"
                        + "\n   movement across them is partly cairn's own pivot, not the world's.");
        return sb.ToString();
    }
}
#endif
