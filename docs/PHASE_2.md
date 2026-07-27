# Fase 2 — Historial, manifiestos y ciclo periódico

Estado: implementación y validación real controlada completadas el 24 de julio
de 2026.

## Alcance implementado

La fase trabaja exclusivamente con los productos ya definidos:

- `regional-mu`, Murcia, cadencia de catálogo de 10 minutos;
- `national`, composición nacional, cadencia de catálogo de 30 minutos.

No se ha añadido procesamiento de reflectividad, georreferenciación, MapLibre,
animación ni otros radares.

El ciclo `aemet-radar run` realiza, por producto:

1. consulta y descarga mediante el cliente seguro de la Fase 1;
2. reintentos limitados para errores transitorios;
3. archivo y deduplicación SHA-256;
4. retención de originales e informes;
5. reconstrucción del manifiesto si la ingesta tuvo éxito;
6. actualización del índice y `health.json`.

Si un producto falla, el ciclo continúa con el siguiente y conserva sin cambios
su manifiesto válido anterior.

## Configuración

Los valores por defecto son:

| Variable | Valor | Uso |
| --- | ---: | --- |
| `AEMET_POLL_INTERVAL_SECONDS` | 300 | intervalo entre inicios de ciclo |
| `AEMET_RETRY_ATTEMPTS` | 3 | máximo de intentos por producto |
| `AEMET_RETRY_BACKOFF_SECONDS` | 1 | espera inicial del backoff |
| `AEMET_RETENTION_HOURS` | 24 | conservación inicial |
| `AEMET_HISTORY_HOURS` | 3.8333333333333335 | ventana pública (230 min) |

Los argumentos homónimos de `run` tienen prioridad sobre el entorno. La espera
de reintento se duplica hasta un máximo interno de 60 segundos.

Se reintentan:

- errores de transporte;
- HTTP 408, 425 y 429;
- HTTP o estado AEMET 5xx.

No se reintentan 401, 404, respuestas con contrato inválido ni GIF no válidos.

## Modelo temporal

La Fase 1 no encontró `productTime` verificable en las muestras reales de
Murcia. Por ello cada fotograma declara su base temporal:

```json
{
  "time": "2026-07-24T12:03:00Z",
  "timeSource": "retrievedAt",
  "productTime": null,
  "retrievedAt": "2026-07-24T12:03:00Z"
}
```

Cuando existe una candidata con valor en el informe, `timeSource` es
`productTime`. En caso contrario, `time` es la hora real de obtención y no se
presenta como hora del producto.

La ventana se ancla en el último fotograma disponible, no en la hora de
generación. Esto mantiene visible el último historial válido durante una caída,
mientras `health.json` informa de su antigüedad.

Los fotogramas se:

- validan contra su producto y ruta permitida;
- deduplican primero por hash;
- deduplican después por instante, conservando la revisión obtenida más tarde;
- ordenan por tiempo efectivo;
- filtran de forma inclusiva entre `último - 3 h 50 min` y `último`.

Para un radar regional, una secuencia completa contiene 24 fotogramas contando
ambos extremos. La cifra nacional depende de su cadencia real.

## Representación de huecos

`frames` contiene solo observaciones reales. Si dos observaciones consecutivas
están separadas aproximadamente 1,5 veces su cadencia, `gaps` describe la
ausencia. Se admite un segundo de tolerancia para absorber el jitter subsegundo
observado en el polling:

```json
{
  "after": "2026-07-24T10:50:00Z",
  "before": "2026-07-24T11:10:00Z",
  "expectedCadenceMinutes": 10,
  "missingCount": 1,
  "expectedTimes": ["2026-07-24T11:00:00Z"],
  "timeBasis": "productTime"
}
```

Una llegada retrasada se inserta en su posición al reconstruir y elimina el
hueco. No se crean GIF, hashes ni entradas de `frames` para intervalos ausentes.

## Publicación

El árbol servido es:

```text
data/
├── raw/
│   └── <producto>/<AAAA>/<MM>/<DD>/<sha256>.{gif,json}
├── reports/
│   └── phase-2/failures/<timestamp>-<producto>-download-validation.json
├── radar/
│   ├── index.json
│   ├── regional-mu/manifest.json
│   └── national/manifest.json
└── status/
    └── health.json
```

Todos los JSON se escriben en un temporal del mismo directorio, se sincronizan
y se publican con reemplazo atómico. Las URLs de los fotogramas apuntan a
originales locales mediante `/raw/...`; son una salida de inspección de esta
fase, no overlays finales.

`health.json` incluye por producto:

- última consulta y último éxito;
- resultado e intentos del último ciclo;
- último fotograma y último `productTime` disponible;
- base temporal;
- antigüedad y umbral de retraso;
- fotogramas archivados y publicables;
- error seguro, cuando exista.

Un dato se marca retrasado al superar dos veces la cadencia de su producto.

Si Pillow rechaza una descarga, el cuerpo no se archiva y el manifiesto
anterior permanece intacto. El ciclo registra únicamente propiedades seguras:

```json
{
  "code": "download_validation_error",
  "details": {
    "sizeBytes": 1234,
    "sha256": "sha256:...",
    "declaredContentType": "text/html"
  },
  "diagnosticReport": "reports/phase-2/failures/..."
}
```

