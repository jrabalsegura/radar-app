# Worker

Paquete Python del worker de Radar AEMET.

La Fase 2 añade el historial de originales de Murcia y composición nacional,
publicación atómica, retención y ejecución periódica. No procesa reflectividad.

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
