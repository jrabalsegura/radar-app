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

Los manifiestos se anclan en el último fotograma disponible. La duración visible
queda definida por ADR-016. Los huecos describen intervalos esperados sin crear
entradas de fotograma ni duplicar observaciones. La detección admite un segundo
de tolerancia alrededor del umbral para que el jitter subsegundo del polling no
oculte una ausencia.

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

Una descarga que no supera la validación de GIF no se reintenta inmediatamente
ni se archiva como original. Se genera un diagnóstico seguro con tamaño, MIME
declarado y SHA-256, pero sin cuerpo, credenciales o URL efímera. El siguiente
ciclo periódico vuelve a consultar normalmente.

**Motivo:** repetir errores permanentes aumenta carga sin mejorar la
recuperación; conservar la última publicación mantiene el servicio útil durante
una incidencia temporal de AEMET.

---

## ADR-014 — Clasificación exacta y máscara temporal para Murcia

**Estado:** aceptada para `regional-v1`.

La extracción de Murcia usa el recorte `480×480`, una cobertura circular en
píxeles con centro `(240, 240)` y radio `250`, los once índices exactos
observados en la leyenda y una máscara binaria versionada. La máscara estática
excluye solo posiciones que mantienen el mismo índice clasificado en todas las
muestras de referencia; no excluye posiciones invariantes de fondo.

El amarillo puro se conserva fuera de la máscara y se descarta dentro de ella.
Así se eliminan los límites administrativos sin eliminar globalmente la clase
rotulada como 48 dBZ. Un cambio de dimensiones, modo o RGB esperado produce un
error explícito.

La máscara inicial se generó con 20 originales distintos de los días 23 y 24 de
julio de 2026. Excluyó 3.611 píxeles amarillos fijos y ninguna clase inequívoca.
El informe versionado conserva hashes, algoritmo y limitación conocida: un eco
idéntico en todas las referencias podría confundirse con un elemento fijo.

**Motivo:** las muestras comparten geometría y paleta, pero el amarillo también
dibuja fronteras. La separación espacial reproducible conserva más información
meteorológica que descartar el color completo y es auditable sin edición manual
opaca.

---

## ADR-015 — Calibración azimutal y salida Web Mercator para Murcia

**Estado:** aceptada para `regional-georeference-v1`.

El GIF regional de Murcia se interpreta como una rejilla azimutal equidistante
WGS84, norte arriba, de `480×480` píxeles y 1.000 metros por píxel. El radar
Murcia–Fortuna (`FTN`) ocupa el píxel `(240, 240)` y las coordenadas oficiales
`38.26438295, -1.18970006`. El alcance meteorológico publicado por AEMET se
limita a 240 km.

La decisión se validó contra ocho cruces provinciales de la topología que sirve
el visor AEMET, creada a partir de datos del IGN. La distancia entre el píxel
amarillo observado y la posición calculada fue 0,369 píxeles de media y 0,700
píxeles como máximo. La configuración falla si cualquier control supera un
píxel.

El worker reproyecta la capa a una rejilla rectangular EPSG:3857 de 1.000 metros
por píxel, recorta fuera del alcance nominal y usa exclusivamente vecino más
próximo. MapLibre recibe el PNG resultante como fuente `image` y cuatro esquinas
WGS84; no interpreta ni adivina la proyección original.

**Motivo:** una imagen azimutal colocada solo por sus cuatro esquinas deformaría
el interior. Reproyectar antes de servirla mantiene el ajuste durante zoom y
pan. El vecino más próximo conserva las clases RGBA exactas y evita inventar
valores meteorológicos intermedios.

---

## ADR-016 — Ventana visible de tres horas

**Estado:** aceptada; sustituye la duración de dos horas prevista inicialmente.

El backend y el frontend publican y reproducen las tres horas anteriores al
último fotograma disponible. Con una cadencia exacta de 10 minutos, Murcia puede
contener hasta 19 observaciones contando ambos extremos. Los originales siguen
con una retención predeterminada de 24 horas.

La cantidad real puede ser menor por ausencias o distinta cuando la única base
disponible es `retrievedAt` y el sondeo no coincide exactamente con la cadencia
del producto. En ningún caso se completa la ventana duplicando o interpolando
imágenes.

**Motivo:** dos horas ofrecían poco contexto para evaluar el desplazamiento de
la precipitación. Tres horas aumentan el contexto sin hacer pesado el
manifiesto ni la precarga del único radar de esta fase.

---

## ADR-017 — Derivado público inmutable por hash y crossfade de dos capas

**Estado:** aceptada para Murcia.

Cada original de Murcia se procesa una sola vez mientras sigan vigentes la
paleta, la máscara y la calibración. Su PNG Web Mercator se publica bajo una URL
que contiene el SHA-256 del original y el manifiesto lo referencia mediante
`imageUrl`.

