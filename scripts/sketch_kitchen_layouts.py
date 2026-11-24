#!/usr/bin/env python3
"""Kitchen and furniture layout studies for the open hall/kitchen/living space.

Draws the resolved target model (walls, openings, shafts, equipment) and
overlays alternative kitchen and living arrangements. Kitchen modules are laid
out along wall runs, so prep lengths, landings, work-triangle legs, aisle
widths and service-route lengths are computed from geometry and checked
against ergonomic rules rather than typed in.

Usage: python3 scripts/sketch_kitchen_layouts.py [data/target.yaml] [out_dir]
"""

import copy
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from model_loader import load_model

MODEL = Path("data/target.yaml")
OUT_DIR = Path("exports/concepts/kitchen_layouts")
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# Plan crop (metres) and scale.
X0, X1, Y0, Y1 = 0.05, 9.65, 4.75, 13.45
SCALE = 115
PAD, TOP = 40, 120
PANEL_W = 820

DEPTH = 0.60
OPEN_SPACE = 123

# Concept targets informed by kitchen planning guidelines; not building requirements.
MAIN_PREP_MIN, MAIN_PREP_GOOD = 0.90, 1.20
TOTAL_PREP_MIN = 1.60
PREP_UNIT_MIN = 0.60
HOB_SIDE_MIN, HOB_SIDE_ONE = 0.30, 0.40
SINK_SIDE_MIN, SINK_SIDE_ONE = 0.45, 0.60
FRIDGE_LANDING = 0.40
LEG_MIN, LEG_MAX, TRIANGLE_MAX = 1.20, 2.70, 7.90
AISLE_MIN = 1.20
DRAIN_FALL = 0.02
EPS = 1e-6

COLORS = {
    "background": "#f4f1ea",
    "paper": "#fffdf8",
    "wall": "#2d333b",
    "room": "#eef1f3",
    "open": "#f7efe3",
    "bath": "#dcebf2",
    "window": "#cfe8f7",
    "door": "#a5753d",
    "shaft": "#b85b45",
    "new_wall": "#c0392b",
    "counter": "#e2c79f",
    "tall": "#8d6e4c",
    "appliance": "#c9d2da",
    "prep": "#8fcf8a",
    "living": "#c7d3e6",
    "dining": "#d9c3e3",
    "hall": "#e6dcc8",
    "triangle": "#e67e22",
    "drain": "#b84949",
    "duct": "#7d4fa3",
    "ac": "#15917f",
    "brick": "#9b461e",
    "text": "#222831",
    "muted": "#616b76",
    "ok": "#2e8b57",
    "fail": "#c0392b",
    "keep_clear": "#e74c3c",
}

TALL = {"fridge", "oven", "pantry", "tank"}
COUNTER = {"prep", "dw", "blind"}


def font(size, bold=False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT, size)


# --------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------

def rect(x, y, w, d):
    return [(x, y), (x + w, y), (x + w, y + d), (x, y + d)]


def inside(pt, poly):
    x, y = pt
    result = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > y) != (y2 > y):
            if x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                result = not result
    return result


def bbox(poly):
    xs, ys = zip(*poly)
    return min(xs), min(ys), max(xs), max(ys)


def samples(poly, step=0.025, inset=0.012):
    x0, y0, x1, y1 = bbox(poly)
    points = []
    y = y0 + inset
    while y < y1 - inset + 1e-9:
        x = x0 + inset
        while x < x1 - inset + 1e-9:
            if inside((x, y), poly):
                points.append((x, y))
            x += step
        y += step
    return points


def overlaps(a, b):
    ax0, ay0, ax1, ay1 = bbox(a)
    bx0, by0, bx1, by1 = bbox(b)
    if ax1 <= bx0 or bx1 <= ax0 or ay1 <= by0 or by1 <= ay0:
        return False
    return any(inside(p, b) for p in samples(a))


def polyline_length(points):
    return sum(math.dist(p, q) for p, q in zip(points, points[1:]))


# --------------------------------------------------------------------------
# Kitchen runs
# --------------------------------------------------------------------------

class Module:
    def __init__(self, run, kind, start, width, role=None, label=None,
                 corner_leg=False, poly=None, front=None, open_joint=False):
        self.run = run
        # Joined to its chain neighbours at an obtuse angle, so the worktop
        # stays usable across the joint (unlike a 90-degree corner).
        self.open_joint = open_joint
        self.kind = kind
        self.start = start
        self.width = width
        self.role = role
        self.label = label
        self.corner_leg = corner_leg
        if poly is None:
            o, u, n = run["origin"], run["dir"], run["normal"]
            a = (o[0] + u[0] * start, o[1] + u[1] * start)
            b = (a[0] + u[0] * width, a[1] + u[1] * width)
            poly = [a, b, (b[0] + n[0] * DEPTH, b[1] + n[1] * DEPTH),
                    (a[0] + n[0] * DEPTH, a[1] + n[1] * DEPTH)]
            front = [poly[3], poly[2]]
        self.poly = poly
        self.front = front

    @property
    def frontage(self):
        if self.kind == "blind":
            return 0.0
        return polyline_length(self.front)

    @property
    def front_mid(self):
        points = self.front
        total = polyline_length(points)
        walked = 0.0
        for p, q in zip(points, points[1:]):
            step = math.dist(p, q)
            if walked + step >= total / 2:
                t = (total / 2 - walked) / step
                return (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t)
            walked += step
        return points[-1]


def build_run(run):
    modules, offset = [], 0.0
    for spec in run["modules"]:
        kind, width = spec[0], spec[1]
        extra = spec[2] if len(spec) > 2 else {}
        modules.append(Module(run, kind, offset, width, **extra))
        offset += width
    run["built"] = modules
    run["length"] = offset
    return modules


def chain_modules(option, extras):
    """Modules in working order along the connected counter, runs joined at corners."""
    chain = []
    for item in option["chain"]:
        if isinstance(item, str):
            chain.append(extras[item])
            continue
        name, reverse = item
        modules = option["runs"][name]["built"]
        chain.extend(reversed(modules) if reverse else modules)
    return chain


def continuous(a, b):
    return a.run is b.run or a.open_joint or b.open_joint


def side_frontage(chain, index, direction):
    """Uninterrupted worktop beside the appliance, across open joints only."""
    total, i = 0.0, index + direction
    while (0 <= i < len(chain) and continuous(chain[i - direction], chain[i])
           and chain[i].kind in {"prep", "dw"}):
        total += chain[i].frontage
        i += direction
    return total


# --------------------------------------------------------------------------
# Options
# --------------------------------------------------------------------------

