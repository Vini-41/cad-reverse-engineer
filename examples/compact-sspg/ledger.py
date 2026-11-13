"""Writes evidence.yaml: the paper's ledger (hand-copied quotes) and the probes of the released STL bodies.

Run: ../../scripts/cadrev python -I ledger.py   (from this directory)
Each STL datum is snapped to a triangle corner of its body (corners lie on the true surface, see SKILL.md step 4),
or, for a point mid-flat on a planar face, checked to lie on a triangle.
"""
import math
import struct
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SRC = {
    "sun": "sources/sspg_sun.STL",
    "planet": "sources/sspg_planet.STL",
    "carrier_updated": "sources/sspg_carrier_updated.STL",
    "sec_carrier": "sources/sspg_sec_carrier.STL",
    "gearbox_casing": "sources/sspg_gearbox_casing.STL",
    "bearing_retainer": "sources/sspg_bearing_retainer.STL",
}


def load(path):
    b = (HERE / path).read_bytes()
    n = struct.unpack("<I", b[80:84])[0]
    a = np.frombuffer(b[84:84 + n * 50], dtype=np.dtype([("n", "<3f4"), ("v", "<9f4"), ("a", "<u2")]))
    return a["v"].reshape(-1, 3, 3).astype(float)


TRI = {k: load(v) for k, v in SRC.items()}
VERT = {k: np.unique(t.reshape(-1, 3), axis=0) for k, t in TRI.items()}
datums = {}
evidence = []
problems = []


def name(body, feat):
    return f"{body}.{feat}"


def V(body, feat, x, y, z, tol=0.03):
    """Snap to the nearest triangle corner of the body."""
    v = VERT[body]
    d = np.linalg.norm(v - np.array([x, y, z]), axis=1)
    i = int(d.argmin())
    if d[i] > tol:
        problems.append(f"{body}.{feat}: nearest corner {d[i]:.4f} from {(x, y, z)}")
    datums[name(body, feat)] = [round(float(c), 5) for c in v[i]]
    return name(body, feat)


def OPP(body, feat, cx, cy, r, z, axis=2):
    """Two corners on a circle (centre cx, cy; radius r; at height z) half a turn apart."""
    v = VERT[body]
    o = [i for i in range(3) if i != axis]
    m = (np.abs(v[:, axis] - z) < 1e-3) & (np.abs(np.hypot(v[:, o[0]] - cx, v[:, o[1]] - cy) - r) < 2e-3)
    w = v[m]
    best = None
    for i in range(len(w)):
        for j in range(i + 1, len(w)):
            a1 = math.atan2(w[i][o[1]] - cy, w[i][o[0]] - cx)
            a2 = math.atan2(w[j][o[1]] - cy, w[j][o[0]] - cx)
            err = abs(abs((a1 - a2 + math.pi) % (2 * math.pi) - math.pi) - math.pi)
            if best is None or err < best[0]:
                best = (err, w[i], w[j])
    if best is None or best[0] > 1e-4:
        problems.append(f"{body}.{feat}: no opposite pair on r={r} at {z} ({len(w)} corners)")
        return None
    datums[name(body, feat + "_a")] = [round(float(c), 5) for c in best[1]]
    datums[name(body, feat + "_b")] = [round(float(c), 5) for c in best[2]]
    return [name(body, feat + "_a"), name(body, feat + "_b")]


def measure(kind, between, along=None):
    pts = [np.array(datums[d]) for d in between]
    if kind == "distance":
        if along:
            return abs(pts[1]["xyz".index(along)] - pts[0]["xyz".index(along)])
        return float(np.linalg.norm(pts[1] - pts[0]))
    a, b, c = pts
    u, w = a - b, c - b
    return math.degrees(math.acos(u @ w / np.linalg.norm(u) / np.linalg.norm(w)))


def probe(pid, body, locator, between, key, value, kind="distance", along=None, tol=None, scope=None):
    if between is None:
        return
    got = measure(kind, between, along)
    lim = tol if tol is not None else (0.01 if kind == "angle" else 0.001)
    flag = "" if abs(got - value) <= lim else "   <-- MISMATCH"
    print(f"{pid:14s} {key:10s} design {value:<9} file {got:.5f}{flag}")
    e = {"id": pid, "source": body, "locator": locator, "probe": kind, "between": between}
    if along:
        e["along"] = along
    e["values"] = {key: value}
    if tol is not None:
        e["tol"] = tol
    if scope:
        e.update(scope)
    evidence.append(e)


