#!/usr/bin/env python3
"""
scene_kit.py - reusable flat-style mini scene illustrations (Pillow only).

Every public draw_* function has the same signature

    draw_xxx(d, box, seed=0)

    d    : a PIL.ImageDraw.ImageDraw
    box  : (x0, y0, x1, y1) in pixels - the only region the scene may touch
    seed : int, varies small details (windows, crowds, ...) deterministically

Rules the scenes follow
  * Everything is drawn inside `box`; every primitive is clamped to it, so a
    scene can never paint over the text that surrounds its box.
  * No text, no randomness, no files, no network.  The built-in generator is a
    tiny LCG, so the same seed always gives the same picture.
  * Scenes are designed on a virtual canvas that is 60 units high; the width
    follows the box aspect ratio, so they work from roughly 3:1 to 6:1 boxes.

Use render_scene() to get an anti-aliased RGB image of a scene, or call the
draw_* functions directly on any ImageDraw.
"""
from PIL import Image, ImageDraw

__all__ = [
    "draw_skyline", "draw_ship", "draw_parliament", "draw_market_chart",
    "draw_summit", "draw_rescue", "draw_fire", "draw_quake", "draw_ballot",
    "draw_stadium", "draw_lab", "draw_flood", "draw_plane", "draw_energy",
    "draw_space", "draw_hospital", "SCENES", "get_scene", "render_scene",
    "draw_scene", "Stage", "P",
]

_RESAMPLE = getattr(Image, "Resampling", Image).LANCZOS

# --------------------------------------------------------------------------
# flat palette
# --------------------------------------------------------------------------
P = {
    "sky": (176, 214, 240), "sky_hi": (128, 182, 228), "dusk": (238, 196, 156),
    "night": (22, 30, 62), "night2": (40, 52, 96), "sun": (255, 212, 72),
    "cloud": (255, 255, 255), "cloud_g": (196, 204, 216), "storm": (120, 132, 150),
    "sea": (44, 114, 172), "sea_d": (30, 86, 140), "sea_l": (98, 164, 208),
    "grass": (104, 168, 96), "grass_d": (72, 130, 74), "ground": (126, 112, 98),
    "road": (68, 72, 82), "white": (250, 250, 248), "ink": (28, 28, 34),
    "red": (204, 44, 48), "orange": (242, 134, 44), "yellow": (250, 208, 62),
    "green": (62, 152, 92), "blue": (52, 104, 194), "navy": (38, 60, 108),
    "slate": (94, 108, 130), "steel": (130, 144, 162), "gray": (152, 152, 158),
    "dgray": (74, 78, 88), "lgray": (206, 210, 216), "brown": (132, 90, 58),
    "stone": (218, 204, 176), "stone_d": (188, 172, 142), "win": (255, 238, 164),
    "teal": (44, 152, 152), "purple": (112, 72, 152), "skin": (240, 192, 152),
    "water": (92, 124, 140), "water_d": (70, 98, 114), "pink": (232, 120, 140),
}


class _Rng:
    """Tiny deterministic LCG (no `random` module involved)."""

    def __init__(self, seed):
        self.s = (int(seed) * 2654435761 + 12345) & 0xFFFFFFFF

    def _next(self):
        self.s = (self.s * 1664525 + 1013904223) & 0xFFFFFFFF
        return self.s >> 8

    def below(self, n):
        return self._next() % max(1, int(n))

    def frac(self):
        return self._next() / float(1 << 24)


# --------------------------------------------------------------------------
# Stage: virtual 60-unit-high canvas mapped onto a pixel box, with clamping
# --------------------------------------------------------------------------
class Stage:
    H = 60.0

    def __init__(self, d, box):
        x0, y0, x1, y1 = [float(v) for v in box]
        if x1 <= x0 or y1 <= y0:
            raise ValueError("scene box is empty: %r" % (box,))
        self.d = d
        self.x0, self.y0 = x0, y0
        self.x1, self.y1 = x1 - 1.0, y1 - 1.0          # last drawable pixel
        self.s = (y1 - y0) / self.H
        self.W = (x1 - x0) / self.s                    # virtual width
        self.cx = self.W / 2.0

    # -- coordinate helpers ------------------------------------------------
    def px(self, x, y):
        return (min(max(self.x0 + x * self.s, self.x0), self.x1),
                min(max(self.y0 + y * self.s, self.y0), self.y1))

    def lw(self, w):
        return max(1, int(round(w * self.s)))

    # -- primitives (all clamped to the box) -------------------------------
    def rect(self, xa, ya, xb, yb, fill=None, outline=None, w=0.5):
        a = self.px(min(xa, xb), min(ya, yb))
        b = self.px(max(xa, xb), max(ya, yb))
        self.d.rectangle([a, b], fill=fill, outline=outline, width=self.lw(w))

    def rrect(self, xa, ya, xb, yb, r, fill=None):
        a = self.px(min(xa, xb), min(ya, yb))
        b = self.px(max(xa, xb), max(ya, yb))
        self.d.rounded_rectangle([a, b], radius=max(1, int(r * self.s)), fill=fill)

    def ell(self, cx, cy, rx, ry, fill=None, outline=None, w=0.5):
        a = self.px(cx - rx, cy - ry)
        b = self.px(cx + rx, cy + ry)
        self.d.ellipse([a, b], fill=fill, outline=outline, width=self.lw(w))

    def circ(self, cx, cy, r, fill=None, outline=None, w=0.5):
        self.ell(cx, cy, r, r, fill, outline, w)

    def pie(self, cx, cy, rx, ry, a0, a1, fill):
        a = self.px(cx - rx, cy - ry)
        b = self.px(cx + rx, cy + ry)
        self.d.pieslice([a, b], a0, a1, fill=fill)

    def poly(self, pts, fill=None, outline=None):
        self.d.polygon([self.px(x, y) for x, y in pts], fill=fill, outline=outline)

    def line(self, pts, fill, w=0.8):
        self.d.line([self.px(x, y) for x, y in pts], fill=fill,
                    width=self.lw(w), joint="curve")

    def band(self, y0, y1, fill):
        self.rect(0, y0, self.W, y1, fill)

    # -- small composite helpers -------------------------------------------
    def sky(self, top=None, mid=None, low=None):
        self.band(0, 60, low or P["sky"])
        self.band(0, 40, mid or P["sky"])
        self.band(0, 20, top or P["sky_hi"])

    def cloud(self, x, y, k=1.0, col=None):
        col = col or P["cloud"]
        self.ell(x, y + 1.0 * k, 9 * k, 2.8 * k, col)
        self.circ(x - 3 * k, y - 1.2 * k, 3.8 * k, col)
        self.circ(x + 2.5 * k, y - 2.0 * k, 4.6 * k, col)

    def person(self, x, base, h, col, head=None):
        self.rect(x - h * 0.17, base - h * 0.62, x + h * 0.17, base, col)
        self.circ(x, base - h * 0.80, h * 0.17, head or P["skin"])

    def flag(self, x, base, h, col):
        self.rect(x - 0.3, base - h, x + 0.3, base, P["lgray"])
        self.poly([(x + 0.3, base - h), (x + h * 0.55, base - h * 0.88),
                   (x + 0.3, base - h * 0.62)], col)

    def flame(self, x, y, k, outer, inner):
        for col, kk in ((outer, k), (inner, k * 0.55)):
            self.poly([(x - 4 * kk, y), (x - 5 * kk, y - 5 * kk), (x - 2 * kk, y - 9 * kk),
                       (x - 3 * kk, y - 14 * kk), (x + 1 * kk, y - 9 * kk),
                       (x + 2 * kk, y - 14 * kk), (x + 5 * kk, y - 6 * kk),
                       (x + 4 * kk, y)], col)


