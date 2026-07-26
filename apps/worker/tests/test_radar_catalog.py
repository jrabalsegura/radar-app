from pathlib import Path

import pytest

from aemet_radar.radar_catalog import load_radar_catalog

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = REPOSITORY_ROOT / "config" / "radars.yaml"


def test_catalog_contains_every_openapi_regional_radar() -> None:
    catalog = load_radar_catalog(CATALOG_PATH)

    assert len(catalog.definitions) == 15
    assert {item.product.aemet_code for item in catalog.definitions} == {
        "am",
        "sa",
        "pm",
        "ba",
        "cc",
        "co",
        "ma",
        "ml",
        "mu",
        "vd",
        "ca",
        "se",
        "va",
        "ss",
        "za",
    }
    assert catalog.definition_for("regional-mu").site_code == "FTN"
    assert catalog.definition_for("regional-ca").map_zoom == pytest.approx(5.7)


def test_unavailable_radars_remain_configured() -> None:
    catalog = load_radar_catalog(CATALOG_PATH)

    awaiting = {
        item.product.id for item in catalog.definitions if item.sample_validation == "awaiting-data"
    }
    assert awaiting == {"regional-co", "regional-va", "regional-ss"}
    assert all(item.reflectivity_config_path.is_file() for item in catalog.definitions)
