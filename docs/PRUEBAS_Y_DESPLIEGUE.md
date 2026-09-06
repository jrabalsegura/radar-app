# Probar y desplegar la revisión del radar

Esta guía corresponde a `codex/radar-review-fixes`. El repositorio es
<https://github.com/jrabalsegura/radar-app>. Para una instalación nueva, usa
[DEPLOY.md](DEPLOY.md); los pasos de servidor de esta guía actualizan la
instalación existente mediante `ssh remote`.

## 1. Preparar y validar en el Mac

```bash
cd /Users/jraba/Desktop/aemet-radar-app-planning
git branch --show-current
git status --short
make install
make check
cd apps/web
npx playwright install chrome
npm run test:e2e
cd ../..
```

Se recomiendan Node 24 y Python 3.13, como en CI. `make install` reinstala también
el código del worker: no basta con editar `src/` y ejecutar una CLI instalada
anteriormente. Las pruebas unitarias no necesitan una API key. Playwright usa
Chrome, un servidor local y cartografía pública OpenFreeMap; necesita conexión
para comprobar el fondo real. Guarda capturas en `apps/web/test-results/` y,
ante fallos, trazas que puedes abrir con `npx playwright show-trace ruta/trace.zip`.

La CI ejecuta lint, formato, tipado, unidades, build, Playwright en escritorio y
móvil, construcción de ambas imágenes y un smoke test contra nginx del
contenedor. Comprueba las 16 fuentes y todas las URLs de imágenes y coberturas
publicadas. No consulta AEMET ni recibe la key. Los resultados del navegador se
conservan durante siete días como artefacto `browser-results`.

## 2. Revisar la interfaz con las muestras incluidas

```bash
make dev-web
```

Abre la URL que imprime Vite. Las imágenes incluidas son históricas: es correcto
que aparezcan como **Retrasado**. La muestra nacional procede de originales del
24 de agosto de 2026: tiene 23 observaciones y un hueco a las 10:30 UTC
—12:30 en Madrid—. No se ha creado una imagen para rellenarlo.

Prueba en escritorio y en un móvil, incluyendo una anchura de 360 px:

| Acción | Resultado esperado |
| --- | --- |
| Abrir Murcia | Ciudades legibles en la primera vista; botones Cerca de mí y Nacional visibles. |
| Aumentar zoom | Más poblaciones progresivamente; Liberty conserva carreteras, costa y relieve. Los nombres dependen también de las teselas disponibles y de las colisiones. |
| Mover/alejar el mapa y pulsar Centrar radar | Recupera centro y zoom iniciales. |
| Explorar una hora y esperar diez minutos o desconectar/reconectar | Conserva encuadre y hora explorada mientras exista; si estabas en la última, sigue la nueva última. |
| Elegir otra hora | La línea Imagen indica la hora realmente dibujada; durante la carga conserva la hora anterior y avisa. |
| Volver rápidamente de A a B y a A con red lenta | B no aparece después; prueba también un hueco sin imagen anterior. |
| Seleccionar el hueco nacional de 12:30 | Marca «intervalo sin dato» y conserva la imagen de 12:20 con su hora real. |
| Pulsar Ir a la última | Vuelve al extremo más reciente y pausa la reproducción; el fotograma dice Última. |
| Elegir Las Palmas en las muestras | Indica Obtenida cuando no hay hora de producto, y fuente alternativa. |
| Cerca de mí junto al radar ya seleccionado, dos veces | Conserva el historial; la ubicación se procesa en el dispositivo. |
| Cerca de mí junto a un radar sin imágenes | Va directamente a la composición nacional. Un radar con imágenes antiguas sigue siendo consultable y muestra su antigüedad. |
| Opciones → Ver zonas sin cobertura, en nacional | Superpone en gris las zonas marcadas por AEMET para esa imagen, si las hay; no sombrea el fondo claro sin ecos. |
| La misma opción en un regional | Sombrea el exterior del alcance nominal de 240 km. No afirma conocer bloqueos ni cobertura efectiva dentro del círculo. |
| Abrir la leyenda dBZ | Muestra los once umbrales; no convierte a mm/h. |
| Desconectar tras cargar y recargar | Mantiene la copia guardada, informa de la desconexión y no la declara actualizada. |
| Teclado y movimiento reducido | Conserva atajos, foco, reproducción y ausencia de transiciones al pedir movimiento reducido. |

La calibración continúa en `config/georeferencing/`, `config/masks/` y
`config/radars.yaml`. Los cambios de etiquetas no alteran coordenadas, proyección,
recorte ni remuestreo de las imágenes. El control anterior «Ver cobertura»
conserva el perímetro de diagnóstico y el emplazamiento.

## 3. Probar el worker sin modificar los datos originales

