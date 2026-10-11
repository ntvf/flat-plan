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

Survey scan: `data/survey-plan.jfif` (to scale, ~99 px/m).
Concept studies under `exports/concepts/` are generated design aids, not
authoritative model data.

## Project structure

```text
data/           Authoritative models, survey, and drawing templates
scripts/        Model validation, IFC generation, drawings, and visualisations
tests/          Model-loading regression tests
build/          Generated intermediate data (ignored)
exports/        Generated IFC, drawings, checks, and renders (ignored)
```

## Main scripts

- `scripts/check_layout.py` — fast PIL verification render of the YAML.
- `scripts/overlay_scan.py` — overlays the model on the survey photo, auto-fits
  the transform, reports habitable-area IoU and inner-face deviation.
- `scripts/detect_windows.py` — finds window openings as breaks in the wall poché.
- `scripts/model_loader.py` — resolves target overlays against the as-is model
  and validates additions and updates.
- `scripts/yaml_to_json.py` — bridge; Blender's Python has no PyYAML.
- `scripts/build_ifc.py` — builds IFC4 geometry, openings, spaces, equipment,
  service routes, surveyed service terminals, and traceable finish properties;
  sanitary fixtures and the washer use dimensioned, recognizable 3D geometry
  rather than generic equipment blocks.
- `scripts/plan_symbols.py` — standard-size door leaves and frames plus
  multi-panel window glazing, wood frames, and handles; shared with the
  annotator so each leaf and swing arc agree.
- `scripts/annotate_drawing.py` — creates the `IfcAnnotation` room labels,
  dimension chains, door swing arcs, and service-terminal marks that Bonsai
  renders.
- `scripts/export_bonsai_drawings.py` — Bonsai-native drawings/sheets → SVG + PDF,
  A3 portrait @ 1:50 with the Polish titleblock in `data/titleblocks/A3-PL.svg`.
- `scripts/render_textured_views.py` — renders an ultra-wide overview plus five
  wide-angle target-state interior views and saves the prepared Blender scene.
- `scripts/sketch_bathroom_layouts.py` — generates the working balanced fixture
  layout for the existing and proposed bathrooms.
- `scripts/sketch_living_layout.py` — furniture layout study for the entrance,
  kitchen, dining and living space, checked against the target room geometry
  and minimum working clearances.

`detect_windows.py` is a survey-transcription utility rather than part of the
normal build. The other scripts are wired into the Make targets below.

## Build

The pipeline runs on Linux and macOS. Prerequisites:

- Python 3; create the project venv with `make setup` (the Makefile uses
  `.venv/bin/python` when it exists, otherwise `python3`).
- Blender with the Bonsai extension. The Makefile picks `/snap/bin/blender`
  on Linux, then `/Applications/Blender.app` on macOS, then `blender` on
  `PATH`; override with `make BLENDER=/path/to/blender`. On macOS:
  `brew install --cask blender`, then
  `/Applications/Blender.app/Contents/MacOS/Blender --online-mode --command extension install --enable bonsai`.
- `rsvg-convert` for drawing PDFs (`apt install librsvg2-bin` /
  `brew install librsvg`); without it only the SVG sheets are produced.
- DejaVu Sans for check images (`brew install --cask font-dejavu` on macOS);
  Arial is used as a fallback.

List the supported workflows with `make help`. The primary builds are:

```sh
make as-is
make target
```

Additional outputs are explicit:

```sh
make concepts
make renders
```

On Linux, use `/snap/bin/blender` (5.2 LTS, has Bonsai 0.8.6); `/usr/bin/blender`
has no Bonsai.

`make STATE=<name> model` builds a single state from `data/<name>.yaml`.
Use `make clean` to remove all reproducible intermediates and exports.

## Outputs

- `exports/as_is.ifc` — 20 walls, 8 modeled door leaves, 5 windows, and 6
  spaces, plus the approved existing-bathroom fixtures and accessible service
  boxes, surveyed equipment, AC routing, floor buildup, shafts, and wall
  finishes.
- `exports/target.ifc` — 22 walls, 9 doors, 5 windows, and 7 spaces; relocates
  the living-area AC and extends its retained line set above the new bathroom.
- `exports/check/` — verification renders and photo overlay/diff.
- `exports/drawings/as_is/sheets/A01 - RZUT - STAN ISTNIEJĄCY.pdf` — the dimensioned
  A3 @ 1:50 plan for contractors; also as SVG, with the raw drawing and the
  layout alongside.
- `exports/drawings/target/sheets/A01 - RZUT - STAN PROJEKTOWANY.pdf` — the
  separate target-state A3 @ 1:50 plan.
- `exports/renders/target/` — one ultra-wide overview, five wide-angle textured
  PNG views, and the generated Blender scene.
- `exports/concepts/bathroom_layouts/balanced.png` — the working fixture-layout
  study, showing boxed surface pipe routes to the surveyed
  connection points and `SH_san`; its fixture arrangement is adopted in the
  authoritative models.
- `exports/concepts/living_layout/recommended.png` — the recommended furniture
  layout for the entrance hall, kitchen, dining and living zones.

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
Both states show the existing wall-mounted gas water heater outside the flat,
centred on the west wall segment north of the entrance door. In the target
state, the retained 100 l tank also moves outside to the west side, directly
below and beside the gas heater.

The balanced bathroom fixture layout is promoted into the models. The existing
bathroom contains the bath, basin, WC and washer; its pipes remain recorded as
concealed routing assumptions but only the connection points are shown.
Its WC is modeled as a wall-hung bowl with a concealed cistern, and its basin
has a rectangular recessed form. In the target state, a new dryer occupies the
washer's former floor position and the retained washer is stacked above it.
Modeled metal fittings include the existing bath and basin taps, the concealed
WC flush plate, and the target basin tap and shower mixer/riser/head set.
Bathroom 9 contains the basin, WC and 90 × 90 shower, with accessible hot/cold
water boxes, sanitary routes with nominal 2% falls, service terminals, and the
extract route to `SH_vent`. Baths, basins, WCs, shower trays, and the washer are
generated as recognizable, dimension-preserving IFC objects instead of cuboid
placeholders. Drain inverts, penetrations, fire stopping,
waterproofing, electrical changes, and finish zones still require design or
site verification.

Also not yet done: as-is/target delta and work-package generation, bill of
quantities per trade with contractor price columns, stable matched before/after
renders, and the combined tender PDF package.

Interior door leaves are modeled throughout with practical assumed swings:
bathroom doors open outward, the storage leaf avoids the bathroom-door corridor
swing, and bedroom leaves rest toward adjacent partitions. These directions
are design assumptions rather than surveyed facts and must be confirmed before
ordering. The render model uses standard 80/90 cm nominal leaves inside the
surveyed rough openings, with 2.10 m wood-framed doors. Windows use wood frames,
handles, and explicit two- or three-panel render layouts; these details are
visual assumptions rather than surveyed joinery.
