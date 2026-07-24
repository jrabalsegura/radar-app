# Configuración

Este directorio contiene configuración versionada y verificable.

- `palettes/regional-mu-v1.json`: geometría y once clases exactas de Murcia.
- `masks/regional-mu-v1.png`: máscara binaria estática de Murcia.
- `masks/regional-mu-v1.json`: algoritmo, hashes y estadísticas de la máscara.
- `control-points/`: reservado para puntos de control geográfico.

`radars.yaml` se creará en la Fase 6, después de validar el inventario de radares.

La máscara se regenera mediante `aemet-radar build-reflectivity-mask` usando al
menos tres originales distintos. No debe editarse manualmente ni sustituirse
sin revisar el informe y las salidas visuales descritas en `docs/PHASE_3.md`.