def _pick(seq, i):
    return seq[i % len(seq)]


# --------------------------------------------------------------------------
# 1. city skyline
# --------------------------------------------------------------------------
def draw_skyline(d, box, seed=0):
    st = Stage(d, box)
    r = _Rng(seed)
    st.sky()
    st.circ(st.W * 0.82, 15, 6.5, P["sun"])
    st.cloud(st.W * 0.22, 12)
    cols = [P["slate"], P["navy"], P["steel"], P["dgray"], P["teal"]]
    x = 0.0
    while x < st.W:
        w = 9 + r.below(10)
        h = 14 + r.below(30)
        top = 52 - h
        xe = min(x + w, st.W)
        st.rect(x, top, xe, 52, _pick(cols, r.below(5)))
        if r.below(3) == 0:
            st.rect(x + w / 2 - 0.6, top - 5, x + w / 2 + 0.6, top, P["dgray"])
        yy = top + 3
        while yy < 48:
            xx = x + 2
            while xx + 2.2 < xe - 1:
                if r.below(4):
                    st.rect(xx, yy, xx + 1.8, yy + 2.2, P["win"])
                xx += 4
            yy += 5
        x += w + 1.2
    st.band(52, 60, P["road"])
    for xx in range(0, int(st.W), 14):
        st.rect(xx, 55.6, xx + 7, 56.6, P["yellow"])


# --------------------------------------------------------------------------
# 2. ship at sea
# --------------------------------------------------------------------------
def draw_ship(d, box, seed=0):
    st = Stage(d, box)
    cx = st.cx
    st.sky()
    st.circ(st.W * 0.18, 16, 6, P["sun"])
    st.cloud(st.W * 0.78, 11)
    st.cloud(st.W * 0.38, 7, 0.7)
    st.band(36, 60, P["sea"])
    st.band(50, 60, P["sea_d"])
    st.poly([(cx - 46, 34), (cx + 48, 34), (cx + 40, 46), (cx - 38, 46)], P["dgray"])
    st.poly([(cx - 39, 41), (cx + 43, 41), (cx + 40, 46), (cx - 38, 46)], P["red"])
    cols = [P["red"], P["blue"], P["orange"], P["green"], P["yellow"], P["teal"]]
    for row in range(2):
        for i in range(8):
            xa = cx - 41 + i * 7.4
            st.rect(xa, 34 - (row + 1) * 5.2, xa + 7.0, 34 - row * 5.2,
                    _pick(cols, i * 2 + row + seed), P["ink"], 0.2)
    st.rect(cx + 30, 17, cx + 43, 34, P["white"])
    st.rect(cx + 28, 15, cx + 45, 18, P["dgray"])
    for i in range(3):
        st.rect(cx + 32 + i * 4, 21, cx + 34.4 + i * 4, 24, P["sea_d"])
    st.rect(cx + 34, 8, cx + 38, 15, P["red"])
    st.rect(cx + 34, 8, cx + 38, 9.6, P["ink"])
    for x in range(-4, int(st.W), 9):
        st.line([(x, 47.5), (x + 3, 46), (x + 6, 47.5), (x + 9, 46)], P["sea_l"], 0.8)
    for x in range(2, int(st.W), 13):
        st.line([(x, 54), (x + 4, 52.6), (x + 8, 54)], P["sea_l"], 0.8)


