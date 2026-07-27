"""Catálogo versionado y validado de radares regionales."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import yaml

from aemet_radar.products import ProductKind, RadarProduct

DEFAULT_CATALOG_PATH = Path("config/radars.yaml")
_VALID_SAMPLE_STATUSES = {"verified", "control-points", "awaiting-data"}
_VALID_AMBIGUOUS_POLICIES = {"discard", "static-mask"}


@dataclass(frozen=True, slots=True)
class SourceRasterDefinition:
    width: int
    height: int
    center_x: float
    center_y: float
    metres_per_pixel: float


@dataclass(frozen=True, slots=True)
class OutputRasterDefinition:
    crs: str
    pixel_size_metres: float
    resampling: str


@dataclass(frozen=True, slots=True)
class RadarDefinition:
    product: RadarProduct
    site_code: str
    site_name: str
    longitude: float
    latitude: float
    map_center_longitude: float
    map_center_latitude: float
    range_kilometres: float
    map_zoom: float
    sample_validation: str
    reflectivity_config_path: Path
    static_mask_path: Path | None
    ambiguous_class_policy: str
    georeferencing_config_path: Path | None
    source_raster: SourceRasterDefinition
    output_raster: OutputRasterDefinition
    configuration_sha256: str

    @property
    def sample_verified(self) -> bool:
        return self.sample_validation != "awaiting-data"


@dataclass(frozen=True, slots=True)
class RadarCatalog:
    path: Path
    definitions: tuple[RadarDefinition, ...]
    sources: dict[str, str]

    @property
    def products(self) -> tuple[RadarProduct, ...]:
        return tuple(item.product for item in self.definitions)

    def definition_for(self, product_id: str) -> RadarDefinition:
        for definition in self.definitions:
            if definition.product.id == product_id:
                return definition
        raise KeyError(product_id)


def load_radar_catalog(path: Path = DEFAULT_CATALOG_PATH) -> RadarCatalog:
    """Carga YAML y rechaza catálogos incompletos o ambiguos."""

    resolved = path.resolve()
    try:
        payload = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError("No se pudo leer config/radars.yaml de forma segura.") from exc
    root = _mapping(payload, "root")
    if _integer(root, "schemaVersion") != 1:
        raise ValueError("Solo se admite schemaVersion 1 en radars.yaml.")
    defaults = _mapping(root.get("defaults"), "defaults")
    source_defaults = _mapping(defaults.get("sourceRaster"), "defaults.sourceRaster")
    output_defaults = _mapping(defaults.get("output"), "defaults.output")
    radar_rows = _list(root, "radars")
    definitions = tuple(
        _parse_radar(
            row,
            defaults=defaults,
            source_defaults=source_defaults,
            output_defaults=output_defaults,
            base_dir=resolved.parent,
        )
        for row in radar_rows
    )
    _validate_catalog(definitions)
    sources_payload = _mapping(root.get("sources"), "sources")
    sources = {
        key: value
        for key, value in sources_payload.items()
        if isinstance(key, str) and isinstance(value, str)
    }
    return RadarCatalog(path=resolved, definitions=definitions, sources=sources)


def _parse_radar(
    value: object,
    *,
    defaults: dict[str, object],
    source_defaults: dict[str, object],
    output_defaults: dict[str, object],
    base_dir: Path,
) -> RadarDefinition:
    row = _mapping(value, "radars[]")
    product_id = _string(row, "id")
    api_code = _string(row, "apiCode")
    reflectivity_path = _resolve_path(
        base_dir,
        _string_with_default(row, defaults, "reflectivityConfig"),
    )
    static_mask_value = row.get("staticMask", defaults.get("staticMask"))
    static_mask_path = (
        _resolve_path(base_dir, static_mask_value)
        if isinstance(static_mask_value, str) and static_mask_value
        else None
    )
    georeferencing_value = row.get("georeferencingConfig")
    georeferencing_path = (
        _resolve_path(base_dir, georeferencing_value)
        if isinstance(georeferencing_value, str) and georeferencing_value
        else None
    )
    policy = _string_with_default(row, defaults, "ambiguousClassPolicy")
    sample_validation = _string(row, "sampleValidation")
    canonical = json.dumps(
        {
            "radar": row,
            "defaults": defaults,
            "sourceRaster": source_defaults,
            "output": output_defaults,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    longitude = _number(row, "longitude")
    latitude = _number(row, "latitude")
    definition = RadarDefinition(
        product=RadarProduct(
            id=product_id,
            label=_string(row, "label"),
            kind=ProductKind.REGIONAL,
            endpoint=f"/api/red/radar/regional/{api_code}",
            cadence_minutes=_integer_with_default(row, defaults, "cadenceMinutes"),
            aemet_code=api_code,
        ),
        site_code=_string(row, "siteCode"),
        site_name=_string(row, "siteName"),
        longitude=longitude,
        latitude=latitude,
        map_center_longitude=(
            _number(row, "mapCenterLongitude") if "mapCenterLongitude" in row else longitude
        ),
        map_center_latitude=(
            _number(row, "mapCenterLatitude") if "mapCenterLatitude" in row else latitude
        ),
        range_kilometres=_number_with_default(row, defaults, "rangeKilometres"),
        map_zoom=_number_with_default(row, defaults, "mapZoom"),
        sample_validation=sample_validation,
        reflectivity_config_path=reflectivity_path,
        static_mask_path=static_mask_path,
        ambiguous_class_policy=policy,
        georeferencing_config_path=georeferencing_path,
        source_raster=SourceRasterDefinition(
            width=_integer(source_defaults, "width"),
            height=_integer(source_defaults, "height"),
            center_x=_number(source_defaults, "centerX"),
            center_y=_number(source_defaults, "centerY"),
            metres_per_pixel=_number(source_defaults, "metresPerPixel"),
        ),
        output_raster=OutputRasterDefinition(
            crs=_string(output_defaults, "crs"),
            pixel_size_metres=_number(output_defaults, "pixelSizeMetres"),
            resampling=_string(output_defaults, "resampling"),
        ),
        configuration_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    )
    if policy not in _VALID_AMBIGUOUS_POLICIES:
        raise ValueError(f"Política ambigua no soportada para {product_id}.")
    if sample_validation not in _VALID_SAMPLE_STATUSES:
        raise ValueError(f"Estado de validación no soportado para {product_id}.")
    if policy == "static-mask" and static_mask_path is None:
        raise ValueError(f"{product_id} requiere una máscara estática.")
    for required_path in (
        definition.reflectivity_config_path,
        definition.static_mask_path,
        definition.georeferencing_config_path,
    ):
        if required_path is not None and not required_path.is_file():
            raise ValueError(f"Falta la configuración referenciada por {product_id}.")
    return definition


def _validate_catalog(definitions: tuple[RadarDefinition, ...]) -> None:
    if len(definitions) != 15:
        raise ValueError("radars.yaml debe declarar los 15 códigos regionales de OpenAPI.")
    for values, label in (
        ([item.product.id for item in definitions], "identificadores"),
        ([cast(str, item.product.aemet_code) for item in definitions], "códigos API"),
        ([item.site_code for item in definitions], "códigos de emplazamiento"),
    ):
        if len(values) != len(set(values)):
            raise ValueError(f"radars.yaml contiene {label} duplicados.")
    if any(not item.product.id.startswith("regional-") for item in definitions):
        raise ValueError("Todos los productos de radars.yaml deben ser regionales.")
    if any(not -180 <= item.longitude <= 180 for item in definitions):
        raise ValueError("Hay una longitud de radar fuera de rango.")
    if any(not -90 <= item.latitude <= 90 for item in definitions):
        raise ValueError("Hay una latitud de radar fuera de rango.")
    if any(not -180 <= item.map_center_longitude <= 180 for item in definitions):
        raise ValueError("Hay una longitud de centro de mapa fuera de rango.")
    if any(not -90 <= item.map_center_latitude <= 90 for item in definitions):
        raise ValueError("Hay una latitud de centro de mapa fuera de rango.")
    if any(item.range_kilometres <= 0 or item.map_zoom <= 0 for item in definitions):
        raise ValueError("Alcance y zoom deben ser positivos.")


def _resolve_path(base_dir: Path, value: object) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError("Las rutas de configuración deben ser texto no vacío.")
    return (base_dir / value).resolve()


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} debe ser un objeto.")
    return cast(dict[str, object], value)


def _list(payload: dict[str, object], key: str) -> list[object]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{key} debe ser una lista.")
    return cast(list[object], value)


def _string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} debe ser texto no vacío.")
    return value


def _string_with_default(
    row: dict[str, object],
    defaults: dict[str, object],
    key: str,
) -> str:
    value = row.get(key, defaults.get(key))
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} debe ser texto no vacío.")
    return value


def _integer(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{key} debe ser un entero.")
    return value


def _integer_with_default(
    row: dict[str, object],
    defaults: dict[str, object],
    key: str,
) -> int:
    value = row.get(key, defaults.get(key))
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{key} debe ser un entero.")
    return value


def _number(payload: dict[str, object], key: str) -> float:
    value = payload.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{key} debe ser un número.")
    return float(value)


def _number_with_default(
    row: dict[str, object],
    defaults: dict[str, object],
    key: str,
) -> float:
    value = row.get(key, defaults.get(key))
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{key} debe ser un número.")
    return float(value)
