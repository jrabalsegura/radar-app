# Operación local

La operación de producción con Podman, systemd y Nginx sigue pendiente de la
Fase 9. Esta guía cubre el worker, la publicación local y el pipeline regional
configurable de la Fase 6.

## Comprobar el estado

```bash
jq . data/status/health.json
jq . data/radar/index.json
```

Por producto, `status` refleja el último ciclo (`current`, `delayed`,
`no-data` o `error`) y `dataStatus` refleja solo la edad del último fotograma.
El umbral de retraso es dos veces la cadencia declarada del producto.

Los fallos de validación de descarga dejan informes seguros bajo:

```text
data/reports/phase-2/failures/
```

Se pueden revisar con:

```bash
for report in data/reports/phase-2/failures/*.json; do
  jq . "$report"
done
```

Estos informes contienen tamaño, MIME declarado y SHA-256, pero nunca el cuerpo
inválido, la API key o la URL efímera.

## Forzar un ciclo completo

```bash
make poll-once
```

Este comando consulta los 15 radares regionales de forma secuencial, aplica
reintentos limitados, conserva 24 horas y publica los JSON. Devuelve código 1 si
al menos un producto falla, aunque los productos correctos sí quedan
actualizados.

## Ejecutar el scheduler

```bash
make run-worker
```

Valores no sensibles configurables en `.env`:

```text
AEMET_POLL_INTERVAL_SECONDS=300
AEMET_RETRY_ATTEMPTS=3
AEMET_RETRY_BACKOFF_SECONDS=1
AEMET_RETENTION_HOURS=24
AEMET_HISTORY_HOURS=3
AEMET_PRODUCT_DELAY_SECONDS=1
```

Los ciclos se programan respecto a su hora de inicio para no acumular la
duración de las llamadas. `Ctrl-C` detiene el proceso.

## Reconstruir desde disco

```bash
make rebuild-manifests
```

No consulta AEMET y no requiere `AEMET_API_KEY`. Relee los informes adyacentes a
los GIF, descarta informes inválidos, ordena y deduplica el historial, genera
los derivados regionales que falten y vuelve a publicar manifiestos, índice y
health. La ventana predeterminada es de tres horas.

## Inspeccionar por HTTP

En una terminal:

```bash
make serve-files
```

En otra:

```bash
curl http://127.0.0.1:8000/radar/index.json
curl http://127.0.0.1:8000/radar/regional-mu/manifest.json
curl http://127.0.0.1:8000/radar/regional-co/manifest.json
curl http://127.0.0.1:8000/status/health.json
```

El servidor es solo local, no permite listar directorios y no sustituye a
Nginx.

## Validar una muestra regional

No consulta AEMET ni requiere API key:

```bash
make validate-radar \
  PRODUCT=regional-am \
  SAMPLE=data/raw/regional-am/AAAA/MM/DD/<sha256>.gif
```

Revisar `reflectivity/preview.png`,
`georeferenced/overlay-3857.png`, `calibration/overlay-3857.png` y
`validation.json`. Si cambian dimensiones o paleta, la validación se detiene y
el perfil debe estudiarse antes de habilitar la capa.

## Regenerar la reflectividad de Murcia

No consulta AEMET ni requiere API key:

```bash
.venv/bin/aemet-radar analyze-reflectivity \
  data/raw/regional-mu/AAAA/MM/DD/<sha256>.gif \
  --output-dir data/debug/phase-3/regional-mu/<sha256-corto>
```

Revisar especialmente:

```text
classified.png     coincidencias antes de eliminar elementos fijos
coverage-mask.png  cobertura circular parametrizada
overlay.png        capa RGBA final
preview.png        transparencia visible sobre damero
report.json        píxeles conservados y descartados por clase
```

La máscara estática está versionada. Su regeneración deliberada requiere al
menos tres originales distintos:

```bash
.venv/bin/aemet-radar build-reflectivity-mask \
  muestra-seca.gif muestra-lluviosa.gif otra-muestra.gif
```

Después se deben revisar el PNG, su informe JSON, varias previsualizaciones y
los golden tests. El procedimiento detallado está en `docs/PHASE_3.md`.

## Rotar la API key

1. Sustituir `AEMET_API_KEY` en `.env` o en el entorno del proceso.
2. Mantener permisos `600` en `.env`.
3. Reiniciar el worker.
4. Ejecutar un único ciclo y comprobar que `lastSuccessAt` avanza.

La clave no se pasa como argumento ni se incluye en los JSON.

## Recuperar la última publicación válida

Un fallo de AEMET no reemplaza el manifiesto del producto afectado. Si un JSON
público se elimina o se considera inconsistente, se reconstruye desde los
originales:

```bash
make rebuild-manifests
```

El rollback de contenedores pertenece a fases posteriores.
