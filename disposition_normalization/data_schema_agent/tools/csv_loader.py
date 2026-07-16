import csv
from pathlib import Path
from typing import Any

_DATA_DIR = Path(__file__).parents[3] / "data" / "structured"
_cache: dict[str, list[dict[str, Any]]] = {}


def _load() -> dict[str, list[dict[str, Any]]]:
    global _cache
    if _cache:
        return _cache
    for path in sorted(_DATA_DIR.glob("*.csv")):
        with open(path, newline="", encoding="utf-8") as f:
            _cache[path.stem] = list(csv.DictReader(f))
    return _cache


def all_datasets() -> dict[str, list[dict[str, Any]]]:
    return _load()


def get_rows(dataset_name: str) -> list[dict[str, Any]]:
    return _load().get(dataset_name, [])


def dataset_names() -> list[str]:
    return list(_load().keys())
