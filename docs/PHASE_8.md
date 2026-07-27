# Fase 8 — UX final, PWA y robustez

## Resultado

El frontend es una PWA responsive e instalable que conserva una interfaz útil
cuando desaparece la conexión. La vista sigue centrada en el radar: selector,
estado, antigüedad del dato, mapa, opacidad y reproducción temporal.

No se han añadido cuentas, alertas, nowcasting ni capas meteorológicas nuevas.
El despliegue y la operación del servidor siguen reservados para la Fase 9.

## PWA y funcionamiento sin conexión

`manifest.webmanifest` define nombre, colores, modo `standalone` e iconos PNG de
192 y 512 píxeles. El service worker se registra únicamente en producción y
mantiene cuatro cachés versionadas:

- shell de la aplicación;
- JSON de índice, salud y manifiestos;
- un máximo de 56 imágenes de radar;
- un máximo de 90 recursos de cartografía visitados.

Las navegaciones y los JSON usan red primero y recuperan la última respuesta
guardada si la red falla. Imágenes y recursos estáticos usan caché primero.
Una activación nueva elimina las versiones antiguas.

Además de la caché HTTP de la PWA, cada respuesta JSON se valida con su contrato
TypeScript antes de guardarse en `localStorage`. Se mantiene una única copia
válida por índice, estado de salud y radar. Una respuesta inválida nunca
reemplaza una copia anterior válida. Si tampoco hay copia local, la interfaz
muestra un estado vacío con reintento.

La primera visita necesita red. A partir de una visita controlada por el service
worker, la aplicación, los historiales ya consultados y las teselas visitadas
pueden recuperarse sin conexión. Una zona de mapa no visitada no se inventa ni
se sustituye por cartografía de otra fuente.

## Controles y estado

- El selector agrupa composición nacional y 15 radares regionales y conserva la
  última elección en el dispositivo.
- Los radares regionales parten de un encuadre de unos 150 km de radio (`zoom
  7.3` a 768 px) y adaptan ese zoom al ancho disponible para conservar una
  extensión geográfica parecida en móvil y escritorio; la composición nacional
  conserva su encuadre general. Canarias aplica la misma adaptación desde su
  ajuste específico. El mapa descuenta dinámicamente la altura de los controles
  temporales y añade un margen de contexto para que localidades situadas al sur
  del radar no queden ocultas por el reproductor.
- `Cerca de mí` usa `navigator.geolocation`, calcula la distancia de gran
  círculo en el navegador y selecciona el radar regional más cercano. Las
  coordenadas no se envían ni se guardan.
- `Ampliar` usa la Fullscreen API sobre el reproductor. MapLibre conserva la
  misma instancia y responde al cambio de tamaño del viewport.
- La opacidad se conserva como preferencia local.
- Los estados `Actualizado`, `Retrasado`, `Sin datos` y `Error temporal` tienen
  texto y color. Una copia guardada degrada un estado actual a `Retrasado`.
- La hora y la antigüedad relativa del último dato están siempre presentes. En
  pantalla completa cada tarjeta conserva también la antigüedad del instante
  seleccionado.
- La pestaña vuelve a consultar el índice, la salud y el manifiesto seleccionado
  cada diez minutos. Si estaba mostrando el último fotograma, avanza al nuevo;
  si el usuario estaba explorando el historial, conserva ese instante mientras
  siga publicado.
- La pérdida y recuperación de conectividad no eliminan el manifiesto visible.

## Accesibilidad y responsive

Todos los controles nativos tienen etiqueta accesible, estado `aria-pressed`
cuando corresponde y foco visible. El reproductor funciona con botones,
deslizador, tabulador, Intro y flechas izquierda/derecha. Los cambios de
reproducción, ubicación y conexión usan regiones de estado.

El diseño cambia de tres columnas en escritorio a una cabecera compacta y un
reproductor a borde completo en móvil. Se respetan `safe-area-inset-*`,
`100dvh`, controles táctiles y anchos desde 320 píxeles.

`prefers-reduced-motion: reduce` elimina animaciones, desplazamiento suave y
crossfade. La reproducción se pausa cuando la pestaña deja de estar visible.

## Memoria y rendimiento

La precarga ya no recorre un historial completo. Carga como máximo ocho
fotogramas priorizando el último y los cercanos al instante elegido, y conserva
como máximo doce promesas de carga. El cambio de radar desmonta MapLibre,
marcadores, observadores, fuentes y listeners.

