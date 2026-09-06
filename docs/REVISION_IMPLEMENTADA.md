# Revisión implementada — 6 de septiembre de 2026

Implementación de los diez hallazgos altos y medios de
[REVIEW_2026-09-06.md](REVIEW_2026-09-06.md) y de las decisiones posteriores del
usuario. Rama: `codex/radar-review-fixes`.

| Hallazgo | Corrección y comprobación |
| --- | --- |
| P1 · La máscara borraba ecos inequívocos | La exclusión estática solo afecta a la clase ambigua. Golden actualizado y prueba de un eco verde bajo una frontera. |
| P1 · Derivados sin retención | Recolección con referencias de originales/manifiestos, protección de hashes compartidos y 24 h desde la detección de orfandad. Pruebas de margen, referencias compartidas y manifiesto ilegible. |
| P1 · GIF nacional desplazaba PNG por hora | Se resuelve publicabilidad antes de deduplicar. El procesamiento nacional ignora GIF al calcular su ventana. Prueba con PNG y GIF de la misma hora. |
| P1 · Retención borraba el último PNG nacional | Publicación antes de limpieza y protección de los originales publicados. Prueba con PNG de más de 24 h y GIF reciente. |
| P1 · Carrera A → B → A | Cancelación de la fuente pendiente en cada selección; la imagen solo se muestra tras cargar la fuente real. Pruebas de retorno a A, hueco y error inicial. |
| P2 · Cerca de mí vaciaba el radar actual | Selección idempotente; prueba de dos pulsaciones sin perder el historial ni repetir la carga. |
| P2 · Actualizado no caducaba | Recalcula la frescura con reloj, cadencia y edad de health/dato. Pruebas de health congelado, ausente y caché. |
| P2 · Refresco reiniciaba el mapa | Instancia asociada al identificador, no a la identidad del objeto JSON; ajustes del panel conservan el encuadre. Recentrado explícito probado. |
| P2 · URL inmutable cambiaba de contenido | Ruta con hash del original y versión efectiva de algoritmo/configuración/coordenadas. Prueba de cambio de máscara sin modificar el archivo publicado anteriormente. |
| P2 · Opciones rompían el contrato | Reconstrucciones parciales mantienen las 16 fuentes; ventana fija de 230 minutos y retirada de la opción. Pruebas de catálogo y CLI. |

También se han añadido:

- hora de la imagen dibujada, fecha/zona, aviso de hueco o carga y distinción de
  hora obtenida/fuente alternativa;
- Nacional, Centrar radar, Ir a la última y leyenda dBZ en móvil y escritorio;
- selección nacional directa si el regional más cercano no tiene imágenes;
- cobertura nacional por observación y exterior del alcance nominal regional,
  como capa opcional separada de los ecos;
- Liberty con rótulos sobre la reflectividad, mejor contraste y pueblos/aldeas
  desde zoom 5/7, según contenido de las teselas;
- hooks de catálogo/manifiesto y geolocalización, y módulo de carga de fuentes;
- métricas locales de primer radar renderizado y transporte de imágenes;
- compresión HTTP de JS/CSS/JSON, nueva versión de service worker y tolerancia a
  fallos de cuota al guardar una respuesta descargada correctamente;
- Playwright en CI y smoke test de las 16 fuentes con todas sus URLs de imagen;
- guía [PRUEBAS_Y_DESPLIEGUE.md](PRUEBAS_Y_DESPLIEGUE.md), con migración de
  derivados, actualización por GitHub/SSH, conservación de Certbot y rollback.

## Evidencia de validación

- `make check` correcto: lint, formato, tipado, **42 pruebas frontend**, **110
  pruebas worker** y build de producción.
- Chrome sobre el build final: **11 E2E correctos**, una omisión prevista de
  pantalla completa móvil. Usa MapLibre, PNG y cartografía OpenFreeMap reales.
- Capturas de escritorio y móvil revisadas: controles visibles, hora coherente,
  etiquetas legibles sobre los ecos y ausencia de desbordamiento horizontal.
- Todas las referencias de imagen/cobertura de las muestras existen; YAML de CI
  y sintaxis del smoke test validados.
- La muestra nacional se regeneró desde originales archivados del 24 de agosto:
  23 imágenes, un hueco real y capas de cobertura con URLs versionadas. No se
  ejecutó una nueva ingesta contra AEMET ni se limpió `data/`.
- En la pasada local de navegador, `appReady` se midió alrededor de 56–63 ms y el
  primer radar alrededor de 492–514 ms. Son observaciones sobre localhost y
  caché de esa ejecución, no un benchmark de producción. Los bytes transferidos
  pueden ser cero con caché; la guía explica cómo comparar visitas.

## Límites de esta entrega

No se han cambiado los archivos de calibración, paletas ni emplazamientos.
No se ha sustituido el proveedor del mapa ni el formato PNG. El chunk de
MapLibre mantiene el aviso de tamaño de Vite —aproximadamente 955 kB antes de
compresión, 249 kB gzip— y carga de forma diferida.

La prueba local de contenedores no se pudo ejecutar porque el motor Docker no
estaba en marcha; queda incorporada a CI y documentada para el Mac. El workflow
no se ha ejecutado aún en GitHub. No se ha hecho push ni actualizado el servidor
SSH. La limpieza de derivados requiere observar ciclos reales después del
margen de 24 horas; su comportamiento se ha probado con datos aislados y reloj
controlado.