Reconstruye en una copia que solo contiene los originales y sus informes:

```bash
mkdir -p tmp/review-data/raw
rsync -a data/raw/ tmp/review-data/raw/
.venv/bin/aemet-radar rebuild-manifests --data-dir tmp/review-data
.venv/bin/aemet-radar rebuild-manifests --data-dir tmp/review-data --product regional-mu
jq '.radars | length' tmp/review-data/radar/index.json
jq '.window.minutes' tmp/review-data/radar/regional-mu/manifest.json
jq '.frames[-1] | {time, imageUrl, noCoverageUrl, sourceProvider}' \
  tmp/review-data/radar/national/manifest.json
```

Espera **16 fuentes** y **230 minutos**, también tras la reconstrucción parcial.
Las nuevas imágenes tienen la ruta
`/radar/<producto>/frames/<hash-original>/<version-procesado>/...png`.
`rebuild-manifests` no consulta AEMET y no ejecuta limpieza. La copia puede ocupar
más que `raw/` porque genera derivados.

Para ver esa publicación con el build, en un directorio temporal nuevo:

```bash
make build
preview_dir=$(mktemp -d "$PWD/tmp/review-preview.XXXXXX")
rsync -a apps/web/dist/ "$preview_dir/"
rm -rf "$preview_dir/radar" "$preview_dir/status"
ln -s "$PWD/tmp/review-data/radar" "$preview_dir/radar"
ln -s "$PWD/tmp/review-data/status" "$preview_dir/status"
python3 -m http.server 4174 --bind 127.0.0.1 --directory "$preview_dir"
```

Abre <http://127.0.0.1:4174>. Para datos nuevos, configura `.env` siguiendo el
README y ejecuta **un único** worker. No ejecutes `poll-once`, reconstrucciones y
el scheduler a la vez sobre el mismo directorio.

La ventana de 230 minutos es fija. Se ha retirado `--history-hours` y la lectura
de `AEMET_HISTORY_HOURS`; una variable antigua se ignora. La retención de
originales continúa siendo configurable, con 24 horas por defecto. La limpieza
protege las publicaciones y hashes compartidos; solo recoge derivados huérfanos
tras 24 horas desde que detectó que dejaron de estar referenciados. En el primer
ciclo no debe desaparecer de golpe todo el material antiguo. Si encuentra
informes o un manifiesto ilegibles, evita limpiar sin referencias fiables.

## 4. Medir arranque y transporte

Sobre el build, abre la consola del navegador:

```javascript
JSON.stringify(window.__RADAR_PERFORMANCE__, null, 2)
```

- `appReadyMilliseconds`: manifiesto disponible e interfaz preparada.
- `radarReadyMilliseconds`: primera imagen cargada por MapLibre y primer render
  con esa capa visible; no espera todas las teselas del mapa base.
- `firstRadarImageUrl`: imagen a la que corresponde esa medición.
- `radarImageRequests`, `radarImageTransferBytes`, `radarImageEncodedBytes` y
  `radarImageDurationMilliseconds`: acumulados de recursos de imagen del mismo
  origen, incluidas las precargas y la capa sin cobertura.

Los tamaños los proporciona Resource Timing. Un cero puede indicar caché o una
limitación del navegador; la suma de duraciones no es tiempo de reloj porque
puede haber peticiones concurrentes. Las métricas se mantienen en memoria y no
se envían a ningún servidor. Playwright las adjunta al resultado.

Compara una primera visita sin caché con una recarga, usando el mismo radar y
conexión. Conservamos PNG y sus clases exactas; cambiar formato requiere medir y
comparar los píxeles primero. nginx comprime JavaScript, CSS y JSON; las imágenes
conservan caché inmutable y las publicaciones JSON siguen con `no-store`.

## 5. Prueba con el servidor de producción en local

Con Docker Desktop u otro motor Docker en ejecución y `.env` configurado:

```bash
make container-up
make container-status
make container-check
make container-logs
```

Abre <http://127.0.0.1:8080>. Al terminar:

```bash
make container-down
```

No elimina `data/`. La comprobación verifica HTTP, las 16 fuentes, manifiestos,
URLs publicadas, cabeceras de imágenes y el aislamiento de la key. El directorio
real se modifica al ejecutar el worker; usa los pasos anteriores si solo quieres
probar una reconstrucción aislada.

## 6. Publicar el código en GitHub

Revisa el diff, conserva los cambios en un commit y sube la rama. Si todavía hay
cambios sin commit, selecciona explícitamente los archivos revisados:

```bash
git status --short
git diff --check
git diff --stat
# Si es necesario: git add <archivos revisados> y git commit -m "Fix radar publication and viewer"
git push -u origin codex/radar-review-fixes
```

