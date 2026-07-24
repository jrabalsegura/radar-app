"""Extracción determinista de reflectividad para el producto regional de Murcia."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import cast

from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError

from aemet_radar.errors import ReflectivityProcessingError
from aemet_radar.storage import atomic_write_bytes, atomic_write_json

PROCESSOR_ID = "regional-v1"
PRODUCT_ID = "regional-mu"
MASK_ALGORITHM = "temporal-invariance-v1"
MINIMUM_MASK_SAMPLES = 3


@dataclass(frozen=True, slots=True)
class CropBox:
    left: int
    top: int
    width: int
    height: int

    @property
    def pillow_box(self) -> tuple[int, int, int, int]:
        return (
            self.left,
            self.top,
            self.left + self.width,
            self.top + self.height,
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "left": self.left,
            "top": self.top,
            "width": self.width,
            "height": self.height,
        }


@dataclass(frozen=True, slots=True)
class CircleCoverage:
    center_x: int
    center_y: int
    radius: int

    def to_dict(self) -> dict[str, object]:
        return {
            "shape": "circle",
            "centerX": self.center_x,
            "centerY": self.center_y,
            "radius": self.radius,
        }


@dataclass(frozen=True, slots=True)
class ReflectivityClass:
    name: str
    palette_index: int
    rgb: tuple[int, int, int]
    legend_dbz: int
    ambiguous: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "paletteIndex": self.palette_index,
            "rgb": list(self.rgb),
            "legendDbz": self.legend_dbz,
            "ambiguous": self.ambiguous,
        }


@dataclass(frozen=True, slots=True)
class ReflectivityConfig:
    schema_version: int
    product_id: str
    processor: str
    expected_width: int
    expected_height: int
    expected_mode: str
    crop: CropBox
    coverage: CircleCoverage
    classes: tuple[ReflectivityClass, ...]

    @property
    def classes_by_index(self) -> dict[int, ReflectivityClass]:
        return {item.palette_index: item for item in self.classes}

    def to_report_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": self.schema_version,
            "productId": self.product_id,
            "processor": self.processor,
            "expectedImage": {
                "width": self.expected_width,
                "height": self.expected_height,
                "mode": self.expected_mode,
            },
            "crop": self.crop.to_dict(),
            "coverage": self.coverage.to_dict(),
            "classes": [item.to_dict() for item in self.classes],
        }


@dataclass(frozen=True, slots=True)
class LoadedGif:
    image: Image.Image
    source_sha256: str
    palette: tuple[tuple[int, int, int], ...]
    used_indexes: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ProcessingResult:
    output_dir: Path
    report_path: Path
    report: dict[str, object]


@dataclass(frozen=True, slots=True)
class MaskBuildResult:
    mask_path: Path
    report_path: Path
    report: dict[str, object]


def load_reflectivity_config(path: Path) -> ReflectivityConfig:
    """Carga y valida la configuración versionada de Murcia."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ReflectivityProcessingError(
            "No se pudo leer la configuración de reflectividad."
        ) from exc
    except json.JSONDecodeError as exc:
        raise ReflectivityProcessingError(
            "La configuración de reflectividad no contiene JSON válido."
        ) from exc
    if not isinstance(payload, dict):
        raise ReflectivityProcessingError(
            "La configuración de reflectividad debe ser un objeto JSON."
        )

    source = _required_mapping(payload, "expectedImage")
    crop_payload = _required_mapping(payload, "crop")
    coverage_payload = _required_mapping(payload, "coverage")
    class_payloads = _required_list(payload, "classes")
    classes = tuple(_parse_class(item) for item in class_payloads)
    config = ReflectivityConfig(
        schema_version=_required_int(payload, "schemaVersion"),
        product_id=_required_string(payload, "productId"),
        processor=_required_string(payload, "processor"),
        expected_width=_required_int(source, "width"),
        expected_height=_required_int(source, "height"),
        expected_mode=_required_string(source, "mode"),
        crop=CropBox(
            left=_required_int(crop_payload, "left"),
            top=_required_int(crop_payload, "top"),
            width=_required_int(crop_payload, "width"),
            height=_required_int(crop_payload, "height"),
        ),
        coverage=CircleCoverage(
            center_x=_required_int(coverage_payload, "centerX"),
            center_y=_required_int(coverage_payload, "centerY"),
            radius=_required_int(coverage_payload, "radius"),
        ),
        classes=classes,
    )
    if _required_string(coverage_payload, "shape") != "circle":
        raise ReflectivityProcessingError("regional-v1 requiere cobertura circular.")
    _validate_config(config)
    return config