def corner_option_a(label="MAIN PREP\non chamfer"):
    """Diagonal worktop following the 1.29 m NW chamfer (existing kitchen).

    The chamfer meets the west wall at 124 degrees and the north wall at 146,
    so the worktop runs on round both joints without a blind corner.
    """
    return Module(
        {"origin": (0, 0), "dir": (1, 0), "normal": (0, 1)},
        "prep", 0, 0, role="main", label=label, open_joint=True,
        poly=[(1.40, 11.77), (2.00, 11.77), (2.00, 11.851), (2.652, 12.29),
              (2.88, 12.29), (2.88, 12.89), (2.47, 12.89), (1.40, 12.17)],
        front=[(2.00, 11.77), (2.00, 11.851), (2.652, 12.29), (2.88, 12.29)],
    )


HALL_WARDROBE = ("wardrobe", rect(3.32, 8.05, 1.94, 0.60), "HALL WARDROBE 194×60", "hall")
TANK_HOUSING = ("tank", rect(1.40, 10.17, 0.60, 0.60), "HW TANK\nhousing", "hall")


def dining(x, y, length=1.60, depth=0.90, chairs_per_side=3, axis="x"):
    items = []
    if axis == "x":
        items.append(("table", rect(x, y, length, depth), f"DINING {length*100:.0f}×{depth*100:.0f}", "dining"))
        pitch = length / chairs_per_side
        for k in range(chairs_per_side):
            cx = x + pitch * (k + 0.5) - 0.225
            items.append(("chair", rect(cx, y - 0.50, 0.45, 0.45), "", "dining"))
            items.append(("chair", rect(cx, y + depth + 0.05, 0.45, 0.45), "", "dining"))
    else:
        items.append(("table", rect(x, y, depth, length), f"DINING\n{length*100:.0f}×{depth*100:.0f}", "dining"))
        pitch = length / chairs_per_side
        for k in range(chairs_per_side):
            cy = y + pitch * (k + 0.5) - 0.225
            items.append(("chair", rect(x - 0.50, cy, 0.45, 0.45), "", "dining"))
            items.append(("chair", rect(x + depth + 0.05, cy, 0.45, 0.45), "", "dining"))
    return items


def living_west():
    """TV on the brick-faced west wall, sofa facing west, clear of OB2."""
    return [
        ("tv", rect(1.40, 10.87, 0.40, 1.20), "TV 120×40", "living"),
        ("coffee", rect(2.30, 10.92, 0.55, 1.10), "COFFEE\nTABLE", "living"),
        ("sofa", rect(3.15, 10.37, 0.95, 2.20), "SOFA\n220×95", "living"),
    ]


