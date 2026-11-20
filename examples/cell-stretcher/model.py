"""Six-well uniaxial cell stretcher (Kah et al. 2021) and its PDMS casting mould.

Every dimension comes from p (params.yaml). Cut parts are built in their cut-file frame:
x right, y down the sheet, origin at the region's bounding-box corner, thickness along +z.
"""

from math import cos, radians, sin

from build123d import *  # noqa: F403

MINS = (Align.MIN, Align.MIN, Align.MIN)
CTR = (Align.CENTER, Align.CENTER, Align.MIN)


# ---------------------------------------------------------------- 2D-in-3D helpers
def rect(x0, y0, x1, y1, t):
    return Pos(x0, y0, 0) * Box(x1 - x0, y1 - y0, t, align=MINS)


def disc(x, y, d, t):
    return Pos(x, y, 0) * Cylinder(d / 2, t, align=CTR)


def slot(x, y, length, w, t):
    return Pos(x, y, 0) * extrude(SlotOverall(length, w), t)


def rrect(x, y, w, h, r, t):
    return Pos(x, y, 0) * extrude(RectangleRounded(w, h, r), t)


def ellipse(x, y, rx, ry, t):
    return Pos(x, y, 0) * extrude(Ellipse(rx, ry), t)


def poly(pts, t):
    return extrude(Polygon(*pts, align=None), t)


def row(x0, pitch, n, w, y0, y1, t):
    """n rectangles of width w starting at x0, every pitch, spanning y0..y1."""
    out = None
    for i in range(int(n)):
        b = rect(x0 + i * pitch, y0, x0 + i * pitch + w, y1, t)
        out = b if out is None else out + b
    return out


def tab_pattern(p, w_total, y0, y1, t):
    """The carriage comb: an outer group at each end and the middle run, symmetric about the centre."""
    a = row(p.tab_o1, p.tab_p, p.tab_n_out, p.tab_w, y0, y1, t)
    b = row(w_total - p.tab_o1 - p.tab_w - (p.tab_n_out - 1) * p.tab_p, p.tab_p, p.tab_n_out, p.tab_w, y0, y1, t)
    c = row(p.tab_m1, p.tab_p, p.tab_n_mid, p.tab_w, y0, y1, t)
    return a + b + c


