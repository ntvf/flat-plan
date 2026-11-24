PYTHON ?= python3
BLENDER ?= /snap/bin/blender
# WSL: route OpenGL (EEVEE) through D3D12 to the NVIDIA GPU instead of
# llvmpipe on the CPU (~10x faster renders). Override with GPU_ENV= to disable.
GPU_ENV ?= GALLIUM_DRIVER=d3d12 MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA

STATE ?= as_is
MODEL := data/$(STATE).yaml
JSON := build/$(STATE).json
IFC := exports/$(STATE).ifc
CHECK := exports/check/$(STATE)_transcription_check.png
DRAWINGS := exports/drawings/$(STATE)
MODEL_SOURCES := $(wildcard data/*.yaml) scripts/model_loader.py

.PHONY: all check compile model ifc drawings overlay as-is target tender rooms

all: model

check:
	$(PYTHON) -m py_compile scripts/*.py
	$(PYTHON) -m unittest discover -s tests

compile: $(JSON)

$(JSON): $(MODEL) $(MODEL_SOURCES) scripts/yaml_to_json.py
	$(PYTHON) scripts/yaml_to_json.py $< $@

model: $(CHECK) $(IFC)

$(CHECK): $(MODEL) $(MODEL_SOURCES) scripts/check_layout.py
	$(PYTHON) scripts/check_layout.py $< $@

$(IFC): $(JSON) scripts/build_ifc.py scripts/plan_symbols.py
	$(BLENDER) -b --python scripts/build_ifc.py -- $< $@

drawings: $(IFC) $(JSON)
	$(BLENDER) -b --python scripts/export_bonsai_drawings.py -- $(IFC) $(DRAWINGS) $(JSON)

overlay:
	$(PYTHON) scripts/overlay_scan.py $(MODEL) \
		7106fea6-ce4f-4979-8eac-ebf5f4a6972b.jfif \
		exports/check/overlay_on_scan.png

as-is:
	$(MAKE) STATE=as_is check model overlay drawings

target:
	$(MAKE) STATE=target check model drawings

tender:
	$(PYTHON) scripts/make_tender_docs.py data/as_is.yaml data/target.yaml exports/tender

# Room sheets; a layout variant renders to its own folder, e.g.
# make rooms ROOMS=target_photo ROOMS_OUT=exports/rooms/variant_photo
ROOMS ?= target
ROOMS_OUT ?= exports/rooms

rooms:
	$(MAKE) STATE=$(ROOMS) compile model
	$(GPU_ENV) $(BLENDER) -b --python scripts/render_room_views.py -- \
		exports/$(ROOMS).ifc build/$(ROOMS).json $(ROOMS_OUT)/renders
	$(PYTHON) scripts/make_room_sheets.py data/$(ROOMS).yaml $(ROOMS_OUT)/renders $(ROOMS_OUT)/rooms_uk.pdf
