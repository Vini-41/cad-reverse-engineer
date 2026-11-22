"""Scale three undimensioned features off Figure 167, a vector drawing, and render them enlarged.

Run from the project directory:  cadrev python measure_fig167.py

Figure 167 (datasheet page 584) is drawn as filled outlines, each line a thin closed band. This reads
the bands' corner coordinates from the PDF, in points, takes each line at the middle of its band, and
scales against the pitch e 0.400 between neighbouring lead ends in the side view (F167-e). It prints
what params.yaml's three `measured` params hold, and the drawn size of each dimensioned value beside
its stated nominal, which shows the drawing is to scale. It writes the enlarged views the evidence
crops fig167-side-x16.png and fig167-notch-x16.png are cut from.
"""

import ctypes
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as raw

HERE = Path(__file__).parent
PAGE = 584          # 1-based
E_PITCH = 0.400     # F167-e, the reference
ZOOM = 16           # the enlarged views, in pixels per point

pdf = pdfium.PdfDocument(HERE / "sources" / "rp2040-datasheet.pdf")
page = pdf[PAGE - 1]
height = page.get_size()[1]

paths = []          # each a list of (kind, x, y), y down from the page's top
for obj in page.get_objects(max_depth=4):
    if obj.type != raw.FPDF_PAGEOBJ_PATH:
        continue
    m = obj.get_matrix()
    pts = []
    for i in range(raw.FPDFPath_CountSegments(obj.raw)):
        seg = raw.FPDFPath_GetPathSegment(obj.raw, i)
        x, y = ctypes.c_float(), ctypes.c_float()
        raw.FPDFPathSegment_GetPoint(seg, x, y)
        px, py = m.on_point(x.value, y.value)
        kind = {raw.FPDF_SEGMENT_MOVETO: "M", raw.FPDF_SEGMENT_LINETO: "L"}.get(raw.FPDFPathSegment_GetType(seg), "C")
        pts.append((kind, px, height - py))
    paths.append(pts)


def box(p):
    xs, ys = [q[1] for q in p], [q[2] for q in p]
    return min(xs), min(ys), max(xs), max(ys)


def inside(p, left, top, right, bottom):
    a = box(p)
    return a[0] >= left and a[1] >= top and a[2] <= right and a[3] <= bottom


def kinds(p):
    return "".join(q[0] for q in p)


def mid(a, b):
    return (a + b) / 2


def circle(p1, p2, p3):
    """Centre and radius of the circle through three points."""
    (x1, y1), (x2, y2), (x3, y3) = p1, p2, p3
    d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    s1, s2, s3 = x1 * x1 + y1 * y1, x2 * x2 + y2 * y2, x3 * x3 + y3 * y3
    cx = (s1 * (y2 - y3) + s2 * (y3 - y1) + s3 * (y1 - y2)) / d
    cy = (s1 * (x3 - x2) + s2 * (x1 - x3) + s3 * (x2 - x1)) / d
    return cx, cy, ((x1 - cx) ** 2 + (y1 - cy) ** 2) ** 0.5


# ---- the side view (drawn turned: the top face to the left, the seating plane to the right) ----------
SIDE = (368, 236, 402, 400)
side = [p for p in paths if inside(p, *SIDE)]
# A lead's end: an outer and an inner four-cornered contour, a trapezoid.
ends = sorted((p for p in side if kinds(p) == "MLLLLMLLLL" and len({round(q[2], 2) for q in p[:4]}) == 4),
              key=lambda p: box(p)[1])
assert len(ends) == 14, len(ends)
centres = [mid(box(p)[1], box(p)[3]) for p in ends]
pt_per_mm = (centres[-1] - centres[0]) / (len(ends) - 1) / E_PITCH


def end_widths(p):
    """A lead end's width at the seating plane and at the top of the lead frame, between line middles."""
    outer, inner = p[:4], p[5:9]
    wide_x, narrow_x = max(q[1] for q in outer), min(q[1] for q in outer)
    at = lambda contour, x: sorted(q[2] for q in contour if abs(q[1] - x) < 0.4)
    ow, iw = at(outer, wide_x), at(inner, wide_x)
    on, i_n = at(outer, narrow_x), at(inner, narrow_x)
    return mid(ow[1], iw[1]) - mid(ow[0], iw[0]), mid(on[1], i_n[1]) - mid(on[0], i_n[0])