# ---------------------------------------------------------------- planet (axis z, centre 16.75, 16.74608)
B = "planet"; cx, cy = 16.75, 16.74608
probe("P-bore", B, "planet, bore at mid-length", OPP(B, "bore", cx, cy, 5, 3.5), "d", 10)
probe("P-cb", B, "planet, end counterbore (bearing seat)", OPP(B, "cb", cx, cy, 6, 0), "d", 12)
probe("P-cbd", B, "planet, counterbore depth", [V(B, "cb0", cx + 6, cy, 0), V(B, "cb1", cx + 6, cy, 3.5)], "h", 3.5, along="z")
# tooth tip corners for the width probe and the shape check: tooth centred at -174.985 deg (file listing)
def polar(cx, cy, r, deg, z):
    return cx + r * math.cos(math.radians(deg)), cy + r * math.sin(math.radians(deg)), z
probe("P-w", B, "planet, face width (tooth tip corner, both faces)",
      [V(B, "tip0", *polar(cx, cy, 16.75, -175.6602, 0)), V(B, "tip0_top", *polar(cx, cy, 16.75, -175.6602, 22.135))], "w", 22.135, along="z")
V(B, "tip_h", *polar(cx, cy, 16.75, -175.6602 + 32 * 360 / 65, 0))

# ---------------------------------------------------------------- sun (axis z, centre 16.5, 16.5)
B = "sun"; cx, cy = 16.5, 16.5
probe("S-len", B, "sun, overall length", [V(B, "tip_bot", cx + 3.5, cy, 0), V(B, "fl_top", cx + 16.5, cy, 42.135)], "l", 42.135, along="z")
probe("S-bdr", B, "sun, counterbore radius beyond the through bore (corners at 0 deg)", [V(B, "bd0", cx + 2.5, cy, 37.135), V(B, "cb0", cx + 4.45, cy, 37.135)], "dr", 1.95)
probe("S-cb", B, "sun, bolt-head counterbore", OPP(B, "cb", cx, cy, 4.45, 42.135), "d", 8.9)
probe("S-cbd", B, "sun, counterbore depth", [V(B, "cb0", cx + 4.45, cy, 37.135), V(B, "cb1", cx + 4.45, cy, 42.135)], "h", 5, along="z")
probe("S-tdr", B, "sun, shaft end radius beyond the bore (corners at 0 deg)", [V(B, "td0", cx + 2.5, cy, 0), V(B, "tip_bot", cx + 3.5, cy, 0)], "dr", 1)
probe("S-cham", B, "sun, shaft end chamfer height", [V(B, "ch0", cx + 3.5, cy, 0), V(B, "ch1", cx + 4, cy, 0.5)], "h", 0.5, along="z")
probe("S-sdr", B, "sun, step radius beyond the shaft (corners at 0 deg)", [V(B, "sd0", cx + 4, cy, 6.5), V(B, "sh1", cx + 4.5, cy, 6.5)], "dr", 0.5)
probe("S-shl", B, "sun, shaft length to the step", [V(B, "sh0", cx + 3.5, cy, 0), V(B, "sh1", cx + 4.5, cy, 6.5)], "l", 6.5, along="z")
probe("S-step", B, "sun, shoulder step diameter", OPP(B, "step", cx, cy, 4.5, 7.5), "d", 9)
probe("S-steph", B, "sun, shoulder step height", [V(B, "st0", cx + 4.5, cy, 6.5), V(B, "st1", cx + 4.5, cy, 7.5)], "h", 1, along="z")
probe("S-hub", B, "sun, hub diameter at the gear's lower face", OPP(B, "hub", cx, cy, 5, 8), "d", 10)
probe("S-hubc", B, "sun, chamfer from step to hub, height", [V(B, "hc0", cx + 4.5, cy, 7.5), V(B, "hc1", cx + 5, cy, 8)], "h", 0.5, along="z")
probe("S-face", B, "sun, toothed length (gear lower face to flange)",
      [V(B, "gt0", *polar(cx, cy, 6.75, -169.8734 + 12 * 14.4, 8)), V(B, "gt1", *polar(cx, cy, 6.75, -169.8734 + 12 * 14.4, 38.135))], "w", 30.135, along="z")