OPTIONS = [
    {
        "slug": "A_existing_nw_corner",
        "title": "A · Kitchen kept at the existing NW services",
        "summary": "Reuses the OB1 water/waste point; living moves east.",
        "runs": {
            "west": {"origin": (1.40, 9.57), "dir": (0, 1), "normal": (1, 0), "modules": [
                ("fridge", 0.60, {"label": "FRIDGE"}),
                ("tank", 0.60, {"label": "TANK\nhousing"}),
                ("prep", 0.40, {"role": "landing", "label": "40"}),
                ("hob", 0.60, {"label": "HOB 60"}),
            ]},
            "north": {"origin": (2.88, 12.89), "dir": (1, 0), "normal": (0, -1), "modules": [
                ("sink", 0.80, {"label": "SINK 80"}),
                ("dw", 0.45, {"role": "landing", "label": "DW45"}),
            ]},
        },
        "extra_modules": [corner_option_a],
        "chain": [("west", False), "corner", ("north", False)],
        "furniture": [
            HALL_WARDROBE,
            *dining(3.95, 9.55, length=1.40, depth=0.80, chairs_per_side=2, axis="y"),
            ("sideboard", rect(5.40, 7.455, 2.00, 0.40), "SIDEBOARD 200×40", "living"),
            ("sofa", rect(6.10, 8.77, 0.95, 2.20), "SOFA\n220×95", "living"),
            ("coffee", rect(7.45, 9.32, 0.60, 1.10), "COFFEE", "living"),
            ("tv", rect(8.56, 9.27, 0.40, 1.20), "TV", "living"),
        ],
        "new_walls": [],
        "ac": None,
        "services": {
            "drain": [[(3.28, 12.59), (3.28, 12.89)]],
            "duct": None,
        },
        "pros": [
            "No new kitchen water/waste: sink stays on the existing OB1 point.",
            "AC stays on the bathroom-2 wall as already modelled.",
            "Living gets the east brick strip as a TV wall.",
        ],
        "cons": [
            "Prep short of 160 cm: only the chamfer piece is usable.",
            "Fridge is cut off from the worktop by the HW tank housing.",
            "Custom angled carcasses on the 1.29 m chamfer.",
            "No ventilation shaft nearby: recirculating hood only.",
            "Kitchen is the first thing seen from the entrance.",
        ],
    },
    {
        "slug": "B_open_L_bathroom2_wall",
        "title": "B · Open L on the bathroom-2 wall + east wall",
        "summary": "Uses the 0.60 m alcove in front of the new bathroom wall.",
        "runs": {
            "alcove": {"origin": (5.26, 7.455), "dir": (1, 0), "normal": (0, 1), "modules": [
                ("oven", 0.60, {"label": "OVEN\nTALL"}),
                ("prep", 0.60, {"role": "secondary", "label": "PREP 2"}),
                ("sink", 0.80, {"label": "SINK 80"}),
                ("dw", 0.60, {"role": "main", "label": "DW"}),
                ("prep", 0.50, {"role": "main", "label": "PREP"}),
                ("blind", 0.28, {"label": ""}),
            ]},
            "east": {"origin": (8.96, 8.12), "dir": (0, 1), "normal": (-1, 0), "modules": [
                ("prep", 0.60, {"role": "main", "corner_leg": True, "label": "CORNER"}),
                ("hob", 0.60, {"label": "HOB 60"}),
                ("prep", 0.60, {"role": "landing", "label": "LAND."}),
                ("fridge", 0.60, {"label": "FRIDGE"}),
            ]},
        },
        "chain": [("alcove", False), ("east", False)],
        "furniture": [
            HALL_WARDROBE,
            TANK_HOUSING,
            *living_west(),
            *dining(5.50, 10.05),
        ],
        "new_walls": [],
        "ac": rect(8.74, 11.40, 0.22, 0.80),
        "services": {
            "drain": [[(6.86, 7.755), (6.86, 7.25), (7.95, 7.25), (7.95, 6.20), (8.64, 6.20)]],
            "duct": [(8.66, 9.02), (8.66, 8.12)],
            "ac_lines": [(7.57, 12.75), (8.85, 12.75), (8.85, 12.20)],
        },
        "pros": [
            "Sink waste and water come through bathroom 2 to SH_san (short run).",
            "Hob is near SH_vent; use recirculation unless a dedicated duct is approved.",
            "Living takes the bright NW corner; old brick backsplash becomes the TV wall.",
            "Fully open plan; kitchen out of the entrance sight line.",
        ],
        "cons": [
            "Fridge sits beside the hob landing rather than the prep side.",
            "AC must move off the bathroom-2 wall (wall cabinets), e.g. east wall high.",
            "East brick strip behind hob must be replaced by a splashback.",
            "Old NW kitchen point capped.",
        ],
    },
    {
        "slug": "C_U_kitchen_with_hall_screen_wall",
        "title": "C · U kitchen with a new hall screen wall",
        "summary": "New 0.10 m partition continues the storage east wall north by 1.90 m.",
        "runs": {
            "west": {"origin": (5.26, 8.055), "dir": (0, 1), "normal": (1, 0), "modules": [
                ("fridge", 0.60, {"label": "FRIDGE"}),
                ("oven", 0.60, {"label": "OVEN\nTALL"}),
                ("pantry", 0.60, {"label": "PANTRY"}),
            ]},
            "alcove": {"origin": (5.26, 7.455), "dir": (1, 0), "normal": (0, 1), "modules": [
                ("blind", 0.60, {"label": ""}),
                ("prep", 0.80, {"role": "secondary", "label": "PREP 2"}),
                ("sink", 0.80, {"label": "SINK 80"}),
                ("dw", 0.60, {"role": "main", "label": "DW"}),
                ("prep", 0.30, {"role": "main", "label": ""}),
                ("blind", 0.28, {"label": ""}),
            ]},
            "east": {"origin": (8.96, 8.12), "dir": (0, 1), "normal": (-1, 0), "modules": [
                ("prep", 0.60, {"role": "main", "corner_leg": True, "label": "CORNER"}),
                ("hob", 0.60, {"label": "HOB 60"}),
                ("prep", 0.60, {"role": "landing", "label": "LAND."}),
            ]},
        },
        "chain": [("west", True), ("alcove", False), ("east", False)],
        "furniture": [
            ("wardrobe", rect(3.32, 8.05, 1.84, 0.60), "HALL WARDROBE 184×60", "hall"),
            ("shoes", rect(4.81, 8.65, 0.35, 1.30), "SHOES\n/COATS\n35", "hall"),
            TANK_HOUSING,
            *living_west(),
            *dining(6.30, 10.85),
        ],
        "new_walls": [("W_kitchen_screen", rect(5.16, 8.05, 0.10, 1.90))],
        "ac": rect(8.74, 11.40, 0.22, 0.80),
        "services": {
            "drain": [[(7.06, 7.755), (7.06, 7.25), (7.95, 7.25), (7.95, 6.20), (8.64, 6.20)]],
            "duct": [(8.66, 9.02), (8.66, 8.12)],
            "ac_lines": [(7.57, 12.75), (8.85, 12.75), (8.85, 12.20)],
        },
        "pros": [
            "Compact triangle; every leg 1.2–2.7 m; 2.5 m clear inside the U.",
            "Three tall units (fridge, oven, pantry) on the new wall; fridge lands on prep 2.",
            "Wall screens the kitchen from the entrance and gives the hall a shoe/coat wall.",
            "Same short waste route as B (bathroom 2 → SH_san).",
            "Hinge the fridge door on its north side so it opens towards prep 2.",
        ],
        "cons": [
            "1.90 m of new partition, reinforced for the tall units.",
            "AC must move off the bathroom-2 wall, e.g. east wall high.",
            "East brick strip behind hob replaced by a splashback; NW point capped.",
            "Slightly less open view from the hall into the kitchen.",
        ],
    },
    {
        "slug": "D_open_east_wall",
        "title": "D · Open east-wall kitchen (recommended)",
        "summary": "No island or new wall; 120 cm main prep plus 60 cm over the dishwasher.",
        "runs": {
            "east": {"origin": (8.86, 8.32), "dir": (0, 1), "normal": (-1, 0), "modules": [
                ("fridge", 0.60, {"label": "FRIDGE"}),
                ("dw", 0.60, {"role": "secondary", "label": "DW\nPREP 60"}),
                ("sink", 0.60, {"label": "SINK 60"}),
                ("prep", 1.20, {"role": "main", "label": "MAIN PREP\n120"}),
                ("hob", 0.60, {"label": "HOB 60"}),
                ("prep", 0.45, {"role": "landing", "label": "LAND. 45"}),
            ]},
        },
        "chain": [("east", False)],
        "furniture": [
            HALL_WARDROBE,
            TANK_HOUSING,
            *living_west(),
            *dining(5.35, 10.05, chairs_per_side=2),
        ],
        "new_walls": [],
        "ac": None,
        "services": {
            "drain": [[(8.66, 9.82), (8.90, 9.82), (8.90, 8.22), (8.50, 8.22),
                       (8.50, 6.20), (8.64, 6.20)]],
            "duct": None,
        },
        "pros": [
            "Unload at the dishwasher worktop, wash, prep, cook: no crossing an aisle.",
            "Main worktop stays clear when the dishwasher is open on the other side of the sink.",
            "Dining stays central, with a separate route to the balcony beside the sofa.",
            "No new partition; keeps the target AC position.",
        ],
        "cons": [
            "Boxed waste in the 10 cm rear void and around SH_vent; survey the stack inlet.",
            "Long fridge-to-hob leg is the trade-off for a single straight run.",
            "Check fridge hinge/filler at the riser and glass splashback over the east brick.",
        ],
    },
    {
        "slug": "E_nw_connected_peninsula",
        "title": "E · NW kitchen with connected peninsula",
        "summary": "Keep the OB1 sink point and get one straight 180 cm prep run.",
        "runs": {
            "north": {"origin": (2.48, 12.89), "dir": (1, 0), "normal": (0, -1), "modules": [
                ("dw", 0.45, {"role": "landing", "label": "DW45"}),
                ("sink", 0.60, {"label": "SINK 60"}),
                ("blind", 0.60),
            ]},
            "peninsula": {"origin": (4.13, 12.29), "dir": (0, -1), "normal": (-1, 0), "modules": [
                ("prep", 1.80, {"role": "main", "label": "MAIN PREP\n180"}),
                ("hob", 0.60, {"label": "HOB 60"}),
                ("prep", 0.45, {"role": "landing", "label": "LAND. 45"}),
            ]},
            "west": {"origin": (1.40, 10.82), "dir": (0, 1), "normal": (1, 0), "modules": [
                ("fridge", 0.60, {"label": "FRIDGE"}),
                ("prep", 0.60, {"role": "landing", "label": "FRIDGE\nLAND."}),
            ]},
        },
        "chain": [("north", False), ("peninsula", False)],
        "furniture": [
            HALL_WARDROBE,
            TANK_HOUSING,
            ("hob_back", rect(4.13, 9.44, 0.20, 1.30), "", "counter"),
            *dining(5.80, 11.20, depth=0.80, chairs_per_side=2),
            ("sofa", rect(6.05, 7.95, 0.95, 2.20), "SOFA\n220×95", "living"),
            ("coffee", rect(7.43, 8.50, 0.55, 1.10), "COFFEE", "living"),
            ("tv", rect(8.56, 8.65, 0.40, 1.20), "TV", "living"),
        ],
        "new_walls": [],
        "ac": None,
        "services": {
            "drain": [[(3.23, 12.59), (3.23, 12.89), (3.29, 12.89)]],
            "duct": None,
        },
        "pros": [
            "One uninterrupted 180 cm worktop between sink and hob; no freestanding island.",
            "Uses the existing sink connection and leaves the target AC in place.",
            "The peninsula screens the worktop without narrowing the OB2 approach.",
        ],
        "cons": [
            "Sink has 45 cm straight landing on the DW side; the other side turns the corner.",
            "Allow a finished end panel and verify balcony leaf, handles and trims on site.",
            "20 cm rear worktop extension at hob; verify appliance clearances and extraction.",
            "Fridge beside the HW tank: verify service and ventilation clearances.",
        ],
    },
    {
        "slug": "F_galley_with_180_wall",
        "title": "F · Galley: 1.80 m wall instead of an island",
        "summary": "New 0.10 m wall off the east wall, parallel to the hall, faces the alcove run 1.27 m away.",
        "runs": {
            "alcove": {"origin": (5.26, 7.455), "dir": (1, 0), "normal": (0, 1), "modules": [
                ("dw", 0.60, {"label": "DW"}),
                ("sink", 0.60, {"label": "SINK 60"}),
                ("prep", 1.20, {"role": "main", "label": "MAIN PREP\n120"}),
                ("hob", 0.60, {"label": "HOB 60"}),
                ("prep", 0.38, {"role": "landing", "label": "38"}),
            ]},
            "wall": {"origin": (8.96, 9.925), "dir": (-1, 0), "normal": (0, -1), "modules": [
                ("oven", 0.60, {"label": "OVEN\nTALL"}),
                ("prep", 0.60, {"role": "secondary", "label": "PREP 2\n60"}),
                ("fridge", 0.60, {"label": "FRIDGE"}),
            ]},
        },
        "chain": [("alcove", False), ("wall", False)],
        "furniture": [
            HALL_WARDROBE,
            TANK_HOUSING,
            *living_west(),
            *dining(6.10, 10.85),
        ],
        "new_walls": [("W_galley", rect(7.16, 9.925, 1.80, 0.10))],
        "ac": rect(8.74, 11.40, 0.22, 0.80),
        "services": {
            "drain": [[(6.16, 7.755), (6.16, 7.25), (7.95, 7.25), (7.95, 6.20), (8.64, 6.20)]],
            "duct": [(7.96, 7.60), (8.64, 7.60)],
            "ac_lines": [(7.57, 12.75), (8.85, 12.75), (8.85, 12.20)],
        },
        "pros": [
            "Sink, 120 cm prep and hob in one straight run; turn round to prep 2 by the fridge.",
            "Tight triangle with no corner units; the 1.27 m aisle stays out of the hall route.",
            "The wall hides the worktop from the living area and holds the tall units.",
            "Hob is beside SH_vent; sink waste takes the short bathroom-2 route to SH_san.",
        ],
        "cons": [
            "1.80 m of new partition, reinforced for the tall oven and fridge.",
            "AC must move off the bathroom-2 wall, e.g. high on the east wall.",
            "The wall cuts across the east brick strip; NW kitchen point is capped.",
            "The galley is visible from the entrance; the hob has only 38 cm of landing on the shaft side.",
        ],
    },
    {
        "slug": "G_nw_U_behind_entrance_wall",
        "title": "G · NW kitchen behind a 1.80 m entrance wall",
        "summary": "Wall runs east from the west wall just north of the entrance door; HW tank removed.",
        "tank_removed": True,
        "runs": {
            "south": {"origin": (2.00, 9.38), "dir": (1, 0), "normal": (0, 1), "modules": [
                ("prep", 0.60, {"role": "secondary", "label": "PREP 2\n60"}),
                ("fridge", 0.60, {"label": "FRIDGE"}),
            ]},
            "west": {"origin": (1.40, 9.98), "dir": (0, 1), "normal": (1, 0), "modules": [
                ("prep", 0.59, {"role": "landing", "label": "LAND.\n59"}),
                ("hob", 0.60, {"label": "HOB 60\n+ oven"}),
                ("prep", 0.60, {"role": "main", "label": "MAIN\nPREP"}),
            ]},
            "north": {"origin": (2.88, 12.89), "dir": (1, 0), "normal": (0, -1), "modules": [
                ("sink", 0.80, {"label": "SINK 80"}),
                ("dw", 0.45, {"label": "DW45"}),
            ]},
        },
        "extra_modules": [corner_option_a],
        "extra_args": ("MAIN PREP\non chamfer",),
        "chain": [("south", True), ("west", False), "corner", ("north", False)],
        "furniture": [
            HALL_WARDROBE,
            ("coats", rect(1.40, 9.28, 0.60, 0.60), "COATS\n60×60\nfrom hall", "hall"),
            *dining(4.90, 9.90, chairs_per_side=3, axis="y"),
            ("sideboard", rect(5.40, 7.455, 2.00, 0.40), "SIDEBOARD 200×40", "living"),
            ("sofa", rect(6.55, 9.27, 0.95, 2.20), "SOFA\n220×95", "living"),
            ("coffee", rect(7.75, 9.82, 0.50, 1.10), "COFFEE", "living"),
            ("tv", rect(8.56, 9.77, 0.40, 1.20), "TV", "living"),
        ],
        "new_walls": [("W_entry_screen", rect(2.00, 9.28, 1.20, 0.10)),
                      ("W_entry_closet_back", rect(1.40, 9.88, 0.60, 0.10))],
        "ac": None,
        "services": {
            "drain": [[(3.28, 12.59), (3.28, 12.89)]],
            "duct": None,
        },
        "pros": [
            "Sink stays on the existing OB1 water/waste point: no new kitchen drainage.",
            "170 cm continuous prep from the sink round the open chamfer to the hob.",
            "Fridge lands on prep 2 at the wall end, next to the hall for shopping.",
            "Wall screens the kitchen from the door; AC stays on the bathroom-2 wall.",
            "The dead kitchen corner is a full-height coat closet opening onto the hall.",
        ],
        "cons": [
            "Needs the HW tank relocated (already in the tender), plus 1.80 m of new wall.",
            "Custom angled carcass and worktop on the 1.29 m chamfer.",
            "Recirculating hood only; no ventilation shaft nearby.",
            "Closet is only 60×60: everyday coats; a sliding or 60 cm hinged door.",
        ],
    },
]



