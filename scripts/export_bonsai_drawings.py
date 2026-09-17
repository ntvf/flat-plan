"""
Export the as-is model as dimensioned drawings using Bonsai's *native*
Drawings/Sheets pipeline.

Produces, under the output directory:
  drawings/<Name>.svg        - the generated 2D plan (vector)
  sheets/<Sheet>.svg/.pdf    - A3 titleblocked sheet with the plan placed on it

Run with:
  blender -b --python scripts/export_bonsai_drawings.py -- <src.ifc> <out_dir> [model.json]
"""

import json
import os
import shutil
import sys

import addon_utils
import bpy

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
SRC_IFC = os.path.abspath(_argv[0]) if len(_argv) > 0 else os.path.join(
    PROJECT, "exports", "as_is.ifc")
OUT_DIR = os.path.abspath(_argv[1]) if len(_argv) > 1 else os.path.join(
    PROJECT, "exports", "drawings")
MODEL_JSON = os.path.abspath(_argv[2]) if len(_argv) > 2 else os.path.join(
    PROJECT, "build", "as_is.json")
WORK_IFC = os.path.join(OUT_DIR, os.path.basename(SRC_IFC))

MODEL_DATA = {}
if os.path.exists(MODEL_JSON):
    with open(MODEL_JSON, encoding="utf-8") as stream:
        MODEL_DATA = json.load(stream)
META = MODEL_DATA.get("meta", {})

TITLEBLOCK = "A3-PL"
TITLEBLOCK_SRC = os.path.join(PROJECT, "data", "titleblocks")
SCALE = "1:50|1/50"

SHEET_NAME = META.get("sheet_name", "RZUT - STAN ISTNIEJĄCY")
SHEET_REVISION = str(META.get("sheet_revision", "0"))
SHEET_DESCRIPTION = META.get(
    "sheet_description", "Inwentaryzacja mieszkania - rzut kondygnacji"
)

ADDON = "bl_ext.user_default.bonsai"


def log(*a):
    print("[bonsai-export]", *a, flush=True)


# --- 0. Clean working dir; Bonsai writes drawings next to the IFC ----------
if os.path.isdir(OUT_DIR):
    shutil.rmtree(OUT_DIR)
os.makedirs(OUT_DIR, exist_ok=True)
shutil.copy(SRC_IFC, WORK_IFC)

addon_utils.enable(ADDON, default_set=True, persistent=True)

import bonsai.tool as tool  # noqa: E402  (must come after addon enable)

# --- 1. Teach Bonsai how to rasterise SVG -> PDF ---------------------------
prefs = bpy.context.preferences.addons[ADDON].preferences
rsvg = shutil.which("rsvg-convert")
if not rsvg:
    log("WARNING: rsvg-convert not found, PDFs will be skipped")
else:
    # Bonsai substitutes the bare tokens "svg" and "pdf" with real paths, so the
    # format flag must be written as --format=pdf to avoid being swallowed too.
    prefs.svg2pdf_command = json.dumps([[rsvg, "--format=pdf", "-o", "pdf", "svg"]])
    log("svg2pdf_command =", prefs.svg2pdf_command)

# --- 2. Load the project ---------------------------------------------------
bpy.ops.bim.load_project(
    filepath=WORK_IFC, is_advanced=False, skip_autosave_recovery=True, skip_recent=True
)
ifc = tool.Ifc.get()
log("loaded", WORK_IFC, "schema", ifc.schema)

storeys = ifc.by_type("IfcBuildingStorey")
if not storeys:
    sys.exit("No IfcBuildingStorey in model - Bonsai cannot place a plan view")
storey = storeys[0]
log("storey:", storey.Name, "id", storey.id())

# --- 3. Add a PLAN_VIEW drawing for the storey -----------------------------
from bonsai.bim.module.drawing.data import DrawingsData  # noqa: E402

props = tool.Drawing.get_document_props()
props.target_view = "PLAN_VIEW"

# The location_hint enum is backed by a lazy cache that is only refreshed by the
# target_view update callback; assigning the default value fires no callback, so
# prime it by hand before reading the enum.
DrawingsData.load()
DrawingsData.data["location_hint"] = DrawingsData.location_hint()
bpy.ops.bim.load_drawings()

hints = [i[0] for i in DrawingsData.data["location_hint"]]
hint = str(storey.id())
if hint not in hints:
    sys.exit(f"storey {hint} not in location_hint enum {hints}")
props.location_hint = hint
log("location_hint =", hint, "of", hints)

bpy.ops.bim.add_drawing()

# The drawing list is a collapsible tree of category rows + drawing rows, and
# categories load collapsed, so create_drawing's poll() would report "No active
# drawing". Expand every category, then select the new drawing row.
bpy.ops.bim.load_drawings()
bpy.ops.bim.toggle_target_view(target_view="PLAN_VIEW", toggle_all=True, option="EXPAND")
log("drawing rows:", [(d.name, d.is_drawing) for d in props.drawings])

drawing_row = None
for idx, item in enumerate(props.drawings):
    if item.is_drawing:
        props.active_drawing_index = idx
        drawing_row = item
        break
if drawing_row is None:
    sys.exit("no drawing row found after add_drawing")