V(B, "tip_h", *polar(cx, cy, 6.75, -169.8734 + 24 * 14.4, 8))
probe("S-fdr", B, "sun, flange radius beyond the counterbore (corners at 0 deg)", [V(B, "cb1", cx + 4.45, cy, 42.135), V(B, "fl_top", cx + 16.5, cy, 42.135)], "dr", 12.05)
probe("S-flt", B, "sun, flange thickness", [V(B, "ft0", cx + 16.5, cy, 38.135), V(B, "ft1", cx + 16.5, cy, 42.135)], "t", 4, along="z")
probe("S-pcd", B, "sun, flange hole circle (holes at 90 and 270 deg, same-side corners)",
      [V(B, "h90", cx + 2, cy + 11.5, 42.135), V(B, "h270", cx + 2, cy - 11.5, 42.135)], "pcd", 23, along="y")
probe("S-hole", B, "sun, flange hole", OPP(B, "hole", cx, cy + 11.5, 2, 42.135), "d", 4)
probe("S-csk", B, "sun, flange hole countersink at the flange's lower face", OPP(B, "csk", cx, cy + 11.5, 4, 38.135), "d", 8)
probe("S-cskd", B, "sun, countersink depth", [V(B, "ck0", cx + 4, cy + 11.5, 38.135), V(B, "ck1", cx + 2, cy + 11.5, 40.135)], "h", 2, along="z")
probe("S-nh", B, "sun, flange holes' angular pitch (same-side corners of three holes)",
      [V(B, "h90", cx + 2, cy + 11.5, 42.135), V(B, "h0", cx + 11.5 + 2, cy, 42.135), V(B, "h270", cx + 2, cy - 11.5, 42.135)],
      "a", 90, kind="angle")

# ---------------------------------------------------------------- carrier (axis z, centre 29, 29, bottom z 0.21)
B = "carrier_updated"; cx, cy = 29, 29
probe("C-h", B, "carrier, overall height (disc bottom to pin top)", [V(B, "bot", cx + 27, cy, 0.21), V(B, "pintop", cx + 4, cy + 22.5, 35.845)], "h", 35.635, along="z")
probe("C-disc", B, "carrier, output disc (bearing seat) diameter", OPP(B, "disc", cx, cy, 27.5, 0.71), "d", 55)
probe("C-cham", B, "carrier, disc lower-edge chamfer", [V(B, "ch0", cx + 27, cy, 0.21), V(B, "ch1", cx + 27.5, cy, 0.71)], "h", 0.5, along="z")
probe("C-dh", B, "carrier, disc height to the flange", [V(B, "dh0", cx + 27, cy, 0.21), V(B, "dh1", cx + 29, cy, 9.21)], "h", 9, along="z")
probe("C-fdr", B, "carrier, flange radius beyond the disc (corners at 0 deg)", [V(B, "fd0", cx + 27.5, cy, 9.21), V(B, "ft0", cx + 29, cy, 9.21)], "dr", 1.5)
probe("C-flt", B, "carrier, flange thickness", [V(B, "ft0", cx + 29, cy, 9.21), V(B, "ft1", cx + 29, cy, 10.71)], "t", 1.5, along="z")
probe("C-b1", B, "carrier, central bore, output side", OPP(B, "b1", cx, cy, 6.5, 0.21), "d", 13)
probe("C-b1d", B, "carrier, central bore depth to the bearing seat", [V(B, "b1z0", cx + 6.5, cy, 0.21), V(B, "b1z1", cx + 8, cy, 5.71)], "h", 5.5, along="z")
probe("C-b2", B, "carrier, sun bearing seat bore", OPP(B, "b2", cx, cy, 8, 5.71), "d", 16)
probe("C-b2d", B, "carrier, sun bearing seat depth to its chamfer", [V(B, "b2z0", cx + 8, cy, 5.71), V(B, "b2z1", cx + 8, cy, 10.21)], "h", 4.5, along="z")
probe("C-b2c", B, "carrier, sun bearing seat chamfer diameter", OPP(B, "b2c", cx, cy, 8.5, 10.71), "d", 17)
pin = (cx, cy + 22.5)
probe("C-pock", B, "carrier, planet-pin pocket radius beyond the pin bore (corners at 180 deg)",
      [V(B, "pk0", pin[0] - 4.65, pin[1], 5.21), V(B, "pk1", pin[0] - 2.7, pin[1], 5.21)], "dr", 1.95, along="x")
