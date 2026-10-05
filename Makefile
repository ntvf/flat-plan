PYTHON ?= python3
BLENDER ?= /snap/bin/blender

STATE ?= as_is
MODEL := data/$(STATE).yaml
SURVEY := data/survey-plan.jfif
JSON := build/$(STATE).json
IFC := exports/$(STATE).ifc
CHECK := exports/check/$(STATE)_transcription_check.png
OVERLAY := exports/check/$(STATE)_overlay.png
DRAWINGS := exports/drawings/$(STATE)
MODEL_SOURCES := $(wildcard data/*.yaml) scripts/model_loader.py

.PHONY: all help check compile model drawings overlay concepts renders as-is target clean

all: model

help:
	@printf '%s\n' \
		'make as-is    Build and verify the surveyed model and drawings' \
		'make target   Build and verify the renovation model and drawings' \
		'make concepts Generate bathroom layout studies' \
		'make renders  Render the target model views' \
		'make check    Run syntax checks and unit tests' \
		'make clean    Remove all generated files'

check:
	$(PYTHON) -m py_compile scripts/*.py
	$(PYTHON) -m unittest discover -s tests

compile: $(JSON)

$(JSON): $(MODEL) $(MODEL_SOURCES) scripts/yaml_to_json.py
	mkdir -p $(@D)
	$(PYTHON) scripts/yaml_to_json.py $< $@

model: $(CHECK) $(IFC)

$(CHECK): $(MODEL) $(MODEL_SOURCES) scripts/check_layout.py
	mkdir -p $(@D)
	$(PYTHON) scripts/check_layout.py $< $@

$(IFC): $(JSON) scripts/build_ifc.py scripts/plan_symbols.py
	mkdir -p $(@D)
	$(BLENDER) -b --python scripts/build_ifc.py -- $< $@

drawings: $(IFC) $(JSON)
	mkdir -p $(DRAWINGS)
	$(BLENDER) -b --python scripts/export_bonsai_drawings.py -- $(IFC) $(DRAWINGS) $(JSON)

overlay: $(OVERLAY)

$(OVERLAY): $(MODEL) $(MODEL_SOURCES) scripts/overlay_scan.py $(SURVEY)
	mkdir -p $(@D)
	$(PYTHON) scripts/overlay_scan.py $(MODEL) $(SURVEY) $@

concepts:
	$(PYTHON) scripts/sketch_bathroom_layouts.py

renders:
	$(MAKE) STATE=target model
	$(BLENDER) -b --python scripts/render_textured_views.py -- exports/target.ifc exports/renders/target

as-is:
	$(MAKE) STATE=as_is check model overlay drawings

target:
	$(MAKE) STATE=target check model drawings

clean:
	rm -rf build exports