MapLibre y su CSS se cargan en un chunk diferido. El shell inicial de producción
queda en aproximadamente 216 kB minificados (68 kB gzip); la cartografía se
descarga después. El tamaño restante del chunk de mapa corresponde
principalmente a MapLibre y queda aislado de la primera interacción.

El orden de CSS es relevante: al resolver el chunk diferido, MapLibre puede
inyectar su hoja después de `styles.css`. Por eso la geometría del contenedor se
declara con `.map-canvas.maplibregl-map`, que tiene especificidad suficiente
para conservar `position: absolute`, `width: 100%` y `height: 100%`. No debe
sustituirse por una regla menos específica sin ejecutar las pruebas de
navegador.

MapLibre construye la URL de su worker mediante una función interna que Vite no
puede analizar como el patrón estático `new Worker(new URL(...))`. El frontend
importa por ello `maplibre-gl-worker.mjs?worker&url` y configura esa URL antes de
crear el mapa. Así el build emite un worker versionado junto con todas sus
dependencias; sin esta declaración, el raster de relieve puede aparecer aunque
no funcionen las teselas vectoriales, las carreteras ni las etiquetas.

Las métricas se recogen solo en memoria, sin telemetría remota, en
`window.__RADAR_PERFORMANCE__`:

- tiempo hasta que el primer manifiesto válido deja la aplicación lista;
- FCP y LCP;
- CLS;
- INP cuando el navegador ofrece entradas `event`.

## Pruebas

Vitest cubre contratos existentes, caché válida e inválida, fallback sin red,
geolocalización local, antigüedad, actualización automática sin interrumpir el
historial y límites de precarga.

Playwright ejecuta los recorridos principales en Chrome de escritorio y móvil:

- carga, edad visible, selector nacional, opacidad, reproducción y teclado;
- lienzo WebGL visible y contenedor de mapa con altura real, para detectar
  regresiones de orden o especificidad CSS;
- descarga satisfactoria de al menos una tesela vectorial de OpenFreeMap, para
  comprobar que el worker de producción está empaquetado y operativo;
- recarga real con el contexto de navegador sin conexión;
- `prefers-reduced-motion`;
- permiso de geolocalización y selección del radar más cercano.

Comandos:

```bash
npm --prefix apps/web test
npm --prefix apps/web run test:e2e
npm --prefix apps/web run lint
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
```

## Producción local y diagnóstico

El artefacto estático se prueba con los JSON e imágenes generados por el worker
mediante:

```bash
make poll-once
make preview-live
```

`make preview-live` encadena el build, comprueba que existen `dist/index.html`,
`data/radar/index.json` y `data/status/health.json`, crea
`tmp/live-preview/`, enlaza los datos locales y sirve el resultado en
`http://127.0.0.1:4173/`. Al ser una única dependencia de Make, un build
interrumpido detiene el proceso y nunca se publica como si estuviera completo.

Durante la validación de la fase se detectaron tres síntomas diferentes:

1. Servir un `dist` copiado después de cancelar Vite produjo un listado de
   directorio porque faltaba `index.html`.
2. Tras convertir MapLibre en un import diferido, su regla
   `.maplibregl-map { position: relative }` se cargaba después de la regla de la
   aplicación. El contenedor quedaba con altura computada `0px`, aunque estilo,
   teselas, manifiesto e imágenes respondieran correctamente.
3. El servidor de desarrollo resolvía el worker de MapLibre desde
   `node_modules`, pero el build no lo emitía. El mapa de producción mostraba
   únicamente el raster de relieve: faltaban teselas vectoriales, carreteras,
   límites y etiquetas.

El segundo caso no era un problema de versión, worker WebGL, georreferenciación
ni reflectividad. El tercero sí correspondía al empaquetado del worker. Ambas
correcciones se describen en “Memoria y rendimiento”; la prueba E2E mide la
geometría real y exige una tesela vectorial, además del estado
`data-map-ready`.

Los mensajes `beforeinstallprompt` y la advertencia sobre la metaetiqueta de
iOS no impiden renderizar el mapa. Un `AbortError` aislado durante desarrollo
puede proceder de la limpieza deliberada de efectos de React Strict Mode; si
las peticiones de estilo y datos completan y el mapa tiene dimensiones, no
indica por sí solo un fallo de publicación.

La instalación PWA y la Fullscreen API dependen del soporte y de las políticas
del navegador. El botón `Instalar` aparece cuando el navegador emite
`beforeinstallprompt`; en plataformas que usan su propio menú de instalación,
el manifiesto sigue disponible.