Abre el PR hacia `main` y espera a que **Frontend**, **Worker** y **Container
images** estén verdes. Integra el PR antes de seguir con el procedimiento basado
en `main`. No añadas `.env`, `data/` ni los temporales.

## 7. Actualizar el servidor existente mediante SSH

Entra en el servidor y verifica que el checkout esté limpio y en `main`. Si
producción sigue otra rama, elige explícitamente esa rama; no mezcles `main`
con un checkout de otra rama mediante `pull`.

```bash
ssh remote
cd /var/www/aemet-radar
git branch --show-current
git status --short
sudo systemctl start aemet-radar-backup.service
sudo systemctl show aemet-radar-backup.service --property=Result --value
# El último comando debe decir "success"; en otro caso revisa el backup.
git fetch origin
git switch main
git pull --ff-only origin main
release=$(git rev-parse --short=12 HEAD)
```

Construye las dos imágenes antes de cambiar los servicios:

```bash
sudo podman build --file deploy/containers/worker.Containerfile \
  --tag "localhost/aemet-radar-worker:$release" .
sudo podman build --file deploy/containers/web.Containerfile \
  --tag "localhost/aemet-radar-web:$release" .
sudo podman tag localhost/aemet-radar-worker:current localhost/aemet-radar-worker:rollback
sudo podman tag localhost/aemet-radar-web:current localhost/aemet-radar-web:rollback
```

La migración regenera derivados con URLs versionadas desde disco. Para evitar
dos escritores, detén el worker y ejecuta la imagen nueva una sola vez. El web
sigue sirviendo la publicación durante la operación:

```bash
sudo systemctl stop aemet-radar-worker.service
sudo podman run --rm --user 10001:10001 \
  --volume /var/lib/aemet-radar/data:/data:rw,z \
  "localhost/aemet-radar-worker:$release" rebuild-manifests --data-dir /data
```

**Si falla, no continúes con el cambio de etiquetas:** arranca el worker anterior
con `sudo systemctl start aemet-radar-worker.service`, revisa el error y repite
cuando esté resuelto. La reconstrucción no ejecuta la limpieza ni necesita el
secreto.

Si termina correctamente:

```bash
sudo podman tag "localhost/aemet-radar-worker:$release" localhost/aemet-radar-worker:current
sudo podman tag "localhost/aemet-radar-web:$release" localhost/aemet-radar-web:current
sudo systemctl start aemet-radar-worker.service
sudo systemctl restart aemet-radar-web.service
./deploy/scripts/smoke-test.sh http://127.0.0.1:8088
./deploy/scripts/smoke-test.sh https://radar.joserabalsegura.com
sudo nginx -t
sudo systemctl status aemet-radar-worker.service aemet-radar-web.service
```

Esta revisión no cambia los Quadlets. **Conserva el virtual host de
`/etc/nginx/sites-available/radar.joserabalsegura.com` que modificó Certbot.** No
copies de nuevo la plantilla HTTP del repositorio ni ejecutes la sección de
instalación inicial de nginx. La compresión nueva está en nginx del contenedor
y llega al reconstruir el web.

Verifica la UI por HTTPS, las nuevas URLs, una hora del historial, cobertura y
modo sin conexión. Después de un ciclo, comprueba que avanza `generatedAt`:

```bash
curl -fsS http://127.0.0.1:8088/status/health.json \
  | jq '{generatedAt, status, products: [.products[] | {id, status, lastPollAt, lastFrameTime}]}'
sudo podman logs --since 15m aemet-radar-worker
sudo df -h /var/lib/aemet-radar/data
sudo du -sh /var/lib/aemet-radar/data/radar /var/lib/aemet-radar/data/processed
```

La primera regeneración necesita espacio para las versiones nuevas y las
anteriores. El recolector empieza a recuperar huérfanos después de su margen de
24 horas; no borres manualmente las carpetas por hash. Los navegadores recibirán
las URLs nuevas con el manifiesto, y el service worker tiene una versión nueva.

## 8. Volver al release anterior

```bash
sudo systemctl stop aemet-radar-worker.service
sudo podman tag localhost/aemet-radar-worker:rollback localhost/aemet-radar-worker:current
sudo podman tag localhost/aemet-radar-web:rollback localhost/aemet-radar-web:current
sudo systemctl start aemet-radar-worker.service
sudo systemctl restart aemet-radar-web.service
cd /var/www/aemet-radar
./deploy/scripts/smoke-test.sh http://127.0.0.1:8088
```

El código anterior puede leer los campos adicionales de los manifiestos y las
URLs versionadas; la ventana sigue siendo de 230 minutos. No restaura ni borra
datos y conserva HTTPS. Mantén la copia de seguridad hasta haber observado el
nuevo release. La restauración de datos es un procedimiento separado en
[OPERATIONS.md](OPERATIONS.md).
