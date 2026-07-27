# Worker

Paquete Python del worker de Radar AEMET.

La Fase 6 ejecuta un pipeline regional configurable para los 15 códigos
publicados por AEMET. Cada radar tiene manifiesto, estado, centro y cobertura
propios. Un producto temporalmente sin imagen conserva un manifiesto vacío y
sigue consultándose.

La cronología PPI del visor oficial es la fuente primaria y no requiere key.
La API key de fallback OpenData solo se lee de `AEMET_API_KEY`. La CLI también
puede cargar un `.env` local ignorado por Git; una variable ya exportada tiene
prioridad.

```bash
.venv/bin/aemet-radar fetch-once
.venv/bin/aemet-radar fetch-once --product regional-mu
.venv/bin/aemet-radar check-inventory
.venv/bin/aemet-radar run --cycles 1
.venv/bin/aemet-radar run
.venv/bin/aemet-radar rebuild-manifests
.venv/bin/aemet-radar validate-radar --product regional-am ruta/al/original.gif
.venv/bin/aemet-radar serve-files
.venv/bin/aemet-radar analyze-reflectivity ruta/al/original.gif
.venv/bin/aemet-radar georeference-murcia ruta/al/overlay.png
.venv/bin/aemet-radar build-radar-masks \
  --sample-root data/phase6-samples \
  --sample-root data/mask-samples \
  --sample-root data/manual-phase2
.venv/bin/aemet-radar build-reviewed-dry-mask \
  ruta/al/original.gif ruta/al/ppi-vacio.png \
  --product regional-ml \
  --observed-at 2026-07-26T10:50:00Z \
  --dry-reference-url https://www.aemet.es/es/api-eltiempo/radar/imagen-radar/PPI/AHR260726105000.PPI.Z_005_240.png
```

La salida estándar contiene únicamente un resumen JSON sin URLs efímeras ni
credenciales. Los originales e informes se guardan bajo `data/`, que está
ignorado por Git.

`check-inventory` consulta secuencialmente la pasarela con una pausa de un
segundo y no descarga los GIF regionales.

`run` consulta una vez por ciclo la cronología PPI, archiva hasta 24
observaciones por radar y después procesa solo novedades. Si la cronología, el
emplazamiento o el PPI más reciente no son utilizables, consulta OpenData. Los
PPI secos son válidos; una lámina de indisponibilidad no lo es.

`run` reintenta únicamente fallos transitorios, aplica backoff exponencial y no
reemplaza el manifiesto de un producto cuando falla su consulta. Los valores
por defecto se pueden ajustar con `AEMET_POLL_INTERVAL_SECONDS`,
`AEMET_RETRY_ATTEMPTS`, `AEMET_RETRY_BACKOFF_SECONDS`,
`AEMET_RETENTION_HOURS`, `AEMET_HISTORY_HOURS` y
`AEMET_PRODUCT_DELAY_SECONDS`. Este último introduce por defecto un segundo
entre productos y no espera después del último.

`rebuild-manifests` y `serve-files` no necesitan API key. La reconstrucción
genera también cualquier derivado regional que falte en la ventana pública. El
servidor escucha solo en `127.0.0.1` por defecto y no permite listar
directorios.

Las descargas que no superan la validación no se archivan. El worker
publica tamaño, MIME declarado y SHA-256 en la salida estructurada y en
`data/reports/phase-2/failures/`, sin conservar el cuerpo o la URL efímera.

`analyze-reflectivity` tampoco necesita API key. Valida el GIF contra la
geometría y paleta versionadas, genera todas las imágenes de depuración y escribe
una capa `overlay.png` RGBA. Por defecto usa:

```text
config/palettes/regional-mu-v1.json
config/masks/regional-mu-v1.png
data/debug/phase-3/regional-mu/
```

`build-radar-masks` exige al menos tres hashes distintos y dos horas de
separación por radar. `build-reflectivity-mask` permite regenerar una máscara
individual. Solo debe
utilizarse con una selección revisada de muestras secas y lluviosas; el informe
adyacente registra exactamente las referencias y píxeles excluidos.

`build-reviewed-dry-mask` cubre una excepción más estricta: exige el PNG RGBA
original del PPI oficial para el mismo radar y hora, con transparencia y un
único color visible. Rechaza capas con ecos, texto o avisos de
indisponibilidad y registra URL, hora y hashes de ambas imágenes.

`georeference-murcia` tampoco necesita API key. Exige el PNG RGBA `480×480`
producido por `analyze-reflectivity`, aplica la calibración versionada y escribe
por defecto:

```text
config/georeferencing/regional-mu-v1.json
data/debug/phase-4/regional-mu/overlay-3857.png
data/debug/phase-4/regional-mu/georeferencing.json
```

La salida usa EPSG:3857, píxeles de 1.000 m y vecino más próximo. El informe
incluye esquinas para una fuente `image` de MapLibre, hashes, círculo de
cobertura y el error de los ocho puntos de control.

El PPI primario elimina fondo y no-dato conservando exactamente los once
colores de reflectividad; usa las esquinas oficiales de AEMET y publica:

```text
data/radar/<radar>/frames/<sha256>/overlay.png
```

El fallback GIF reutiliza los derivados si coinciden el hash del original, la
paleta, la máscara y la calibración. Los publica bajo:

```text
data/processed/<radar>/<sha256>/reflectivity/
data/radar/<radar>/frames/<sha256>/overlay-3857.png
```

`validate-radar` aplica exactamente la estrategia de `config/radars.yaml` y
genera la capa, su reproyección y una previsualización de límites. No necesita
API key. El contrato y las limitaciones del perfil compartido están en
`docs/PHASE_6.md`.