def entrance_wardrobe_variant(base):
    """G with the wall moved 0.60 north so a full wardrobe faces the hall."""
    option = copy.deepcopy(base)
    option.update(
        slug="G2_nw_U_with_entrance_wardrobe",
        title="G2 · As G, with a 180 cm wardrobe facing the entrance",
        summary="Wall moved 0.60 m north; the strip in front of the door becomes a full wardrobe.",
        new_walls=[("W_entry_screen", rect(1.40, 9.88, 1.80, 0.10))],
    )
    runs = option["runs"]
    runs["south"]["origin"] = (1.40, 9.98)
    runs["south"]["modules"].insert(0, ("blind", 0.60, {"label": ""}))
    runs["west"]["origin"] = (1.40, 10.58)
    runs["west"]["modules"] = runs["west"]["modules"][:2]
    option["furniture"] = [item for item in option["furniture"] if item[0] != "coats"]
    option["furniture"].append(("wardrobe", rect(1.40, 9.28, 1.80, 0.60),
                                "ENTRANCE WARDROBE 180×60", "hall"))
    option["pros"] = [
        "Sink stays on the existing OB1 point: no new kitchen drainage.",
        "Full 180×60 wardrobe opposite the door, 1.23 m clear hall in front of it.",
        "Still 110 cm prep round the chamfer + 60 cm by the fridge.",
        "Wall screens the kitchen from the door; AC stays on the bathroom-2 wall.",
    ]
    option["cons"] = [
        "Kitchen loses the 60 cm west prep unit: main prep is only the chamfer worktop.",
        "Custom angled carcass and worktop on the 1.29 m chamfer.",
        "Blind corner behind the wardrobe; recirculating hood only.",
        "Needs the HW tank relocated (already in the tender), plus 1.80 m of new wall.",
    ]
    return option


