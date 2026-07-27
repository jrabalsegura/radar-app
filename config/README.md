# Configuración

Este directorio contiene configuración versionada y verificable.

- `radars.yaml`: catálogo de los 15 endpoints regionales, emplazamientos,
  centros, estrategia y estado de validación.
- `palettes/regional-safe-v1.json`: contrato estricto compartido por las
  muestras regionales verificadas.
- `palettes/regional-mu-v1.json`: geometría y once clases exactas de Murcia.
- `masks/regional-<código>-v1.png`: máscara binaria propia de cada radar
  calibrado.
- `masks/regional-<código>-v1.json`: algoritmo, hashes, horas y estadísticas de
  cada máscara.
- `georeferencing/regional-mu-v1.json`: centro, proyección, resolución, salida y
  ocho puntos de control geográfico de Murcia.

Un radar puede figurar como `awaiting-data`: sigue publicándose en el índice y
consultándose, pero no genera una capa hasta recibir un GIF que supere el perfil.
Las rutas se resuelven respecto a este directorio y se validan al cargar el
catálogo.

Para revisar una muestra con la estrategia declarada:

```bash
make validate-radar PRODUCT=regional-am SAMPLE=ruta/a/muestra.gif
```

El alta de un código nuevo requiere una fuente oficial, una muestra real y la
revisión descrita en `docs/PHASE_6.md`; no exige modificar el procesador,
publicador o frontend.

Las máscaras se regeneran en lote con `aemet-radar build-radar-masks`. La
herramienta deduplica por contenido y exige por defecto tres originales
distintos separados al menos dos horas. Solo convierte en exclusión fija una
clase marcada como ambigua que permanezca idéntica en todas las muestras; una
intensidad no ambigua nunca se enmascara por permanecer inmóvil. Ninguna
máscara debe editarse manualmente ni activarse sin revisar su informe y las
salidas visuales descritas en `docs/PHASE_3.md`.

Málaga documenta la excepción `ambiguous-reviewed-dry-reference-v1`: su único
GIF se cotejó con un PPI oficial vacío del mismo radar y hora mediante
`build-reviewed-dry-mask`. La herramienta valida automáticamente que la
referencia tenga transparencia y un solo color visible. La evidencia original
y su informe están bajo `docs/evidence/phase-6/official-viewer/`.

Los radares sin evidencia suficiente mantienen la política conservadora
`discard`: siguen operativos, pero no publican el amarillo ambiguo hasta que
pueda generarse su máscara específica.

La calibración se valida cada vez que se ejecuta
`aemet-radar georeference-murcia`. Un control que supere un píxel de error
interrumpe el proceso; los datos de referencia y la medición están documentados
en `docs/PHASE_4.md`.
