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

# (hinge, side): hinge is which end of the opening the leaf is fixed to,
# side is which face of the wall it swings out from.
DEFAULT_SWING = ("start", "+")


def _axis(w, d):
    """True when the opening runs along X (a wall running east-west)."""
    return w >= d


def window_panes(w, d, height):
    """Two panes inset from each wall face, so the plan cut shows the standard
    pair of parallel lines rather than a solid block."""
    t, i = PANE_THICKNESS, PANE_INSET
    if _axis(w, d):
        # Wall runs along X; d is the wall thickness.
        if d < 2 * (i + t):
            return [(0.0, 0.0, 0.0, w, d, height)]
        return [(0.0, i, 0.0, w, t, height),
                (0.0, d - i - t, 0.0, w, t, height)]
    if w < 2 * (i + t):
        return [(0.0, 0.0, 0.0, w, d, height)]
    return [(i, 0.0, 0.0, t, d, height),
            (w - i - t, 0.0, 0.0, t, d, height)]


def door_leaf(w, d, height, swing=None):
    """A single leaf standing open at 90 degrees to the wall."""
    hinge, side = swing or DEFAULT_SWING
    t = LEAF_THICKNESS

    if _axis(w, d):
        # Wall runs along X, clear width w, thickness d; leaf projects in Y.
        x = 0.0 if hinge == "start" else w - t
        y = d if side == "+" else -w
        return [(x, y, 0.0, t, w, height)]

    # Wall runs along Y, clear width d, thickness w; leaf projects in X.
    y = 0.0 if hinge == "start" else d - t
    x = w if side == "+" else -d
    return [(x, y, 0.0, d, t, height)]


def door_swing_arc(at, size, swing=None, segments=12):
    """The quarter-circle swept by the leaf, as a polyline in model
    coordinates. Starts at the open leaf tip and ends at the shut position, so
    it closes the conventional door symbol."""
    import math

    x0, y0 = at
    w, d = size
    hinge, side = swing or DEFAULT_SWING

    if _axis(w, d):
        radius = w
        hx = x0 if hinge == "start" else x0 + w
        hy = y0 + d if side == "+" else y0
        # Angle of the open leaf, and the direction the shut leaf points.
        open_angle = math.pi / 2 if side == "+" else -math.pi / 2
        shut_angle = 0.0 if hinge == "start" else math.pi
    else:
        radius = d
        hx = x0 + w if side == "+" else x0
        hy = y0 if hinge == "start" else y0 + d
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
