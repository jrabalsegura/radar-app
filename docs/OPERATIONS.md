# Operación local

La operación de producción con Podman, systemd y Nginx sigue pendiente de la
Fase 9. Esta guía cubre únicamente el worker y la publicación local de la Fase
2.

## Comprobar el estado

```bash
jq . data/status/health.json
jq . data/radar/index.json
```

Por producto, `status` refleja el último ciclo (`current`, `delayed`,
`no-data` o `error`) y `dataStatus` refleja solo la edad del último fotograma.
El umbral de retraso es dos veces la cadencia declarada del producto.

## Forzar un ciclo completo

```bash
make poll-once
```

Este comando consulta Murcia y nacional, aplica reintentos limitados, conserva
24 horas y publica los JSON. Devuelve código 1 si al menos un producto falla,
aunque los productos correctos sí quedan actualizados.

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
AEMET_HISTORY_HOURS=2
```

Los ciclos se programan respecto a su hora de inicio para no acumular la
duración de las llamadas. `Ctrl-C` detiene el proceso.

## Reconstruir desde disco

```bash
make rebuild-manifests
```

No consulta AEMET y no requiere `AEMET_API_KEY`. Relee los informes adyacentes a
los GIF, descarta informes inválidos, ordena y deduplica el historial y vuelve a
publicar manifiestos, índice y health.

## Inspeccionar por HTTP

En una terminal:

```bash
make serve-files
```

En otra:

```bash
curl http://127.0.0.1:8000/radar/index.json
curl http://127.0.0.1:8000/radar/regional-mu/manifest.json
curl http://127.0.0.1:8000/status/health.json
```

El servidor es solo local, no permite listar directorios y no sustituye a
Nginx.

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

La regeneración de derivados, habilitación de otros radares y rollback de
contenedores pertenecen a fases posteriores.
