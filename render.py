#!/usr/bin/env python3
"""
render_v2.py - one-page newspaper image, 1024 x 1024 PNG, Pillow only.

    render_page(stories, date_str, numbers, timeline, out_items, out_path)

stories    list of dicts with the fields
               number, kicker, headline, deck, tag, source, scene, pin_x, pin_y
           * stories that have a `scene` become illustrated cards (first 15);
             all other stories become numbered one-liners after the cards.
             The page is designed for 13-15 cards and 30-41 stories in total.
           * tag   : CONFIRMED | OFFICIAL | REPORTED | CLAIM
           * scene : a name from scene_kit.SCENES (aliases such as "market",
                     "climate", "election", "science" are understood)
           * pin_x, pin_y : where the card's pin goes on the world map.  Either
                     longitude / latitude in degrees (e.g. 139.7, 35.7) or map
                     fractions 0..1 (x west->east, y north->south) when both
                     values lie inside 0..1.  lonlat_to_pin() converts.
date_str   e.g. "Wednesday 25 November 2026"
numbers    4-6 items for the "Day in Numbers" strip: (value, label) pairs
timeline   items (utc_time, text) or (utc_time, text, story_number), utc_time
           being "HH:MM" (or a float hour)
out_items  strings listing old news that was deliberately excluded

Every piece of text is measured with Pillow's own metrics (getlength/getbbox)
and wrapped, shrunk or ellipsized to fit its box, and a final ledger check
verifies that no two text runs overlap and nothing leaves the canvas.  The
program is deterministic: same input -> byte-identical PNG.
"""
import math
import os
import re
import sys

from PIL import Image, ImageDraw, ImageFont

import scene_kit

# ---------------------------------------------------------------- constants
W = H = 1024
SS = 3                                   # supersampling for drawn shapes
MAX_CARDS = 15
PNG_LIMIT = 1024 * 1024
RESAMPLE = getattr(Image, "Resampling", Image).LANCZOS

PAPER = (247, 243, 232)
CARD_BG = (255, 252, 244)
INK = (24, 24, 28)
RED = (190, 28, 36)
WHITE = (255, 255, 255)
GRAY = (92, 92, 98)
DECK = (52, 52, 58)
YELLOW = (255, 205, 70)
OCEAN = (186, 214, 232)
GRID = (166, 196, 218)
LAND = (222, 212, 186)
COAST = (150, 138, 110)

TAG_COL = {"CONFIRMED": (28, 120, 64), "OFFICIAL": (30, 78, 160),
           "REPORTED": (168, 98, 0), "CLAIM": (140, 36, 110)}

# page grid -----------------------------------------------------------------
MX0, MX1 = 12, 1012
MAST = (10, 134)
INFO = (140, 208)
ROW3 = (214, 338)
CARDS = (344, 804)
ONE = (810, 976)
FOOT = (980, 1012)
LEFT_W = 312                              # width of the left column (date check / map)
GAP = 6
DATE_MIN_INK = 102                        # px height of the day numeral (>= 100)

TITLE_LINES = ("THE WORLD", "IN ONE PAGE")


# ------------------------------------------------------------------- fonts
_FONT_PATHS = {
    "serif_bold": ["/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf", "DejaVuSerif-Bold.ttf",
                   "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf", "LiberationSerif-Bold.ttf",
                   "/usr/share/fonts/truetype/freefont/FreeSerifBold.ttf",
                   "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf", "C:/Windows/Fonts/timesbd.ttf"],
    "sans_bold": ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "DejaVuSans-Bold.ttf",
                  "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", "LiberationSans-Bold.ttf",
                  "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "C:/Windows/Fonts/arialbd.ttf"],
    "sans": ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "DejaVuSans.ttf",
             "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", "LiberationSans-Regular.ttf",
             "/System/Library/Fonts/Supplemental/Arial.ttf", "C:/Windows/Fonts/arial.ttf"],
    "cond_bold": ["/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf", "DejaVuSansCondensed-Bold.ttf",
                  "/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Bold.ttf",
                  "/System/Library/Fonts/Supplemental/Arial Narrow Bold.ttf", "C:/Windows/Fonts/arialnb.ttf"],
    "cond": ["/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf", "DejaVuSansCondensed.ttf",
             "/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Regular.ttf",
             "/System/Library/Fonts/Supplemental/Arial Narrow.ttf", "C:/Windows/Fonts/arialn.ttf"],
    "cond_italic": ["/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Oblique.ttf",
                    "DejaVuSansCondensed-Oblique.ttf",
                    "/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Italic.ttf"],
}
# role -> [(file family, fake_bold)] in order of preference
_CHAIN = {
    "title": [("serif_bold", False), ("sans_bold", False), ("sans", True)],
    "heavy": [("sans_bold", False), ("cond_bold", False), ("sans", True)],
    "bold": [("cond_bold", False), ("sans_bold", False), ("cond", True), ("sans", True)],
    "reg": [("cond", False), ("sans", False)],
    "ital": [("cond_italic", False), ("cond", False), ("sans", False)],
}
_resolved = {}
_faces = {}


class Face:
    """A font plus the metrics the layout code needs."""

    def __init__(self, font, fake=False):
        self.font = font
        self.fake = fake
        self.anchored = isinstance(font, ImageFont.FreeTypeFont)
        try:
            self.asc, self.desc = font.getmetrics()
        except Exception:
            bb = font.getbbox("Ag")
            self.asc, self.desc = bb[3], 1
        self.lh = self.asc + self.desc                 # line pitch: ink never touches the next line

    def width(self, s):
        return float(self.font.getlength(s)) + (1.0 if (self.fake and s) else 0.0)

    def bbox(self, s):
        """Ink box of `s` relative to the point it is drawn at (anchor 'la')."""
        bb = self.font.getbbox(s, anchor="la") if self.anchored else self.font.getbbox(s)
        return bb[0], bb[1], bb[2] + (1 if self.fake else 0), bb[3]


def _resolve(role):
    if role in _resolved:
        return _resolved[role]
    found = None
    for fam, fake in _CHAIN[role]:
        for p in _FONT_PATHS[fam]:
            try:
                ImageFont.truetype(p, 10)
                found = (p, fake)
                break
            except (OSError, IOError):
                continue
        if found:
            break
    _resolved[role] = found
    return found


def get_face(role, size):
    key = (role, int(size))
    if key not in _faces:
        res = _resolve(role)
        if res:
            _faces[key] = Face(ImageFont.truetype(res[0], int(size)), res[1])
        else:                                          # last resort: Pillow's built-in font
            try:
                _faces[key] = Face(ImageFont.load_default(int(size)), role in ("title", "heavy", "bold"))
            except TypeError:
                _faces[key] = Face(ImageFont.load_default(), False)
    return _faces[key]


# ------------------------------------------------------- text fitting tools
def ellipsize(s, face, max_w, force=False):
    s = str(s)
    if not force and face.width(s) <= max_w:
        return s
    s = s.rstrip()
    while s and face.width(s + "...") > max_w:
        s = s[:-1].rstrip()
    return s + "..." if face.width(s + "...") <= max_w else ""


