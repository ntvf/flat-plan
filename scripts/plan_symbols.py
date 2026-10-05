"""
Plan symbols for doors and windows.

A door or window modelled as one solid box is invisible in a plan drawing: the
box exactly refills the opening it sits in and is drawn with the same black
"cut" fill as the wall, so the wall reads as continuous. Both therefore need
geometry that survives the plan cut as the conventional symbol:

  * a window is two panes separated by a gap,
  * a door is a thin leaf standing open at 90 degrees, plus a swing arc.

Shared by build_ifc.py (which builds the solids) and annotate_drawing.py
(which draws the arcs), so the arc always matches the leaf.

Geometry convention, matching `data/*.yaml`: an opening has its lower-left
corner at `at` and extent `size` = [w, d]. The longer of w/d is the clear
width; the shorter is the wall thickness. All coordinates returned here are
local to `at`.
"""

PANE_THICKNESS = 0.05
PANE_INSET = 0.03
LEAF_THICKNESS = 0.04
FRAME_WIDTH = 0.06
FRAME_DEPTH = 0.08
FRAME_TRIM = 0.05

# (hinge, side): hinge is which end of the opening the leaf is fixed to,
# side is which face of the wall it swings out from.
DEFAULT_SWING = ("start", "+")


def _axis(w, d):
    """True when the opening runs along X (a wall running east-west)."""
    return w >= d


def window_panes(w, d, height, panel_count=2):
    """Glazing split into framed panels, with two plan-visible glass layers."""
    t, i = PANE_THICKNESS, PANE_INSET
    f = FRAME_WIDTH
    panel_count = max(1, int(panel_count))
    clear_length = (w if _axis(w, d) else d) - (panel_count + 1) * f
    panel_width = clear_length / panel_count
    clear_height = height - 2 * f
    if panel_width <= 0 or clear_height <= 0:
        panel_count = 1
        panel_width = max(w, d)
        f = 0.0
        clear_height = height

    parts = []
    if _axis(w, d):
        if d < 2 * (i + t):
            return [(0.0, 0.0, 0.0, w, d, height)]
        for panel in range(panel_count):
            x = f + panel * (panel_width + f)
            parts.extend([
                (x, i, f, panel_width, t, clear_height),
                (x, d - i - t, f, panel_width, t, clear_height),
            ])
        return parts
    if w < 2 * (i + t):
        return [(0.0, 0.0, 0.0, w, d, height)]
    for panel in range(panel_count):
        y = f + panel * (panel_width + f)
        parts.extend([
            (i, y, f, t, panel_width, clear_height),
            (w - i - t, y, f, t, panel_width, clear_height),
        ])
    return parts


def window_frame(w, d, height, panel_count=2):
    """Perimeter frame and mullions for renderable multi-panel windows."""
    f = FRAME_WIDTH
    depth = min(FRAME_DEPTH, d if _axis(w, d) else w)
    panel_count = max(1, int(panel_count))
    parts = []
    if _axis(w, d):
        y = (d - depth) / 2
        parts.extend([
            (0.0, y, 0.0, w, depth, f),
            (0.0, y, height - f, w, depth, f),
            (0.0, y, f, f, depth, height - 2 * f),
            (w - f, y, f, f, depth, height - 2 * f),
        ])
        step = (w - f) / panel_count
        for panel in range(1, panel_count):
            x = panel * step
            parts.append((x - f / 2, y, f, f, depth, height - 2 * f))
        return parts

    x = (w - depth) / 2
    parts.extend([
        (x, 0.0, 0.0, depth, d, f),
        (x, 0.0, height - f, depth, d, f),
        (x, 0.0, f, depth, f, height - 2 * f),
        (x, d - f, f, depth, f, height - 2 * f),
    ])
    step = (d - f) / panel_count
    for panel in range(1, panel_count):
        y = panel * step
        parts.append((x, y - f / 2, f, depth, height - 2 * f))
    return parts