# --------------------------------------------------------------------------
# 3. parliament building
# --------------------------------------------------------------------------
def draw_parliament(d, box, seed=0):
    st = Stage(d, box)
    cx = st.cx
    st.sky()
    st.cloud(st.W * 0.15, 11)
    st.cloud(st.W * 0.86, 9, 0.8)
    st.band(50, 60, P["stone_d"])
    st.rect(cx - 46, 33, cx + 46, 50, P["stone"])
    for i in range(4):
        for side in (-1, 1):
            xa = cx + side * (24 + i * 5.5) - 1.1
            st.rect(xa, 38, xa + 2.2, 44, P["sea_d"])
    st.rect(cx - 46, 31.5, cx + 46, 33, P["stone_d"])
    st.rect(cx - 21, 26, cx + 21, 50, P["stone"])
    st.poly([(cx - 23, 26), (cx + 23, 26), (cx, 18)], P["stone_d"])
    st.poly([(cx - 17, 25), (cx + 17, 25), (cx, 19.5)], P["stone"])
    for i in range(8):
        xa = cx - 18 + i * 5.1
        st.rect(xa, 28, xa + 1.9, 50, P["white"])
    st.rect(cx - 22, 26, cx + 22, 28, P["stone_d"])
    st.rect(cx - 9, 12, cx + 9, 18.5, P["stone_d"])
    st.pie(cx, 12.5, 9, 8, 180, 360, P["blue"])
    st.rect(cx - 1, 1.5, cx + 1, 6, P["stone_d"])
    st.flag(cx, 2.5, 5, P["red"])
    st.rect(cx - 25, 50, cx + 25, 52, P["stone_d"])
    st.rect(cx - 29, 52, cx + 29, 54, P["stone"])
    for x in range(0, int(st.W), 12):
        st.circ(x + 3, 56.5, 2.2, P["grass_d"])


