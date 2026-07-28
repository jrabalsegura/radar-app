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
    assert catalog.definition_for("regional-ma").map_zoom == pytest.approx(7.3)
    assert catalog.definition_for("regional-ca").map_zoom == pytest.approx(6.9)
    assert catalog.definition_for("regional-ma").map_center_latitude == pytest.approx(40.41678)
    assert catalog.definition_for("regional-ml").map_center_longitude == pytest.approx(-3.5986)
    assert catalog.definition_for("regional-ml").map_center_latitude == pytest.approx(37.1773)
    assert catalog.definition_for("regional-mu").map_center_latitude == pytest.approx(37.84)
    assert catalog.definition_for("regional-am").map_center_longitude == pytest.approx(
        catalog.definition_for("regional-am").longitude
    )


def test_unavailable_radars_remain_configured() -> None:
    catalog = load_radar_catalog(CATALOG_PATH)

    awaiting = {
        item.product.id for item in catalog.definitions if item.sample_validation == "awaiting-data"
    }
    assert awaiting == {"regional-co", "regional-va", "regional-ss"}
    assert all(item.reflectivity_config_path.is_file() for item in catalog.definitions)


def test_each_calibrated_radar_uses_its_own_mask() -> None:
    catalog = load_radar_catalog(CATALOG_PATH)
    calibrated = {
        item.product.id: item.static_mask_path.name
        for item in catalog.definitions
        if item.static_mask_path is not None
    }

    assert calibrated == {
        product_id: f"{product_id}-v1.png"
        for product_id in {
            "regional-am",
            "regional-sa",
            "regional-pm",
            "regional-ba",
            "regional-cc",
            "regional-ma",
            "regional-ml",
            "regional-mu",
            "regional-vd",
            "regional-ca",
            "regional-se",
            "regional-za",
        }
    }
    assert all(
        item.ambiguous_class_policy == "static-mask"
        for item in catalog.definitions
        if item.product.id in calibrated
    )