def window_handles(w, d, height, panel_count=2):
    """Small render-only handles, one per window panel."""
    f = FRAME_WIDTH
    depth = min(FRAME_DEPTH, d if _axis(w, d) else w)
    panel_count = max(1, int(panel_count))
    parts = []
    handle_z = max(f, height * 0.46)
    if _axis(w, d):
        panel_width = (w - (panel_count + 1) * f) / panel_count
        y = (d + depth) / 2
        for panel in range(panel_count):
            x = f + panel * (panel_width + f) + panel_width - 0.025
            parts.extend([
                (x, y, handle_z, 0.02, 0.025, 0.13),
                (x, y, handle_z + 0.09, 0.08, 0.025, 0.02),
            ])
        return parts

    panel_width = (d - (panel_count + 1) * f) / panel_count
    x = (w + depth) / 2
    for panel in range(panel_count):
        y = f + panel * (panel_width + f) + panel_width - 0.025
        parts.extend([
            (x, y, handle_z, 0.025, 0.02, 0.13),
            (x, y, handle_z + 0.09, 0.025, 0.08, 0.02),
        ])
    return parts


def door_leaf(w, d, height, swing=None, leaf_width=None):
    """A single leaf standing open at 90 degrees to the wall."""
    hinge, side = swing or DEFAULT_SWING
    t = LEAF_THICKNESS
    opening_width = w if _axis(w, d) else d
    leaf_width = min(float(leaf_width or opening_width), opening_width)
    inset = (opening_width - leaf_width) / 2

    if _axis(w, d):
        x = inset if hinge == "start" else w - inset - t
        y = d if side == "+" else -leaf_width
        return [(x, y, 0.0, t, leaf_width, height)]

    y = inset if hinge == "start" else d - inset - t
    x = w if side == "+" else -leaf_width
    return [(x, y, 0.0, leaf_width, t, height)]


def door_frame(w, d, height):
    """Architrave around a rough opening without reducing its clear width."""
    trim = FRAME_TRIM
    depth_extra = 0.02
    if _axis(w, d):
        return [
            (-trim, -depth_extra, 0.0, trim, d + 2 * depth_extra, height + trim),
            (w, -depth_extra, 0.0, trim, d + 2 * depth_extra, height + trim),
            (-trim, -depth_extra, height, w + 2 * trim,
             d + 2 * depth_extra, trim),
        ]
    return [
        (-depth_extra, -trim, 0.0, w + 2 * depth_extra, trim, height + trim),
        (-depth_extra, d, 0.0, w + 2 * depth_extra, trim, height + trim),
        (-depth_extra, -trim, height, w + 2 * depth_extra,
         d + 2 * trim, trim),
    ]


def door_swing_arc(at, size, swing=None, segments=12, leaf_width=None):
    """The quarter-circle swept by the leaf, as a polyline in model
    coordinates. Starts at the open leaf tip and ends at the shut position, so
    it closes the conventional door symbol."""
    import math

    x0, y0 = at
    w, d = size
    hinge, side = swing or DEFAULT_SWING
    opening_width = w if _axis(w, d) else d
    radius = min(float(leaf_width or opening_width), opening_width)
    inset = (opening_width - radius) / 2

    if _axis(w, d):
        hx = x0 + inset if hinge == "start" else x0 + w - inset
        hy = y0 + d if side == "+" else y0
        # Angle of the open leaf, and the direction the shut leaf points.
        open_angle = math.pi / 2 if side == "+" else -math.pi / 2
        shut_angle = 0.0 if hinge == "start" else math.pi
    else:
        hx = x0 + w if side == "+" else x0
        hy = y0 + inset if hinge == "start" else y0 + d - inset
        open_angle = 0.0 if side == "+" else math.pi
        shut_angle = math.pi / 2 if hinge == "start" else -math.pi / 2

    # Sweep the short way round, which is always the 90 degree quadrant.
    delta = shut_angle - open_angle
    while delta > math.pi:
        delta -= 2 * math.pi
    while delta < -math.pi:
        delta += 2 * math.pi

    return [(hx + radius * math.cos(open_angle + delta * i / segments),
             hy + radius * math.sin(open_angle + delta * i / segments))
            for i in range(segments + 1)]