# --------------------------------------------------------------------------
# 4. falling market chart
# --------------------------------------------------------------------------
def draw_market_chart(d, box, seed=0):
    st = Stage(d, box)
    r = _Rng(seed)
    st.rect(0, 0, st.W, 60, (22, 30, 54))
    for y in (10, 22, 34, 46):
        st.line([(0, y), (st.W, y)], (46, 58, 88), 0.4)
    n = max(8, int((st.W - 16) / 8.0))
    for i in range(n):
        x = 8 + i * (st.W - 16) / float(n - 1)
        base = 12 + 30.0 * i / (n - 1)
        jit = (r.frac() - 0.5) * 10
        up = jit < -1.5
        col = P["green"] if up else (226, 64, 64)
        c = base + jit * 0.5
        st.line([(x, c - 6), (x, c + 6)], col, 0.5)
        st.rect(x - 2, c - 3, x + 2, c + 3, col)
    cx = st.cx
    st.line([(cx - 38, 11), (cx - 10, 24), (cx + 4, 21), (cx + 30, 42)], (255, 214, 214), 2.2)
    st.poly([(cx + 36, 50), (cx + 22, 44), (cx + 33, 35)], (255, 214, 214))
    st.rect(0, 52, st.W, 60, (30, 40, 70))
    for x in range(4, int(st.W), 10):
        st.rect(x, 55, x + 5, 58, P["red"] if (x // 10) % 3 else P["lgray"])


# --------------------------------------------------------------------------
# 5. climate summit
# --------------------------------------------------------------------------
def draw_summit(d, box, seed=0):
    st = Stage(d, box)
    cx = st.cx
    st.sky((150, 200, 236), (190, 224, 244), (222, 240, 248))
    st.ell(cx, 62, st.W * 0.7, 14, P["grass"])
    st.band(55, 60, P["grass"])
    for x, k in ((10, 1.0), (st.W - 10, 1.0)):
        st.rect(x - 0.6, 24, x + 0.6, 50, P["white"])
        st.circ(x, 24, 1.2, P["lgray"])
        for ang in ((0, -9), (-8, 5), (8, 5)):
            st.line([(x, 24), (x + ang[0], 24 + ang[1])], P["white"], 1.1)
    st.circ(cx, 21, 13, P["blue"])
    for blob in (((-8, 15), (-3, 12), (-1, 18), (-6, 24), (-10, 21)),
                 ((2, 17), (9, 15), (11, 23), (5, 30), (3, 24))):
        st.poly([(cx + a, b) for a, b in blob], P["green"])
    st.pie(cx, 21, 13, 13, 200, 290, (120, 176, 232))
    st.rect(cx - 3, 34, cx + 3, 46, P["dgray"])
    st.rect(cx - 9, 45, cx + 9, 48, P["slate"])
    cols = [P["red"], P["blue"], P["yellow"], P["green"], P["orange"], P["purple"]]
    for i in range(4):
        st.flag(cx - 24 - i * 9, 44, 17, _pick(cols, i + seed))
        st.flag(cx + 24 + i * 9, 44, 17, _pick(cols, i + 3 + seed))
    for i in range(-5, 6):
        x = cx + i * 7.2
        if abs(i) < 1:
            continue
        st.person(x, 49, 11, _pick([P["navy"], P["dgray"], P["teal"], P["purple"]], i))
    st.rect(cx - 52, 49, cx + 52, 53, P["brown"])
    st.rect(cx - 52, 53, cx + 52, 54.2, P["ink"])


# --------------------------------------------------------------------------
# 6. rescue (helicopter + flood roof)
# --------------------------------------------------------------------------
def draw_rescue(d, box, seed=0):
    st = Stage(d, box)
    cx = st.cx
    st.sky((142, 156, 176), (168, 180, 196), (190, 198, 210))
    st.cloud(st.W * 0.15, 10, 1.0, P["cloud_g"])
    st.cloud(st.W * 0.85, 13, 0.9, P["cloud_g"])
    st.band(44, 60, P["water"])
    st.band(52, 60, P["water_d"])
    for x in range(-4, int(st.W), 11):
        st.line([(x, 47), (x + 3, 45.6), (x + 6, 47)], P["sea_l"], 0.7)
    hx, hy = cx - 4, 16
    st.line([(hx - 22, hy - 7), (hx + 22, hy - 7)], P["ink"], 0.9)
    st.rect(hx - 0.5, hy - 7, hx + 0.5, hy - 4, P["ink"])
    st.ell(hx, hy, 11, 6, P["red"])
    st.rect(hx + 8, hy - 2.5, hx + 24, hy, P["red"])
    st.poly([(hx + 22, hy - 2.5), (hx + 25, hy - 8), (hx + 27, hy - 8), (hx + 25, hy)], P["red"])
    st.ell(hx - 4, hy - 1, 4.4, 3, P["sky_hi"])
    st.line([(hx - 10, hy + 8), (hx + 8, hy + 8)], P["ink"], 0.7)
    st.line([(hx - 6, hy + 5), (hx - 6, hy + 8)], P["ink"], 0.7)
    st.line([(hx + 4, hy + 5), (hx + 4, hy + 8)], P["ink"], 0.7)
    st.line([(hx - 1, hy + 6), (hx - 1, 36)], P["ink"], 0.5)
    st.rect(hx - 2.2, 36, hx + 2.2, 42, P["orange"])
    st.circ(hx, 34.6, 2.0, P["skin"])
    st.rect(hx - 3, 42, hx - 1.4, 46, P["dgray"])
    st.rect(hx + 1.4, 42, hx + 3, 46, P["dgray"])
    rx = cx + 28
    st.poly([(rx - 12, 47), (rx, 36), (rx + 12, 47)], P["brown"])
    st.rect(rx - 9, 47, rx + 9, 50, P["stone_d"])
    st.person(rx + 1, 44, 8, P["yellow"])
    bx = cx - 34
    st.poly([(bx - 9, 48), (bx + 10, 48), (bx + 7, 52), (bx - 6, 52)], P["orange"])
    st.person(bx - 2, 48, 7, P["navy"])
    st.person(bx + 4, 48, 7, P["teal"])


# --------------------------------------------------------------------------
# 7. fire
# --------------------------------------------------------------------------
def draw_fire(d, box, seed=0):
    st = Stage(d, box)
    r = _Rng(seed)
    cx = st.cx
    st.rect(0, 0, st.W, 60, P["night"])
    st.band(30, 60, P["night2"])
    for _ in range(26):
        st.circ(r.frac() * st.W, r.frac() * 24, 0.35, (230, 230, 240))
    for x, k in ((cx + 6, 1.0), (cx + 26, 0.75), (cx - 8, 1.0)):
        st.circ(x, 12 - k * 2, 9 * k, (88, 92, 108))
    st.circ(cx + 18, 7, 8, (70, 74, 90))
    bx = cx - 30
    st.rect(bx, 20, bx + 40, 52, P["dgray"])
    for yy in (24, 32, 40):
        for xx in range(int(bx) + 4, int(bx) + 38, 8):
            lit = ((xx + yy + seed) % 3) != 0
            st.rect(xx, yy, xx + 4, yy + 4, P["orange"] if lit else (44, 48, 60))
    st.flame(bx + 12, 28, 1.3, P["orange"], P["yellow"])
    st.flame(bx + 28, 22, 1.7, P["red"], P["orange"])
    st.flame(bx + 6, 46, 0.9, P["orange"], P["yellow"])
    st.flame(bx + 34, 44, 1.0, P["red"], P["yellow"])
    st.band(52, 60, P["road"])
    tx = cx + 36
    st.rect(tx, 42, tx + 24, 52, P["red"])
    st.rect(tx + 15, 37, tx + 24, 42, P["red"])
    st.rect(tx + 17, 38.5, tx + 22.5, 41, P["sea_l"])
    st.rect(tx + 1, 38, tx + 13, 40, P["lgray"])
    st.circ(tx + 5, 52, 3, P["ink"])
    st.circ(tx + 19, 52, 3, P["ink"])
    st.circ(tx + 5, 52, 1.2, P["lgray"])
    st.circ(tx + 19, 52, 1.2, P["lgray"])
    st.line([(tx + 1, 38), (tx - 8, 33), (tx - 14, 30)], P["sea_l"], 0.8)


# --------------------------------------------------------------------------
# 8. earthquake
# --------------------------------------------------------------------------
def draw_quake(d, box, seed=0):
    st = Stage(d, box)
    cx = st.cx
    st.sky((230, 200, 160), (240, 218, 182), (246, 232, 204))
    st.circ(st.W * 0.84, 16, 6, (252, 236, 190))
    for x in range(0, int(st.W), 15):
        st.rect(x, 34 - (x * 7) % 11, x + 12, 50, P["stone_d"])
    st.band(50, 60, P["ground"])
    st.poly([(cx - 3, 50), (cx + 3, 50), (cx + 1, 54), (cx + 5, 57), (cx + 2, 60), (cx - 4, 60),
             (cx - 1, 56), (cx - 4, 53)], P["ink"])
    st.poly([(cx - 40, 50), (cx - 24, 50), (cx - 28, 22), (cx - 44, 24)], P["slate"])
    for yy in (28, 35, 42):
        st.poly([(cx - 41 - (50 - yy) * 0.08, yy), (cx - 37 - (50 - yy) * 0.08, yy),
                 (cx - 37 - (50 - yy) * 0.08, yy + 3), (cx - 41 - (50 - yy) * 0.08, yy + 3)], P["win"])
    st.poly([(cx + 8, 50), (cx + 30, 50), (cx + 34, 26), (cx + 14, 30)], P["steel"])
    st.line([(cx + 16, 31), (cx + 22, 40), (cx + 18, 50)], P["ink"], 0.6)
    st.poly([(cx + 34, 50), (cx + 46, 50), (cx + 42, 44), (cx + 38, 47)], P["stone_d"])
    for k in range(7):
        bx = cx - 18 + k * 4.2
        st.rect(bx, 47.5 - (k % 3), bx + 3, 50, _pick([P["stone_d"], P["dgray"], P["brown"]], k))
    for x, y, k in ((cx - 14, 46, 1.0), (cx + 40, 48, 0.8), (cx - 48, 47, 0.8)):
        st.circ(x, y, 4.5 * k, (222, 210, 190))
        st.circ(x + 4 * k, y + 1, 3.5 * k, (232, 222, 204))
    st.rect(3, 3, 74, 21, P["white"], P["ink"], 0.4)
    pts = []
    for i in range(0, 69):
        amp = 1.0 + 7.0 * (1 - abs(i - 38) / 38.0) if abs(i - 38) < 38 else 1.0
        pts.append((5 + i, 12 + amp * (1 if i % 2 else -1) * (0.4 + 0.6 * ((i * 7) % 5) / 4.0)))
    st.line(pts, P["red"], 0.6)
    st.line([(4.5, 12), (73, 12)], P["lgray"], 0.3)


# --------------------------------------------------------------------------
# 9. ballot box
# --------------------------------------------------------------------------
def draw_ballot(d, box, seed=0):
    st = Stage(d, box)
    cx = st.cx
    st.rect(0, 0, st.W, 60, (214, 228, 246))
    for x in range(0, int(st.W), 12):
        st.rect(x, 0, x + 6, 60, (222, 235, 250))
    st.band(50, 60, P["slate"])
    st.rect(cx - 6.5, 6, cx + 6.5, 28, P["white"], P["ink"], 0.4)
    for yy in (10, 13, 16):
        st.line([(cx - 4, yy), (cx + 1, yy)], P["lgray"], 0.8)
    st.line([(cx - 3.5, 22), (cx - 1.4, 24.6), (cx + 3.6, 18.4)], P["green"], 1.5)
    st.rect(cx - 19, 28, cx + 19, 52, P["blue"])
    st.rect(cx - 21, 24, cx + 21, 28.5, P["navy"])
    st.rect(cx - 9, 25.4, cx + 9, 27, P["ink"])
    st.circ(cx, 40, 6, P["white"])
    st.line([(cx - 3, 40), (cx - 1, 42.5), (cx + 3.4, 37)], P["blue"], 1.4)
    for side in (-1, 1):
        for i in range(3):
            x = cx + side * (34 + i * 9)
            st.person(x, 50, 14 - i, _pick([P["red"], P["orange"], P["navy"], P["teal"]], i + side + seed))
    for x in range(6, int(st.W), 22):
        st.poly([(x, 8), (x + 1.3, 11), (x + 4.4, 11), (x + 2, 13), (x + 3, 16), (x, 14),
                 (x - 3, 16), (x - 2, 13), (x - 4.4, 11), (x - 1.3, 11)], P["yellow"])


# --------------------------------------------------------------------------
# 10. stadium
# --------------------------------------------------------------------------
def draw_stadium(d, box, seed=0):
    st = Stage(d, box)
    r = _Rng(seed)
    cx = st.cx
    st.sky((120, 170, 224), (156, 200, 238), (190, 220, 242))
    st.rect(0, 20, st.W, 42, P["dgray"])
    st.rect(0, 16, st.W, 20, P["white"])
    crowd = [P["red"], P["yellow"], P["blue"], P["white"], P["orange"], P["green"]]
    for row, y in enumerate((23, 27.5, 32, 36.5)):
        for x in range(2, int(st.W), 4):
            st.circ(x + (row % 2) * 2, y, 1.1, _pick(crowd, r.below(6)))
    st.band(42, 60, P["grass"])
    for i, x in enumerate(range(-6, int(st.W) + 8, 14)):
        if i % 2:
            st.poly([(x, 42), (x + 14, 42), (x + 20, 60), (x + 6, 60)], P["grass_d"])
    st.ell(cx, 52, 20, 5.5, None, P["white"], 0.5)
    st.line([(cx, 46.5), (cx, 57.5)], P["white"], 0.5)
    st.circ(cx, 52, 2.5, P["white"])
    st.rect(cx - 15, 3, cx + 15, 14, P["ink"])
    for i in range(5):
        st.rect(cx - 12 + i * 5.2, 5.5, cx - 8.6 + i * 5.2, 11.5, P["yellow"] if i % 2 else P["orange"])
    for x in (8, st.W - 8):
        st.rect(x - 0.7, 8, x + 0.7, 42, P["lgray"])
        st.rect(x - 5, 3, x + 5, 9, P["dgray"])
        for k in range(3):
            st.circ(x - 3 + k * 3, 6, 1.1, P["yellow"])
    st.circ(cx + 12, 49, 2.4, P["white"], P["ink"], 0.3)


# --------------------------------------------------------------------------
# 11. laboratory
# --------------------------------------------------------------------------
def draw_lab(d, box, seed=0):
    st = Stage(d, box)
    cx = st.cx
    st.rect(0, 0, st.W, 60, (212, 236, 238))
    for x in range(0, int(st.W), 10):
        st.line([(x, 0), (x, 46)], (194, 224, 228), 0.3)
    for y in range(0, 46, 10):
        st.line([(0, y), (st.W, y)], (194, 224, 228), 0.3)
    st.band(46, 60, P["brown"])
    st.rect(0, 46, st.W, 48, (176, 126, 84))
    mx = cx - 40
    st.rect(mx - 8, 43, mx + 9, 46, P["dgray"])
    st.poly([(mx + 4, 43), (mx + 8, 43), (mx + 8, 24), (mx + 3, 20), (mx - 1, 22)], P["slate"])
    st.poly([(mx - 7, 12), (mx - 3, 10), (mx + 3, 28), (mx - 1, 30)], P["dgray"])
    st.rect(mx - 6, 33, mx + 2, 35, P["steel"])
    st.circ(mx - 8, 10, 1.8, P["lgray"])
    st.circ(cx, 33, 8, (230, 244, 250), P["ink"], 0.5)
    st.rect(cx - 2.2, 20, cx + 2.2, 27, (230, 244, 250), P["ink"], 0.5)
    st.pie(cx, 33, 7.6, 7.6, 0, 180, P["green"])
    for bx, by, br in ((cx - 2, 31, 1.1), (cx + 2.4, 29, 0.8), (cx + 0.4, 27, 0.7)):
        st.circ(bx, by, br, (210, 246, 220))
    fx = cx + 20
    st.poly([(fx - 2, 26), (fx + 2, 26), (fx + 8, 45), (fx - 8, 45)], (230, 244, 250), P["ink"])
    st.poly([(fx - 5.4, 36), (fx + 5.4, 36), (fx + 8, 45), (fx - 8, 45)], P["purple"])
    st.rect(fx - 2.6, 23.5, fx + 2.6, 26, P["lgray"])
    rx = cx + 46
    st.rect(rx - 12, 38, rx + 12, 39.4, P["dgray"])
    for i, col in enumerate((P["red"], P["blue"], P["yellow"], P["green"])):
        tx = rx - 9 + i * 6
        st.rect(tx - 1.6, 28, tx + 1.6, 44, (232, 244, 250), P["ink"], 0.3)
        st.rect(tx - 1.4, 34 + (i % 2) * 2, tx + 1.4, 43.8, col)
    for i in range(14):
        t = i / 13.0
        y = 6 + 3.2 * i
        if y > 24:
            break
        st.line([(rx - 8 + 7 * ((i % 2) * 2 - 1) * 0.8, y), (rx - 8 + 7 * (((i + 1) % 2) * 2 - 1) * 0.8, y)],
                P["pink"], 0.5)
    st.line([(rx - 8 - 5, 4), (rx - 8, 10), (rx - 8 + 5, 16), (rx - 8, 22)], P["blue"], 0.7)
    st.line([(rx - 8 + 5, 4), (rx - 8, 10), (rx - 8 - 5, 16), (rx - 8, 22)], P["red"], 0.7)


# --------------------------------------------------------------------------
# 12. flood / storm
# --------------------------------------------------------------------------
def draw_flood(d, box, seed=0):
    st = Stage(d, box)
    r = _Rng(seed)
    cx = st.cx
    st.sky((96, 108, 130), (124, 136, 156), (156, 166, 182))
    for x in range(0, int(st.W), 22):
        st.cloud(x + 8, 9 + (x % 3) * 2, 1.3, P["storm"])
    for _ in range(40):
        x = r.frac() * st.W
        y = 14 + r.frac() * 30
        st.line([(x, y), (x - 1.6, y + 5)], (206, 222, 238), 0.4)
    for i, (x, w, hh) in enumerate(((cx - 40, 16, 12), (cx - 8, 20, 15), (cx + 28, 16, 11))):
        st.rect(x, 40 - hh, x + w, 52, _pick([P["stone"], P["pink"], P["lgray"]], i))
        st.poly([(x - 2, 40 - hh), (x + w / 2, 33 - hh), (x + w + 2, 40 - hh)], P["brown"])
        st.rect(x + w / 2 - 2, 42 - hh + 3, x + w / 2 + 2, 42 - hh + 8, P["win"])
    st.rect(cx + 52, 24, cx + 54, 46, P["brown"])
    st.circ(cx + 53, 22, 7, P["grass_d"])
    st.band(42, 60, P["water"])
    st.band(50, 60, P["water_d"])
    for x in range(-3, int(st.W), 9):
        st.line([(x, 45), (x + 3, 43.6), (x + 6, 45), (x + 9, 43.6)], P["sea_l"], 0.7)
    for x in range(1, int(st.W), 12):
        st.line([(x, 53), (x + 4, 51.6), (x + 8, 53)], P["sea_l"], 0.7)
    st.poly([(cx - 20, 48), (cx - 4, 48), (cx - 7, 52), (cx - 17, 52)], P["orange"])
    st.person(cx - 12, 48, 7, P["navy"])


# --------------------------------------------------------------------------
# 13. airport / plane
# --------------------------------------------------------------------------
def draw_plane(d, box, seed=0):
    st = Stage(d, box)
    cx = st.cx
    st.sky((110, 168, 226), (150, 198, 238), (196, 224, 244))
    st.cloud(st.W * 0.2, 14, 1.1)
    st.cloud(st.W * 0.78, 24, 0.8)
    st.band(46, 60, P["grass"])
    st.poly([(0, 60), (st.W, 60), (st.W * 0.72, 46), (st.W * 0.28, 46)], P["road"])
    for i in range(5):
        y0 = 48 + i * 2.8
        w = 0.7 + i * 0.5
        st.rect(cx - w, y0, cx + w, y0 + 1.6 + i * 0.4, P["white"])
    tx = 12
    st.rect(tx - 2, 24, tx + 2, 46, P["lgray"])
    st.rect(tx - 7, 16, tx + 7, 24, P["steel"])
    st.rect(tx - 6, 18, tx + 6, 21.5, P["sea_l"])
    st.rect(tx - 8, 14.5, tx + 8, 16.4, P["dgray"])
    px, py = cx + 4, 25
    st.line([(px - 36, py + 14), (px - 8, py + 5)], (230, 238, 246), 1.6)
    st.ell(px, py, 24, 4.2, P["white"], P["lgray"], 0.4)
    st.poly([(px + 22, py - 1), (px + 30, py - 1.2), (px + 24, py + 2)], P["white"])
    st.poly([(px - 20, py - 1), (px - 25, py - 11), (px - 21.5, py - 11), (px - 13, py - 1)], P["blue"])
    st.poly([(px - 3, py + 2), (px + 10, py + 2), (px - 8, py + 14), (px - 14, py + 14)], P["steel"])
    st.poly([(px - 3, py - 2), (px + 8, py - 2), (px - 7, py - 10), (px - 12, py - 10)], P["lgray"])
    st.ell(px - 6, py + 6.5, 2.4, 1.3, P["dgray"])
    for i in range(9):
        st.circ(px - 14 + i * 3.4, py - 0.4, 0.55, P["sea_d"])


# --------------------------------------------------------------------------
# 14. energy (cooling towers, pylons, wind)
# --------------------------------------------------------------------------
def draw_energy(d, box, seed=0):
    st = Stage(d, box)
    cx = st.cx
    st.sky((142, 190, 232), (176, 212, 240), (208, 230, 246))
    st.circ(st.W * 0.1, 14, 5.5, P["sun"])
    st.ell(cx, 66, st.W * 0.65, 18, P["grass"])
    st.band(50, 60, P["grass_d"])
    for k, x in enumerate((cx - 22, cx + 4)):
        st.poly([(x - 9, 52), (x - 6, 32), (x - 7, 22), (x + 7, 22), (x + 6, 32), (x + 9, 52)], P["lgray"])
        st.rect(x - 7, 21, x + 7, 23, P["steel"])
        st.circ(x + 1, 17 - k * 1.5, 6, P["white"])
        st.circ(x + 7, 12 - k * 2, 5, (238, 242, 248))
    st.rect(cx + 20, 28, cx + 38, 52, P["slate"])
    st.rect(cx + 24, 14, cx + 27, 28, P["dgray"])
    st.rect(cx + 24, 14, cx + 27, 16, P["red"])
    st.circ(cx + 26, 10, 3.6, P["cloud_g"])
    for i in range(3):
        st.rect(cx + 22 + i * 5, 34, cx + 25 + i * 5, 39, P["win"])
    for x in (cx - 50, cx - 62):
        st.line([(x, 52), (x + 2.5, 30), (x + 5, 52)], P["dgray"], 0.8)
        st.line([(x - 3, 34), (x + 8, 34)], P["dgray"], 0.8)
        st.line([(x - 2, 38), (x + 7, 38)], P["dgray"], 0.8)
    st.line([(cx - 53, 34), (cx - 65, 34)], P["dgray"], 0.3)
    for x in (cx + 54, cx + 70):
        st.rect(x - 0.6, 26, x + 0.6, 52, P["white"])
        for a in ((0, -9), (-8, 5), (8, 5)):
            st.line([(x, 26), (x + a[0], 26 + a[1])], P["white"], 1.0)
        st.circ(x, 26, 1.3, P["lgray"])
    st.band(52, 60, P["road"])


# --------------------------------------------------------------------------
# 15. space launch
# --------------------------------------------------------------------------
def draw_space(d, box, seed=0):
    st = Stage(d, box)
    r = _Rng(seed)
    cx = st.cx
    st.rect(0, 0, st.W, 60, (12, 16, 40))
    st.band(30, 60, (20, 26, 62))
    for _ in range(46):
        st.circ(r.frac() * st.W, r.frac() * 40, 0.3 + r.frac() * 0.3, (236, 236, 250))
    big_r = max(90.0, st.W * 0.75)             # horizon arc: a polygon, so nothing is clamped
    for rr, col, top in ((big_r, P["blue"], 45.0), (big_r - 3.5, (60, 130, 214), 48.5)):
        mid = top + rr
        arc = [(0.0, 60.0)]
        xx = 0.0
        while xx <= st.W:
            dx = xx - cx
            arc.append((xx, mid - (max(0.0, rr * rr - dx * dx)) ** 0.5))
            xx += 3.0
        arc += [(st.W, mid - (max(0.0, rr * rr - (st.W - cx) ** 2)) ** 0.5), (st.W, 60.0)]
        st.poly(arc, col)
    for blob in (((-30, 52), (-18, 50), (-14, 54), (-26, 57)), ((6, 50.5), (20, 50), (26, 55), (10, 54))):
        st.poly([(cx + a, b) for a, b in blob], P["green"])
    st.rect(cx - 3.5, 8, cx + 3.5, 38, P["white"], P["lgray"], 0.3)
    st.poly([(cx - 3.5, 8), (cx + 3.5, 8), (cx, -1)], P["red"])
    st.poly([(cx - 3.5, 30), (cx - 8, 40), (cx - 3.5, 38)], P["red"])
    st.poly([(cx + 3.5, 30), (cx + 8, 40), (cx + 3.5, 38)], P["red"])
    st.circ(cx, 16, 1.9, P["sea_l"], P["dgray"], 0.4)
    st.rect(cx - 3.5, 24, cx + 3.5, 25.5, P["dgray"])
    st.poly([(cx - 3, 38), (cx + 3, 38), (cx + 1.6, 52), (cx, 58), (cx - 1.6, 52)], P["orange"])
    st.poly([(cx - 1.6, 38), (cx + 1.6, 38), (cx, 50)], P["yellow"])
    for x, y, k in ((cx - 10, 52, 1.0), (cx + 9, 53, 1.1), (cx - 1, 57, 1.3)):
        st.circ(x, y, 4 * k, (220, 224, 236))
    st.rect(cx - 44, 22, cx - 40, 52, P["dgray"])
    st.rect(cx - 49, 22, cx - 40, 24, P["steel"])


# --------------------------------------------------------------------------
# 16. hospital / health
# --------------------------------------------------------------------------
def draw_hospital(d, box, seed=0):
    st = Stage(d, box)
    cx = st.cx
    st.sky((196, 226, 242), (214, 236, 246), (230, 244, 250))
    st.cloud(st.W * 0.12, 11, 0.9)
    st.band(52, 60, P["road"])
    st.rect(cx - 30, 14, cx + 22, 52, P["white"], P["lgray"], 0.4)
    st.rect(cx - 36, 28, cx - 30, 52, P["lgray"])
    for yy in (19, 29, 39):
        for i in range(5):
            xa = cx - 25 + i * 9.6
            st.rect(xa, yy, xa + 5, yy + 5, P["sea_l"])
    st.rect(cx - 4, 44, cx + 4, 52, P["sea_d"])
    st.rect(cx - 5, 6, cx + 5, 14, P["white"], P["lgray"], 0.4)
    st.rect(cx - 1, 7, cx + 1, 13, P["red"])
    st.rect(cx - 3.6, 9.2, cx + 3.6, 10.8, P["red"])
    ax = cx + 36
    st.rrect(ax, 38, ax + 30, 52, 1.5, P["white"])
    st.rect(ax + 19, 33, ax + 30, 40, P["white"])
    st.rect(ax, 43, ax + 30, 45, P["red"])
    st.rect(ax + 21, 35, ax + 28, 38.5, P["sea_l"])
    st.rect(ax + 11.5, 40.2, ax + 12.8, 44.4, P["red"])
    st.rect(ax + 9.6, 41.8, ax + 14.7, 43, P["red"])
    st.circ(ax + 6, 52, 3, P["ink"])
    st.circ(ax + 24, 52, 3, P["ink"])
    st.circ(ax + 6, 52, 1.2, P["lgray"])
    st.circ(ax + 24, 52, 1.2, P["lgray"])
    st.rect(ax + 12, 31, ax + 17, 33, P["blue"])
    st.person(cx - 44, 52, 11, P["teal"])
    st.person(cx - 52, 52, 11, P["blue"])


# --------------------------------------------------------------------------
# registry
# --------------------------------------------------------------------------
SCENES = {
    "skyline": draw_skyline, "ship": draw_ship, "parliament": draw_parliament,
    "market_chart": draw_market_chart, "summit": draw_summit, "rescue": draw_rescue,
    "fire": draw_fire, "quake": draw_quake, "ballot": draw_ballot,
    "stadium": draw_stadium, "lab": draw_lab, "flood": draw_flood,
    "plane": draw_plane, "energy": draw_energy, "space": draw_space,
    "hospital": draw_hospital,
}

_ALIASES = {
    "market": "market_chart", "chart": "market_chart", "economy": "market_chart",
    "stocks": "market_chart", "finance": "market_chart", "crash": "market_chart",
    "climate": "summit", "diplomacy": "summit", "talks": "summit", "un": "summit",
    "government": "parliament", "politics": "parliament", "law": "parliament",
    "election": "ballot", "vote": "ballot", "poll": "ballot",
    "sport": "stadium", "sports": "stadium", "football": "stadium", "soccer": "stadium",
    "science": "lab", "research": "lab", "tech": "lab", "laboratory": "lab",
    "earthquake": "quake", "disaster": "rescue", "wildfire": "fire", "blaze": "fire",
    "city": "skyline", "urban": "skyline", "port": "ship", "shipping": "ship",
    "sea": "ship", "flight": "plane", "aviation": "plane", "airport": "plane",
    "power": "energy", "oil": "energy", "gas": "energy", "launch": "space",
    "rocket": "space", "medical": "hospital", "health": "hospital",
    "rain": "flood", "storm": "flood", "weather": "flood",
}


def get_scene(name):
    """Resolve a scene name / alias / 'draw_xxx' to a drawing function."""
    key = str(name or "").strip().lower().replace("-", "_").replace(" ", "_")
    if key.startswith("draw_"):
        key = key[5:]
    key = _ALIASES.get(key, key)
    return SCENES.get(key, draw_skyline)


def draw_scene(d, box, name, seed=0):
    """Draw the named scene into `box` of an existing ImageDraw."""
    get_scene(name)(d, box, seed)


def render_scene(name, width, height, seed=0, ss=3):
    """Return an anti-aliased RGB image (width x height) of the named scene.

    The scene is drawn at `ss` x resolution on its own canvas and then reduced,
    so nothing can spill outside the requested rectangle."""
    width, height, ss = int(width), int(height), max(1, int(ss))
    big = Image.new("RGB", (width * ss, height * ss), P["sky"])
    get_scene(name)(ImageDraw.Draw(big), (0, 0, width * ss, height * ss), seed)
    return big.resize((width, height), _RESAMPLE) if ss > 1 else big


if __name__ == "__main__":      # contact sheet of every scene (quick visual check)
    names = list(SCENES)
    cw, ch, cols = 240, 56, 4
    rows = (len(names) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (cw + 6) + 6, rows * (ch + 6) + 6), (240, 236, 224))
    for i, n in enumerate(names):
        sheet.paste(render_scene(n, cw, ch, seed=i + 1), (6 + (i % cols) * (cw + 6), 6 + (i // cols) * (ch + 6)))
    sheet.save("scene_sheet.png")
    print("wrote scene_sheet.png with", len(names), "scenes")
