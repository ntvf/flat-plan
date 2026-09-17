"""Load a renovation model, resolving an optional base model and changes."""

from copy import deepcopy
from pathlib import Path

import yaml


def _merge(base, overlay):
    result = deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _items_by_id(data, section):
    items = data.get(section)
    if not isinstance(items, list):
        raise ValueError(f"cannot change non-list section {section!r}")
    keyed = {}
    for item in items:
        if not isinstance(item, dict) or "id" not in item:
            raise ValueError(f"every item in {section!r} must have an id")
        if item["id"] in keyed:
            raise ValueError(f"duplicate id {item['id']!r} in {section!r}")
        keyed[item["id"]] = item
    return items, keyed


def _apply_changes(data, changes):
    result = deepcopy(data)

    for section, additions in changes.get("add", {}).items():
        items, keyed = _items_by_id(result, section)
        for addition in additions:
            item_id = addition.get("id")
            if item_id is None:
                raise ValueError(f"new item in {section!r} has no id")
            if item_id in keyed:
                raise ValueError(f"cannot add existing id {item_id!r} to {section!r}")
            item = deepcopy(addition)
            items.append(item)
            keyed[item_id] = item

    for section, updates in changes.get("update", {}).items():
        _items, keyed = _items_by_id(result, section)
        for update in updates:
            item_id = update.get("id")
            if item_id not in keyed:
                raise ValueError(f"cannot update missing id {item_id!r} in {section!r}")
            keyed[item_id] = _merge(keyed[item_id], update)
        result[section] = [keyed[item["id"]] for item in result[section]]

    for section, removals in changes.get("remove", {}).items():
        items, keyed = _items_by_id(result, section)
        unknown = set(removals) - set(keyed)
        if unknown:
            raise ValueError(f"cannot remove missing ids {sorted(unknown)!r} from {section!r}")
        result[section] = [item for item in items if item["id"] not in removals]

    return result


def load_model(path):
    path = Path(path).resolve()
    with path.open(encoding="utf-8") as stream:
        document = yaml.safe_load(stream)
    if not isinstance(document, dict):
        raise ValueError(f"{path} must contain a YAML mapping")

    base_name = document.pop("extends", None)
    changes = document.pop("changes", {})
    if base_name:
        base = load_model(path.parent / base_name)
        data = _merge(base, document)
    else:
        data = document

    if not isinstance(changes, dict):
        raise ValueError(f"changes in {path} must be a mapping")
    return _apply_changes(data, changes)