No se hace un reintento inmediato de contenido inválido. La siguiente ejecución
programada vuelve a consultar AEMET, evitando una ráfaga de peticiones durante
una transición defectuosa del origen.

## Retención

La retención compara `lastRetrievedAt` —o `retrievedAt` si nunca fue
duplicado— con el límite de 24 horas. El GIF y su informe se eliminan como par.
El último fotograma válido de cada producto se conserva aunque sea más antiguo,
para no convertir una incidencia externa en pérdida total de datos.

## Comandos

```bash
make poll-once
make run-worker
make rebuild-manifests
make serve-files
```

Equivalentes con opciones:

```bash
.venv/bin/aemet-radar run --cycles 1 --product regional-mu
.venv/bin/aemet-radar run --poll-interval 300 --retry-attempts 3
.venv/bin/aemet-radar rebuild-manifests --history-hours 3
.venv/bin/aemet-radar serve-files --host 127.0.0.1 --port 8000
```

`rebuild-manifests` y `serve-files` no leen la API key.

La instalación usa un paquete local normal en vez de un editable. Python 3.13
en macOS omite archivos `.pth` con el indicador de archivo oculto, que puede
heredarse dentro de `.venv` y dejar roto el ejecutable de una instalación
editable. La instalación local evita depender de ese mecanismo y CI usa el
mismo comando.

## Validación automatizada

Las pruebas usan GIF e informes sintéticos y cubren:

- 24 fotogramas regionales completos;
- 7 fotogramas nacionales completos;
- orden desordenado en disco;
- duplicados por hash y por instante;
- ventana pública de 3 horas y 50 minutos con originales adicionales conservados;
- secuencia incompleta y detección del hueco;
- llegada tardía que rellena el hueco;
- jitter subsegundo alrededor del umbral real de 15 minutos;
- fallback explícito a `retrievedAt`;
- informes inválidos;
- retención de 24 horas y conservación del último válido;
- backoff exponencial, límite de intentos y errores no reintentables;
- intervalo periódico sin deriva acumulada;
- publicación atómica ante fallo de reemplazo;
- fallo AEMET 503 que mantiene byte a byte el manifiesto anterior;
- diagnóstico persistente de contenido inválido sin cuerpo ni secretos;
- ciclo completo simulado que genera manifiesto, índice y health;
- reconstrucción sin API key.

## Validación real controlada

El 24 de julio de 2026 se ejecutó un único ciclo contra AEMET con dos intentos
máximos y un directorio temporal separado del archivo de desarrollo:

| Producto | Resultado |
| --- | --- |
| Murcia | almacenado y publicado, 1 intento, estado actual |
| Nacional | estado AEMET 404, 1 intento, sin manifiesto falso |

Murcia siguió sin aportar evidencia de `productTime`; el manifiesto declaró
`timeSource: "retrievedAt"` y `productTime: null`. El 404 nacional se clasificó
como no reintentable, por lo que no se generó carga repetida.

En aquella validación inicial `health.json` quedó `degraded`, diferenciando
Murcia `current` de nacional `error` con `dataStatus: "no-data"`. ADR-022
sustituyó después esa semántica: un estado AEMET 404 es ahora `no-data`, sin
`lastError` ni degradación global cuando los demás productos están actuales.
Una auditoría confirmó que ni la API key ni las URLs efímeras aparecían en
informes, manifiestos o health. El directorio temporal se eliminó después de la
comprobación.

Una segunda validación manual archivó 18 originales. La reconstrucción actual
los publica dentro de una ventana exacta de 3 horas y 50 minutos y representa
tres ausencias detectadas, sin crear imágenes para ellas. Los
fotogramas quedaron ordenados, con hashes únicos y cada SHA-256 coincidió con el
GIF referenciado.

La prueba observó varias respuestas que Pillow no pudo identificar como GIF. El
manifiesto sobrevivió a todos esos ciclos. También mostró una separación real
de `14:59.962813` entre dos originales: era 37 milisegundos inferior al umbral
de 15 minutos y la primera implementación no la marcaba. Esa observación motivó
la tolerancia de un segundo y una prueba de regresión con los timestamps reales.

## Limitaciones conocidas

- La hora real del producto de Murcia sigue sin resolverse cuando AEMET no
  aporta evidencia; se usa y etiqueta la hora de obtención.
- La composición nacional seguía temporalmente no disponible en la validación
  real de esta fase. El scheduler conserva su estado como error o sin datos sin
  inventar contenido.
- Las respuestas inválidas de la prueba prolongada ocurrieron antes de añadir
  los informes seguros, por lo que su MIME y tamaño concretos no pueden
  recuperarse retrospectivamente. Los ciclos futuros sí dejarán ese diagnóstico.
- El servidor HTTP incluido es solo una ayuda local. HTTPS, Nginx, unidades de
  servicio y reinicio automático pertenecen a la Fase 9.
- Desde la Fase 5, los manifiestos conservan `rawUrl` para auditoría e incorporan
  `imageUrl` para el derivado transparente georreferenciado de Murcia.
