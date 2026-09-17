# Flat Renovation Pipeline

BIM pipeline for a flat renovation in Warsaw: an **as-is** (surveyed) IFC model
with visual verification against the original scaled survey drawing, and
(planned) a **target** state plus a contractor tender PDF package.

## Source of truth

`data/as_is.yaml` is the single authoritative dataset — outline, rooms, walls,
columns, service shafts, doors, windows, balcony. Everything else is generated.
Written dimensions from the survey are authoritative; the photo is used for
topology and positions.

Survey scan: `7106fea6-ce4f-4979-8eac-ebf5f4a6972b.jfif` (to scale, ~99 px/m).

## Scripts

- `scripts/check_layout.py` — fast PIL verification render of the YAML.
- `scripts/overlay_scan.py` — overlays the model on the survey photo, auto-fits
  the transform, reports habitable-area IoU and inner-face deviation.
- `scripts/detect_windows.py` — finds window openings as breaks in the wall poché.
- `scripts/yaml_to_json.py` — bridge; Blender's Python has no PyYAML.
- `scripts/build_ifc.py` — builds IFC4 with real `IfcOpeningElement` voids.
- `scripts/plan_symbols.py` — plan symbols for doors and windows, shared
  between the IFC builder and the annotator so leaf and swing arc agree.
- `scripts/annotate_drawing.py` — creates the `IfcAnnotation` room labels,
  dimension chains and door swing arcs that Bonsai renders.
- `scripts/export_bonsai_drawings.py` — Bonsai-native drawings/sheets → SVG + PDF,
  A3 portrait @ 1:50 with the Polish titleblock in `data/titleblocks/A3-PL.svg`.

## Rebuild after any YAML edit

```sh
python3 scripts/check_layout.py data/as_is.yaml exports/check/as_is_transcription_check.png
python3 scripts/yaml_to_json.py data/as_is.yaml build/as_is.json
/snap/bin/blender -b --python scripts/build_ifc.py -- build/as_is.json exports/as_is.ifc
python3 scripts/overlay_scan.py data/as_is.yaml 7106fea6-ce4f-4979-8eac-ebf5f4a6972b.jfif exports/check/overlay_on_scan.png
/snap/bin/blender -b --python scripts/export_bonsai_drawings.py -- exports/as_is.ifc exports/drawings
```

Blender must be `/snap/bin/blender` (5.2 LTS, has Bonsai 0.8.6); `/usr/bin/blender`
has no Bonsai.

## Outputs

- `exports/as_is.ifc` — 20 walls, 6 doors, 6 windows, 6 spaces.
- `exports/check/` — verification renders and photo overlay/diff.
- `exports/drawings/sheets/A01 - RZUT - STAN ISTNIEJĄCY.pdf` — the dimensioned
  A3 @ 1:50 plan for contractors; also as SVG, with the raw drawing and the
  layout alongside.

## Status

As-is model complete and photo-verified (habitable IoU 87.3%, median inner-face
deviation 30 mm, total 95.56 m² against the stated 95.5 m²). The dimensioned
A3 @ 1:50 tender plan is generated end to end.

Not yet done: the target (renovated) state, bill of quantities per trade with
contractor price columns, 3D before/after renders, and the combined tender PDF
package.

Door swing directions are inferred, not surveyed; they are set explicitly per
door via `swing: [hinge, side]` in `data/as_is.yaml` and should be confirmed
on site.
