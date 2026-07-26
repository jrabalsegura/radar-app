# Worker

Paquete Python del worker de Radar AEMET.

La Fase 4 conserva la extracción `regional-v1` y añade
`regional-georeference-v1` para reproyectar exclusivamente Murcia a Web
Mercator. El resto de radares sigue fuera de alcance.

La API key solo se lee de `AEMET_API_KEY`. La CLI también puede cargar un `.env`
local ignorado por Git; una variable ya exportada tiene prioridad.

```bash
.venv/bin/aemet-radar fetch-once
.venv/bin/aemet-radar fetch-once --product regional-mu
.venv/bin/aemet-radar check-inventory
.venv/bin/aemet-radar run --cycles 1
.venv/bin/aemet-radar run
.venv/bin/aemet-radar rebuild-manifests
.venv/bin/aemet-radar serve-files
.venv/bin/aemet-radar analyze-reflectivity ruta/al/original.gif
.venv/bin/aemet-radar georeference-murcia ruta/al/overlay.png
.venv/bin/aemet-radar build-reflectivity-mask muestra1.gif muestra2.gif muestra3.gif
```

La salida estándar contiene únicamente un resumen JSON sin URLs efímeras ni
credenciales. Los originales e informes se guardan bajo `data/`, que está
ignorado por Git.

`check-inventory` consulta secuencialmente la pasarela con una pausa de un
segundo y no descarga los GIF regionales.

`run` reintenta únicamente fallos transitorios, aplica backoff exponencial y no
reemplaza el manifiesto de un producto cuando falla su consulta. Los valores
por defecto se pueden ajustar con `AEMET_POLL_INTERVAL_SECONDS`,
`AEMET_RETRY_ATTEMPTS`, `AEMET_RETRY_BACKOFF_SECONDS`,
`AEMET_RETENTION_HOURS` y `AEMET_HISTORY_HOURS`.

`rebuild-manifests` y `serve-files` no necesitan API key. El servidor escucha
solo en `127.0.0.1` por defecto y no permite listar directorios.

Las descargas que no superan la validación no se archivan como GIF. El worker
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

`build-reflectivity-mask` exige al menos tres hashes distintos. Solo debe
utilizarse con una selección revisada de muestras secas y lluviosas; el informe
adyacente registra exactamente las referencias y píxeles excluidos.

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