El navegador precarga primero el último fotograma, deduplica solicitudes por URL
y alterna dos fuentes `image` de MapLibre para hacer una transición breve de
opacidad. Durante un hueco conserva visible la última capa real, pero mantiene
la hora original de esa imagen y marca el intervalo como `Sin dato`: no genera
una observación intermedia. Con `prefers-reduced-motion`, la transición dura
cero milisegundos.

**Motivo:** las URLs inmutables permiten caché y evitan reprocesamiento. Dos
capas suavizan el cambio visual sin interpolar reflectividad, de acuerdo con
ADR-005. Mantener la última imagen mejora la continuidad al seguir una tormenta
sin alterar el contrato del manifiesto.

---

## ADR-018 — Catálogo completo y estado sin datos

**Estado:** aceptada para la red regional.

Los 15 códigos regionales publicados en OpenAPI forman parte del catálogo, del
worker, del índice y del selector. La ausencia temporal de una imagen produce
un manifiesto vacío y estado `no-data`; no elimina ni deshabilita el
emplazamiento. Solo se dibuja reflectividad cuando un GIF supera la validación
estricta del perfil asignado.

Los emplazamientos oficiales sin endpoint OpenAPI no se consultan mediante
códigos inferidos. Se incorporarán cuando exista un contrato oficial.

**Motivo:** una indisponibilidad por mantenimiento no debe exigir desplegar
código ni hacer desaparecer un radar que volverá a publicar datos. A la vez, un
estado explícito evita presentar el servicio como actualizado.

---

## ADR-019 — Perfil regional conservador y georreferenciación por centro

**Estado:** aceptada con limitación documentada.

Las 12 muestras disponibles comparten plantilla indexada `480×530` y paleta de
64 entradas. `regional-safe-v1` las valida de forma exacta y reproyecta cada
rejilla desde una proyección azimutal equidistante centrada en su emplazamiento
oficial. Un cambio de plantilla o paleta interrumpe la publicación.

Murcia conserva su máscara temporal y la clase amarilla de 48 dBZ fuera de
elementos fijos. Los demás radares descartan ese amarillo, ambiguo con límites
administrativos, hasta contar con máscaras específicas construidas con varias
muestras.

**Motivo:** compartir un contrato observado reduce configuración duplicada sin
asumir silenciosamente que AEMET nunca lo cambiará. Descartar la clase ambigua
es una pérdida conocida y preferible a publicar fronteras como precipitación.

---

## ADR-020 — Ingesta regional secuencial y escalonada

**Estado:** aceptada.

Los productos se consultan secuencialmente con una pausa configurable de un
segundo entre ellos y sin espera después del último. Cada producto mantiene
reintentos y estado independientes; un error no interrumpe el resto del ciclo.

**Motivo:** evita ráfagas innecesarias contra AEMET OpenData y conserva un
comportamiento determinista y observable.

---

## ADR-021 — Máscara temporal específica por radar

**Estado:** aceptada; sustituye la limitación amarilla de ADR-019 cuando existe
evidencia suficiente.

Cada radar calibrado referencia un PNG binario propio en su cuadrícula
`480×480`. `ambiguous-temporal-invariance-v2` deduplica los originales por
SHA-256 y exige al menos tres imágenes distintas con dos horas entre la primera
y la última. Solo una clase marcada como ambigua puede convertirse en
exclusión fija; una clase inequívoca nunca se enmascara aunque permanezca
inmóvil.

El informe adyacente registra radar, algoritmo, hashes, horas, ventana,
configuración y número de píxeles por clase. Un producto 404, congelado o con
menos de tres hashes mantiene `discard` y no hereda la máscara de otro radar.
El catálogo propaga explícitamente `static-mask` al clasificador y un cambio de
política invalida los derivados anteriores.

**Motivo:** los límites dibujados difieren entre emplazamientos. Compartir una
máscara produciría falsos huecos o fronteras meteorológicas; forzar una
calibración sin diversidad temporal podría borrar un eco amarillo real.

---

## ADR-022 — Estado AEMET 404 como ausencia de datos

**Estado:** aceptada.

La pasarela de AEMET responde HTTP 200 y declara `estado: 404` cuando un
producto válido no tiene datos. El worker lo representa como `no-data`: ejecuta
un único intento, conserva y reconstruye cualquier manifiesto previo, aplica
retención, no crea `lastError` y vuelve a consultar en el siguiente ciclo.

Una combinación de productos `current` y `no-data` mantiene el estado global
`ok`. La presencia de `delayed` o `error` lo deja `degraded`; si todos están sin
datos, el estado global es `no-data`. Los HTTP 5xx, fallos de transporte,
contratos inválidos y descargas no válidas continúan siendo errores.

**Motivo:** OpenAPI define 404 como “petición sin datos” y mantiene publicados
los códigos regionales. Tratar una ausencia funcional como una avería produce
alarmas falsas sin aportar capacidad de recuperación.