def corner_sink_variant(base):
    """G with the sink on the chamfer and the main prep under OB1."""
    option = copy.deepcopy(base)
    option.update(
        slug="H_nw_U_corner_sink_window_prep",
        title="H · As G, sink on the chamfer, prep under the window",
        summary="Sink moves about 1 m onto the chamfer; the worktop under OB1 becomes the prep.",
        extra_modules=[corner_sink],
        extra_args=(),
    )
    runs = option["runs"]
    runs["west"]["modules"] = [
        ("prep", 0.40, {"role": "landing", "label": "LAND.\n40"}),
        ("hob", 0.60, {"label": "HOB 60\n+ oven"}),
        ("prep", 0.79, {"role": "main", "label": "PREP\n79"}),
    ]
    runs["north"]["modules"] = [
        ("dw", 0.45, {"label": "DW45"}),
        ("prep", 0.80, {"role": "secondary", "label": "WINDOW\nPREP 80"}),
    ]
    option["services"] = {"drain": [[(2.33, 12.11), (2.60, 12.59), (3.28, 12.59), (3.28, 12.89)]],
                          "duct": None}
    option["pros"] = [
        "Prep under OB1 in daylight; no tap under the window sash.",
        "Sink still within about 1 m of the existing OB1 water/waste point.",
        "Dishwasher stays beside the sink; coat closet as in G.",
    ]
    option["cons"] = [
        "Sink to hob shrinks to 79 cm, so cutting moves away from the hob.",
        "Corner sink: deep diagonal cabinet, longer reach to the tap, awkward to stand at.",
        "Window prep is beyond the sink: wash, chop at the window, carry back past the sink.",
        "Custom angled sink cabinet; waste reroute in the plinth.",
    ]
    return option


def corner_sink():
    module = corner_option_a("SINK\non chamfer")
    module.kind, module.role = "sink", None
    return module


OPTIONS.append(entrance_wardrobe_variant(OPTIONS[-1]))
OPTIONS.append(corner_sink_variant(OPTIONS[-2]))


# Zones that must stay free of furniture, in every option.
KEEP_CLEAR = {
    "entrance landing": rect(1.40, 8.28, 0.90, 0.90),
    "corridor mouth": rect(2.42, 8.05, 0.90, 0.90),
    "balcony door OB2 approach": rect(4.13, 12.09, 1.46, 0.80),
}


# --------------------------------------------------------------------------
# Analysis
# --------------------------------------------------------------------------

class Space:
    def __init__(self, model, new_walls):
        rooms = {room["id"]: room for room in model["rooms"]}
        room = rooms[OPEN_SPACE]
        self.polygon = [tuple(p) for p in room["polygon"]]
        self.holes = [[tuple(p) for p in (rooms[i].get("footprint") or rooms[i]["polygon"])]
                      for i in room.get("subtract", [])]
        self.holes += [poly for _, poly in new_walls]

    def free(self, pt):
        return inside(pt, self.polygon) and not any(inside(pt, h) for h in self.holes)