probe("C-pockd", B, "carrier, planet-pin pocket depth", [V(B, "pkd0", pin[0] - 4.65, pin[1], 0.21), V(B, "pk0", pin[0] - 4.65, pin[1], 5.21)], "h", 5, along="z")
probe("C-pinb", B, "carrier, planet-pin bore", OPP(B, "pinb", *pin, 2.7, 35.845), "d", 5.4)
probe("C-pin", B, "carrier, planet pin outside diameter", OPP(B, "pin", *pin, 4, 35.845), "d", 8)
probe("C-col", B, "carrier, pin collar diameter", OPP(B, "col", *pin, 5, 10.71), "d", 10)
probe("C-colh", B, "carrier, pin collar height (flange top to pin step)", [V(B, "co0", pin[0] + 5, pin[1], 10.71), V(B, "co1", pin[0] + 4, pin[1], 12.21)], "h", 1.5, along="z")
probe("C-colf", B, "carrier, collar edge round (tangent points)", [V(B, "cf0", pin[0] + 5, pin[1], 11.71), V(B, "co1", pin[0] + 4, pin[1], 12.21)], "h", 0.5, along="z")
bolt = (cx, cy - 23.5)
probe("C-bolt", B, "carrier, extrusion bolt hole", OPP(B, "bolt", *bolt, 1.7, 35.845), "d", 3.4)
probe("C-bcb", B, "carrier, bolt counterbore radius beyond the hole (corners at 180 deg)",
      [V(B, "bc0", bolt[0] - 3.15, bolt[1], 3.21), V(B, "bc1", bolt[0] - 1.7, bolt[1], 3.21)], "dr", 1.45, along="x")
probe("C-bcbd", B, "carrier, bolt counterbore depth", [V(B, "bcd0", bolt[0] - 3.15, bolt[1], 0.21), V(B, "bc0", bolt[0] - 3.15, bolt[1], 3.21)], "h", 3, along="z")
b30 = (cx + 23.5 * math.cos(math.radians(30)), cy + 23.5 * math.sin(math.radians(30)))
probe("C-bR", B, "carrier, bolt circle: holes at -90 and 30 deg, +x corners, along y (1.5 x radius)",
      [V(B, "bR0", bolt[0] + 1.7, bolt[1], 35.845), V(B, "bR1", b30[0] + 1.7, b30[1], 35.845)], "dy", 35.25, along="y")
nut = (cx + 18, cy)
probe("C-nut", B, "carrier, disc bolt hole", OPP(B, "nut", *nut, 2.2, 0.21), "d", 4.4)
probe("C-nutR", B, "carrier, disc bolt circle (holes at 0 and 180 deg, +x corners)",
      [V(B, "nR0", cx + 18 + 2.2, cy, 0.21), V(B, "nR1", cx - 18 + 2.2, cy, 0.21)], "d", 36)
probe("C-hex", B, "carrier, nut trap across corners (corners at 90 and -90 deg)",
      [V(B, "hx0", nut[0], nut[1] + 4.0415, 10.71), V(B, "hx1", nut[0], nut[1] - 4.0415, 10.71)], "ac", 8.083)
probe("C-hexd", B, "carrier, nut trap depth", [V(B, "hxd0", nut[0], nut[1] + 4.0415, 4.71), V(B, "hx0", nut[0], nut[1] + 4.0415, 10.71)], "h", 6, along="z")
probe("C-hexang", B, "carrier, nut trap corner angle (corners at 30, 90, 150 deg about the hole)",
      [V(B, "hx30", *polar(nut[0], nut[1], 4.0415, 30, 10.71)), V(B, "hx0", nut[0], nut[1] + 4.0415, 10.71), V(B, "hx150", *polar(nut[0], nut[1], 4.0415, 150, 10.71))],
      "a", 120, kind="angle")
