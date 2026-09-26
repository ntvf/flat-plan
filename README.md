# Flat Renovation Pipeline

BIM pipeline for a flat renovation in Warsaw: an **as-is** (surveyed) IFC model
with visual verification against the original scaled survey drawing, and a
**target** state with a second bathroom, relocated air conditioner, and
contractor drawing. Bathroom fit-out and the complete tender package are still
being designed.

## Source of truth

`data/as_is.yaml` is the authoritative surveyed dataset. `data/target.yaml`
extends it through explicit additions and updates, avoiding a duplicate copy of
retained geometry. Everything under `build/` and `exports/` is generated.
Written dimensions from the survey are authoritative; the photo is used for
topology and positions.

Survey scan: `7106fea6-ce4f-4979-8eac-ebf5f4a6972b.jfif` (to scale, ~99 px/m).
Concept studies under `exports/concepts/` are generated design aids, not
authoritative model data.

## Scripts

- `scripts/check_layout.py` — fast PIL verification render of the YAML.
- `scripts/overlay_scan.py` — overlays the model on the survey photo, auto-fits
  the transform, reports habitable-area IoU and inner-face deviation.
- `scripts/detect_windows.py` — finds window openings as breaks in the wall poché.
- `scripts/model_loader.py` — resolves target overlays against the as-is model
  and validates additions and updates.
- `scripts/yaml_to_json.py` — bridge; Blender's Python has no PyYAML.
- `scripts/build_ifc.py` — builds IFC4 geometry, openings, spaces, equipment,
  service routes, surveyed service terminals, and traceable finish properties.
- `scripts/plan_symbols.py` — plan symbols for doors and windows, shared
  between the IFC builder and the annotator so leaf and swing arc agree.
- `scripts/annotate_drawing.py` — creates the `IfcAnnotation` room labels,
  dimension chains, door swing arcs, and service-terminal marks that Bonsai
  renders.
- `scripts/export_bonsai_drawings.py` — Bonsai-native drawings/sheets → SVG + PDF,
  A3 portrait @ 1:50 with the Polish titleblock in `data/titleblocks/A3-PL.svg`.
- `scripts/render_textured_views.py` — renders three fixed target-state interior
  views and saves the prepared Blender scene.
- `scripts/sketch_bathroom_layouts.py` — generates six comparative fixture-layout
  concepts for the existing and proposed bathrooms, with all proposed water
  and waste routes kept out of the floor in accessible wall/plinth boxes.

## Rebuild after any YAML edit

Install the host-Python dependencies once with:

```sh
python3 -m pip install -r requirements.txt
```

Then rebuild the complete as-is deliverable with:

```sh
make as-is
```

The individual commands remain:

```sh
python3 scripts/check_layout.py data/as_is.yaml exports/check/as_is_transcription_check.png
python3 scripts/yaml_to_json.py data/as_is.yaml build/as_is.json
/snap/bin/blender -b --python scripts/build_ifc.py -- build/as_is.json exports/as_is.ifc
python3 scripts/overlay_scan.py data/as_is.yaml 7106fea6-ce4f-4979-8eac-ebf5f4a6972b.jfif exports/check/overlay_on_scan.png
/snap/bin/blender -b --python scripts/export_bonsai_drawings.py -- exports/as_is.ifc exports/drawings/as_is build/as_is.json
```

Blender must be `/snap/bin/blender` (5.2 LTS, has Bonsai 0.8.6); `/usr/bin/blender`
has no Bonsai.

`make STATE=<name> model` builds another state from `data/<name>.yaml`.
`make target` builds the renovated model and its sheet under
`exports/drawings/target/`, separately from the as-is deliverables.

Generate the target visualisations and bathroom layout studies separately:

```sh
/snap/bin/blender -b --python scripts/render_textured_views.py -- exports/target.ifc exports/renders/target
python3 scripts/sketch_bathroom_layouts.py
```

## Outputs

- `exports/as_is.ifc` — 20 walls, 3 doors, 5 unfilled interior openings,
  5 windows, and 6 spaces, plus surveyed equipment, AC routing, service
  terminals, floor buildup, shafts, and brick-tile wall finishes.
- `exports/target.ifc` — 22 walls, 9 doors, 5 windows, and 7 spaces; relocates
  the living-area AC and extends its retained line set above the new bathroom.
- `exports/check/` — verification renders and photo overlay/diff.
- `exports/drawings/as_is/sheets/A01 - RZUT - STAN ISTNIEJĄCY.pdf` — the dimensioned
  A3 @ 1:50 plan for contractors; also as SVG, with the raw drawing and the
  layout alongside.
- `exports/drawings/target/sheets/A01 - RZUT - STAN PROJEKTOWANY.pdf` — the
  separate target-state A3 @ 1:50 plan.
- `exports/renders/target/` — three fixed textured PNG views and the generated
  Blender scene.
- `exports/concepts/bathroom_layouts/` — six fixture-layout studies and a
  comparison overview, showing boxed surface pipe routes to the surveyed
  connection points and `SH_san`; these have not yet been adopted into
  `data/target.yaml`.

## Status

The as-is geometry is complete and photo-verified (habitable IoU 87.3%, median
inner-face deviation 30 mm, total 95.57 m² against the stated 95.0 m²). It now
also records the existing AC and concealed line set, 100 l hot-water tank,
brick-tile wall finishes, bathroom and kitchen service connection points, and
the reported 100 mm floor buildup. Unknown concealed routes, drain inverts,
connection heights, and the exact insulation product remain explicitly marked
for on-site verification.

The target adds bathroom 9 between the storage and east façade. Its north
plasterboard wall runs from the storage to the south edge of `SH_vent`; its
south closure fills the 1.08 m gap beside the existing 2.30 m wall. The current
door assumption is an 0.80 m leaf opening outward into the corridor. The
living-area AC moves to the new north partition with backing requirements and
a modeled extension of the retained OB3 line set above the bathroom ceiling.

Six bathroom fixture-layout concepts have been generated, but no option has
been selected or promoted into the target model. Bathroom fixtures, hot/cold
water, sanitary drainage with verified falls and inverts, ventilation,
penetrations, waterproofing, electrical changes, and finish zones are therefore
not yet modeled.

Also not yet done: as-is/target delta and work-package generation, bill of
quantities per trade with contractor price columns, stable matched before/after
renders, and the combined tender PDF package.

The as-is interior entries are unfilled 0.90 m wall openings. Actual as-is
doors are the entrance, balcony door OB2, and the east panel of the room 6
corner glazing. Target interior door swing directions are inferred rather than
surveyed and should be confirmed on site.