def analyse(option, model):
    for run in option["runs"].values():
        build_run(run)
    extras = {"corner": factory(*option.get("extra_args", ())) for factory in option.get("extra_modules", [])}
    modules = [m for run in option["runs"].values() for m in run["built"]]
    modules += list(extras.values())
    option["modules"] = modules
    space = Space(model, option["new_walls"])

    obstacles = [(m.label or m.kind, m.poly) for m in modules]
    obstacles += [(label or kind, poly) for kind, poly, label, _ in option["furniture"]]

    for name, poly in obstacles:
        bad = [p for p in samples(poly) if not space.free(p)]
        assert not bad, f"{option['slug']}: {name!r} leaves the free floor at {bad[0]}"
    for i, (name_a, a) in enumerate(obstacles):
        for name_b, b in obstacles[i + 1:]:
            assert not overlaps(a, b), f"{option['slug']}: {name_a!r} overlaps {name_b!r}"
        for zone, poly in KEEP_CLEAR.items():
            assert not overlaps(a, poly), f"{option['slug']}: {name_a!r} blocks the {zone}"

    chain = chain_modules(option, extras)
    sink = next(i for i, m in enumerate(chain) if m.kind == "sink")
    hob = next(i for i, m in enumerate(chain) if m.kind == "hob")
    lo, hi = sorted((sink, hob))
    between = chain[lo + 1:hi]
    assert all(m.kind in COUNTER for m in between), "sink and hob must share a worktop"
    main_straight = straight_prep(between)
    secondary = straight_prep(chain, role="secondary")
    total_prep = main_straight + (secondary if secondary >= PREP_UNIT_MIN - EPS else 0.0)

    hob_sides = sorted((side_frontage(chain, hob, -1), side_frontage(chain, hob, 1)))
    sink_sides = sorted((side_frontage(chain, sink, -1), side_frontage(chain, sink, 1)))
    dw_adjacent = any(chain[j].kind == "dw" for j in (sink - 1, sink + 1) if 0 <= j < len(chain))
    fridge = next(m for m in modules if m.kind == "fridge")
    fridge_run = fridge.run["built"]
    fridge_idx = fridge_run.index(fridge)
    fridge_landing = max(side_frontage(fridge_run, fridge_idx, -1),
                         side_frontage(fridge_run, fridge_idx, 1))

    points = {"fridge": fridge.front_mid, "sink": chain[sink].front_mid, "hob": chain[hob].front_mid}
    legs = {
        "fridge–sink": math.dist(points["fridge"], points["sink"]),
        "sink–hob": math.dist(points["sink"], points["hob"]),
        "hob–fridge": math.dist(points["hob"], points["fridge"]),
    }

    aisle = aisle_width(option, space, obstacles)
    services = option["services"]
    drain = sum(polyline_length(route) for route in services["drain"])

    checks = [
        ("Main straight prep sink↔hob", f"{main_straight*100:.0f} cm",
         main_straight >= MAIN_PREP_MIN - EPS, f"≥ {MAIN_PREP_MIN*100:.0f} (aim {MAIN_PREP_GOOD*100:.0f}+)"),
        ("Secondary straight prep", f"{secondary*100:.0f} cm", secondary == 0 or secondary >= PREP_UNIT_MIN - EPS,
         f"optional; ≥ {PREP_UNIT_MIN*100:.0f} if split"),
        ("Total straight prep", f"{total_prep*100:.0f} cm", total_prep >= TOTAL_PREP_MIN - EPS, f"≥ {TOTAL_PREP_MIN*100:.0f}"),
        ("Hob straight landings", f"{hob_sides[0]*100:.0f} / {hob_sides[1]*100:.0f} cm",
         hob_sides[0] >= HOB_SIDE_MIN - EPS and hob_sides[1] >= HOB_SIDE_ONE - EPS, f"≥ {HOB_SIDE_MIN*100:.0f} / {HOB_SIDE_ONE*100:.0f}"),
        ("Sink straight landings", f"{sink_sides[0]*100:.0f} / {sink_sides[1]*100:.0f} cm",
         sink_sides[0] >= SINK_SIDE_MIN - EPS and sink_sides[1] >= SINK_SIDE_ONE - EPS, f"≥ {SINK_SIDE_MIN*100:.0f} / {SINK_SIDE_ONE*100:.0f}"),
        ("Fridge landing", f"{fridge_landing*100:.0f} cm", fridge_landing >= FRIDGE_LANDING - EPS, f"≥ {FRIDGE_LANDING*100:.0f}"),
        ("Dishwasher beside sink", "yes" if dw_adjacent else "no", dw_adjacent, "adjacent"),
        ("Triangle legs", " / ".join(f"{v:.2f}" for v in legs.values()) + " m",
         all(LEG_MIN - EPS <= v <= LEG_MAX + EPS for v in legs.values()), f"{LEG_MIN:.1f}–{LEG_MAX:.1f} m each"),
        ("Triangle total", f"{sum(legs.values()):.2f} m", sum(legs.values()) <= TRIANGLE_MAX, f"≤ {TRIANGLE_MAX:.1f} m"),
        ("Narrowest work aisle", f"{aisle:.2f} m", aisle >= AISLE_MIN - EPS, f"≥ {AISLE_MIN:.2f} m"),
    ]
    option["analysis"] = {
        "checks": checks,
        "points": points,
        "legs": legs,
        "drain_length": drain,
        "drain_fall": drain * DRAIN_FALL,
        "duct_length": polyline_length(services["duct"]) if services.get("duct") else None,
        "ac_lines": polyline_length(services["ac_lines"]) if services.get("ac_lines") else None,
        "new_wall_length": sum(max(bbox(p)[2] - bbox(p)[0], bbox(p)[3] - bbox(p)[1])
                               for _, p in option["new_walls"]),
    }
    return option


def straight_prep(modules, role=None):
    """Longest uninterrupted span, excluding blind and 90-degree corners."""
    best = length = 0.0
    previous = None
    for m in modules:
        if m.kind not in COUNTER or m.kind == "blind" or m.corner_leg or (
            len(m.front) != 2 and not m.open_joint) or (role is not None and m.role != role):
            previous, length = None, 0.0
            continue
        if previous is None or not continuous(previous, m):
            length = 0.0
        length += m.frontage
        best = max(best, length)
        previous = m
    return best


def aisle_width(option, space, obstacles, limit=3.0, step=0.01):
    narrowest = limit
    for m in option["modules"]:
        if m.kind == "blind" or len(m.front) != 2:
            continue
        n = m.run["normal"]
        (ax, ay), (bx, by) = m.front
        length = math.dist(m.front[0], m.front[1])
        count = max(int(length / 0.1), 1)
        others = [poly for _, poly in obstacles if poly is not m.poly]
        for k in range(count + 1):
            t = 0.05 + (length - 0.10) * k / count
            x = ax + (bx - ax) * t / length
            y = ay + (by - ay) * t / length
            d = step
            while d < limit:
                p = (x + n[0] * d, y + n[1] * d)
                if not space.free(p) or any(inside(p, o) for o in others):
                    break
                d += step
            narrowest = min(narrowest, d)
    return narrowest


# --------------------------------------------------------------------------
# Drawing
# --------------------------------------------------------------------------

def tp(pt):
    """Model metres to pixels on the clipped plan canvas, north up."""
    return (pt[0] - X0) * SCALE, (Y1 - pt[1]) * SCALE


def draw_poly(draw, poly, fill=None, outline=None, width=1):
    pixels = [tp(p) for p in poly]
    draw.polygon(pixels, fill=fill)
    if outline:
        draw.line(pixels + [pixels[0]], fill=outline, width=width)


def dashed(draw, points, fill, width=3, dash=9, gap=6):
    pixels = [tp(p) for p in points]
    for (x1, y1), (x2, y2) in zip(pixels, pixels[1:]):
        length = math.hypot(x2 - x1, y2 - y1)
        if not length:
            continue
        ux, uy = (x2 - x1) / length, (y2 - y1) / length
        pos = 0.0
        while pos < length:
            end = min(pos + dash, length)
            draw.line((x1 + ux * pos, y1 + uy * pos, x1 + ux * end, y1 + uy * end), fill=fill, width=width)
            pos += dash + gap


def label(draw, pt, text, size=11, bold=True, fill=None):
    fill = fill or COLORS["text"]
    halo = COLORS["wall"] if fill == "white" else "white"
    draw.multiline_text(tp(pt), text, font=font(size, bold), fill=fill,
                        anchor="mm", align="center", stroke_width=2, stroke_fill=halo)