n60 = (cx + 18 * math.cos(math.radians(60)), cy + 18 * math.sin(math.radians(60)))
n120 = (cx + 18 * math.cos(math.radians(120)), cy + 18 * math.sin(math.radians(120)))
probe("C-nn", B, "carrier, disc bolt holes' angular pitch (+x corners of three holes)",
      [V(B, "nR0", cx + 18 + 2.2, cy, 0.21), V(B, "n60", n60[0] + 2.2, n60[1], 0.21), V(B, "n120", n120[0] + 2.2, n120[1], 0.21)],
      "a", 120, kind="angle")
probe("C-tip", B, "carrier, extrusion tip (flat on the inner circle) to the seat chamfer edge, along y",
      [V(B, "etip", 29.2593, 17.753, 10.71), V(B, "b2c_s", cx, cy - 8.5, 10.71)], "dy", 2.75, along="y", tol=0.005)
# shape-check corners
V(B, "s_pin90", pin[0] + 4, pin[1], 35.845)
V(B, "s_bolt", bolt[0] + 1.7, bolt[1], 35.845)
V(B, "s_disc", cx + 27.5, cy, 0.71)

# ---------------------------------------------------------------- secondary carrier (axis z, centre 28.25, 28.25, bottom 0.278)
B = "sec_carrier"; cx, cy = 28.25, 28.25
probe("K-od", B, "secondary carrier, outside diameter", OPP(B, "od", cx, cy, 28.25, 6.778), "d", 56.5)
probe("K-id", B, "secondary carrier, inside diameter", OPP(B, "id", cx, cy, 16, 6.778), "d", 32)
probe("K-t", B, "secondary carrier, plate thickness", [V(B, "t0", *polar(cx, cy, 28.25, 4.615, 1.778)), V(B, "t1", *polar(cx, cy, 28.25, 4.615, 6.778))], "t", 5, along="z")
kp = (cx, cy + 22.5)
probe("K-bh", B, "secondary carrier, pin boss height below the plate",
      [V(B, "bh0", kp[0] + 4.25, kp[1], 0.278), V(B, "bh1", kp[0] + 4, kp[1], 1.778)], "h", 1.5, along="z")
probe("K-bid", B, "secondary carrier, pin boss bore", OPP(B, "bid", *kp, 4, 1.778), "d", 8)
probe("K-bch", B, "secondary carrier, pin boss bore chamfer",
      [V(B, "bc0", kp[0] + 4, kp[1], 0.528), V(B, "bh0", kp[0] + 4.25, kp[1], 0.278)], "h", 0.25, along="z")
probe("K-btr", B, "secondary carrier, pin boss root radius beyond the pin hole (corners at -90 deg)",
      [V(B, "bt0", kp[0], kp[1] - 2.5, 1.778), V(B, "bt1", kp[0], kp[1] - 6.5, 1.778)], "dr", 4)
probe("K-pin", B, "secondary carrier, pin hole", OPP(B, "pin", *kp, 2.5, 1.778), "d", 5)
probe("K-phex", B, "secondary carrier, pin nut trap across corners (corners at 0 and 180 deg)",
      [V(B, "ph0", kp[0] + 5.0807, kp[1], 6.778), V(B, "ph1", kp[0] - 5.0807, kp[1], 6.778)], "ac", 10.161, tol=0.002)
probe("K-hexd", B, "secondary carrier, nut trap depth", [V(B, "hd0", kp[0] + 5.0807, kp[1], 4.278), V(B, "ph0", kp[0] + 5.0807, kp[1], 6.778)], "h", 2.5, along="z")
kb = (cx, cy - 24.25)
probe("K-bolt", B, "secondary carrier, bolt hole", OPP(B, "bolt", *kb, 1.5, 1.778), "d", 3)
probe("K-bhex", B, "secondary carrier, bolt nut trap across corners (corners at 90 and -90 deg)",
      [V(B, "bx0", kb[0], kb[1] + 3.6373, 6.778), V(B, "bx1", kb[0], kb[1] - 3.6373, 6.778)], "ac", 7.275, tol=0.002)