def wrap_text(text, face, max_w, max_lines=None):
    """Greedy word wrap measured with the font.  Returns (lines, truncated)."""
    lines, cur = [], ""
    for word in str(text).split():
        while face.width(word) > max_w and len(word) > 1:      # break an over-long word
            k = len(word)
            while k > 1 and face.width(word[:k]) > max_w:
                k -= 1
            if cur:
                lines.append(cur)
                cur = ""
            lines.append(word[:k])
            word = word[k:]
        trial = (cur + " " + word).strip()
        if face.width(trial) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    if max_lines is not None and len(lines) > max_lines:
        if max_lines <= 0:
            return [], True
        lines = lines[:max_lines]
        lines[-1] = ellipsize(lines[-1], face, max_w, force=True)
        return lines, True
    return lines, False


def fit_face(role, text, max_w, sizes):
    """Largest size (iterating `sizes` in order) whose one-line width fits."""
    face = None
    for sz in sizes:
        face = get_face(role, sz)
        if face.width(text) <= max_w:
            return face
    return face


def aa_circle(img, cx, cy, r, fill, k=4):
    """Anti-aliased filled circle (drawn on a k-times mask, then reduced)."""
    pad = 2
    size = int(math.ceil(2 * r)) + 2 * pad + 2
    ox = int(math.floor(cx - r)) - pad
    oy = int(math.floor(cy - r)) - pad
    mask = Image.new("L", (size * k, size * k), 0)
    ImageDraw.Draw(mask).ellipse([(cx - r - ox) * k, (cy - r - oy) * k,
                                  (cx + r - ox) * k, (cy + r - oy) * k], fill=255)
    img.paste(fill, (ox, oy), mask.resize((size, size), RESAMPLE))


# ----------------------------------------------------------------- the page
class Page:
    def __init__(self):
        self.img = Image.new("RGB", (W, H), PAPER)
        self.d = ImageDraw.Draw(self.img)
        self.boxes = []                                # ink box of every text run drawn

    def text(self, x, y, s, face, fill, align="l", max_w=None):
        """Draw one line; (x, y) is the left/centre/right top of the line box."""
        s = str(s)
        if max_w is not None:
            s = ellipsize(s, face, max_w)
        if not s:
            return 0.0
        w = face.width(s)
        if align == "r":
            x -= w
        elif align == "c":
            x -= w / 2.0
        x, y = int(round(x)), int(round(y))
        bx0, by0, bx1, by1 = face.bbox(s)
        kw = {"anchor": "la"} if face.anchored else {}
        self.d.text((x, y), s, font=face.font, fill=fill, **kw)
        if face.fake:
            self.d.text((x + 1, y), s, font=face.font, fill=fill, **kw)
        self.boxes.append((x + bx0, y + by0, x + bx1, y + by1, s))
        return w

    def text_in(self, cx, cy, s, face, fill):
        """Draw `s` with its ink centred on (cx, cy)."""
        bx0, by0, bx1, by1 = face.bbox(str(s))
        self.text(cx - (bx0 + bx1) / 2.0, cy - (by0 + by1) / 2.0, s, face, fill)


def check_layout(boxes, margin=4):
    """Return a list of problems: text outside the canvas or text over text."""
    problems = []
    for (a0, b0, a1, b1, t) in boxes:
        if a0 < margin or b0 < margin or a1 > W - margin or b1 > H - margin:
            problems.append("outside canvas: %r" % t)
    n = len(boxes)
    for i in range(n):
        a = boxes[i]
        for j in range(i + 1, n):
            b = boxes[j]
            if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
                problems.append("overlap: %r / %r" % (a[4], b[4]))
    return problems


# --------------------------------------------------------------- masthead
def split_date(date_str):
    toks = str(date_str).replace(",", " ").split()
    for i, t in enumerate(toks):
        if t.isdigit() and len(t) <= 2:
            return " ".join(toks[:i]).upper(), t, " ".join(toks[i + 1:]).upper()
    return None