def process_reflectivity_sample(
    source_path: Path,
    *,
    config_path: Path,
    static_mask_path: Path,
    output_dir: Path,
) -> ProcessingResult:
    """Regenera las salidas de análisis y la capa RGBA de una muestra."""

    config = load_reflectivity_config(config_path)
    loaded = _load_indexed_gif(source_path, config)
    static_mask = _load_static_mask(static_mask_path, config.crop)
    coverage_mask = _build_coverage_mask(config)
    cropped = loaded.image.crop(config.crop.pillow_box)
    normalized = loaded.image.convert("RGB")
    crop_rgb = cropped.convert("RGB")
    classified, alpha, overlay, counts = _classify(
        cropped,
        static_mask,
        coverage_mask,
        config,
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    output_images = {
        "normalized": ("normalized.png", normalized),
        "crop": ("crop.png", crop_rgb),
        "palette": (
            "palette.png",
            _palette_visualization(loaded.palette, loaded.used_indexes, config),
        ),
        "classified": ("classified.png", classified),
        "staticMask": ("static-mask.png", static_mask),
        "coverageMask": ("coverage-mask.png", coverage_mask),
        "mask": ("mask.png", alpha),
        "overlay": ("overlay.png", overlay),
        "preview": ("preview.png", _checkerboard_preview(overlay)),
    }
    for filename, image in output_images.values():
        _atomic_save_png(output_dir / filename, image)

    config_sha256 = _sha256_file(config_path)
    mask_sha256 = _sha256_file(static_mask_path)
    classes_by_index = config.classes_by_index
    class_statistics = []
    for palette_index, item in classes_by_index.items():
        source_count, kept_count, discarded_count, outside_coverage_count = counts[palette_index]
        class_statistics.append(
            {
                **item.to_dict(),
                "classifiedPixels": source_count,
                "keptPixels": kept_count,
                "discardedByStaticMask": discarded_count,
                "discardedOutsideCoverage": outside_coverage_count,
            }
        )

    crop_pixels = config.crop.width * config.crop.height
    classified_pixels = sum(item[0] for item in counts.values())
    kept_pixels = sum(item[1] for item in counts.values())
    discarded_pixels = sum(item[2] for item in counts.values())
    outside_coverage_pixels = sum(item[3] for item in counts.values())
    yellow = next((item for item in class_statistics if item["ambiguous"]), None)
    report: dict[str, object] = {
        "schemaVersion": 1,
        "productId": config.product_id,
        "processor": config.processor,
        "source": {
            "fileName": source_path.name,
            "sha256": f"sha256:{loaded.source_sha256}",
            "format": "GIF",
            "width": loaded.image.width,
            "height": loaded.image.height,
            "mode": loaded.image.mode,
            "usedPaletteIndexes": list(loaded.used_indexes),
        },
        "configuration": {
            **config.to_report_dict(),
            "paletteConfigSha256": f"sha256:{config_sha256}",
            "staticMaskSha256": f"sha256:{mask_sha256}",
        },
        "statistics": {
            "sourcePixels": loaded.image.width * loaded.image.height,
            "croppedPixels": crop_pixels,
            "classifiedPixelsBeforeStaticMask": classified_pixels,
            "reflectivityPixels": kept_pixels,
            "discardedByStaticMask": discarded_pixels,
            "discardedOutsideCoverage": outside_coverage_pixels,
            "unclassifiedPixels": crop_pixels - classified_pixels,
            "transparentPixels": crop_pixels - kept_pixels,
            "classes": class_statistics,
        },
        "ambiguities": {
            "yellow": {
                "policy": "keep-only-outside-versioned-static-mask",
                "result": yellow,
                "note": (
                    "El amarillo puro también dibuja límites administrativos. "
                    "Solo se conserva donde la máscara temporal no lo identifica como fijo."
                ),
            }
        },
        "outputs": {key: filename for key, (filename, _image) in output_images.items()},
        "limitations": [
            "Configuración validada únicamente para regional-mu con plantilla 480x530.",
            "La separación usa coincidencia exacta de paleta; una plantilla distinta falla.",
            "La máscara puede descartar un eco que permaneciera idéntico en todas sus muestras "
            "de generación; los hashes de referencia quedan registrados para revisión.",
            "La salida no está georreferenciada.",
        ],
    }
    report_path = output_dir / "report.json"
    atomic_write_json(report_path, report)
    return ProcessingResult(output_dir=output_dir, report_path=report_path, report=report)


def build_static_mask(
    sample_paths: Sequence[Path],
    *,
    config_path: Path,
    mask_path: Path,
    report_path: Path | None = None,
) -> MaskBuildResult:
    """Genera una máscara fija a partir de píxeles clasificados temporalmente invariantes."""

    config = load_reflectivity_config(config_path)
    unique_samples: dict[str, LoadedGif] = {}
    for path in sample_paths:
        loaded = _load_indexed_gif(path, config)
        unique_samples.setdefault(loaded.source_sha256, loaded)
    if len(unique_samples) < MINIMUM_MASK_SAMPLES:
        raise ReflectivityProcessingError(
            f"Se requieren al menos {MINIMUM_MASK_SAMPLES} muestras GIF distintas.",
            details={"distinctSamples": len(unique_samples)},
        )

    samples = [unique_samples[digest] for digest in sorted(unique_samples)]
    crops = [sample.image.crop(config.crop.pillow_box) for sample in samples]
    crop_bytes = [item.tobytes() for item in crops]
    first = crop_bytes[0]
    class_indexes = config.classes_by_index
    mask_data = bytearray([255]) * len(first)
    excluded = Counter[int]()
    for position, palette_index in enumerate(first):
        if palette_index not in class_indexes:
            continue
        if all(candidate[position] == palette_index for candidate in crop_bytes[1:]):
            mask_data[position] = 0
            excluded[palette_index] += 1

    mask = Image.frombytes("L", (config.crop.width, config.crop.height), bytes(mask_data))
    _atomic_save_png(mask_path, mask)
    resolved_report_path = report_path or mask_path.with_suffix(".json")
    report: dict[str, object] = {
        "schemaVersion": 1,
        "productId": config.product_id,
        "processor": config.processor,
        "algorithm": MASK_ALGORITHM,
        "configurationSha256": f"sha256:{_sha256_file(config_path)}",
        "maskSha256": f"sha256:{_sha256_file(mask_path)}",
        "sourceHashes": [f"sha256:{digest}" for digest in sorted(unique_samples)],
        "distinctSamples": len(unique_samples),
        "crop": config.crop.to_dict(),
        "coverage": config.coverage.to_dict(),
        "semantics": {
            "255": "eligible-for-reflectivity-classification",
            "0": "fixed-classified-pixel-excluded",
        },
        "excludedPixels": sum(excluded.values()),
        "excludedByClass": [
            {
                **class_indexes[index].to_dict(),
                "pixels": count,
            }
            for index, count in sorted(excluded.items())
        ],
        "method": (
            "Se excluye un píxel solo si todas las muestras distintas contienen en esa "
            "posición el mismo índice de una clase de reflectividad. Los fondos negro y gris "
            "no se convierten en exclusiones fijas."
        ),
        "knownRisk": (
            "Un eco idéntico en posición y clase a través de todas las muestras de referencia "
            "podría quedar excluido; se mitiga usando muestras secas y lluviosas separadas."
        ),
    }
    atomic_write_json(resolved_report_path, report)
    return MaskBuildResult(
        mask_path=mask_path,
        report_path=resolved_report_path,
        report=report,
    )


def _parse_class(value: object) -> ReflectivityClass:
    if not isinstance(value, dict):
        raise ReflectivityProcessingError("Cada clase de reflectividad debe ser un objeto JSON.")
    payload = cast(dict[str, object], value)
    rgb_values = _required_list(payload, "rgb")
    if len(rgb_values) != 3 or not all(
        isinstance(component, int) and not isinstance(component, bool) for component in rgb_values
    ):
        raise ReflectivityProcessingError("Cada color RGB debe contener tres enteros.")
    rgb = cast(list[int], rgb_values)
    ambiguous = payload.get("ambiguous", False)
    if not isinstance(ambiguous, bool):
        raise ReflectivityProcessingError("El campo ambiguous debe ser booleano.")
    return ReflectivityClass(
        name=_required_string(payload, "name"),
        palette_index=_required_int(payload, "paletteIndex"),
        rgb=(rgb[0], rgb[1], rgb[2]),
        legend_dbz=_required_int(payload, "legendDbz"),
        ambiguous=ambiguous,
    )


def _validate_config(config: ReflectivityConfig) -> None:
    if config.schema_version != 1:
        raise ReflectivityProcessingError("La versión de configuración no está soportada.")
    if config.product_id != PRODUCT_ID or config.processor != PROCESSOR_ID:
        raise ReflectivityProcessingError(
            "La configuración no corresponde al procesador regional de Murcia."
        )
    if config.expected_width <= 0 or config.expected_height <= 0:
        raise ReflectivityProcessingError("Las dimensiones esperadas deben ser positivas.")
    if config.expected_mode != "P":
        raise ReflectivityProcessingError("regional-v1 requiere una imagen GIF indexada.")
    crop = config.crop
    if (
        crop.left < 0
        or crop.top < 0
        or crop.width <= 0
        or crop.height <= 0
        or crop.left + crop.width > config.expected_width
        or crop.top + crop.height > config.expected_height
    ):
        raise ReflectivityProcessingError("El recorte queda fuera de la imagen esperada.")
    coverage = config.coverage
    if (
        coverage.radius <= 0
        or coverage.center_x < 0
        or coverage.center_x >= crop.width
        or coverage.center_y < 0
        or coverage.center_y >= crop.height
    ):
        raise ReflectivityProcessingError("La cobertura circular no es válida.")
    if not config.classes:
        raise ReflectivityProcessingError("La configuración no contiene clases.")
    indexes = [item.palette_index for item in config.classes]
    if len(indexes) != len(set(indexes)):
        raise ReflectivityProcessingError("Los índices de clase deben ser únicos.")
    if any(index < 0 or index > 255 for index in indexes):
        raise ReflectivityProcessingError("Los índices de paleta deben estar entre 0 y 255.")
    if any(component < 0 or component > 255 for item in config.classes for component in item.rgb):
        raise ReflectivityProcessingError("Los componentes RGB deben estar entre 0 y 255.")
    ambiguous = [item for item in config.classes if item.ambiguous]
    if len(ambiguous) != 1 or ambiguous[0].rgb != (255, 255, 0):
        raise ReflectivityProcessingError(
            "regional-v1 debe declarar exactamente el amarillo puro como clase ambigua."
        )


def _load_indexed_gif(path: Path, config: ReflectivityConfig) -> LoadedGif:
    try:
        content = path.read_bytes()
        with Image.open(BytesIO(content)) as candidate:
            candidate.seek(0)
            candidate.load()
            if candidate.format != "GIF":
                raise ReflectivityProcessingError("La muestra no es un GIF.")
            if getattr(candidate, "n_frames", 1) != 1:
                raise ReflectivityProcessingError("La muestra GIF debe tener un solo fotograma.")
            image = candidate.copy()
    except ReflectivityProcessingError:
        raise
    except (OSError, UnidentifiedImageError, SyntaxError) as exc:
        raise ReflectivityProcessingError(
            "No se pudo abrir la muestra GIF de forma segura."
        ) from exc

    actual = {"width": image.width, "height": image.height, "mode": image.mode}
    expected = {
        "width": config.expected_width,
        "height": config.expected_height,
        "mode": config.expected_mode,
    }
    if actual != expected:
        raise ReflectivityProcessingError(
            "La muestra no coincide con la plantilla configurada de regional-v1.",
            details={"expected": expected, "actual": actual},
        )
    palette_values = image.getpalette()
    if palette_values is None:
        raise ReflectivityProcessingError("La muestra GIF no contiene una paleta indexada.")
    palette = tuple(
        tuple(palette_values[offset : offset + 3])
        for offset in range(0, len(palette_values) - 2, 3)
    )
    for item in config.classes:
        if item.palette_index >= len(palette) or palette[item.palette_index] != item.rgb:
            actual_rgb = (
                list(palette[item.palette_index]) if item.palette_index < len(palette) else None
            )
            raise ReflectivityProcessingError(
                "La paleta GIF no coincide con regional-v1.",
                details={
                    "paletteIndex": item.palette_index,
                    "expectedRgb": list(item.rgb),
                    "actualRgb": actual_rgb,
                },
            )
    histogram = image.histogram()[:256]
    used_indexes = tuple(index for index, count in enumerate(histogram) if count)
    return LoadedGif(
        image=image,
        source_sha256=hashlib.sha256(content).hexdigest(),
        palette=cast(tuple[tuple[int, int, int], ...], palette),
        used_indexes=used_indexes,
    )


def _load_static_mask(path: Path, crop: CropBox) -> Image.Image:
    try:
        with Image.open(path) as candidate:
            candidate.load()
            mask = candidate.convert("L")
    except (OSError, UnidentifiedImageError, SyntaxError) as exc:
        raise ReflectivityProcessingError(
            "No se pudo abrir la máscara estática versionada."
        ) from exc
    expected_size = (crop.width, crop.height)
    if mask.size != expected_size:
        raise ReflectivityProcessingError(
            "La máscara estática no coincide con el recorte.",
            details={"expected": list(expected_size), "actual": list(mask.size)},
        )
    values = set(mask.tobytes())
    if not values.issubset({0, 255}):
        raise ReflectivityProcessingError("La máscara estática debe ser binaria (0 o 255).")
    return mask


def _classify(
    cropped: Image.Image,
    static_mask: Image.Image,
    coverage_mask: Image.Image,
    config: ReflectivityConfig,
) -> tuple[
    Image.Image,
    Image.Image,
    Image.Image,
    dict[int, tuple[int, int, int, int]],
]:
    classes = config.classes_by_index
    source = cropped.tobytes()
    mask = static_mask.tobytes()
    coverage = coverage_mask.tobytes()
    classified_bytes = bytearray(len(source) * 4)
    overlay_bytes = bytearray(len(source) * 4)
    alpha_bytes = bytearray(len(source))
    source_counts = Counter[int]()
    kept_counts = Counter[int]()
    discarded_counts = Counter[int]()
    outside_coverage_counts = Counter[int]()

    for position, palette_index in enumerate(source):
        item = classes.get(palette_index)
        if item is None:
            continue
        source_counts[palette_index] += 1
        rgba_offset = position * 4
        classified_bytes[rgba_offset : rgba_offset + 4] = bytes((*item.rgb, 255))
        if mask[position] == 0:
            discarded_counts[palette_index] += 1
            continue
        if coverage[position] == 0:
            outside_coverage_counts[palette_index] += 1
            continue
        kept_counts[palette_index] += 1
        overlay_bytes[rgba_offset : rgba_offset + 4] = bytes((*item.rgb, 255))
        alpha_bytes[position] = 255

    size = (config.crop.width, config.crop.height)
    counts = {
        index: (
            source_counts[index],
            kept_counts[index],
            discarded_counts[index],
            outside_coverage_counts[index],
        )
        for index in classes
    }
    return (
        Image.frombytes("RGBA", size, bytes(classified_bytes)),
        Image.frombytes("L", size, bytes(alpha_bytes)),
        Image.frombytes("RGBA", size, bytes(overlay_bytes)),
        counts,
    )


def _build_coverage_mask(config: ReflectivityConfig) -> Image.Image:
    coverage = config.coverage
    radius_squared = coverage.radius * coverage.radius
    data = bytearray(config.crop.width * config.crop.height)
    for y in range(config.crop.height):
        for x in range(config.crop.width):
            distance_squared = (x - coverage.center_x) ** 2 + (y - coverage.center_y) ** 2
            if distance_squared <= radius_squared:
                data[y * config.crop.width + x] = 255
    return Image.frombytes(
        "L",
        (config.crop.width, config.crop.height),
        bytes(data),
    )


def _palette_visualization(
    palette: Sequence[tuple[int, int, int]],
    used_indexes: Iterable[int],
    config: ReflectivityConfig,
) -> Image.Image:
    indexes = tuple(used_indexes)
    row_height = 20
    width = 260
    image = Image.new("RGB", (width, max(1, len(indexes)) * row_height), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    classes = config.classes_by_index
    for row, index in enumerate(indexes):
        top = row * row_height
        rgb = palette[index]
        draw.rectangle((0, top, 39, top + row_height - 1), fill=rgb)
        item = classes.get(index)
        classification = (
            f"reflectivity {item.legend_dbz} dBZ" + (" ambiguous" if item.ambiguous else "")
            if item is not None
            else "discarded"
        )
        draw.text((46, top + 4), f"{index:02d} {rgb} {classification}", fill="black", font=font)
    return image


def _checkerboard_preview(overlay: Image.Image) -> Image.Image:
    background = Image.new("RGBA", overlay.size, (224, 224, 224, 255))
    draw = ImageDraw.Draw(background)
    tile = 16
    for top in range(0, overlay.height, tile):
        for left in range(0, overlay.width, tile):
            if (left // tile + top // tile) % 2:
                draw.rectangle(
                    (left, top, left + tile - 1, top + tile - 1),
                    fill=(176, 176, 176, 255),
                )
    background.alpha_composite(overlay)
    return background.convert("RGB")


def _atomic_save_png(path: Path, image: Image.Image) -> None:
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=False, compress_level=9)
    atomic_write_bytes(path, buffer.getvalue())


def _sha256_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ReflectivityProcessingError("No se pudo calcular el hash de configuración.") from exc


def _required_mapping(payload: Mapping[str, object], key: str) -> dict[str, object]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ReflectivityProcessingError(f"El campo {key} debe ser un objeto.")
    return cast(dict[str, object], value)


def _required_list(payload: Mapping[str, object], key: str) -> list[object]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ReflectivityProcessingError(f"El campo {key} debe ser una lista.")
    return cast(list[object], value)


def _required_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ReflectivityProcessingError(f"El campo {key} debe ser texto no vacío.")
    return value


def _required_int(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ReflectivityProcessingError(f"El campo {key} debe ser un entero.")
    return value