k30 = (cx + 24.25 * math.cos(math.radians(30)), cy + 24.25 * math.sin(math.radians(30)))
probe("K-bR", B, "secondary carrier, bolt circle: holes at -90 and 30 deg, +x corners, along y (1.5 x radius)",
      [V(B, "bR0", kb[0] + 1.5, kb[1], 1.778), V(B, "bR1", k30[0] + 1.5, k30[1], 1.778)], "dy", 36.375, along="y")
V(B, "s_pin", kp[0] + 5.0807, kp[1], 6.778)
V(B, "s_bolt", kb[0] + 1.5, kb[1], 1.778)
kp2 = polar(cx, cy, 22.5, -30, 6.778)
V(B, "s_pin2", kp2[0] + 5.0807, kp2[1], 6.778)

# ---------------------------------------------------------------- gearbox casing (axis z, centre 51.4, 56.15)
B = "gearbox_casing"; cx, cy = 51.4, 56.15
probe("G-h", B, "casing, overall height", [V(B, "h0", cx + 44, cy, 0), V(B, "h1", cx + 51.4 * math.cos(math.radians(4.6155)), cy + 51.4 * math.sin(math.radians(4.6155)), 40.635)], "h", 40.635, along="z")
probe("G-odr", B, "casing, output-end outside radius beyond the bore entry (corners at 0 deg)", [V(B, "bc0", cx + 37, cy, 0), V(B, "h0", cx + 44, cy, 0)], "dr", 7)
probe("G-b0", B, "casing, bearing bore entry (chamfered) diameter", OPP(B, "b0", cx, cy, 37, 0), "d", 74)
probe("G-b1r", B, "casing, bearing bore radius inside the bore entry (corners at 0 deg)", [V(B, "bc0", cx + 37, cy, 0), V(B, "bc1", cx + 36, cy, 1)], "dr", 1, along="x")
probe("G-bch", B, "casing, bearing bore entry chamfer height", [V(B, "bc0", cx + 37, cy, 0), V(B, "bc1", cx + 36, cy, 1)], "h", 1, along="z")
probe("G-b1d", B, "casing, bearing bore depth", [V(B, "bc0", cx + 37, cy, 0), V(B, "bd1", cx + 36, cy, 9)], "h", 9, along="z")
probe("G-lipr", B, "casing, shoulder lip radius inside the bearing bore (corners at 0 deg)", [V(B, "lh0", cx + 34.5, cy, 9), V(B, "bd1", cx + 36, cy, 9)], "dr", 1.5)
probe("G-liph", B, "casing, lip height to the ring's lower face", [V(B, "lh0", cx + 34.5, cy, 9), V(B, "lh1", cx + 34.5, cy, 10.5)], "h", 1.5, along="z")
probe("G-ringw", B, "casing, ring gear face width (tooth tip corner, both faces)",
      [V(B, "rw0", *polar(cx, cy, 38.25, -178.8907, 10.5)), V(B, "rw1", *polar(cx, cy, 38.25, -178.8907, 34.135))], "w", 23.635, along="z")
probe("G-neck0", B, "casing, taper from the output-end diameter to the ring's outside, height",
      [V(B, "nk0", cx + 44, cy, 10.5), V(B, "nk1", cx + 43.75, cy, 11.699)], "h", 1.199, along="z")
probe("G-neck1", B, "casing, ring outside cylinder's upper end (flare tangent)", [V(B, "nk1", cx + 43.75, cy, 11.699), V(B, "nk2", cx + 43.75, cy, 14.256)], "h", 2.557, along="z")
probe("G-fl", B, "casing, flare's end on the body cylinder, below the top face",
      [V(B, "fe0", cx + 51.4, cy, 30.993), V(B, "fe1", cx + 51.4 * math.cos(math.radians(4.6155)), cy + 51.4 * math.sin(math.radians(4.6155)), 40.635)], "h", 9.642, along="z")
probe("G-body", B, "casing, body diameter at the motor end", OPP(B, "body", cx, cy, 51.4, 40.635), "d", 102.8)
probe("G-pk", B, "casing, motor-end spigot pocket diameter", OPP(B, "pk", cx, cy, 48.4, 40.635), "d", 96.8)
probe("G-pkd", B, "casing, spigot pocket depth", [V(B, "pd0", cx + 48.4 * math.cos(math.radians(10)), cy + 48.4 * math.sin(math.radians(10)), 38.635),
                                                  V(B, "pd1", cx + 48.4 * math.cos(math.radians(10)), cy + 48.4 * math.sin(math.radians(10)), 40.635)], "h", 2, along="z")