log("active drawing:", drawing_row.name)
bpy.ops.bim.activate_drawing(drawing=drawing_row.ifc_definition_id)
log("scene camera:", getattr(bpy.context.scene.camera, "name", None))

# --- 3b. Scale the drawing to 1:50 ----------------------------------------
# diagram_scale lives on the camera data, not on the document props, and its
# enum is "<human readable>|<fraction>".
camera = bpy.context.scene.camera
camera.data.BIMCameraProperties.diagram_scale = SCALE
log("diagram_scale =", camera.data.BIMCameraProperties.diagram_scale)

# --- 3c. Annotate: room labels and dimension chains -----------------------
# Bonsai renders plans from IfcAnnotation entities, so without this step the
# sheet is correct but completely unlabelled.
sys.path.insert(0, os.path.join(PROJECT, "scripts"))
import annotate_drawing  # noqa: E402

if MODEL_DATA:
    _counts, _bounds = annotate_drawing.annotate(MODEL_DATA)

    # Frame the drawing on the annotated extents. Bonsai's new drawings default
    # to a 50 m view, which at 1:50 is a 1000 mm canvas - the plan then sits
    # far outside an A3 sheet. BIMCameraProperties.width/height are in metres
    # and their update callback recomputes ortho_scale and the raster size.
    bx0, by0, bx1, by1 = _bounds
    cprops = camera.data.BIMCameraProperties
    cprops.width = max(bx1 - bx0, 0.1)
    cprops.height = max(by1 - by0, 0.1)
    camera.matrix_world.translation.x = (bx0 + bx1) / 2
    camera.matrix_world.translation.y = (by0 + by1) / 2
    log(f"framed {cprops.width:.2f} x {cprops.height:.2f} m "
        f"-> {cprops.width * 1000 / 50:.0f} x {cprops.height * 1000 / 50:.0f} mm at 1:50")
else:
    log("WARNING: no model JSON at", MODEL_JSON, "- drawing will be unlabelled")

# Re-activate so the new annotations are collected into the drawing view.
bpy.ops.bim.activate_drawing(drawing=drawing_row.ifc_definition_id)

# --- 4. Generate the drawing (SVG + PDF) -----------------------------------
# print_all=True drives bpy.ops.wm.redraw_timer, which has no valid context in
# background mode; the single-drawing path renders straight from scene.camera.
bpy.ops.bim.create_drawing(print_all=False, open_viewer=False, sync=True)

# --- 5. Put the drawing on a sheet and render the sheet --------------------
# Bonsai only offers titleblocks it can find on disk, so drop ours into the
# project's titleblock directory before the enum is read.
tb_dir = tool.Ifc.resolve_uri(tool.Drawing.get_default_titleblock_path(TITLEBLOCK))
tb_dir = os.path.dirname(tb_dir)
os.makedirs(tb_dir, exist_ok=True)
tb_src = os.path.join(TITLEBLOCK_SRC, TITLEBLOCK + ".svg")
if os.path.exists(tb_src):
    shutil.copy(tb_src, os.path.join(tb_dir, TITLEBLOCK + ".svg"))
    from bonsai.bim.module.drawing.data import SheetsData  # noqa: E402
    SheetsData.load()
    available = [i[0] for i in SheetsData.data["titleblocks"]]
    if TITLEBLOCK in available:
        props.titleblock = TITLEBLOCK
    log("titleblock =", props.titleblock, "of", available)
else:
    log("WARNING: no titleblock at", tb_src, "- falling back to", props.titleblock)

bpy.ops.bim.add_sheet()

# Name the sheet. Bonsai has no rename operator, so the document information
# and the layout/titleblock reference paths are edited directly; otherwise
# every sheet is called "UNTITLED", including in the titleblock's {{Name}}.
sheet = tool.Ifc.get().by_type("IfcDocumentInformation")[-1]
identification = sheet.Identification
tool.Ifc.run("document.edit_information", information=sheet,
             attributes={"Name": SHEET_NAME, "Revision": SHEET_REVISION,
                         "Description": SHEET_DESCRIPTION})
for reference in sheet.HasDocumentReferences or []:
    if reference.Description == "LAYOUT":
        tool.Ifc.run("document.edit_reference", reference=reference, attributes={
            "Location": tool.Drawing.get_default_layout_path(identification, SHEET_NAME)})
log("sheet:", identification, SHEET_NAME)

bpy.ops.bim.load_sheets()

for idx, item in enumerate(props.sheets):
    if item.is_sheet:
        props.active_sheet_index = idx
        break
for idx, item in enumerate(props.drawings):
    if item.is_drawing:
        props.active_drawing_index = idx
        break

try:
    bpy.ops.bim.add_drawing_to_sheet()
    bpy.ops.bim.create_sheets(create_all=True, open_viewer=False)
except Exception as exc:  # sheet placement is the fragile part, keep drawings
    log("sheet step failed:", exc)

# --- 6. Report what landed on disk ----------------------------------------
log("--- OUTPUT ---")
for root, _dirs, files in os.walk(OUT_DIR):
    for f in sorted(files):
        p = os.path.join(root, f)
        log(f"{os.path.relpath(p, OUT_DIR):55s} {os.path.getsize(p):>9,d} B")
