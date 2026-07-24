# DECISIONS.md — Registro inicial de decisiones

Las decisiones se numerarán como `ADR-XXX`. No se borrarán cuando cambien: se marcarán como sustituidas.

---

## ADR-001 — Arquitectura sin base de datos para el MVP

**Estado:** aceptada provisionalmente.

Se utilizarán archivos originales, derivados y manifiestos JSON publicados atómicamente. Una base de datos solo se añadirá si aparece una necesidad concreta que no pueda resolverse de forma fiable con este modelo.

**Motivo:** el producto es de lectura, tiene poca cardinalidad, conserva una ventana temporal pequeña y debe ser fácil de operar en un servidor personal.

---

## ADR-002 — La API key solo vive en el worker

**Estado:** aceptada.

El navegador no llamará directamente a AEMET. El worker descargará y publicará recursos derivados. La clave se inyectará mediante entorno y nunca se incluirá en el repositorio.

---

## ADR-003 — Conservar originales

**Estado:** aceptada.

Se almacenará temporalmente el GIF original junto con el resultado procesado. Esto permitirá reprocesar cuando cambie la máscara, paleta o georreferenciación sin volver a consultar AEMET.

---

## ADR-004 — Procesadores regional y nacional independientes

**Estado:** aceptada.

La composición nacional no se obligará a compartir geometría, máscaras o transformación con los radares regionales. Compartirán interfaces y utilidades, pero podrán utilizar implementaciones distintas.

---

## ADR-005 — No interpolar reflectividad en el MVP

**Estado:** aceptada.

Las transiciones de opacidad solo suavizarán el cambio visual. No se generarán observaciones meteorológicas intermedias.

---

## ADR-006 — Murcia como radar piloto

**Estado:** aceptada.

Murcia será el primer radar regional para desarrollar y validar ingesta, separación de reflectividad, georreferenciación y timeline.

---

## ADR-007 — MapLibre con estilo configurable

**Estado:** aceptada.

MapLibre será el motor de mapa. La URL del estilo se configurará mediante entorno para no acoplar el proyecto desde el principio a un proveedor concreto de teselas.

---

## ADR-008 — Autenticación AEMET mediante cabecera y entorno

**Estado:** aceptada.

El cliente leerá `AEMET_API_KEY` del entorno y la enviará exclusivamente en la
cabecera `api_key` de la llamada inicial a OpenData. No se reenviará a las URLs
efímeras de datos o metadatos. La CLI puede cargar un `.env` local ignorado por
Git sin sobrescribir variables ya exportadas.

Los errores públicos no incluirán cabeceras, cuerpos de respuesta ni objetos
HTTP completos. Las pruebas verificarán con una clave ficticia que el secreto no
aparece en mensajes ni informes.

**Motivo:** la especificación OpenAPI oficial define `api_key` como cabecera y
esta opción evita incluir el secreto en URLs, historial del shell y logs de
acceso.

---

## ADR-009 — Identidad de originales por SHA-256

**Estado:** aceptada.

Cada original se identifica por el SHA-256 de sus bytes y se archiva bajo el
producto y la fecha UTC de obtención. Una segunda descarga con el mismo hash no
crea otro GIF ni otro informe.

`productTime` solo se publica como candidata cuando existe evidencia en
cabeceras, metadatos internos o nombre del recurso. La cadencia y `retrievedAt`
no se utilizarán para inventar una hora de producto.

**Motivo:** durante el spike todavía no se ha demostrado una fuente fiable de la
hora impresa, mientras que el hash permite deduplicar de forma determinista.

---

## ADR-010 — Separar catálogo publicado y disponibilidad observada

**Estado:** aceptada.

Un código presente en OpenAPI no se considerará habilitado ni disponible por ese
solo hecho. El worker distinguirá el código HTTP de la respuesta y el campo
`estado` declarado por AEMET.

La comprobación controlada del 23 de julio de 2026 obtuvo estado 200 para 12 de
15 radares regionales; A Coruña (`co`), Valencia (`va`) y Vizcaya (`ss`)
devolvieron estado AEMET 404. La composición nacional también devolvió estado
AEMET 404 en dos consultas, pese a seguir publicada en OpenAPI.

**Motivo:** el catálogo describe recursos admitidos, pero la disponibilidad es
estado temporal. No se eliminarán códigos por una observación puntual ni se
habilitarán en el producto sin la validación específica de fases posteriores.

---

## ADR-011 — Base temporal explícita por fotograma

**Estado:** aceptada.

El historial usa `productTime` cuando el informe contiene una candidata con
valor temporal. Cuando esa evidencia no existe, usa `retrievedAt` únicamente
como hora de obtención y publica `timeSource: "retrievedAt"` y
`productTime: null`.

Los manifiestos se anclan en el último fotograma disponible y publican como
máximo las dos horas anteriores a ese instante. Los huecos describen intervalos
esperados sin crear entradas de fotograma ni duplicar observaciones.

**Motivo:** `SPEC.md` permite presentar la hora de obtención cuando no se puede
determinar la hora del producto. Mantener ambas semánticas separadas evita
afirmar una precisión que la Fase 1 no pudo demostrar.

---

## ADR-012 — Publicación estática y atómica bajo el directorio de datos

**Estado:** aceptada.

Los manifiestos se publican en `data/radar/`, y el estado en
`data/status/health.json`. Cada JSON se serializa en un temporal del mismo
directorio, se sincroniza y se reemplaza con `os.replace`.

El servidor de inspección local sirve `data/` en `127.0.0.1` y deniega el
listado de directorios. No es el servidor de producción de la Fase 9.

**Motivo:** conserva la arquitectura sin base de datos de ADR-001 y garantiza
que un lector nunca observe un JSON escrito parcialmente.

---

## ADR-013 — Reintentos selectivos y conservación ante fallos

**Estado:** aceptada.

El ciclo periódico reintenta transportes fallidos, HTTP 408/425/429 y estados
5xx, con máximo configurable y backoff exponencial. No reintenta errores de
autenticación, contrato, validación de imagen ni estados funcionales como 404.

Si la ingesta de un producto falla, su manifiesto no se reconstruye ni se
vacía. `health.json` registra el error y diferencia ese fallo del estado
temporal de los datos existentes. La retención por defecto es de 24 horas y
nunca elimina el último fotograma válido de un producto.

**Motivo:** repetir errores permanentes aumenta carga sin mejorar la
recuperación; conservar la última publicación mantiene el servicio útil durante
una incidencia temporal de AEMET.
