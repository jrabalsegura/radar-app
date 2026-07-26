# Configuración

Este directorio contiene configuración versionada y verificable.

- `radars.yaml`: catálogo de los 15 endpoints regionales, emplazamientos,
  centros, estrategia y estado de validación.
- `palettes/regional-safe-v1.json`: contrato estricto compartido por las
  muestras regionales verificadas; descarta el amarillo ambiguo.
- `palettes/regional-mu-v1.json`: geometría y once clases exactas de Murcia.
- `masks/regional-mu-v1.png`: máscara binaria estática de Murcia.
- `masks/regional-mu-v1.json`: algoritmo, hashes y estadísticas de la máscara.
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

La máscara se regenera mediante `aemet-radar build-reflectivity-mask` usando al
menos tres originales distintos. No debe editarse manualmente ni sustituirse
sin revisar el informe y las salidas visuales descritas en `docs/PHASE_3.md`.

La calibración se valida cada vez que se ejecuta
`aemet-radar georeference-murcia`. Un control que supere un píxel de error
interrumpe el proceso; los datos de referencia y la medición están documentados
en `docs/PHASE_4.md`.