probe("G-lobe", B, "casing, pocket lobes' peaks at 0 and 180 deg", [V(B, "lb0", cx + 49.9, cy, 40.635), V(B, "lb180", cx - 49.9, cy, 40.635)], "d", 99.8)
probe("G-nlobe", B, "casing, pocket lobes' angular pitch (peaks at 0, 20, 40 deg)",
      [V(B, "lb0", cx + 49.9, cy, 40.635), V(B, "lb20", *polar(cx, cy, 49.9, 20, 40.635)[:2], 40.635), V(B, "lb40", *polar(cx, cy, 49.9, 40, 40.635)[:2], 40.635)],
      "a", 160, kind="angle")
probe("G-sh45", B, "casing, shelf inner edge below the pocket", OPP(B, "sh45", cx, cy, 45, 38.635), "d", 90)
probe("G-sh43", B, "casing, bore above the ring", OPP(B, "sh43", cx, cy, 43.25, 36.135), "d", 86.5)
probe("G-shc", B, "casing, chamfer from the bore above the ring to the shelf, height",
      [V(B, "sc0", cx + 43.25, cy, 36.135), V(B, "sc1", cx + 45, cy, 38.635)], "h", 2.5, along="z")
probe("G-shb", B, "casing, bore above the ring, straight length", [V(B, "sb0", cx + 43.25, cy, 35.135), V(B, "sc0", cx + 43.25, cy, 36.135)], "h", 1, along="z")
probe("G-shf", B, "casing, round at the ring's upper face (tangent points)", [V(B, "sf0", cx + 42.25, cy, 34.135), V(B, "sb0", cx + 43.25, cy, 35.135)], "h", 1, along="z")
lug = (cx, cy + 52.4)
probe("G-lugt", B, "casing, mounting lug tips at 90 and 270 deg", [V(B, "lt90", cx, cy + 56.15, 40.635), V(B, "lt270", cx, cy - 56.15, 40.635)], "d", 112.3)
probe("G-lugR", B, "casing, lug hole circle (holes at 90 and 270 deg, +x corners)",
      [V(B, "lR90", cx + 1.5, cy + 52.4, 40.635), V(B, "lR270", cx + 1.5, cy - 52.4, 40.635)], "d", 104.8)
probe("G-lugh", B, "casing, lug hole", OPP(B, "lugh", *lug, 1.5, 40.635), "d", 3)
l30 = polar(cx, cy, 52.4, 30, 40.635); lm30 = polar(cx, cy, 52.4, -30, 40.635)
probe("G-nlug", B, "casing, lugs' angular pitch (+x corners of holes at 90, 30, -30 deg)",
      [V(B, "lR90", cx + 1.5, cy + 52.4, 40.635), V(B, "l30", l30[0] + 1.5, l30[1], 40.635), V(B, "lm30", lm30[0] + 1.5, lm30[1], 40.635)],
      "a", 120, kind="angle")
probe("G-lcb", B, "casing, lug counterbore from below", OPP(B, "lcb", *lug, 2.95, 36.135), "d", 5.9)
probe("G-lcbz", B, "casing, lug counterbore's top below the top face", [V(B, "lz0", lug[0] + 1.5, lug[1], 36.135), V(B, "lR90", cx + 1.5, cy + 52.4, 40.635)], "h", 4.5, along="z")
hole = (cx, cy + 40)
probe("G-hole", B, "casing, output-end bolt hole", OPP(B, "hole", *hole, 2, 0), "d", 4)
probe("G-holed", B, "casing, output-end bolt hole depth", [V(B, "hd0", hole[0] + 2, hole[1], 0), V(B, "hd1", hole[0] + 2, hole[1], 9)], "h", 9, along="z")
probe("G-holeR", B, "casing, output-end bolt circle (holes at 90 and 270 deg, +x corners)",
      [V(B, "hd0", hole[0] + 2, hole[1], 0), V(B, "hR270", cx + 2, cy - 40, 0)], "d", 80)