def draw_door(draw, door):
    x, y = door["at"]
    w, d = door["size"]
    draw_poly(draw, rect(x, y, w, d), fill=COLORS["paper"])
    if not door.get("has_leaf", True):
        return
    hinge_end, side = door.get("swing", ["start", "+"])
    sign = 1 if side == "+" else -1
    if w < d:
        face = x + w if sign > 0 else x
        hinge = (face, y if hinge_end == "start" else y + d)
        closed = (0, 1 if hinge_end == "start" else -1)
        opened = (sign, 0)
        length = d
    else:
        face = y + d if sign > 0 else y
        hinge = (x if hinge_end == "start" else x + w, face)
        closed = (1 if hinge_end == "start" else -1, 0)
        opened = (0, sign)
        length = w
    arc = [(hinge[0] + length * (math.cos(t) * closed[0] + math.sin(t) * opened[0]),
            hinge[1] + length * (math.cos(t) * closed[1] + math.sin(t) * opened[1]))
           for t in [i * math.pi / 40 for i in range(21)]]
    draw.line([tp(p) for p in arc], fill=COLORS["door"], width=2)
    draw.line([tp(hinge), tp(arc[-1])], fill=COLORS["door"], width=4)


def draw_model(draw, model, option):
    rooms = {room["id"]: room for room in model["rooms"]}
    draw_poly(draw, [tuple(p) for p in model["outline"]], fill=COLORS["wall"])
    for room in model["rooms"]:
        fill = COLORS["open"] if room["id"] == OPEN_SPACE else (
            COLORS["bath"] if room["function"] == "bathroom" else COLORS["room"])
        draw_poly(draw, room["polygon"], fill=fill)
    for hole in rooms[OPEN_SPACE].get("subtract", []):
        draw_poly(draw, rooms[hole].get("footprint") or rooms[hole]["polygon"], fill=COLORS["wall"])
        draw_poly(draw, rooms[hole]["polygon"], fill=COLORS["bath"] if hole == 9 else COLORS["room"])
    for wall in model["walls"]:
        draw_poly(draw, rect(*wall["at"], *wall["size"]), fill=COLORS["wall"])
    for column in model.get("columns", []):
        draw_poly(draw, rect(*column["at"], *column["size"]), fill="#555")
    for shaft in model["shafts"]:
        poly = rect(*shaft["at"], *shaft["size"])
        draw_poly(draw, poly, fill=COLORS["shaft"])
        x0, y0, x1, y1 = bbox(poly)
        label(draw, ((x0 + x1) / 2, (y0 + y1) / 2), shaft["id"].replace("SH_", ""), 9, fill="white")
    for window in model["windows"]:
        poly = rect(*window["at"], *window["size"])
        draw_poly(draw, poly, fill=COLORS["window"], outline="#3c7fb1")
        x0, y0, x1, y1 = bbox(poly)
        if y1 > Y0:
            label(draw, ((x0 + x1) / 2, (y0 + y1) / 2), window["id"], 10)
    for door in model["doors"]:
        draw_door(draw, door)
    for _, poly in option["new_walls"]:
        draw_poly(draw, poly, fill=COLORS["new_wall"])
    for finish in model.get("wall_finishes", []):
        dashed(draw, finish["segment"], COLORS["brick"], width=5, dash=6, gap=3)
    for terminal in model.get("service_terminals", []):
        if terminal["room"] == OPEN_SPACE:
            px, py = tp(terminal["at"])
            draw.ellipse((px - 7, py - 7, px + 7, py + 7), fill="white", outline=COLORS["drain"], width=3)
    for name in (8, 9, 4):
        room = rooms[name]
        x0, y0, x1, y1 = bbox(room["polygon"])
        at = room.get("label_at") or ((x0 + x1) / 2, (y0 + y1) / 2)
        if Y0 < at[1] < Y1:
            label(draw, at, room["name"], 11, bold=False, fill=COLORS["muted"])


def draw_option(draw, model, option):
    draw_model(draw, model, option)
    for zone in KEEP_CLEAR.values():
        dashed(draw, zone + zone[:1], COLORS["keep_clear"], width=1, dash=4, gap=4)

    for kind, poly, text, group in option["furniture"]:
        fill = COLORS[group]
        draw_poly(draw, poly, fill=fill, outline=COLORS["wall"], width=2)
        if text:
            x0, y0, x1, y1 = bbox(poly)
            label(draw, ((x0 + x1) / 2, (y0 + y1) / 2), text, 10)
    for item in model.get("equipment", []):
        if item["id"] == "HW_TANK_100L" and not option.get("tank_removed"):
            x, y, _ = item["at"]
            w, d, _ = item["size"]
            draw.ellipse([tp((x + 0.03, y + d - 0.03)), tp((x + w - 0.03, y + 0.03))],
                         outline=COLORS["tall"], width=2)
        if item["id"] == "AC_living" and option["ac"] is None:
            draw_poly(draw, rect(*item["at"][:2], *item["size"][:2]), fill=COLORS["ac"])
    if option["ac"]:
        draw_poly(draw, option["ac"], fill=COLORS["ac"])
        x0, y0, x1, y1 = bbox(option["ac"])
        label(draw, (x0 - 0.18, (y0 + y1) / 2), "AC", 10, fill=COLORS["ac"])

    for m in option["modules"]:
        if m.kind in TALL:
            fill = COLORS["tall"]
        elif m.kind in {"sink", "hob", "dw"}:
            fill = COLORS["appliance"] if m.kind == "dw" else COLORS["counter"]
        else:
            fill = COLORS["counter"]
        draw_poly(draw, m.poly, fill=fill, outline=COLORS["wall"], width=2)
        if m.role in {"main", "secondary"}:
            draw_poly(draw, m.poly, fill=COLORS["prep"], outline=COLORS["wall"], width=2)
        x0, y0, x1, y1 = bbox(m.poly)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if m.kind == "sink":
            draw.rounded_rectangle([tp((cx - 0.20, cy + 0.20)), tp((cx + 0.20, cy - 0.20))],
                                   radius=6, fill="white", outline=COLORS["wall"], width=2)
        if m.kind == "hob":
            for dx in (-0.14, 0.14):
                for dy in (-0.13, 0.13):
                    px, py = tp((cx + dx, cy + dy))
                    draw.ellipse((px - 9, py - 9, px + 9, py + 9), outline=COLORS["wall"], width=2)
        if m.kind == "blind":
            draw.line([tp((x0, y0)), tp((x1, y1))], fill=COLORS["muted"], width=1)
            draw.line([tp((x0, y1)), tp((x1, y0))], fill=COLORS["muted"], width=1)
        if m.label:
            label(draw, (cx, cy), m.label, 9 if m.kind in TALL else 10,
                  fill="white" if m.kind in TALL else COLORS["text"])

    services = option["services"]
    for route in services["drain"]:
        dashed(draw, route, COLORS["drain"], width=3)
    if services.get("duct"):
        dashed(draw, services["duct"], COLORS["duct"], width=4)
    if services.get("ac_lines"):
        dashed(draw, services["ac_lines"], COLORS["ac"], width=3)

    points = option["analysis"]["points"]
    loop = [points["fridge"], points["sink"], points["hob"], points["fridge"]]
    dashed(draw, loop, COLORS["triangle"], width=3, dash=5, gap=5)
    for p in points.values():
        px, py = tp(p)
        draw.ellipse((px - 6, py - 6, px + 6, py + 6), fill=COLORS["triangle"])
    for (name, length), (p, q) in zip(option["analysis"]["legs"].items(), zip(loop, loop[1:])):
        label(draw, ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2), f"{length:.2f}", 10, fill=COLORS["triangle"])


