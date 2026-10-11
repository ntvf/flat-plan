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
- `data/target.yaml` is an overlay on the as-is model, resolved by
  `scripts/model_loader.py`.
- Coordinates are metres, origin at the outer south-west corner of the lower
  block; X grows east and Y grows north.
- Generated files are under `build/` and `exports/`; do not edit them directly.
- Survey scan: `data/survey-plan.jfif`.
- Blender must have the Bonsai extension. The Makefile auto-detects it:
  `/snap/bin/blender` on Linux (`/usr/bin/blender` there has no Bonsai), then
  `/Applications/Blender.app` on macOS; override with `BLENDER=...`. Keep
  scripts platform-neutral (no hard-coded system paths or add-on repo names).

## Current modeled state

- As-is state is modeled and photo-verified.
- Existing rooms: three bedrooms, one bathroom, one storage room, and an open
  hall/kitchen/living space.
- Current net modeled area is about 95.57 m², matching the surveyed total
  closely enough for the current transcription.
- Current generated outputs include `exports/as_is.ifc`, verification overlays
  under `exports/check/`, and an A3 1:50 as-is contractor plan PDF under
  `exports/drawings/as_is/sheets/`.
- The target model adds a 4.87 m² second bathroom east of the storage, bounded
  north at the ventilation riser and entered through an 0.80 m outward-opening
  door beside the existing 2.30 m wall.
- Target outputs include `exports/target.ifc` and the target-state sheet under
  `exports/drawings/target/`.
- All walls, including the bedroom partitions, are model data in `walls`; the
  IFC carries a `ModelWall` pset (id, kind, material, renovation status,
  length, thickness) on every wall and a `ModelSpace` pset on every space.
- The as-is IFC models leaves in all interior openings using practical assumed
  swings, plus the entrance, OB2, and the east DK6 panel; the target adds the
  new bathroom door.
  Both contain real windows/openings, spaces with floor-area quantities, service
  shafts, a structural column, walls, bathroom fixtures/utilities, and plan
  annotations.

## Pipeline

Rebuild after authoritative YAML changes:

```sh
make as-is
make target
```

## Next implementation steps

1. Verify and refine the modeled bathroom utility routing to `SH_san` /
   `SH_vent`: survey drain inverts, coordinate real falls and fittings, then
   add penetrations, fire stopping, waterproofing zones, electrical changes,
   and product-specific fixture clearances.
2. Add delta/work-package generation by comparing as-is vs target: demolition,
   new partitions, plumbing, drainage, ventilation, electrical, waterproofing,
   tiling, flooring, painting, doors, fixtures, and finishing works.
3. Add bill-of-quantities output with contractor pricing columns in CSV/JSON
   and printable PDF tables. Quantities should be computed from geometry and
   annotated model properties, not manually typed totals.
4. Add Blender scene/opening support for visual inspection and before/after 3D
   renders, using IFC/Bonsai as the source and producing stable camera views.
5. Build a combined tender PDF package containing the as-is plan, target plan,
   demolition/new-work plans, 3D visualisations, notes, and BoQ tables.

Prefer surgical, reproducible pipeline changes. Keep source data authoritative,
generated outputs disposable, and every quantity traceable back to modeled
geometry or explicit YAML properties.