def draw_masthead(pg, date_str, n_stories):
    d = pg.d
    y0, y1 = MAST
    mh = y1 - y0
    parts = split_date(date_str)
    if parts is None:                                  # unparseable date: show it whole
        bw = 470
        d.rectangle([MX0, y0, MX0 + bw - 1, y1 - 1], fill=INK)
        f = fit_face("heavy", str(date_str).upper(), bw - 24, range(70, 11, -1))
        pg.text(MX0 + bw / 2.0, y0 + (mh - f.lh) // 2, str(date_str).upper(), f, WHITE, "c", bw - 24)
        block_x1 = MX0 + bw
    else:
        weekday, day, rest = parts
        size = 40                                      # smallest font whose day numeral is >= 102 px tall
        nf = get_face("heavy", size)
        bb = nf.bbox(day)
        while bb[3] - bb[1] < DATE_MIN_INK and size < 260:
            size += 1
            nf = get_face("heavy", size)
            bb = nf.bbox(day)
        while bb[3] - bb[1] > mh - 10 and size > 20:
            size -= 1
            nf = get_face("heavy", size)
            bb = nf.bbox(day)
        ink_h, ink_w = bb[3] - bb[1], bb[2] - bb[0]
        top_ink = y0 + (mh - ink_h) // 2
        bot_ink = top_ink + ink_h
        if weekday:
            line_a, line_b = weekday, rest
        else:
            toks = rest.split()
            line_a, line_b = (toks[0] if toks else ""), " ".join(toks[1:])
        pad = 14
        col_w = 212
        fa = fit_face("heavy", line_a, col_w, range(40, 9, -1))
        fb = fit_face("heavy", line_b, col_w, range(40, 9, -1))
        col_w = int(math.ceil(max(fa.width(line_a), fb.width(line_b)))) + 1
        col_x = MX0 + pad + int(ink_w) + 16
        block_x1 = col_x + col_w + pad
        d.rectangle([MX0, y0, block_x1 - 1, y1 - 1], fill=INK)
        pg.text(MX0 + pad - bb[0], top_ink - bb[1], day, nf, PAPER)
        ba, bb2 = fa.bbox(line_a), fb.bbox(line_b)
        pg.text(col_x, top_ink - ba[1], line_a, fa, YELLOW, max_w=col_w)
        pg.text(col_x, bot_ink - bb2[3], line_b, fb, YELLOW, max_w=col_w)
        mid = (top_ink + (ba[3] - ba[1]) + bot_ink - (bb2[3] - bb2[1])) // 2
        d.rectangle([col_x, mid - 1, col_x + col_w - 1, mid], fill=YELLOW)

    # title block ------------------------------------------------------
    x_t0, x_t1 = block_x1 + 14, MX1
    tw = x_t1 - x_t0
    d.rectangle([x_t0, y0, x_t1 - 1, y0 + 2], fill=INK)
    d.rectangle([x_t0, y1 - 3, x_t1 - 1, y1 - 1], fill=INK)
    tf = get_face("bold", 9)
    tag_y = y1 - 3 - 4 - tf.lh
    rule_y = tag_y - 4
    d.line([(x_t0, rule_y), (x_t1 - 1, rule_y)], fill=INK, width=1)
    pg.text((x_t0 + x_t1) / 2.0, tag_y,
            "DAILY DIGEST  |  %d STORIES  |  ALL TIMES UTC" % n_stories, tf, RED, "c", tw)
    r_top, r_bot = y0 + 3 + 5, rule_y - 5
    for size in range(72, 13, -1):
        f = get_face("title", size)
        b1, b2 = f.bbox(TITLE_LINES[0]), f.bbox(TITLE_LINES[1])
        gap = max(6, size // 7)
        h1, h2 = b1[3] - b1[1], b2[3] - b2[1]
        if (max(f.width(TITLE_LINES[0]), f.width(TITLE_LINES[1])) <= tw - 12
                and h1 + gap + h2 <= r_bot - r_top):
            break
    ink_top = r_top + (r_bot - r_top - (h1 + gap + h2)) // 2
    cx = (x_t0 + x_t1) / 2.0
    pg.text(cx, ink_top - b1[1], TITLE_LINES[0], f, INK, "c", tw)
    pg.text(cx, ink_top + h1 + gap - b2[1], TITLE_LINES[1], f, INK, "c", tw)


# --------------------------------------------------------------- date check
def draw_date_check(pg, box, out_items):
    x0, y0, x1, y1 = box
    d = pg.d
    d.rectangle([x0, y0, x1 - 1, y1 - 1], fill=(253, 234, 230), outline=RED, width=2)
    hf = get_face("heavy", 9)
    hh = hf.lh + 3
    d.rectangle([x0, y0, x1 - 1, y0 + hh], fill=RED)
    pg.text(x0 + 6, y0 + 2, "DATE CHECK", hf, WHITE)
    sf = get_face("ital", 8)
    pg.text(x1 - 6, y0 + 2 + (hf.lh - sf.lh) // 2, "old news deliberately excluded", sf, WHITE, "r",
            (x1 - x0) - 110)
    items = [re.sub(r"^\s*out\s*:\s*", "", str(t), flags=re.I) for t in (out_items or [])]
    if not items:
        items = ["nothing excluded"]
    top, avail = y0 + hh + 4, (y1 - 4) - (y0 + hh + 4)
    for size in (9, 8, 7):
        rf, bf = get_face("reg", size), get_face("bold", size)
        if rf.lh * len(items) <= avail or size == 7:
            break
    max_rows = max(1, avail // rf.lh)
    if len(items) > max_rows:
        items = items[:max_rows - 1] + ["+%d more" % (len(items) - max_rows + 1)]
    for i, t in enumerate(items):
        y = top + i * rf.lh
        pre = "" if t.startswith("+") else "OUT:"
        pw = pg.text(x0 + 6, y, pre, bf, RED) if pre else 0
        pg.text(x0 + 6 + pw + (4 if pre else 0), y, t, rf, INK, max_w=(x1 - 6) - (x0 + 6 + pw + 4))


# ------------------------------------------------------------ day in numbers
def _pair(it):
    if isinstance(it, dict):
        return str(it.get("value", "")), str(it.get("label", ""))
    it = list(it)
    return str(it[0]), (str(it[1]) if len(it) > 1 else "")


def draw_numbers(pg, box, items):
    x0, y0, x1, y1 = box
    d = pg.d
    d.rectangle([x0, y0, x1 - 1, y1 - 1], fill=CARD_BG, outline=INK, width=1)
    lab_w = 62
    d.rectangle([x0, y0, x0 + lab_w - 1, y1 - 1], fill=INK)
    lf = get_face("heavy", 10)
    mid = (y0 + y1) / 2.0
    pg.text(x0 + lab_w / 2.0, mid - lf.lh - 1, "DAY IN", lf, WHITE, "c", lab_w - 6)
    pg.text(x0 + lab_w / 2.0, mid + 1, "NUMBERS", lf, YELLOW, "c", lab_w - 4)
    items = [_pair(i) for i in (items or [])][:6]
    if not items:
        return
    n = len(items)
    cw = (x1 - x0 - lab_w) / float(n)
    labf = get_face("reg", 8)
    for i, (val, lab) in enumerate(items):
        xa = x0 + lab_w + int(round(i * cw))
        xb = x0 + lab_w + int(round((i + 1) * cw))
        if i:
            d.line([(xa, y0 + 6), (xa, y1 - 7)], fill=(190, 184, 168), width=1)
        inner = xb - xa - 10
        vf = fit_face("heavy", val, inner, range(26, 9, -1))
        pg.text((xa + xb) / 2.0, y0 + 4, val, vf, RED if i % 2 == 0 else INK, "c", inner)
        lines, _ = wrap_text(lab, labf, inner, 2)
        ly = y0 + 4 + vf.lh + 3
        for ln in lines:
            pg.text((xa + xb) / 2.0, ly, ln, labf, DECK, "c", inner)
            ly += labf.lh


# ---------------------------------------------------------------- world map
LON0, LON1, LAT_N, LAT_S = -170.0, 180.0, 80.0, -58.0

_LAND = [
    # North America
    [(-168, 66), (-162, 70), (-156, 71.5), (-141, 69.5), (-128, 70), (-115, 68), (-100, 68), (-95, 72),
     (-85, 69), (-82, 66), (-90, 64), (-94, 59), (-92, 57), (-85, 55), (-80, 52), (-79, 57), (-78, 62),
     (-72, 62), (-65, 60), (-62, 57), (-56, 52), (-60, 47), (-66, 45), (-70, 43), (-70, 41.5), (-74, 40),
     (-76, 37), (-76, 35), (-81, 31), (-80, 26), (-82, 26), (-83, 29), (-89, 30), (-94, 29.5), (-97, 26),
     (-97.5, 22), (-95, 18.5), (-91, 19), (-90, 21), (-87, 21), (-88, 16), (-84, 15.5), (-83, 11), (-80, 9),
     (-77.5, 8.5), (-79, 7.5), (-83, 8.5), (-86, 11), (-88, 13), (-92, 14.5), (-96, 15.7), (-105, 19.5),
     (-109, 24), (-112, 29), (-115, 30), (-117, 32.5), (-120.5, 34.5), (-124, 40), (-124.5, 46), (-123, 48.5),
     (-128, 51), (-133, 55), (-138, 59), (-146, 61), (-152, 59), (-158, 57), (-163, 55), (-158, 58.5),
     (-162, 60), (-166, 62), (-164, 64)],
    # Greenland
    [(-73, 78), (-60, 82), (-30, 83.5), (-18, 81), (-20, 72), (-22, 70), (-32, 68), (-42, 60), (-48, 61),
     (-53, 67), (-55, 71), (-62, 76)],
    # Baffin / Ellesmere
    [(-80, 73.5), (-68, 70), (-62, 66.5), (-66, 62.5), (-74, 64), (-78, 68)],
    [(-90, 79.5), (-72, 79.8), (-62, 80), (-70, 77), (-84, 76.5)],
    # South America
    [(-77.5, 8.5), (-72, 12), (-63, 10.7), (-60, 8.5), (-52, 5), (-50, 0), (-44, -2.5), (-35, -5.5),
     (-35, -9), (-39, -14), (-39, -19), (-43, -23), (-48, -26), (-48.5, -28), (-53, -34), (-57, -35),
     (-58, -38.5), (-62, -39), (-65, -41), (-64, -45), (-67.5, -46.5), (-66, -48), (-69, -51), (-68.5, -54),
     (-72, -53.5), (-75, -50), (-74, -44), (-73.5, -37), (-71.5, -30), (-70.5, -18), (-76, -14), (-81, -5.5),
     (-80, -1), (-78.5, 2)],
    # Africa
    [(-17, 21), (-13, 27.5), (-10, 30), (-9.5, 33), (-6, 35.8), (0, 35.5), (10, 37.3), (11, 33.5), (20, 32),
     (25, 32), (32, 31.2), (34, 28), (37, 22), (39, 16), (43, 12), (51, 12), (51, 10), (48, 5), (41, -2),
     (40, -10), (40.5, -15), (35, -20), (35.5, -24), (32.5, -28.5), (27, -33.5), (20, -34.8), (18, -32),
     (14.5, -22.5), (12, -17), (13.5, -11), (12, -5), (9.5, -1), (9.5, 4), (5, 6), (-2, 5), (-8, 4.5),
     (-12, 7.5), (-15, 11), (-17, 14.7), (-16.5, 19)],
    # Eurasia
    [(-9.5, 36.7), (-9, 43), (-1.5, 43.5), (-4.5, 48), (2, 51), (8, 54), (8.5, 57), (10.5, 57.5), (10.5, 54.5),
     (14, 54), (21, 55), (21, 59), (24, 59.5), (29, 60), (23, 60.5), (21.5, 63), (25, 65.5), (21, 65),
     (17.5, 62.5), (18.5, 60), (16, 56), (12.5, 56), (11, 59), (5.5, 58.5), (5, 62), (14, 68), (20, 70),
     (28, 71), (40, 67), (44, 68.5), (55, 68), (68, 69), (73, 72), (80, 73), (100, 77), (112, 74), (130, 71),
     (140, 72.5), (160, 70), (170, 70), (180, 68), (180, 65), (172, 62.5), (163, 59.5), (156, 57), (156, 51),
     (151, 59), (142, 59), (137, 54), (141, 52), (140, 48), (135, 43.5), (130, 42.5), (129.5, 40),
     (127.5, 39.5), (129, 36), (126.5, 34.5), (126, 37.5), (125, 39.5), (121.5, 39), (121.5, 40.5), (118, 39),
     (119, 37), (122.5, 37), (120.5, 35), (121.5, 31.5), (122, 29), (119.5, 25.5), (116, 22.8), (110, 21),
     (108, 21.5), (106.5, 19), (109, 15), (109, 11.5), (105, 8.7), (105, 10.5), (100.5, 13.5), (99.5, 10),
     (100.5, 7), (103.5, 3), (104, 1.5), (101.5, 2.5), (98, 8), (98.5, 13.5), (97.5, 16.5), (94.5, 16),
     (94, 19), (92, 21), (90, 22), (87, 21.5), (86.5, 20), (80.5, 15.5), (80, 10), (77.5, 8), (76, 10),
     (73, 17), (72.5, 21), (70, 21), (68, 23.5), (66.5, 25.5), (62, 25.2), (57, 25.8), (56.5, 27), (51, 28),
     (48, 30), (50, 26), (51.5, 24.5), (56, 26), (58, 23.5), (59.5, 22.5), (57, 19), (52, 16), (45, 12.7),
     (43, 13.5), (39, 21), (35, 28), (34.5, 29.5), (32.5, 30), (34, 31.5), (35.5, 34), (36, 36.5), (30, 36.5),
     (27, 37), (26.5, 40), (23.5, 40), (22, 37), (21, 40), (19.5, 41.5), (16, 43.5), (13.5, 45.5), (12.5, 44),
     (16, 41.5), (18.5, 40), (16.5, 38), (15.8, 38), (15.5, 40), (12.5, 42), (10, 44), (8, 44), (3.5, 43.2),
     (3, 42), (0, 39), (-0.5, 38), (-2, 36.8), (-5.5, 36), (-6.5, 37), (-9, 37)],
    # islands
    [(-5.5, 50), (1.5, 51), (1.7, 53), (-0.5, 54.8), (-2, 57.5), (-3.5, 58.6), (-6, 57.5), (-5, 55.5),
     (-3, 54.5), (-4.5, 53.3), (-5, 51.7)],                                              # Great Britain
    [(-10, 51.7), (-6, 52), (-6, 55), (-8, 55.2), (-10, 53.8)],                          # Ireland
    [(-24, 65.5), (-18, 66.3), (-14, 65), (-18, 63.4), (-22.5, 63.8)],                   # Iceland
    [(130, 31), (132, 33.5), (135, 34), (140, 35), (141.5, 38), (142, 40.5), (140, 41.5), (140, 40),
     (139.5, 37), (136, 36.5), (133, 35.5), (130.5, 34)],                                # Honshu / Kyushu
    [(140, 42), (141.5, 45.4), (145, 43.3), (143, 42)],                                  # Hokkaido
    [(95, 5.5), (98, 4), (104, -1), (106, -3), (105.5, -5.8), (102, -4), (98, 0.5), (95.5, 3.5)],  # Sumatra
    [(105.5, -6.5), (114.5, -7.5), (114, -8.7), (106, -7.7)],                            # Java
    [(109, 1.5), (111, 2), (115, 5), (117.5, 7), (119, 5), (118, 1), (116.5, -3.5), (114, -4), (110, -3),
     (109.5, 0)],                                                                         # Borneo
    [(131, -1), (138, -1.8), (145, -4.5), (150, -10), (142, -9), (138, -8), (134, -4)],  # New Guinea
    [(120, 18.5), (122, 18.3), (122, 14), (124, 13), (120.5, 14)],                       # Luzon
    [(122, 8), (126, 9), (126, 6.5), (122.5, 7)],                                        # Mindanao
    [(114, -22), (114, -26), (115, -34), (118, -35), (124, -33.5), (131, -31.5), (135, -34.5), (138, -35.5),
     (140, -38), (146, -39), (150, -37), (153, -31), (153, -25), (149, -20.5), (146, -18.5), (145.5, -15),
     (143, -11), (141.5, -13), (141, -17), (136, -15), (137, -12), (132, -11.5), (129, -15), (125, -14.5),
     (122, -17.5), (119, -20)],                                                           # Australia
    [(145, -41), (148, -41), (147.5, -43.5), (146, -43.5)],                              # Tasmania
    [(172.7, -34.5), (175.5, -37), (178.5, -37.7), (175, -41.5), (174.5, -39.5), (173.5, -37)],   # NZ north
    [(172.5, -40.5), (174, -41.5), (171, -44.5), (169, -46.5), (167, -46), (171, -42.5)],          # NZ south
    [(44, -25), (47, -25), (50, -15.5), (49.5, -12), (47, -15), (44, -20)],              # Madagascar
    [(-85, 22), (-82, 23.2), (-77, 21), (-74, 20), (-78, 20), (-81, 22)],                # Cuba
    [(80, 6), (81.8, 7.5), (80, 9.8)],                                                   # Sri Lanka
]
_LAKES = [
    [(28, 41.5), (28, 45), (31, 46.5), (34, 46), (36.5, 45.2), (40, 43.5), (41.5, 41.5), (36, 41.8), (31, 41.2)],
    [(47, 45), (50, 46.5), (53, 45), (53, 41), (54, 37), (50.5, 37), (49, 40), (47.5, 43)],
]
_NUDGE = [(0, 0)] + [(round(math.cos(a * math.pi / 4) * rr, 2), round(math.sin(a * math.pi / 4) * rr, 2))
                     for rr in (10, 15, 20) for a in range(8)]


def lonlat_to_pin(lon, lat):
    """Convert degrees to the 0..1 map fractions that pin_x / pin_y also accept."""
    return (float(lon) - LON0) / (LON1 - LON0), (LAT_N - float(lat)) / (LAT_N - LAT_S)


def _pin_frac(s):
    try:
        px, py = float(s.get("pin_x", 0.5)), float(s.get("pin_y", 0.5))
    except (TypeError, ValueError):
        px, py = 0.5, 0.5
    if not (0.0 <= px <= 1.0 and 0.0 <= py <= 1.0):
        px, py = lonlat_to_pin(px, py)
    return min(max(px, 0.0), 1.0), min(max(py, 0.0), 1.0)


def draw_map(pg, box, cards):
    x0, y0, x1, y1 = box
    d = pg.d
    hf = get_face("heavy", 9)
    pg.text(x0 + 1, y0, "WORLD MAP", hf, RED)
    sf = get_face("ital", 8)
    pg.text(x1 - 1, y0 + (hf.lh - sf.lh) // 2, "pin number = story number", sf, GRAY, "r", (x1 - x0) - 90)
    my0 = y0 + hf.lh + 2
    mw, mh = x1 - x0, y1 - my0
    layer = Image.new("RGB", (mw * SS, mh * SS), OCEAN)
    ld = ImageDraw.Draw(layer)

    def proj(lon, lat):
        return ((lon - LON0) / (LON1 - LON0) * mw * SS, (LAT_N - lat) / (LAT_N - LAT_S) * mh * SS)

    for lon in range(-150, 180, 30):
        ld.line([proj(lon, LAT_N), proj(lon, LAT_S)], fill=GRID, width=1)
    for lat in range(-30, 80, 30):
        ld.line([proj(LON0, lat), proj(LON1, lat)], fill=GRID, width=1)
    for poly in _LAND:
        pts = [proj(lo, la) for lo, la in poly]
        ld.polygon(pts, fill=LAND)
        ld.line(pts + [pts[0]], fill=COAST, width=1)
    for poly in _LAKES:
        ld.polygon([proj(lo, la) for lo, la in poly], fill=OCEAN)

    r = 6.5
    placed = []                                              # pin centres, 1x map coordinates
    centres = []
    for s in cards:
        fx, fy = _pin_frac(s)
        tx, ty = fx * mw, fy * mh
        spot = None
        for dx, dy in _NUDGE:
            cx, cy = tx + dx, ty + dy
            if cx < r + 1 or cx > mw - r - 1 or cy < r + 1 or cy > mh - r - 1:
                continue
            if all((cx - px) ** 2 + (cy - py) ** 2 >= (2 * r + 1) ** 2 for px, py in placed):
                spot = (cx, cy)
                break
        if spot is None:
            spot = (min(max(tx, r + 1), mw - r - 1), min(max(ty, r + 1), mh - r - 1))
        placed.append(spot)
        centres.append((s, spot, (tx, ty)))
    for s, (cx, cy), (tx, ty) in centres:                     # leader lines first, then pins
        if abs(cx - tx) + abs(cy - ty) > 0.5:
            ld.line([(tx * SS, ty * SS), (cx * SS, cy * SS)], fill=INK, width=SS)
            ld.ellipse([tx * SS - 2 * SS / 2, ty * SS - SS, tx * SS + SS, ty * SS + SS], fill=INK)
    for s, (cx, cy), _ in centres:
        ld.ellipse([(cx - r - 1) * SS, (cy - r - 1) * SS, (cx + r + 1) * SS, (cy + r + 1) * SS], fill=WHITE)
        ld.ellipse([(cx - r) * SS, (cy - r) * SS, (cx + r) * SS, (cy + r) * SS], fill=RED)
    pg.img.paste(layer.resize((mw, mh), RESAMPLE), (x0, my0))
    d.rectangle([x0, my0, x1 - 1, y1 - 1], outline=INK, width=1)
    nf = get_face("heavy", 8)
    for s, (cx, cy), _ in centres:
        pg.text_in(x0 + cx, my0 + cy, s.get("number", ""), nf, WHITE)


# ----------------------------------------------------------------- timeline
def _parse_hour(t):
    if isinstance(t, (int, float)):
        return max(0.0, min(24.0, float(t)))
    m = re.match(r"\s*(\d{1,2})(?:[:.hH](\d{2}))?", str(t))
    if not m:
        return None
    return max(0.0, min(24.0, int(m.group(1)) + (int(m.group(2)) if m.group(2) else 0) / 60.0))


def _norm_event(e):
    if isinstance(e, dict):
        t, txt, num = e.get("time"), e.get("text") or e.get("label") or "", e.get("story") or e.get("number")
    else:
        e = list(e)
        t, txt, num = e[0], (e[1] if len(e) > 1 else ""), (e[2] if len(e) > 2 else None)
    h = _parse_hour(t)
    if h is None:
        return None
    hh, mm = divmod(int(round(h * 60)), 60)
    return {"hour": h, "time": "%02d:%02d" % (hh, mm), "text": str(txt), "num": num}


def draw_timeline(pg, box, events):
    x0, y0, x1, y1 = box
    d = pg.d
    hf = get_face("heavy", 9)
    pg.text(x0 + 1, y0, "THE DAY IN UTC", hf, RED)
    sf = get_face("ital", 8)
    pg.text(x1 - 1, y0 + (hf.lh - sf.lh) // 2, "00:00 - 24:00 UTC, red marker = story", sf, GRAY, "r",
            (x1 - x0) - 120)
    by0 = y0 + hf.lh + 2
    d.rectangle([x0, by0, x1 - 1, y1 - 1], fill=CARD_BG, outline=INK, width=1)
    events = sorted([e for e in (_norm_event(e) for e in (events or [])) if e], key=lambda e: e["hour"])
    ax0, ax1 = x0 + 12, x1 - 12

    def hx(h):
        return ax0 + (ax1 - ax0) * h / 24.0

    bar_h, stem = 12, 7
    lane_h = (y1 - by0 - 8 - bar_h - 2 * stem) // 2
    lane_top = by0 + 4
    bar_y0 = lane_top + lane_h + stem
    bar_y1 = bar_y0 + bar_h
    below_top = bar_y1 + stem
    for h in range(24):                                      # night / day bar
        col = (236, 190, 72) if 6 <= h < 18 else (52, 70, 126)
        d.rectangle([int(round(hx(h))), bar_y0, int(round(hx(h + 1))) - 1, bar_y1 - 1], fill=col)
    for e in events:
        ex = int(round(hx(e["hour"])))
        d.line([(ex, bar_y0), (ex, bar_y1 - 1)], fill=RED, width=1)
    hrf = get_face("bold", 8)
    for h in range(0, 25, 3):
        s = "%02d" % h
        w = hrf.width(s)
        cx = min(max(hx(h), ax0 + w / 2.0 + 3), ax1 - w / 2.0 - 3)
        d.rectangle([int(cx - w / 2.0 - 2), bar_y0 + 1, int(cx + w / 2.0 + 2), bar_y1 - 2], fill=PAPER)
        pg.text_in(cx, (bar_y0 + bar_y1) / 2.0, s, hrf, INK)

    tf, rf = get_face("bold", 9), get_face("reg", 8)
    for side in (0, 1):                                       # 0 = above the bar, 1 = below
        evs = [e for k, e in enumerate(events) if k % 2 == side]
        prev_end = x0 + 3
        for j, e in enumerate(evs):
            ex = hx(e["hour"])
            limit = (hx(evs[j + 1]["hour"]) - 6) if j + 1 < len(evs) else (x1 - 5)
            start = max(ex - 2, prev_end + 4)
            if limit - start < 64:                            # too tight on the right: shift left
                start = max(prev_end + 4, min(start, limit - 64), x0 + 4)
            avail = max(0.0, limit - start)
            ix = int(round(ex))
            if side == 0:
                d.polygon([(ix - 4, bar_y0 - 6), (ix + 4, bar_y0 - 6), (ix, bar_y0 - 1)], fill=RED)
            else:
                d.polygon([(ix - 4, bar_y1 + 5), (ix + 4, bar_y1 + 5), (ix, bar_y1)], fill=RED)
            head = e["time"]
            num = ("#" + str(e["num"])) if e["num"] not in (None, "") else ""
            lines, _ = wrap_text(e["text"], rf, avail, max(0, (lane_h - tf.lh) // rf.lh)) if avail > 20 else ([], False)
            total_h = tf.lh + len(lines) * rf.lh
            ty = (lane_top + lane_h - total_h) if side == 0 else below_top
            sx = int(round(start))
            tw = pg.text(sx, ty, head, tf, INK, max_w=avail)
            width_used = tw
            nx = sx + int(math.ceil(tw)) + 4
            if num and tf.width(num) <= (sx + avail) - nx:
                width_used = (nx - sx) + pg.text(nx, ty, num, tf, RED)
            yy = ty + tf.lh
            for ln in lines:
                width_used = max(width_used, pg.text(sx, yy, ln, rf, DECK, max_w=avail))
                yy += rf.lh
            prev_end = sx + width_used


# -------------------------------------------------------------------- cards
FIT_PAIRS = [(12, 9), (12, 8), (11, 9), (11, 8), (10, 8), (10, 7), (9, 7), (8, 7)]


def card_rows(n):
    if n <= 0:
        return []
    rows = 1 if n <= 5 else (2 if n <= 10 else 3)
    base, extra = divmod(n, rows)
    return [base + (1 if i < extra else 0) for i in range(rows)]


def draw_card(pg, s, x, y, w, h):
    d = pg.d
    d.rectangle([x, y, x + w - 1, y + h - 1], fill=CARD_BG, outline=INK, width=1)
    ih = 50 if h >= 130 else max(26, int(h * 0.34))
    num = str(s.get("number", ""))
    try:
        seed = int(num)
    except ValueError:
        seed = 0
    pg.img.paste(scene_kit.render_scene(s.get("scene"), w - 2, ih, seed, SS), (x + 1, y + 1))
    d.line([(x + 1, y + 1 + ih), (x + w - 2, y + 1 + ih)], fill=INK, width=1)
    pad = 5
    tw = w - 2 * pad
    ty = y + ih + 5

    kf, nf = get_face("bold", 8), get_face("heavy", 8)       # number badge + red kicker
    rad = max(6.5, nf.width(num) / 2.0 + 2.5)
    row_h = max(kf.lh, int(2 * rad) + 1)
    bcx, bcy = x + pad + rad, ty + row_h / 2.0
    aa_circle(pg.img, bcx, bcy, rad, RED)
    pg.text_in(bcx, bcy, num, nf, WHITE)
    kx = x + pad + 2 * rad + 4
    pg.text(kx, ty + (row_h - kf.lh) // 2, str(s.get("kicker", "")).upper(), kf, RED, max_w=(x + w - pad) - kx)
    ty += row_h + 2

    foot_h = 11                                              # certainty chip + source
    fy = y + h - foot_h - 4
    tag = str(s.get("tag", "")).upper()
    cf = get_face("bold", 7)
    chip_w = int(cf.width(tag)) + 8 if tag else 0
    if tag:
        d.rounded_rectangle([x + pad, fy, x + pad + chip_w - 1, fy + foot_h - 1], radius=2,
                            fill=TAG_COL.get(tag, GRAY))
        pg.text_in(x + pad + chip_w / 2.0, fy + foot_h / 2.0, tag, cf, WHITE)
    srcf = get_face("ital", 8)
    sx = x + pad + chip_w + (5 if tag else 0)
    pg.text(sx, fy + (foot_h - srcf.lh) // 2, s.get("source", ""), srcf, GRAY, max_w=(x + w - pad) - sx)

    avail = (fy - 3) - ty                                    # headline + deck, largest sizes that fit
    head, deck = str(s.get("headline", "")), str(s.get("deck", ""))
    best = None
    for hs, ds in FIT_PAIRS:
        hf, df = get_face("bold", hs), get_face("reg", ds)
        hl, ht = wrap_text(head, hf, tw, 2)
        dl, dt = wrap_text(deck, df, tw, 3)
        need = len(hl) * hf.lh + ((2 + len(dl) * df.lh) if dl else 0)
        if not ht and not dt and need <= avail:
            best = (hf, df, hl, dl)
            break
    if best is None:                                         # nothing fits whole: keep headline, trim deck
        hf, df = get_face("bold", FIT_PAIRS[-1][0]), get_face("reg", FIT_PAIRS[-1][1])
        hl, _ = wrap_text(head, hf, tw, 2)
        n_deck = max(0, min(3, (avail - len(hl) * hf.lh - 2) // df.lh))
        dl, _ = wrap_text(deck, df, tw, n_deck)
        best = (hf, df, hl, dl)
    hf, df, hl, dl = best
    yy = ty
    for ln in hl:
        pg.text(x + pad, yy, ln, hf, INK, max_w=tw)
        yy += hf.lh
    yy += 2
    for ln in dl:
        pg.text(x + pad, yy, ln, df, DECK, max_w=tw)
        yy += df.lh


def draw_cards(pg, box, cards):
    x0, y0, x1, y1 = box
    rows = card_rows(len(cards))
    if not rows:
        return
    gap = 5
    rh = (y1 - y0 - gap * (len(rows) - 1)) // len(rows)
    total = x1 - x0
    idx = 0
    for r, cnt in enumerate(rows):
        yy = y0 + r * (rh + gap)
        for k in range(cnt):
            xa = x0 + (k * (total + gap)) // cnt
            xb = x0 + ((k + 1) * (total + gap)) // cnt - gap
            draw_card(pg, cards[idx], xa, yy, xb - xa, rh)
            idx += 1


# --------------------------------------------------------------- one-liners
def draw_oneliners(pg, box, items):
    x0, y0, x1, y1 = box
    d = pg.d
    hf, lf = get_face("heavy", 9), get_face("reg", 8)
    pg.text(x0, y0, "ALSO TODAY - %d MORE STORIES" % len(items), hf, RED)
    entries = list(TAG_COL.items())                          # legend, right aligned
    widths = [6 + 3 + lf.width(t) for t, _ in entries]
    lx = x1 - (sum(widths) + 10 * (len(entries) - 1))
    for (t, col), wd in zip(entries, widths):
        d.rectangle([int(lx), y0 + (hf.lh - 6) // 2 + 1, int(lx) + 5, y0 + (hf.lh - 6) // 2 + 6], fill=col)
        pg.text(lx + 9, y0 + (hf.lh - lf.lh) // 2, t, lf, DECK)
        lx += wd + 10
    d.line([(x0, y0 + hf.lh + 1), (x1 - 1, y0 + hf.lh + 1)], fill=INK, width=1)
    if not items:
        return
    gy0 = y0 + hf.lh + 4
    n = len(items)
    cols = 3 if n <= 30 else 4
    rows = -(-n // cols)
    row_h = min(20, (y1 - gy0) // rows)
    col_w = (x1 - x0) / float(cols)

    def row_width(it, size, numw):
        rf, sf = get_face("reg", size), get_face("ital", size)
        src = str(it.get("source", ""))
        return 8 + numw + 4 + rf.width(str(it.get("headline", ""))) + ((6 + sf.width(src)) if src else 0)

    chosen = None
    for size in (11, 10, 9, 8, 7):
        if get_face("reg", size).lh > row_h:
            continue
        numw = max(get_face("bold", size).width(str(it.get("number", ""))) for it in items)
        if all(row_width(it, size, numw) <= col_w - 8 for it in items):
            chosen = size
            break
    if chosen is None:
        chosen = 7
        for size in (11, 10, 9, 8, 7):
            if get_face("reg", size).lh <= row_h:
                chosen = size
                break
    rf, bf, sf = get_face("reg", chosen), get_face("bold", chosen), get_face("ital", chosen)
    numw = max(bf.width(str(it.get("number", ""))) for it in items)
    for c in range(1, cols):
        xs = x0 + int(round(c * col_w))
        d.line([(xs, gy0 + 1), (xs, y1 - 2)], fill=(200, 194, 178), width=1)
    for i, it in enumerate(items):
        c, r = divmod(i, rows)
        cx0 = x0 + int(round(c * col_w))
        cx1 = x0 + int(round((c + 1) * col_w))
        x = cx0 + 4
        y = gy0 + r * row_h + max(0, (row_h - rf.lh) // 2)
        tcol = TAG_COL.get(str(it.get("tag", "")).upper(), GRAY)
        d.rectangle([x, y + (rf.lh - 5) // 2, x + 4, y + (rf.lh - 5) // 2 + 4], fill=tcol)
        pg.text(x + 8, y, it.get("number", ""), bf, INK)
        hx0 = x + 8 + numw + 4
        right = cx1 - 4
        src = str(it.get("source", ""))
        head = str(it.get("headline", ""))
        reserve = (6 + sf.width(src)) if src else 0
        if right - hx0 - reserve < 60:
            src, reserve = "", 0
        hw = pg.text(hx0, y, head, rf, INK, max_w=right - hx0 - reserve)
        if src:
            pg.text(hx0 + hw + 6, y, src, sf, GRAY, max_w=right - (hx0 + hw + 6))


# ------------------------------------------------------------------- footer
def draw_footer(pg, box, stories, note):
    x0, y0, x1, y1 = box
    pg.d.line([(x0, y0), (x1 - 1, y0)], fill=INK, width=2)
    srcs = []
    for s in stories:
        name = str(s.get("source", "")).strip()
        if name and name not in srcs:
            srcs.append(name)
    body = ", ".join(srcs) + ((" | " + str(note)) if note else "")
    for size in (9, 8, 7):
        bf, rf = get_face("heavy", size), get_face("reg", size)
        lw = bf.width("NEWS SOURCES:") + 6
        lines, trunc = wrap_text(body, rf, (x1 - x0) - lw, 2)
        if not trunc and len(lines) * rf.lh <= (y1 - y0) - 6:
            break
    pg.text(x0, y0 + 4, "NEWS SOURCES:", bf, RED)
    for i, ln in enumerate(lines):
        pg.text(x0 + lw, y0 + 4 + i * rf.lh, ln, rf, DECK, max_w=(x1 - x0) - lw)


# --------------------------------------------------------------------- save
def save_png(img, path, limit=PNG_LIMIT):
    img.save(path, format="PNG", optimize=True)
    if os.path.getsize(path) > limit:                        # deterministic fallback: 256-colour palette
        quant = getattr(Image, "Quantize", Image).MEDIANCUT
        img.quantize(colors=256, method=quant).save(path, format="PNG", optimize=True)
    size = os.path.getsize(path)
    if size > limit:
        raise RuntimeError("PNG is %d bytes, above the %d byte limit" % (size, limit))
    with Image.open(path) as chk:
        if chk.size != (W, H):
            raise RuntimeError("unexpected output size %r" % (chk.size,))
    return size


# --------------------------------------------------------------------- main
def render_page(stories, date_str, numbers, timeline, out_items, out_path="newspaper.png",
                footer_note=None, strict=False):
    """Draw the whole page and save it as a 1024x1024 PNG.  Returns out_path.

    strict=True raises if the layout ledger finds overlapping / out-of-canvas text;
    otherwise problems are only reported on stderr."""
    pg = Page()
    cards = [s for s in stories if s.get("scene")][:MAX_CARDS]
    taken = set(id(s) for s in cards)
    rest = [s for s in stories if id(s) not in taken]
    if not (30 <= len(stories) <= 41) or not (13 <= len(cards) <= 15):
        sys.stderr.write("note: %d stories / %d cards (brief asks for 30-41 / 13-15)\n"
                         % (len(stories), len(cards)))

    pg.d.rectangle([4, 4, W - 5, H - 5], outline=INK, width=2)
    draw_masthead(pg, date_str, len(stories))
    left, right = MX0, MX0 + LEFT_W + GAP
    draw_date_check(pg, (left, INFO[0], left + LEFT_W, INFO[1]), out_items)
    draw_numbers(pg, (right, INFO[0], MX1, INFO[1]), numbers)
    draw_map(pg, (left, ROW3[0], left + LEFT_W, ROW3[1]), cards)
    draw_timeline(pg, (right, ROW3[0], MX1, ROW3[1]), timeline)
    draw_cards(pg, (MX0, CARDS[0], MX1, CARDS[1]), cards)
    draw_oneliners(pg, (MX0, ONE[0], MX1, ONE[1]), rest)
    draw_footer(pg, (MX0, FOOT[0], MX1, FOOT[1]), stories, footer_note)

    problems = check_layout(pg.boxes)
    if problems:
        msg = "layout problems:\n  " + "\n  ".join(problems)
        if strict:
            raise RuntimeError(msg)
        sys.stderr.write(msg + "\n")
    save_png(pg.img, out_path)
    return out_path


render = render_page


# ---------------------------------------------------------------- entry data
def entry_data():
    """Verified news of Wednesday 25 November 2026 (see SOURCES.md).

    Researched 26 Nov 2026 from Just Security's Early Edition 25 Nov 2026
    and OneTurn News' 25 Nov 2026 front page, plus the Reuters/BBC/AP/UEFA
    wires they carry. 36 stories (15 cards + 21 one-liners), 7 regions.
    OUT items are big events from 20-24 Nov deliberately excluded."""
    def card(n, kicker, headline, deck, tag, source, scene, lon, lat):
        return dict(number=n, kicker=kicker, headline=headline, deck=deck, tag=tag, source=source,
                    scene=scene, pin_x=lon, pin_y=lat)

    def line(n, headline, tag, source):
        return dict(number=n, kicker="", headline=headline, deck="", tag=tag, source=source,
                    scene=None, pin_x=None, pin_y=None)

    stories = [
        card(1, "IRAN · STRAIT OF HORMUZ", "Two tankers hit mines and catch fire",
             "IRGC says two tankers struck naval mines and exploded in the strait; "
             "Iran's army deploys new surveillance systems.",
             "CONFIRMED", "Reuters", "ship", 56.5, 26.5),
        card(2, "DISASTER · CAIRO", "Tanker fire kills at least 31 in Cairo",
             "A fuel tanker overturned and ignited on Cairo's ring road; 31 killed, "
             "21 injured and dozens of cars burned.",
             "CONFIRMED", "BBC", "fire", 31.2, 30.0),
        card(3, "TRADE · WASHINGTON", "US proposes tariffs on 14 partners",
             "White House proposes new tariffs on China, the EU, Japan, India and "
             "10 more after a probe into industrial subsidies.",
             "CONFIRMED", "AP", "market_chart", -77.0, 38.9),
        card(4, "YEMEN · RAS TANURA", "Houthis say they hit Saudi refinery",
             "Houthis claim an attack on Ras Tanura, the kingdom's largest refinery; "
             "the coalition says 4 drones were intercepted.",
             "CLAIM", "Reuters", "energy", 50.1, 26.6),
        card(5, "UKRAINE · KYIV", "Russia hits Kyiv with ballistic missiles",
             "Missiles struck a shopping centre and two buildings late Wednesday; "
             "an Odesa strike kills 2 and injures 3.",
             "CONFIRMED", "Reuters", "skyline", 30.5, 50.4),
        card(6, "MARKETS · NEW YORK", "Tech stocks tumble on AI doubts",
             "The Nikkei falls 2.78% and the S&P 500 slips 0.25% as AI-spending "
             "doubts spread; Nvidia drops about 7%.",
             "CONFIRMED", "OneTurn", "market_chart", -74.0, 40.7),
        card(7, "SUDAN · BLUE NILE", "RSF drone strikes kill 19 in Sudan",
             "Emergency Lawyers says RSF drones killed 19 civilians, including "
             "6 women, and wounded 20.",
             "REPORTED", "Reuters", "rescue", 34.5, 11.8),
        card(8, "COLOMBIA · CARTAGENA", "All 76 hostages freed in siege",
             "Colombian forces storm a supermarket and free all 76 hostages after "
             "a 17-hour siege; no deaths are reported.",
             "CONFIRMED", "OneTurn", "rescue", -75.5, 10.4),
        card(9, "JUSTICE · NEW YORK", "US jury convicts Huawei of fraud",
             "A federal court finds Huawei guilty of bank fraud and trade-secret "
             "theft, but acquits it of racketeering.",
             "CONFIRMED", "BBC", "parliament", -73.9, 40.7),
        card(10, "SPACE · JIUQUAN", "Shenzhou-24 docks with Pakistani aboard",
             "China's Shenzhou-24 docks at its space station carrying Pakistan's "
             "first astronaut — the first foreigner aboard.",
             "CONFIRMED", "Reuters", "space", 100.3, 41.8),
        card(11, "CLIMATE · VATICAN", "Pope warns as COP31 blame game begins",
             "Leo XIV decries the failed Antalya talks; OPEC blames the EU for the "
             "collapse after 190 nations left with no deal.",
             "OFFICIAL", "AP", "summit", 12.5, 41.9),
        card(12, "PACIFIC · HONIARA", "Solomons sign Australia security treaty",
             "Treaty bars any foreign military base on the islands; Honiara told "
             "China its 2022 pact will not be renewed.",
             "CONFIRMED", "NYT", "summit", 160.0, -9.4),
        card(13, "SPORT · BRUGES", "Liverpool and Barça win big in Europe",
             "Liverpool beat Brugge 3-0, Barcelona beat Sabah 4-1; Lille "
             "stun Bayern 2-1, PSG draw 2-2 with Roma.",
             "CONFIRMED", "UEFA", "stadium", 3.2, 51.2),
        card(14, "GAZA · GAZA CITY", "Israel kills Hamas security chief",
             "A strike kills Hamas colonel Mohammad Abuelouf, his wife and two "
             "children; another strike kills one in Karama.",
             "CONFIRMED", "Reuters", "skyline", 34.5, 31.5),
        card(15, "NIGERIA · NIGER STATE", "Militants kill at least 30 in Nigeria",
             "Residents say gunmen killed at least 30 and burned homes in Borgu; "
             "the governor pledges $1,250 per family.",
             "REPORTED", "Reuters", "rescue", 6.5, 10.0),
        line(16, "US weighs strikes on top Iranian leaders", "REPORTED", "OneTurn"),
        line(17, "LNA vows revenge after 2 officers die", "REPORTED", "AP"),
        line(18, "Merz: Russia wants more than Ukraine", "OFFICIAL", "Reuters"),
        line(19, "Poland plans no-fly zone on east border", "REPORTED", "OneTurn"),
        line(20, "Knesset advances Oct 7 inquiry", "REPORTED", "OneTurn"),
        line(21, "China probes Shanghai party chief", "REPORTED", "OneTurn"),
        line(22, "Ramaphosa wins impeachment court battle", "CONFIRMED", "OneTurn"),
        line(23, "North Korea expels Swiss diplomat", "REPORTED", "OneTurn"),
        line(24, "Bangladesh garment wage up 36% to $139", "CONFIRMED", "Reuters"),
        line(25, "US inflation hits 3.8% in October", "OFFICIAL", "OneTurn"),
        line(26, "Poundland collapses; 11,000 jobs at risk", "REPORTED", "OneTurn"),
        line(27, "Argentina enters technical recession", "REPORTED", "OneTurn"),
        line(28, "SpaceX cleared for 1m data-centre satellites", "OFFICIAL", "OneTurn"),
        line(29, "CIA and intelligence office breached", "REPORTED", "Reuters"),
        line(30, "Sánchez pledges €22bn spending spree", "REPORTED", "The Times"),
        line(31, "Wolbachia mosquitoes cut infections 68%", "REPORTED", "OneTurn"),
        line(32, "UN warns HIV gains could unravel", "OFFICIAL", "OneTurn"),
        line(33, "EU unveils €50bn tech fund", "OFFICIAL", "OneTurn"),
        line(34, "Sinner sidelined after knee surgery", "CONFIRMED", "Reuters"),
        line(35, "Canary Islands log 2,000 arrivals in a day", "REPORTED", "OneTurn"),
        line(36, "Sealed Mario game sells for record $96,875", "REPORTED", "OneTurn"),
    ]
    numbers = [("490,334", "Russian soldiers dead since 2022"), ("31", "killed in Cairo tanker fire"),
               ("76", "hostages freed in Cartagena"), ("19", "civilians killed in Sudan"),
               ("-2.78%", "Nikkei fall"), ("36%", "Bangladesh wage rise")]
    timeline = [("03:00", "Huawei verdict reported", 9), ("08:00", "Cairo tanker fire kills 31", 2),
                ("11:00", "US tariff plan unveiled", 3), ("13:00", "Houthis claim refinery hit", 4),
                ("15:00", "Shenzhou-24 docks", 10), ("18:40", "Nigeria attack reported", 15),
                ("19:00", "Champions League night", 13), ("21:00", "Wall Street closes lower", 6)]
    out_items = ["COP31 talks collapse, no deal — Sun 22 Nov",
                 "Nvidia brings back Jensen Huang — Tue 24 Nov",
                 "Ukraine sinks corvette at Benghazi — Sun 22 Nov",
                 "China death sentence for spy leaks — Mon 23 Nov",
                 "El Chapo Isidro captured — Fri 20 Nov"]
    return stories, numbers, timeline, out_items


# ------------------------------------------------ usage example (5 lines)
if __name__ == "__main__":
    stories, numbers, timeline, out_items = entry_data()
    note = "Scenes are drawn illustrations, not photographs · Press time 01:04 UTC 26 Nov 2026"
    path = render_page(stories, "Wednesday 25 November 2026", numbers, timeline, out_items, "entry.png", note)
    print(path, os.path.getsize(path), "bytes")                  # 4: 1024x1024 PNG, <= 1 MiB
    # 5: rendering twice gives byte-identical files (no clocks, no randomness, no network)