def draw_panel(draw, option, x, y):
    a = option["analysis"]
    draw.text((x, y), "Ergonomic checks (computed from the layout)", font=font(19, True), fill=COLORS["text"])
    y += 34
    for name, value, ok, rule in a["checks"]:
        colour = COLORS["ok"] if ok else COLORS["fail"]
        draw.text((x, y), "✓" if ok else "✗", font=font(18, True), fill=colour)
        draw.text((x + 26, y + 2), name, font=font(15), fill=COLORS["text"])
        draw.text((x + 250, y + 2), value, font=font(15, True), fill=colour)
        draw.text((x + 560, y + 2), rule, font=font(13), fill=COLORS["muted"])
        y += 27
    y += 12
    draw.text((x, y), "Services", font=font(19, True), fill=COLORS["text"])
    y += 32
    lines = []
    if a["drain_length"] > 0.5:
        lines.append(f"Concept waste to SH_san: {a['drain_length']:.2f} m in plan, "
                     f"fall ≈ {a['drain_fall']*100:.0f} cm at {DRAIN_FALL*100:.0f}%")
    else:
        lines.append(f"Sink on existing OB1 point: {a['drain_length']:.2f} m new waste")
    lines.append(f"Hood duct study: {a['duct_length']:.2f} m; dedicated outlet not confirmed"
                 if a["duct_length"] else "Hood: recirculating; keep room ventilation independent")
    if a["ac_lines"]:
        lines.append(f"AC moved high on east wall: {a['ac_lines']:.2f} m line extension from OB3")
    if a["new_wall_length"]:
        lines.append(f"New partition: {a['new_wall_length']:.2f} m × 2.70 m (red)")
    for line in lines:
        draw.text((x, y), "• " + line, font=font(15), fill=COLORS["text"])
        y += 24
    for heading, items, colour in (("For", option["pros"], COLORS["ok"]),
                                   ("Against", option["cons"], COLORS["fail"])):
        y += 12
        draw.text((x, y), heading, font=font(19, True), fill=colour)
        y += 30
        for item in items:
            draw.text((x, y), "• " + item, font=font(15), fill=COLORS["text"])
            y += 24


def draw_legend(draw, x, y):
    entries = [
        (COLORS["prep"], "prep worktop"), (COLORS["counter"], "worktop / landing"),
        (COLORS["tall"], "tall unit"), (COLORS["appliance"], "dishwasher"),
        (COLORS["new_wall"], "new wall"), (COLORS["living"], "living"),
        (COLORS["dining"], "dining"), (COLORS["hall"], "hall"),
    ]
    for colour, text in entries:
        draw.rectangle((x, y, x + 22, y + 16), fill=colour, outline=COLORS["wall"])
        draw.text((x + 30, y + 8), text, font=font(13), fill=COLORS["muted"], anchor="lm")
        x += 40 + draw.textlength(text, font=font(13))
    for colour, text in ((COLORS["triangle"], "work triangle"), (COLORS["drain"], "new waste"),
                         (COLORS["duct"], "hood duct"), (COLORS["ac"], "AC lines"),
                         (COLORS["keep_clear"], "keep clear")):
        dashed_px(draw, (x, y + 8), (x + 30, y + 8), colour)
        draw.text((x + 38, y + 8), text, font=font(13), fill=COLORS["muted"], anchor="lm")
        x += 50 + draw.textlength(text, font=font(13))


def dashed_px(draw, a, b, colour):
    for k in range(0, int(b[0] - a[0]), 9):
        draw.line((a[0] + k, a[1], min(a[0] + k + 5, b[0]), a[1]), fill=colour, width=3)


def render(model, option, path):
    plan_w = int((X1 - X0) * SCALE)
    plan_h = int((Y1 - Y0) * SCALE)
    image = Image.new("RGB", (PAD * 2 + plan_w + PANEL_W, TOP + plan_h + 90), COLORS["background"])
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((15, 15, image.width - 15, image.height - 15), radius=20, fill=COLORS["paper"])
    draw.text((PAD, 32), option["title"], font=font(30, True), fill=COLORS["text"])
    draw.text((PAD, 76), option["summary"] + "  Furniture checked for overlaps and keep-clear zones.",
              font=font(17), fill=COLORS["muted"])
    plan = Image.new("RGB", (plan_w, plan_h), COLORS["paper"])
    draw_option(ImageDraw.Draw(plan), model, option)
    image.paste(plan, (PAD, TOP))
    draw_panel(draw, option, PAD + plan_w + 30, TOP + 10)
    draw_legend(draw, PAD, TOP + plan_h + 30)
    image.save(path, optimize=True)
    return image


def overview(images, options, path):
    thumb_w = 900
    thumbs = [img.resize((thumb_w, int(img.height * thumb_w / img.width)), Image.LANCZOS) for img in images]
    gap = 24
    width = thumb_w * 2 + gap * 3
    height = 150 + sum(t.height + gap for t in thumbs[::2]) + gap
    sheet = Image.new("RGB", (width, height), COLORS["background"])
    draw = ImageDraw.Draw(sheet)
    draw.text((gap, 24), "OPEN SPACE — KITCHEN + FURNITURE OPTIONS", font=font(32, True), fill=COLORS["text"])
    draw.text((gap, 72), "Aim for 120 cm clear between sink and hob + 60 cm secondary, "
              "or one uninterrupted 160–180 cm run.", font=font(18), fill=COLORS["muted"])
    draw.text((gap, 100), "Work aisles are measured with appliances shut and chairs as drawn. "
              "Verify swings, service heights and finishes on site.", font=font(18), fill=COLORS["muted"])
    y = 150
    for index, thumb in enumerate(thumbs):
        x = gap + (index % 2) * (thumb_w + gap)
        sheet.paste(thumb, (x, y))
        if index % 2 == 1:
            y += thumb.height + gap
    sheet.save(path, optimize=True)


def main(model_path=MODEL, out_dir=OUT_DIR):
    model = load_model(model_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    images = []
    for option in OPTIONS:
        analyse(option, model)
        path = out_dir / f"{option['slug']}.png"
        images.append(render(model, option, path))
        passed = sum(ok for _, _, ok, _ in option["analysis"]["checks"])
        print(f"{option['slug']}: {passed}/{len(option['analysis']['checks'])} checks → {path}")
        for name, value, ok, rule in option["analysis"]["checks"]:
            print(f"   {'ok ' if ok else 'BAD'} {name:24s} {value:28s} {rule}")
    overview(images, OPTIONS, out_dir / "overview.png")
    print(f"overview → {out_dir / 'overview.png'}")


if __name__ == "__main__":
    main(*sys.argv[1:])
