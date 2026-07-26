# Configuración

Este directorio contiene configuración versionada y verificable.

- `palettes/regional-mu-v1.json`: geometría y once clases exactas de Murcia.
- `masks/regional-mu-v1.png`: máscara binaria estática de Murcia.
- `masks/regional-mu-v1.json`: algoritmo, hashes y estadísticas de la máscara.
- `georeferencing/regional-mu-v1.json`: centro, proyección, resolución, salida y
  ocho puntos de control geográfico de Murcia.

`radars.yaml` se creará en la Fase 6, después de validar el inventario de radares.

La máscara se regenera mediante `aemet-radar build-reflectivity-mask` usando al
menos tres originales distintos. No debe editarse manualmente ni sustituirse
sin revisar el informe y las salidas visuales descritas en `docs/PHASE_3.md`.

La calibración se valida cada vez que se ejecuta
`aemet-radar georeference-murcia`. Un control que supere un píxel de error
interrumpe el proceso; los datos de referencia y la medición están documentados
en `docs/PHASE_4.md`.
