PYTHON ?= python3
BLENDER ?= /snap/bin/blender

STATE ?= as_is
MODEL := data/$(STATE).yaml
JSON := build/$(STATE).json
IFC := exports/$(STATE).ifc
CHECK := exports/check/$(STATE)_transcription_check.png

.PHONY: all check compile model ifc drawings overlay as-is

all: model

check:
	$(PYTHON) -m py_compile scripts/*.py

compile: $(JSON)

$(JSON): $(MODEL) scripts/yaml_to_json.py
	$(PYTHON) scripts/yaml_to_json.py $< $@

model: $(CHECK) $(IFC)

$(CHECK): $(MODEL) scripts/check_layout.py
	$(PYTHON) scripts/check_layout.py $< $@

$(IFC): $(JSON) scripts/build_ifc.py scripts/plan_symbols.py
	$(BLENDER) -b --python scripts/build_ifc.py -- $< $@

drawings: $(IFC) $(JSON)
	$(BLENDER) -b --python scripts/export_bonsai_drawings.py -- $(IFC) exports/drawings $(JSON)

overlay:
	$(PYTHON) scripts/overlay_scan.py $(MODEL) \
		7106fea6-ce4f-4979-8eac-ebf5f4a6972b.jfif \
		exports/check/overlay_on_scan.png

as-is: STATE=as_is
as-is: check model overlay drawings