wide = sum(end_widths(p)[0] for p in ends) / len(ends) / pt_per_mm
narrow = sum(end_widths(p)[1] for p in ends) / len(ends) / pt_per_mm

# The body's outline is the one contour as tall as the row of lead ends; its left side is the top face,
# its right side the underside.
body = max(side, key=lambda p: box(p)[3] - box(p)[1] if box(p)[2] - box(p)[0] > 5 else 0)
xs = sorted({round(q[1], 3) for q in body})
top_face, underside = mid(xs[0], xs[1]), mid(xs[-2], xs[-1])
seating = mid(max(q[1] for q in ends[0]), max(q[1] for q in ends[0][5:9]))
frame_top = mid(min(q[1] for q in ends[0]), min(q[1] for q in ends[0][5:9]))

# ---- the bottom view: the centre pad and its notch ----------------------------------------------------
pad = next(p for p in paths if inside(p, 160, 470, 225, 535) and box(p)[2] - box(p)[0] > 50)
split = next(i for i, q in enumerate(pad) if i and q[0] == "M")
outer, inner = pad[:split], pad[split:]
left_edge = mid(min(q[1] for q in outer), min(q[1] for q in inner))
right_edge = mid(max(q[1] for q in outer), max(q[1] for q in inner))
low_edge = mid(max(q[2] for q in outer), max(q[2] for q in inner))


def arc(contour):
    """The circle through the notch's arc: the ends of its curve segments."""
    on = [(q[1], q[2]) for i, q in enumerate(contour)
          if (q[0] == "C" and i % 3 == (next(j for j, r in enumerate(contour) if r[0] == "C") + 2) % 3)]
    start = contour[next(j for j, r in enumerate(contour) if r[0] == "C") - 1]
    return circle((start[1], start[2]), on[0], on[-1])


(ox, oy, o_r), (ix, iy, i_r) = arc(outer), arc(inner)
notch_x, notch_y, notch_r = mid(ox, ix), mid(oy, iy), mid(o_r, i_r)

print(f"scale: {pt_per_mm:.4f} points per mm, from the pitch of {len(ends)} lead ends at e = {E_PITCH}")
print("measured (params.yaml):")
print(f"  lead_top_w       {narrow:.4f}   a lead end's width at the top of the lead frame")
print(f"  standoff_drawn   {(seating - underside) / pt_per_mm:.4f}   seating plane to the body's underside")
print(f"  notch_out        {(left_edge - notch_x) / pt_per_mm:.4f}   the notch's centre, outside the pad's edge")
print("drawn against stated:")
print(f"  b   {wide:.4f}  (0.180)    a lead end's width at the seating plane")
print(f"  A3  {(seating - frame_top) / pt_per_mm:.4f}  (0.203)")
print(f"  A2  {(frame_top - top_face) / pt_per_mm:.4f}  (0.650)")
print(f"  D2  {(right_edge - left_edge) / pt_per_mm:.4f}  (3.100)")
print(f"  notch R  {notch_r / pt_per_mm:.4f}  (0.20)")
print(f"  notch offset  {(low_edge - notch_y) / pt_per_mm:.4f}  (0.450)")

# ---- the enlarged views the crops are cut from ----------------------------------------------------------
out = HERE / "figures" / "datasheet"
out.mkdir(parents=True, exist_ok=True)
width = page.get_size()[0]
for name, (left, top, right, bottom) in {"p584-side-x16": (366, 236, 410, 296),
                                         "p584-notch-x16": (150, 498, 190, 534)}.items():
    image = page.render(scale=ZOOM, crop=(left, height - bottom, width - right, top)).to_pil()
    image.save(out / f"{name}.png")
    print(f"wrote figures/datasheet/{name}.png {image.size}")
