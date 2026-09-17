# Flat renovation plan-as-code context

This project is a plan-as-code renovation workflow for a Warsaw flat. The goal
is to keep both the surveyed **as-is** model and the renovated **target** model
in source-controlled, reviewable data files, then generate BIM/IFC, Blender
views, 3D visualisations, contractor-ready PDFs, and automatically counted work
quantities from those models.

The owner wants to add an additional bathroom and make the required utilities
available. Future agents should treat plumbing, drainage, ventilation, hot/cold
water, electrical changes, waterproofing, demolition, new partitions, finishes,
fixtures, and affected floor/wall/ceiling areas as first-class modeled data so
contractors can price the work from generated bills of quantities.

## Current source of truth

- `data/as_is.yaml` is the authoritative surveyed flat model.
- Coordinates are metres, origin at the outer south-west corner of the lower
  block; X grows east and Y grows north.
- Generated files are under `build/` and `exports/`; do not edit them directly.
- Survey scan: `7106fea6-ce4f-4979-8eac-ebf5f4a6972b.jfif`.
- Blender for this project must be `/snap/bin/blender`, because it has Bonsai;
  `/usr/bin/blender` exists but does not provide the required Bonsai workflow.

## Current modeled state

- As-is state is modeled and photo-verified.
- Existing rooms: three bedrooms, one bathroom, one storage room, and an open
  hall/kitchen/living space.
- Current net modeled area is about 95.56 m², matching the surveyed total
  closely enough for the current transcription.
- Current generated outputs include `exports/as_is.ifc`, verification overlays
  under `exports/check/`, and an A3 1:50 as-is contractor plan PDF at
  `exports/drawings/sheets/A01 - RZUT - STAN ISTNIEJĄCY.pdf`.
- The current IFC contains real doors/windows/openings, spaces with floor-area
  quantities, service shafts, a structural column, walls, and plan annotations.

## Pipeline

Rebuild after authoritative YAML changes:

```sh
python3 scripts/check_layout.py data/as_is.yaml exports/check/as_is_transcription_check.png
python3 scripts/yaml_to_json.py data/as_is.yaml build/as_is.json
/snap/bin/blender -b --python scripts/build_ifc.py -- build/as_is.json exports/as_is.ifc
python3 scripts/overlay_scan.py data/as_is.yaml 7106fea6-ce4f-4979-8eac-ebf5f4a6972b.jfif exports/check/overlay_on_scan.png
/snap/bin/blender -b --python scripts/export_bonsai_drawings.py -- exports/as_is.ifc exports/drawings
```

## Next implementation steps

1. Add a target-state source model, probably `data/target.yaml`, derived from
   `data/as_is.yaml`, with explicit schema for demolished, retained, and new
   elements.
2. Model the additional bathroom location and utility routing from the existing
   drainage/ventilation shaft `SH_san` / `SH_vent`, including slopes, risers,
   penetrations, waterproofing zones, fixtures, and constraints.
3. Generalise the IFC builder so it can build any named state (`as_is`,
   `target`) and export separate files such as `exports/as_is.ifc` and
   `exports/target.ifc`.
4. Add delta/work-package generation by comparing as-is vs target: demolition,
   new partitions, plumbing, drainage, ventilation, electrical, waterproofing,
   tiling, flooring, painting, doors, fixtures, and finishing works.
5. Add bill-of-quantities output with contractor pricing columns in CSV/JSON
   and printable PDF tables. Quantities should be computed from geometry and
   annotated model properties, not manually typed totals.
6. Add Blender scene/opening support for visual inspection and before/after 3D
   renders, using IFC/Bonsai as the source and producing stable camera views.
7. Build a combined tender PDF package containing the as-is plan, target plan,
   demolition/new-work plans, 3D visualisations, notes, and BoQ tables.

Prefer surgical, reproducible pipeline changes. Keep source data authoritative,
generated outputs disposable, and every quantity traceable back to modeled
geometry or explicit YAML properties.