def build(p):
    parts, datums, assembly = {}, {}, {}
    t6, t3 = p.t6, p.t3
    W = p.prof_short_L + 2 * p.prof_w  # outer width of the frame, the end plates' width
    h6 = t6 / 2

    def d(name, x, y, z):
        datums[name] = (x, y, z)

    # ================================================================ stretcher end plates
    def end_row(cx, h1, h2, t):
        yy = p.ep_h - p.row_off
        s = slot(cx - p.slot_dx, yy, p.slot_L, p.slot_w, t) + slot(cx + p.slot_dx, yy, p.slot_L, p.slot_w, t)
        for hx in (h1, h2):
            s = s + disc(cx - hx, yy, p.d_m5, t) + disc(cx + hx, yy, p.d_m5, t)
        return s

    # A: far end-piece, inner layer (lead-screw and rod bores)
    a = rect(0, 0, W, p.ep_h, t6)
    a = a - disc(W / 2 - p.ep_m3_dx, p.ep_m3_y, p.d_m3tap, t6) - disc(W / 2 + p.ep_m3_dx, p.ep_m3_y, p.d_m3tap, t6)
    for x in (p.scr_x, p.rod_x, W - p.rod_x, W - p.scr_x):
        a = a - disc(x, p.ax_y, p.d_bore8, t6)
    for x in (p.ep_h1, p.ep_h2, W - p.ep_h1, W - p.ep_h2):
        a = a - disc(x, p.ep_h - p.row_off, p.d_m6, t6)
    a = a - end_row(W / 2, W / 2 - p.ep_h3, W / 2 - p.ep_h4, t6)
    parts["end_far_in"] = a
    d("end_far_in.m3_l", W / 2 - p.ep_m3_dx, p.ep_m3_y, h6)
    d("end_far_in.screw_l", p.scr_x, p.ax_y, h6)
    d("end_far_in.screw_r", W - p.scr_x, p.ax_y, h6)
    d("end_far_in.rod_l", p.rod_x, p.ax_y, h6)

    # B: far end-piece, outer layer
    b = rect(0, 0, W, p.ep_h, t6)
    b = b - disc(W / 2 - p.ep_m3_dx, p.ep_m3_y, p.d_m3clr, t6) - disc(W / 2 + p.ep_m3_dx, p.ep_m3_y, p.d_m3clr, t6)
    for x in (p.ep_h1, p.ep_h2, W - p.ep_h1, W - p.ep_h2):
        b = b - disc(x, p.ep_h - p.row_off, p.d_m6, t6)
    b = b - end_row(W / 2, W / 2 - p.ep_h3, W / 2 - p.ep_h4, t6)
    parts["end_far_out"] = b
    d("end_far_out.m3_l", W / 2 - p.ep_m3_dx, p.ep_m3_y, h6)
    d("end_far_out.m3_r", W / 2 + p.ep_m3_dx, p.ep_m3_y, h6)
    d("end_far_out.m6_l", p.ep_h1, p.ep_h - p.row_off, h6)

    # D: motor-end end-piece, inner layer (rod bores, D-sub cut-out)
    cw = p.ec_w / 2
    rod_half = W / 2 - p.rod_x
    dd = rect(0, 0, p.ec_w, p.ep_h, t6)
    dd = dd - disc(cw - p.ep_m3_dx, p.ep_m3_y, p.d_m3tap, t6) - disc(cw + p.ep_m3_dx, p.ep_m3_y, p.d_m3tap, t6)
    dd = dd - disc(cw - rod_half, p.ax_y, p.d_bore8, t6) - disc(cw + rod_half, p.ax_y, p.d_bore8, t6)
    dd = dd - rrect(cw, p.dsub_y, p.dsub_w, p.dsub_h, p.dsub_r, t6)
    dd = dd - disc(cw - p.dsub_dx, p.dsub_y, p.d_m3tap, t6) - disc(cw + p.dsub_dx, p.dsub_y, p.d_m3tap, t6)
    dd = dd - end_row(cw, p.ec_h1, p.ec_h2, t6)
    parts["end_motor_in"] = dd
    d("end_motor_in.rod_l", cw - rod_half, p.ax_y, h6)
    d("end_motor_in.rod_r", cw + rod_half, p.ax_y, h6)
    d("end_motor_in.m3_l", cw - p.ep_m3_dx, p.ep_m3_y, h6)

    # C: motor-end end-piece, outer layer (connector window)
    c = rect(0, 0, p.ec_w, p.ep_h, t6)
    c = c - disc(cw - p.ep_m3_dx, p.ep_m3_y, p.d_m3clr_c, t6) - disc(cw + p.ep_m3_dx, p.ep_m3_y, p.d_m3clr_c, t6)
    c = c - rrect(cw, p.dsub_y, p.win_w, p.win_h, p.win_r, t6)
    c = c - end_row(cw, p.ec_h1, p.ec_h2, t6)
    parts["end_motor_out"] = c
    d("end_motor_out.m3_l", cw - p.ep_m3_dx, p.ep_m3_y, h6)
    d("end_motor_out.m3_r", cw + p.ep_m3_dx, p.ep_m3_y, h6)
    d("end_motor_out.m5_l", cw - p.ec_h1, p.ep_h - p.row_off, h6)

    # ================================================================ carriage
    # H: carriage top wall, comb on both long edges, slots for the partitions
    hh = p.car_d
    h = rect(t6, t6, W - t6, hh - t6, t6)
    h = h + tab_pattern(p, W, 0, t6, t6) + tab_pattern(p, W, hh - t6, hh, t6)
    side_y = (hh - p.tab_w) / 2
    h = h + rect(0, side_y, t6, side_y + p.tab_w, t6) + rect(W - t6, side_y, W, side_y + p.tab_w, t6)
    for ox in (p.o_x, W - p.o_x):
        h = h - rect(ox - h6, t6, ox + h6, t6 + p.h_notch, t6)
        h = h - rect(ox - h6, hh - t6 - p.h_notch, ox + h6, hh - t6, t6)
    parts["carriage_top"] = h
    d("carriage_top.p1", p.o_x + t6, hh / 2, t6)
    d("carriage_top.p2", W / 2, hh / 2, t6)
    d("carriage_top.p3", p.tab_m1 + p.tab_w / 2, hh - t6 / 2, t6)

    # G: carriage face plates (lead-screw nut and linear-bearing seats)
    gh = p.g_h
    band0 = p.tab_o1 + (p.tab_n_out - 1) * p.tab_p + p.tab_w
    g = rect(0, 0, W, gh - t6, t6) - tab_pattern(p, W, 0, t6, t6)
    g = g + rect(band0, gh - t6, W - band0, gh, t6) - row(p.tab_m1, p.tab_p, p.tab_n_mid, p.tab_w, gh - t6, gh, t6)
    gy = (gh - p.tab_w) / 2
    g = g - rect(0, gy, t6, gy + p.tab_w, t6) - rect(W - t6, gy, W, gy + p.tab_w, t6)
    for ox in (p.o_x, W - p.o_x):
        g = g - rect(ox - h6, gy, ox + h6, gy + p.tab_w, t6)
    ca, sa = cos(radians(p.hole_ang)), sin(radians(p.hole_ang))
    for sx in (-1, 1):
        nx = W / 2 + sx * (W / 2 - p.scr_x)
        bxx = W / 2 + sx * (W / 2 - p.rod_x)
        g = g - disc(nx, p.g_ax, p.d_nut, t6) - disc(bxx, p.g_ax, p.d_brg, t6)
        rn = p.nut_pcd / 2
        for ux in (-1, 1):
            for uy in (-1, 1):
                g = g - disc(nx + ux * rn * ca, p.g_ax + uy * rn * sa, p.d_m3tap, t6)
        rb = p.brg_pcd / 2
        for u in (-1, 1):
            g = g - disc(bxx - sx * u * rb * ca, p.g_ax - u * rb * sa, p.d_m3tap, t6)
    parts["carriage_face"] = g
    d("carriage_face.brg_l", p.rod_x, p.g_ax, h6)
    d("carriage_face.brg_l_top", p.rod_x, p.g_ax, t6)
    d("carriage_face.brg_l_bot", p.rod_x, p.g_ax, 0)
    d("carriage_face.nut_l", p.scr_x, p.g_ax, h6)
    d("carriage_face.nut_r", W - p.scr_x, p.g_ax, h6)
    d("carriage_face.brg_r", W - p.rod_x, p.g_ax, h6)
    d("carriage_face.mid", W / 2, gh / 2, t6)

    # E: carriage flange carrying the mobile substrate mountings
    ex0 = (W - p.e_w) / 2
    e = rect(t6, t6, p.e_w - t6, p.e_h, t6)
    e = e - rect(t6, hh - t6, t6 + p.e_notch, hh, t6) - rect(p.e_w - t6 - p.e_notch, hh - t6, p.e_w - t6, hh, t6)
    e = e + rect(0, side_y, t6, side_y + p.tab_w, t6) + rect(p.e_w - t6, side_y, p.e_w, side_y + p.tab_w, t6)
    e = e + row(p.tab_m1 - ex0, p.tab_p, p.tab_n_mid, p.tab_w, 0, t6, t6)
    e = e - row(p.tab_m1 + p.tab_w - ex0, p.tab_p, p.tab_n_mid - 1, p.tab_w, hh - t6, hh, t6)
    for k in range(int(p.n_wells)):
        xc = p.well_x0 + k * p.well_p - ex0
        e = e - disc(xc - p.q_m4_dx, p.e_hole_y, p.d_m4tap, t6) - disc(xc + p.q_m4_dx, p.e_hole_y, p.d_m4tap, t6)
    parts["carriage_flange"] = e
    d("carriage_flange.h1", p.well_x0 - ex0 - p.q_m4_dx, p.e_hole_y, h6)
    d("carriage_flange.h12", p.well_x0 + (p.n_wells - 1) * p.well_p - ex0 + p.q_m4_dx, p.e_hole_y, h6)
    d("carriage_flange.p_mid", p.e_w / 2, hh / 2, t6)

    # O1 / O2: carriage partitions and end caps
    o1 = rect(t6, 0, hh - t6, gh, t6) + rect(0, gy, t6, gy + p.tab_w, t6) + rect(hh - t6, gy, hh, gy + p.tab_w, t6)
    o1 = o1 - rect(side_y, 0, side_y + p.tab_w, t6, t6) - rect(side_y, gh - t6, side_y + p.tab_w, gh, t6)
    parts["carriage_partition"] = o1
    d("carriage_partition.p1", hh / 2, gh / 2, t6)
    d("carriage_partition.p2", t6 / 2, gy + p.tab_w / 2, t6)
    d("carriage_partition.p3", hh / 2, t6 + t6 / 2, t6)
    o2 = rect(t6, 0, hh - t6, gh - t6, t6) + rect(0, gy, t6, gy + p.tab_w, t6) + rect(hh - t6, gy, hh, gy + p.tab_w, t6)
    o2 = o2 - rect(side_y, 0, side_y + p.tab_w, t6, t6)
    parts["carriage_end"] = o2
    d("carriage_end.p1", hh / 2, gh / 2, t6)
    d("carriage_end.p2", t6 / 2, gy + p.tab_w / 2, t6)
    d("carriage_end.p3", hh / 2, t6 + t6 / 2, t6)

    # ================================================================ stationary bar
    f = rect(0, 0, W, p.f_h, t6)
    for k in range(int(p.n_wells)):
        xc = p.well_x0 + k * p.well_p
        f = f - disc(xc - p.q_m4_dx, p.f_m4_y, p.d_m4tap, t6) - disc(xc + p.q_m4_dx, p.f_m4_y, p.d_m4tap, t6)
        for yy in (p.ep_h1, p.ep_h2):
            f = f - disc(xc, yy, p.d_m5clr, t6)
    for yy in (p.ep_h1, p.ep_h2):
        f = f - disc(p.well_x0 - p.f_c_off, yy, p.d_m5clr, t6)
        f = f - disc(p.well_x0 + (p.n_wells - 1) * p.well_p + p.f_c_off, yy, p.d_m5clr, t6)
        for x in (p.ep_h1, p.ep_h2, W - p.ep_h1, W - p.ep_h2):
            f = f - disc(x, yy, p.d_m5, t6)
    parts["stat_bar"] = f
    d("stat_bar.m4_1", p.well_x0 - p.q_m4_dx, p.f_m4_y, h6)
    d("stat_bar.m5_a", p.ep_h1, p.ep_h1, h6)
    d("stat_bar.m5_b", W - p.ep_h1, p.ep_h2, h6)

    # ================================================================ substrate mounting plate
    qcx = p.q_w / 2
    q = rect(0, p.q_lobe_r, p.q_w, p.q_h, t6) + rect(qcx - p.q_lobe_dx, p.q_neck_y, qcx + p.q_lobe_dx, p.q_lobe_r, t6)
    q = q + disc(qcx - p.q_lobe_dx, p.q_lobe_r, 2 * p.q_lobe_r, t6) + disc(qcx + p.q_lobe_dx, p.q_lobe_r, 2 * p.q_lobe_r, t6)
    q = q - disc(qcx - p.q_lobe_dx, p.q_lobe_r, p.d_m3tap, t6) - disc(qcx + p.q_lobe_dx, p.q_lobe_r, p.d_m3tap, t6)
    q = q - disc(qcx - p.q_c_dx, p.q_c_y, p.d_m4tap, t6) - disc(qcx + p.q_c_dx, p.q_c_y, p.d_m4tap, t6)
    q = q - disc(qcx - p.q_m4_dx, p.q_b_y, p.d_m4clr, t6) - disc(qcx + p.q_m4_dx, p.q_b_y, p.d_m4clr, t6)
    parts["mount_plate"] = q
    d("mount_plate.post_a", qcx - p.q_lobe_dx, p.q_lobe_r, h6)
    d("mount_plate.post_b", qcx + p.q_lobe_dx, p.q_lobe_r, h6)
    d("mount_plate.m4_a", qcx - p.q_m4_dx, p.q_b_y, h6)
    d("mount_plate.c_b", qcx + p.q_c_dx, p.q_c_y, h6)

    # ================================================================ stretch-holding frames
    def frame(w, sx, ww):
        fr = rrect(w / 2, p.fr_h / 2, w, p.fr_h, p.fr_r, t6)
        fr = fr - rrect(w / 2, p.fr_h / 2, ww, p.fr_win_h, p.fr_win_r, t6)
        for x in (sx, w - sx):
            for y in (p.fr_h / 2 - p.fr_slot_dy / 2, p.fr_h / 2 + p.fr_slot_dy / 2):
                fr = fr - slot(x, y, p.fr_slot_L, p.fr_slot_w, t6)
        return fr

    parts["frame_wide"] = frame(p.fw_w, p.fw_slot_x, p.fw_win_w)
    parts["frame_narrow"] = frame(p.fn_w, p.fn_slot_x, p.fn_win_w)
    for nm, w, sx in (("frame_wide", p.fw_w, p.fw_slot_x), ("frame_narrow", p.fn_w, p.fn_slot_x)):
        d(nm + ".s1", sx, p.fr_h / 2, t6)  # side bar, between its two slots
        d(nm + ".s2", w - sx, p.fr_h / 2, t6)
        d(nm + ".s3", w / 2, p.fr_r / 2, t6)  # end bar

    # ================================================================ corner plates, switch plate, rod flanges
    kp = rect(0, 0, p.k_w, p.k_h, t6)
    for i in range(int(p.k_n)):
        for yy in (p.ep_h1, p.ep_h2):
            kp = kp - disc(p.ep_h1 + i * p.k_p, yy, p.d_m5, t6)
    parts["corner_plate"] = kp
    d("corner_plate.a", p.ep_h1, p.ep_h1, h6)
    d("corner_plate.b", p.ep_h1 + (p.k_n - 1) * p.k_p, p.ep_h1, h6)
    d("corner_plate.c", p.ep_h1, p.ep_h2, h6)

    sp = rect(0, 0, p.n_w, p.n_h, t6)
    sp = sp - disc(p.sw_x - p.sw_dx, p.sw_y, p.d_sw, t6) - disc(p.sw_x + p.sw_dx, p.sw_y, p.d_sw, t6)
    for x in (p.ep_h1, p.ep_h2):
        for yy in (p.n_hy, p.n_hy + p.k_p):
            sp = sp - disc(x, yy, p.d_m5, t6)
    parts["switch_plate"] = sp
    d("switch_plate.sw_a", p.sw_x - p.sw_dx, p.sw_y, h6)
    d("switch_plate.m5_a", p.ep_h1, p.n_hy, h6)
    d("switch_plate.m5_d", p.ep_h2, p.n_hy + p.k_p, h6)

    ov = ellipse(p.ov_rx, p.ov_ry, p.ov_rx, p.ov_ry, t6) - disc(p.ov_rx, p.ov_ry, p.d_ov, t6)
    ov = ov - disc(p.ov_rx - p.ov_hx, p.ov_ry, p.d_m3clr, t6) - disc(p.ov_rx + p.ov_hx, p.ov_ry, p.d_m3clr, t6)
    parts["rod_flange"] = ov
    d("rod_flange.c", p.ov_rx, p.ov_ry, h6)
    d("rod_flange.a", p.ov_rx - p.ov_hx, p.ov_ry, h6)
    d("rod_flange.b", p.ov_rx + p.ov_hx, p.ov_ry, h6)
    d("rod_flange.top_pt", p.ov_rx, p.ov_ry / 2, t6)

    # ================================================================ motor box
    bx = p.mb_w
    n0, n1 = p.mb_n0, p.mb_n0 + p.tab_p
    lf = rect(0, 0, bx, bx, t6)
    for a0 in (n0, n1):
        lf = lf - rect(0, a0, t6, a0 + p.tab_w, t6) - rect(bx - t6, a0, bx, a0 + p.tab_w, t6)
        lf = lf - rect(a0, bx - t6, a0 + p.tab_w, bx, t6)
    lf = lf - disc(bx / 2, bx / 2, p.d_pilot, t6)
    for ux in (-1, 1):
        for uy in (-1, 1):
            lf = lf - disc(bx / 2 + ux * p.motor_hp / 2, bx / 2 + uy * p.motor_hp / 2, p.d_motor_hole, t6)
    parts["motor_face"] = lf
    d("motor_face.c", bx / 2, bx / 2, h6)
    d("motor_face.h1", bx / 2 - p.motor_hp / 2, bx / 2 - p.motor_hp / 2, h6)
    d("motor_face.h2", bx / 2 + p.motor_hp / 2, bx / 2 - p.motor_hp / 2, h6)

    mb = rect(t6, t6, bx - t6, bx, t6)
    for a0 in (n0, n1):
        mb = mb + rect(0, a0, t6, a0 + p.tab_w, t6) + rect(bx - t6, a0, bx, a0 + p.tab_w, t6)
        mb = mb + rect(a0, 0, a0 + p.tab_w, t6, t6)
    for ux in (-1, 1):
        for yy in (p.mb_hy, p.mb_hy + p.mb_hp):
            mb = mb - disc(bx / 2 + ux * p.mb_hx, yy, p.d_m6, t6)
    parts["motor_base"] = mb
    d("motor_base.h1", bx / 2 - p.mb_hx, p.mb_hy, h6)
    d("motor_base.h2", bx / 2 + p.mb_hx, p.mb_hy, h6)
    d("motor_base.h3", bx / 2 - p.mb_hx, p.mb_hy + p.mb_hp, h6)

    leg = bx - t6
    gu = poly([(t6, 0), (bx, leg), (t6, leg)], t6)  # counter-clockwise, so it extrudes up
    for a0 in (n0, n1):
        gu = gu + rect(0, a0, t6, a0 + p.tab_w, t6)
    gu = gu + rect(t6, leg, n0, bx, t6) + rect(n0 + p.tab_w, leg, n1, bx, t6) + rect(n1 + p.tab_w, leg, bx, bx, t6)
    parts["motor_gusset"] = gu
    d("motor_gusset.a", t6 / 2, n0 + p.tab_w / 2, t6)
    d("motor_gusset.b", n0 + p.tab_w + p.tab_w / 2, bx - t6 / 2, t6)
    d("motor_gusset.c", t6 + t6 / 2, leg - t6 / 2, t6)

    # ================================================================ purchased stretcher parts
    parts["profile_long"] = Box(p.prof_w, p.prof_long_L, p.prof_h, align=MINS)
    parts["profile_short"] = Box(p.prof_short_L, p.prof_w, p.prof_h, align=MINS)
    d("profile_long.end_a", p.prof_w / 2, 0, p.prof_h / 2)
    d("profile_long.end_b", p.prof_w / 2, p.prof_long_L, p.prof_h / 2)
    d("profile_short.end_a", 0, p.prof_w / 2, p.prof_h / 2)
    d("profile_short.end_b", p.prof_short_L, p.prof_w / 2, p.prof_h / 2)

    parts["lead_screw"] = Cylinder(p.d_screw / 2, p.screw_L, align=CTR)
    d("lead_screw.ax_a", 0, 0, 0)
    d("lead_screw.ax_b", 0, 0, p.screw_L)
    parts["guide_rod"] = Cylinder(p.d_rod / 2, p.rod_L, align=CTR)
    d("guide_rod.ax_a", 0, 0, 0)
    d("guide_rod.ax_b", 0, 0, p.rod_L)
    cp = Cylinder(p.coupler_d / 2, p.coupler_L, align=CTR)
    cp = cp - Cylinder(p.d_screw / 2, p.coupler_L / 2, align=CTR)
    cp = cp - Pos(0, 0, p.coupler_L / 2) * Cylinder(p.d_shaft / 2, p.coupler_L / 2, align=CTR)
    parts["coupler"] = cp
    d("coupler.ax", 0, 0, p.coupler_L)
    mt = Pos(0, 0, p.pilot_h) * Box(p.motor_w, p.motor_w, p.motor_L, align=CTR)
    mt = mt + Cylinder(p.pilot_d / 2, p.pilot_h, align=CTR)
    mt = mt + Pos(0, 0, p.pilot_h - p.shaft_L) * Cylinder(p.d_shaft / 2, p.shaft_L, align=CTR)
    parts["stepper_motor"] = mt
    d("stepper_motor.shaft_tip", 0, 0, p.pilot_h - p.shaft_L)
    d("stepper_motor.face", 0, 0, p.pilot_h)
    parts["rubber_foot"] = Cylinder(p.foot_d / 2, p.foot_h, align=CTR)
    d("rubber_foot.top", 0, 0, p.foot_h)
    d("rubber_foot.bottom", 0, 0, 0)

    # ================================================================ 3D-printed stretching clamp (Clamp.stl frame)
    r_cl = (p.cl_L - p.cl_pitch) / 2
    hy = p.cl_W - r_cl
    px = p.cl_pitch / 2
    r_in = p.cl_nin / 2 - p.cl_c
    r_out = p.cl_nout / 2 - p.cl_c
    cc = cos(radians(p.cl_ang))
    tx, ty = px + r_cl * cc, hy - r_cl * cc  # tangent point of the chamfer on the lobe
    bx0 = tx - ty  # where the chamfer meets the bottom edge
    outline = [(-bx0, 0), (bx0, 0), (tx, ty), (px, hy), (px, p.cl_flat), (-px, p.cl_flat), (-px, hy), (-tx, ty)]
    pl = poly(outline, p.cl_t) + disc(-px, hy, 2 * r_cl, p.cl_t) + disc(px, hy, 2 * r_cl, p.cl_t)

    def u_shape(r, height):
        u = rect(-p.cl_c, 0, p.cl_c, r, height)
        u = u + disc(-p.cl_c, 0, 2 * r, height) + disc(p.cl_c, 0, 2 * r, height)
        return u - rect(-p.cl_c - r, -r, p.cl_c + r, 0, height)

    cl = pl + u_shape(r_out, p.cl_H)
    cl = cl - u_shape(r_in, p.cl_H)
    cl = cl - disc(-px, hy, p.cl_hole, p.cl_t) - disc(px, hy, p.cl_hole, p.cl_t)
    parts["stretch_clamp"] = cl
    d("stretch_clamp.hole_a", -px, hy, p.cl_t / 2)
    d("stretch_clamp.hole_b", px, hy, p.cl_t / 2)
    d("stretch_clamp.corner_l", -bx0, 0, 0)
    d("stretch_clamp.corner_r", bx0, 0, 0)
    d("stretch_clamp.top_l", -bx0, 0, p.cl_t)
    d("stretch_clamp.wall_top", -p.cl_c - r_out, 0, p.cl_H)
    d("stretch_clamp.inner_l", -p.cl_c - r_in, 0, 0)
    d("stretch_clamp.inner_r", p.cl_c + r_in, 0, 0)
    d("stretch_clamp.hole_a_w", -px - p.cl_hole / 2, hy, 0)
    d("stretch_clamp.hole_a_e", -px + p.cl_hole / 2, hy, 0)
    d("stretch_clamp.hole_b_w", px - p.cl_hole / 2, hy, 0)
    d("stretch_clamp.wall_r", p.cl_c + r_out, 0, p.cl_H)
    d("stretch_clamp.flat_l", -p.cl_c, r_in, 0)
    d("stretch_clamp.flat_r", p.cl_c, r_in, 0)

    # ================================================================ mould (Acryl3MM parts, MoldFrame.stl)
    mw = p.mb_side
    base = rect(0, 0, mw, mw, t3)
    for x in (p.mb_corner, mw - p.mb_corner):
        for y in (p.mb_corner, mw - p.mb_corner):
            base = base - disc(x, y, p.d_m4tap, t3)
    for x in (mw / 2 - p.post_half, mw / 2 + p.post_half):
        for y in (mw / 2 - p.post_half, mw / 2 + p.post_half):
            base = base - disc(x, y, p.straw_d, t3)
    parts["mould_base"] = base
    d("mould_base.post_1", mw / 2 - p.post_half, mw / 2 - p.post_half, t3 / 2)
    d("mould_base.post_2", mw / 2 + p.post_half, mw / 2 - p.post_half, t3 / 2)
    d("mould_base.post_3", mw / 2 - p.post_half, mw / 2 + p.post_half, t3 / 2)
    d("mould_base.post_4", mw / 2 + p.post_half, mw / 2 + p.post_half, t3 / 2)
    d("mould_base.m4_1", p.mb_corner, p.mb_corner, t3 / 2)

    pw_ = p.pf_w
    parts["platform"] = rrect(pw_ / 2, pw_ / 2, pw_, pw_, p.pf_r, t3)
    d("platform.top_c", pw_ / 2, pw_ / 2, t3)
    d("platform.edge_w", 0, pw_ / 2, t3 / 2)
    d("platform.edge_e", pw_, pw_ / 2, t3 / 2)
    d("platform.p_a", p.pf_r, p.pf_r, t3)
    d("platform.p_b", pw_ - p.pf_r, p.pf_r, t3)

    jig = rect(0, 0, mw, mw, t3) - rrect(mw / 2, mw / 2, pw_, pw_, p.pf_r, t3)
    for x in (p.mb_corner, mw - p.mb_corner):
        for y in (p.mb_corner, mw - p.mb_corner):
            jig = jig - disc(x, y, p.d_m4clr, t3)
    parts["platform_jig"] = jig
    d("platform_jig.h1", p.mb_corner, p.mb_corner, t3 / 2)
    d("platform_jig.h2", mw - p.mb_corner, p.mb_corner, t3 / 2)
    d("platform_jig.h3", p.mb_corner, mw - p.mb_corner, t3 / 2)

    ring = disc(p.ring_od / 2, p.ring_od / 2, p.ring_od, t3) - disc(p.ring_od / 2, p.ring_od / 2, p.straw_d, t3)
    parts["post_ring"] = ring
    d("post_ring.c", p.ring_od / 2, p.ring_od / 2, t3 / 2)
    d("post_ring.mid_e", p.ring_od / 2 + p.ring_mid_r, p.ring_od / 2, t3)
    d("post_ring.mid_n", p.ring_od / 2, p.ring_od / 2 + p.ring_mid_r, t3)

    parts["straw_post"] = Cylinder(p.straw_d / 2, p.straw_L, align=CTR)
    d("straw_post.wall", p.straw_d / 2, 0, p.straw_L / 2)
    d("straw_post.ax_top", 0, 0, p.straw_L)

    mf = p.mf_w
    lr = (p.mf_lobe_span - p.mf_lobe_p) / 2
    fr_ = rect(-mf / 2, -mf / 2, mf / 2, mf / 2, p.mf_h)
    win = rect(-p.mf_win / 2, -p.mf_win / 2, p.mf_win / 2, p.mf_win / 2, p.mf_h)
    for sx in (-1, 1):
        for sy in (-1, 1):
            win = win + disc(sx * p.mf_lobe_p / 2, sy * p.mf_lobe_p / 2, 2 * lr, p.mf_h)
            fr_ = fr_ - disc(sx * p.mf_hole_p / 2, sy * p.mf_hole_p / 2, p.mf_hole_d, p.mf_h)
    parts["mould_frame"] = fr_ - win
    d("mould_frame.c1", -mf / 2, -mf / 2, 0)
    d("mould_frame.c2", mf / 2, -mf / 2, 0)
    d("mould_frame.c3", mf / 2, mf / 2, p.mf_h)
    d("mould_frame.top", -mf / 2, -mf / 2, p.mf_h)
    d("mould_frame.hole_w", -p.mf_hole_p / 2 - p.mf_hole_d / 2, -p.mf_hole_p / 2, 0)
    d("mould_frame.hole_e", -p.mf_hole_p / 2 + p.mf_hole_d / 2, -p.mf_hole_p / 2, 0)
    d("mould_frame.hole2_e", p.mf_hole_p / 2 - p.mf_hole_d / 2, -p.mf_hole_p / 2, 0)
    d("mould_frame.lobe_n1", -p.mf_lobe_p / 2, p.mf_lobe_p / 2 + lr, 0)
    d("mould_frame.lobe_n2", p.mf_lobe_p / 2, p.mf_lobe_p / 2 + lr, 0)
    d("mould_frame.lobe_s1", -p.mf_lobe_p / 2, -p.mf_lobe_p / 2 - lr, 0)
    d("mould_frame.win_w", -p.mf_win / 2, -p.mf_lobe_p / 2 + lr, 0)
    d("mould_frame.win_e", p.mf_win / 2, -p.mf_lobe_p / 2 + lr, 0)

    # ================================================================ assembly
    XZ = (-90, 0, 0)  # local x -> X, local y -> -Z, local z -> +Y
    YZ = (0, -90, 90)  # local x -> +Y, local y -> -Z, local z -> -X
    FLIP = (180, 0, 0)  # local y -> -Y, local z -> -Z
    R180 = (0, 0, 180)  # local x -> -X, local y -> -Y

    def put(name, part, xyz, rot=(0, 0, 0)):
        assembly[name] = (part, Location(xyz, rot))

    ph, pwid = p.prof_h, p.prof_w
    y_m = p.rod_L - 2 * t6 - pwid  # motor-end short profile
    axis_z = p.ep_h - p.ax_y
    put("profile_long_1", "profile_long", (0, 0, 0))
    put("profile_long_2", "profile_long", (W - pwid, 0, 0))
    put("profile_short_far", "profile_short", (pwid, 0, 0))
    put("profile_short_motor", "profile_short", (pwid, y_m, 0))
    put("end_far_in_1", "end_far_in", (0, -t6, p.ep_h), XZ)
    put("end_far_out_1", "end_far_out", (0, -2 * t6, p.ep_h), XZ)
    xc0 = (W - p.ec_w) / 2
    put("end_motor_in_1", "end_motor_in", (xc0, y_m + pwid, p.ep_h), XZ)
    put("end_motor_out_1", "end_motor_out", (xc0, y_m + pwid + t6, p.ep_h), XZ)
    for i, x in ((1, p.rod_x), (2, W - p.rod_x)):
        put(f"guide_rod_{i}", "guide_rod", (x, -t6, axis_z), XZ)
        put(f"rod_flange_far_{i}", "rod_flange", (x - p.ov_rx, 0, axis_z + p.ov_ry), XZ)
        put(f"rod_flange_motor_{i}", "rod_flange", (x - p.ov_rx, y_m + pwid - t6, axis_z + p.ov_ry), XZ)
    y_cp = -t6 + p.screw_L - p.coupler_L / 2  # the screw reaches halfway into its coupler
    y_face = y_cp + p.coupler_L + p.cp_gap  # motor face plate, front face
    for side, x in (("l", p.scr_x), ("r", W - p.scr_x)):
        put(f"screw_{side}", "lead_screw", (x, -t6, axis_z), XZ)
        put(f"coupler_{side}", "coupler", (x, y_cp, axis_z), XZ)
        put(f"motor_{side}", "stepper_motor", (x, y_face + t6 - p.pilot_h, axis_z), XZ)
        put(f"motor_face_{side}", "motor_face", (x - bx / 2, y_face, axis_z + bx / 2), XZ)
        put(f"motor_base_{side}", "motor_base", (x - bx / 2, y_face + bx + t6, ph + t6), FLIP)
        put(f"motor_gusset_{side}1", "motor_gusset", (x - bx / 2 + t6, y_face, axis_z + bx / 2), YZ)
        put(f"motor_gusset_{side}2", "motor_gusset", (x + bx / 2, y_face, axis_z + bx / 2), YZ)
    for i, (x, y) in enumerate(((0, 0), (W - p.k_w, 0), (0, y_m), (W - p.k_w, y_m)), start=1):
        put(f"corner_plate_{i}", "corner_plate", (x, y, -t6))
        put(f"rubber_foot_{i}", "rubber_foot", (x + p.k_w / 2, y + p.k_h / 2, -t6 - p.foot_h))
    put("switch_plate_1", "switch_plate", (W / 2 - p.n_w / 2, y_m + pwid - p.n_h, ph))

    # stationary bar and its mountings
    yf = p.bar_y
    put("stat_bar_1", "stat_bar", (0, yf + p.f_h, ph + t6), FLIP)
    y_q_s = yf + p.f_h - p.f_m4_y + p.q_b_y  # stationary plate origin (turned 180 degrees)
    z_q = ph + t6
    y_post_s = y_q_s - p.q_lobe_r
    y_post_m = y_post_s + p.baseline  # the mobile posts sit one baseline from the stationary ones
    y_q_m = y_post_m - p.q_lobe_r
    y_car = y_q_m + p.q_b_y + p.e_hole_y - hh  # carriage back face plate, outer face
    z_cl = z_q + t6 + p.sub_t
    for k in range(int(p.n_wells)):
        xc = p.well_x0 + k * p.well_p
        put(f"mount_stat_{k + 1}", "mount_plate", (xc + qcx, y_q_s, z_q), R180)
        put(f"mount_mob_{k + 1}", "mount_plate", (xc - qcx, y_q_m, z_q))
        put(f"clamp_stat_{k + 1}", "stretch_clamp", (xc, y_post_s + hy, z_cl), R180)
        put(f"clamp_mob_{k + 1}", "stretch_clamp", (xc, y_post_m - hy, z_cl))

    # carriage
    z_top = axis_z + p.g_ax
    put("carriage_back", "carriage_face", (0, y_car, z_top), XZ)
    put("carriage_front", "carriage_face", (0, y_car + hh - t6, z_top), XZ)
    put("carriage_top_1", "carriage_top", (0, y_car, z_top - t6))
    put("carriage_flange_1", "carriage_flange", (ex0, y_car + hh, ph + t6), FLIP)
    put("carriage_partition_1", "carriage_partition", (p.o_x + h6, y_car, z_top), YZ)
    put("carriage_partition_2", "carriage_partition", (W - p.o_x + h6, y_car, z_top), YZ)
    put("carriage_end_1", "carriage_end", (t6, y_car, z_top), YZ)
    put("carriage_end_2", "carriage_end", (W, y_car, z_top), YZ)

    # stretch-holding frames, kept beside the stretcher (not fitted at zero stretch)
    for k in range(int(p.n_wells)):
        put(f"frame_wide_{k + 1}", "frame_wide", (p.kit_x, 0, k * t6))
        put(f"frame_narrow_{k + 1}", "frame_narrow", (p.kit_x, 2 * p.fr_h, k * t6))

    # mould, assembled for casting, beside the stretcher
    mx, my = p.kit_x, p.mould_y
    put("mould_base_1", "mould_base", (mx, my, 0))
    put("platform_1", "platform", (mx + mw / 2 - pw_ / 2, my + mw / 2 - pw_ / 2, t3))
    put("mould_frame_1", "mould_frame", (mx + mw / 2, my + mw / 2, t3))
    for i, (sx, sy) in enumerate(((-1, -1), (1, -1), (-1, 1), (1, 1)), start=1):
        cx, cy = mx + mw / 2 + sx * p.post_half, my + mw / 2 + sy * p.post_half
        put(f"straw_post_{i}", "straw_post", (cx, cy, 0))
        put(f"post_ring_{i}", "post_ring", (cx - p.ring_od / 2, cy - p.ring_od / 2, t3))
    put("platform_jig_1", "platform_jig", (mx + 2 * mw, my, 0))

    # ================================================================ motion
    joints = {
        "motor_l": {"type": "revolute", "parent": "profile_long_1", "child": "screw_l",
                    "axis": ["screw_l.ax_a", "screw_l.ax_b"], "drive": "actuated"},
        "motor_r": {"type": "revolute", "parent": "profile_long_2", "child": "screw_r",
                    "axis": ["screw_r.ax_a", "screw_r.ax_b"], "drive": "actuated"},
        "coupling_l": {"type": "fixed", "parent": "screw_l", "child": "coupler_l"},
        "coupling_r": {"type": "fixed", "parent": "screw_r", "child": "coupler_r"},
        "carriage": {"type": "slide", "parent": "profile_long_1", "child": "carriage_back",
                     "axis": ["carriage_back.brg_l_bot", "carriage_back.brg_l_top"],
                     "range": ["stretch_max"], "drive": "passive"},
    }
    for nm in ("carriage_front", "carriage_top_1", "carriage_flange_1", "carriage_partition_1",
               "carriage_partition_2", "carriage_end_1", "carriage_end_2"):
        joints["fix_" + nm] = {"type": "fixed", "parent": "carriage_back", "child": nm}
    for k in range(int(p.n_wells)):
        joints[f"fix_mount_mob_{k + 1}"] = {"type": "fixed", "parent": "carriage_flange_1",
                                            "child": f"mount_mob_{k + 1}"}
        joints[f"fix_clamp_mob_{k + 1}"] = {"type": "fixed", "parent": f"mount_mob_{k + 1}",
                                             "child": f"clamp_mob_{k + 1}"}
    gears = {
        "lead_l": {"driver": "motor_l", "driven": "carriage", "lead": "screw_lead"},
        "lead_r": {"driver": "carriage", "driven": "motor_r", "lead": "screw_lead_r"},
    }
    cables = {"substrate_1": {"path": ["mount_stat_1.post_a", "mount_mob_1.post_b"]}}
    # Where the cut files draw each cut part: its region, the part, where the sheet draws the
    # part's origin, its turn about z and whether it is turned over.
    sheets = {}
    for region, part, x, y, turn, over in [
        ("acryl6mm@19.78,532.27", "end_far_in", p.end_far_in_1_x, p.end_far_in_1_y, 0, False),
        ("acryl6mm@19.78,460.47", "end_far_out", p.end_far_out_1_x, p.end_far_out_1_y, 0, False),
        ("acryl6mm@14.98,316.59", "end_motor_in", p.end_motor_in_1_x, p.end_motor_in_1_y, 0, False),
        ("acryl6mm@14.98,388.47", "end_motor_out", p.end_motor_out_1_x, p.end_motor_out_1_y, 0, False),
        ("acryl6mm@19.78,133.17", "carriage_top", p.carriage_top_1_x, p.carriage_top_1_y, 0, False),
        ("acryl6mm@29.53,226.22", "carriage_face", p.carriage_face_1_x, p.carriage_face_1_y, 0, False),
        ("acryl6mm@29.53,179.22", "carriage_face", p.carriage_face_2_x, p.carriage_face_2_y, 0, False),
        ("acryl6mm@12.68,58.67", "carriage_flange", p.carriage_flange_1_x, p.carriage_flange_1_y, 0, False),
        ("acryl6mm@351.41,366.54", "carriage_partition", p.carriage_partition_1_x, p.carriage_partition_1_y, 0, False),
        ("acryl6mm@302.87,366.54", "carriage_partition", p.carriage_partition_2_x, p.carriage_partition_2_y, 0, False),
        ("acryl6mm@351.41,415.24", "carriage_end", p.carriage_end_1_x, p.carriage_end_1_y, 0, False),
        ("acryl6mm@302.87,415.24", "carriage_end", p.carriage_end_2_x, p.carriage_end_2_y, 0, False),
        ("acryl6mm@19.5,272.92", "stat_bar", p.stat_bar_1_x, p.stat_bar_1_y, 0, False),
        ("acryl6mm@430.2,475.44", "mount_plate", p.mount_plate_1_x, p.mount_plate_1_y, 180, False),
        ("acryl6mm@501.24,475.44", "mount_plate", p.mount_plate_2_x, p.mount_plate_2_y, 180, False),
        ("acryl6mm@465.84,475.44", "mount_plate", p.mount_plate_3_x, p.mount_plate_3_y, 0, False),
        ("acryl6mm@394.8,475.44", "mount_plate", p.mount_plate_4_x, p.mount_plate_4_y, 0, False),
        ("acryl6mm@465.84,558.46", "mount_plate", p.mount_plate_5_x, p.mount_plate_5_y, 0, False),
        ("acryl6mm@394.8,558.46", "mount_plate", p.mount_plate_6_x, p.mount_plate_6_y, 0, False),
        ("acryl6mm@430.2,558.46", "mount_plate", p.mount_plate_7_x, p.mount_plate_7_y, 180, False),
        ("acryl6mm@501.24,558.46", "mount_plate", p.mount_plate_8_x, p.mount_plate_8_y, 180, False),
        ("acryl6mm@465.84,517.35", "mount_plate", p.mount_plate_9_x, p.mount_plate_9_y, 0, False),
        ("acryl6mm@394.8,517.35", "mount_plate", p.mount_plate_10_x, p.mount_plate_10_y, 0, False),
        ("acryl6mm@430.2,517.35", "mount_plate", p.mount_plate_11_x, p.mount_plate_11_y, 180, False),
        ("acryl6mm@501.24,517.35", "mount_plate", p.mount_plate_12_x, p.mount_plate_12_y, 180, False),
        ("acryl6mm@466.09,237.98", "frame_wide", p.frame_wide_1_x, p.frame_wide_1_y, 0, False),
        ("acryl6mm@466.09,378.02", "frame_wide", p.frame_wide_2_x, p.frame_wide_2_y, 0, False),
        ("acryl6mm@466.09,190.4", "frame_wide", p.frame_wide_3_x, p.frame_wide_3_y, 0, False),
        ("acryl6mm@466.09,425.06", "frame_wide", p.frame_wide_4_x, p.frame_wide_4_y, 0, False),
        ("acryl6mm@466.09,285.01", "frame_wide", p.frame_wide_5_x, p.frame_wide_5_y, 0, False),
        ("acryl6mm@466.09,330.45", "frame_wide", p.frame_wide_6_x, p.frame_wide_6_y, 0, False),
        ("acryl6mm@397.69,190.26", "frame_narrow", p.frame_narrow_1_x, p.frame_narrow_1_y, 0, False),
        ("acryl6mm@397.69,284.88", "frame_narrow", p.frame_narrow_2_x, p.frame_narrow_2_y, 0, False),
        ("acryl6mm@397.69,330.31", "frame_narrow", p.frame_narrow_3_x, p.frame_narrow_3_y, 0, False),
        ("acryl6mm@397.69,424.92", "frame_narrow", p.frame_narrow_4_x, p.frame_narrow_4_y, 0, False),
        ("acryl6mm@397.69,237.84", "frame_narrow", p.frame_narrow_5_x, p.frame_narrow_5_y, 0, False),
        ("acryl6mm@397.69,377.89", "frame_narrow", p.frame_narrow_6_x, p.frame_narrow_6_y, 0, False),
        ("acryl6mm@398.55,145.36", "corner_plate", p.corner_plate_1_x, p.corner_plate_1_y, 0, False),
        ("acryl6mm@478.98,145.36", "corner_plate", p.corner_plate_2_x, p.corner_plate_2_y, 0, False),
        ("acryl6mm@398.55,104.86", "corner_plate", p.corner_plate_3_x, p.corner_plate_3_y, 0, False),
        ("acryl6mm@478.98,104.86", "corner_plate", p.corner_plate_4_x, p.corner_plate_4_y, 0, False),
        ("acryl6mm@547.86,189.38", "switch_plate", p.switch_plate_1_x, p.switch_plate_1_y, 0, False),
        ("acryl6mm@356.83,339.62", "rod_flange", p.rod_flange_1_x, p.rod_flange_1_y, 0, False),
        ("acryl6mm@356.83,316.47", "rod_flange", p.rod_flange_2_x, p.rod_flange_2_y, 0, False),
        ("acryl6mm@316.19,339.62", "rod_flange", p.rod_flange_3_x, p.rod_flange_3_y, 0, False),
        ("acryl6mm@316.19,316.47", "rod_flange", p.rod_flange_4_x, p.rod_flange_4_y, 0, False),
        ("acryl6mm@544.02,362.76", "motor_face", p.motor_face_1_x, p.motor_face_1_y, 0, False),
        ("acryl6mm@544.02,418.63", "motor_face", p.motor_face_2_x, p.motor_face_2_y, 0, False),
        ("acryl6mm@550.59,306.53", "motor_base", p.motor_base_1_x, p.motor_base_1_y, 0, False),
        ("acryl6mm@550.59,250.65", "motor_base", p.motor_base_2_x, p.motor_base_2_y, 0, False),
        ("acryl6mm@547.12,539.97", "motor_gusset", p.motor_gusset_1_x, p.motor_gusset_1_y, 180, False),
        ("acryl6mm@547.12,477.7", "motor_gusset", p.motor_gusset_2_x, p.motor_gusset_2_y, 180, False),
        ("acryl6mm@544.59,546.75", "motor_gusset", p.motor_gusset_3_x, p.motor_gusset_3_y, 0, False),
        ("acryl6mm@544.59,484.49", "motor_gusset", p.motor_gusset_4_x, p.motor_gusset_4_y, 0, False),
        ("acryl3mm@7.5,547.5", "mould_base", p.mould_base_1_x, p.mould_base_1_y, 0, False),
        ("acryl3mm@172.5,547.5", "mould_base", p.mould_base_2_x, p.mould_base_2_y, 0, False),
        ("acryl3mm@62.5,547.5", "mould_base", p.mould_base_3_x, p.mould_base_3_y, 0, False),
        ("acryl3mm@117.5,547.5", "mould_base", p.mould_base_4_x, p.mould_base_4_y, 0, False),
        ("acryl3mm@117.5,492.5", "mould_base", p.mould_base_5_x, p.mould_base_5_y, 0, False),
        ("acryl3mm@62.5,492.5", "mould_base", p.mould_base_6_x, p.mould_base_6_y, 0, False),
        ("acryl3mm@7.5,492.5", "platform_jig", p.platform_jig_1_x, p.platform_jig_1_y, 0, False),
        ("acryl3mm@133.0,466.0", "platform", p.platform_1_x, p.platform_1_y, 0, False),
        ("acryl3mm@8.0,466.0", "platform", p.platform_2_x, p.platform_2_y, 0, False),
        ("acryl3mm@33.0,466.0", "platform", p.platform_3_x, p.platform_3_y, 0, False),
        ("acryl3mm@58.0,466.0", "platform", p.platform_4_x, p.platform_4_y, 0, False),
        ("acryl3mm@83.0,466.0", "platform", p.platform_5_x, p.platform_5_y, 0, False),
        ("acryl3mm@108.0,466.0", "platform", p.platform_6_x, p.platform_6_y, 0, True),
        ("acryl3mm@178.44,521.91", "post_ring", p.post_ring_1_x, p.post_ring_1_y, 0, False),
        ("acryl3mm@183.97,515.91", "post_ring", p.post_ring_2_x, p.post_ring_2_y, 0, False),
        ("acryl3mm@178.44,533.91", "post_ring", p.post_ring_3_x, p.post_ring_3_y, 0, False),
        ("acryl3mm@183.97,521.91", "post_ring", p.post_ring_4_x, p.post_ring_4_y, 0, False),
        ("acryl3mm@183.97,527.91", "post_ring", p.post_ring_5_x, p.post_ring_5_y, 0, False),
        ("acryl3mm@178.44,515.91", "post_ring", p.post_ring_6_x, p.post_ring_6_y, 0, False),
        ("acryl3mm@178.44,527.91", "post_ring", p.post_ring_7_x, p.post_ring_7_y, 0, False),
        ("acryl3mm@183.97,533.91", "post_ring", p.post_ring_8_x, p.post_ring_8_y, 0, False),
    ]:
        where = Location((x, y, 0), (0, 0, 1), turn)
        sheets[region] = (part, where * Location((0, 0, 0), (1, 0, 0), 180) if over else where)
    return {"parts": parts, "datums": datums, "assembly": assembly, "sheets": sheets, "joints": joints,
            "gears": gears, "cables": cables}