h30 = polar(cx, cy, 40, 30, 0); hm30 = polar(cx, cy, 40, -30, 0)
probe("G-nhole", B, "casing, output-end bolt holes' angular pitch (+x corners of holes at 90, 30, -30 deg)",
      [V(B, "hd0", hole[0] + 2, hole[1], 0), V(B, "h30", h30[0] + 2, h30[1], 0), V(B, "hm30", hm30[0] + 2, hm30[1], 0)], "a", 120, kind="angle")
probe("G-nut", B, "casing, nut slot across corners (tangential corners)", [V(B, "nt0", hole[0] - 4.0415, hole[1], 3), V(B, "nt1", hole[0] + 4.0415, hole[1], 3)], "ac", 8.083)
probe("G-nutz", B, "casing, nut slot's lower face above the output face", [V(B, "hd0", hole[0] + 2, hole[1], 0), V(B, "nt1", hole[0] + 4.0415, hole[1], 3)], "h", 3, along="z")
probe("G-nutt", B, "casing, nut slot thickness", [V(B, "nt1", hole[0] + 4.0415, hole[1], 3), V(B, "nt2", hole[0] + 4.0415, hole[1], 6.2)], "t", 3.2, along="z")
V(B, "s_lug", cx + 1.5, cy + 52.4, 40.635)
V(B, "s_hole", hole[0] + 2, hole[1], 0)
V(B, "s_ring", *polar(cx, cy, 38.25, 2.27059, 10.5))

# ---------------------------------------------------------------- bearing retainer (axis y, centre 44, 44 in x, z; y 0..2)
B = "bearing_retainer"; cx, cz = 44, 44
probe("R-od", B, "bearing retainer, outside diameter", OPP(B, "od", cx, cz, 44, 0, axis=1), "d", 88)
probe("R-id", B, "bearing retainer, inside diameter", OPP(B, "id", cx, cz, 35.25, 0, axis=1), "d", 70.5)
probe("R-t", B, "bearing retainer, thickness", [V(B, "t0", cx, 0, cz + 44), V(B, "t1", cx, 2, cz + 44)], "t", 2, along="y")
probe("R-hole", B, "bearing retainer, bolt hole", OPP(B, "hole", cx, cz + 40, 2, 0, axis=1), "d", 4)
probe("R-hR", B, "bearing retainer, bolt circle (holes at 90 and 270 deg, +x corners)",
      [V(B, "hR0", cx + 2, 0, cz + 40), V(B, "hR1", cx + 2, 0, cz - 40)], "d", 80)
r30 = (cx + 40 * math.cos(math.radians(30)), cz + 40 * math.sin(math.radians(30)))
rm30 = (cx + 40 * math.cos(math.radians(-30)), cz + 40 * math.sin(math.radians(-30)))
probe("R-nh", B, "bearing retainer, bolt holes' angular pitch (+x corners of holes at 90, 30, -30 deg)",
      [V(B, "hR0", cx + 2, 0, cz + 40), V(B, "h30", r30[0] + 2, 0, r30[1]), V(B, "hm30", rm30[0] + 2, 0, rm30[1])],
      "a", 120, kind="angle")
V(B, "s_od", cx, 2, cz - 44)

if problems:
    print("\n".join(problems))
    sys.exit(1)

# ---------------------------------------------------------------- write
import json  # noqa: E402

PAPER = (HERE / "ledger_paper.yaml").read_text()


def fmt(v):
    return json.dumps(v)


lines = ["# Written by ledger.py (probes and datums of the released STL bodies) around ledger_paper.yaml (the paper's ledger).",
         "# Edit those two files and rerun ledger.py; do not edit this file by hand.", ""]
paper_lines = PAPER.splitlines()
i = paper_lines.index("# PROBES")
lines += paper_lines[:i]
for e in evidence:
    lines.append("  - {" + ", ".join(f"{k}: {fmt(v)}" for k, v in e.items()) + "}")
lines += paper_lines[i + 1:]
lines.append("")
lines.append("datums:")
for k, v in datums.items():
    lines.append(f"  {k}: {fmt(v)}")
(HERE / "evidence.yaml").write_text("\n".join(lines) + "\n")
print(f"wrote {len(evidence)} probes, {len(datums)} datums")
