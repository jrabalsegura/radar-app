# Probar y desplegar la revisión del radar

Esta guía corresponde a `codex/radar-review-fixes`. El repositorio es
<https://github.com/jrabalsegura/radar-app>. Para una instalación nueva, usa
[DEPLOY.md](DEPLOY.md); los pasos de servidor de esta guía actualizan la
instalación existente mediante `ssh remote`.

## 1. Preparar Docker y la configuración

La prueba local usa **Docker Compose con dos contenedores**: `web` sirve el
frontend mediante nginx y `worker` consulta AEMET y procesa las imágenes. Los
archivos de construcción siguen presentes; se llaman `Containerfile`, un nombre
alternativo a `Dockerfile` que Compose ya tiene configurado:

- [web.Containerfile](../deploy/containers/web.Containerfile)
- [worker.Containerfile](../deploy/containers/worker.Containerfile)
- [compose.yaml](../compose.yaml)

Node, Python y las dependencias de la aplicación se instalan dentro de las
imágenes. Para este recorrido necesitas Docker Desktop en marcha, Make y, para
la comprobación automática, `curl` y `jq` en el Mac.

Abre Docker Desktop y espera a que indique que el motor está en ejecución.
Después, en una terminal:

```bash
cd /Users/jraba/Desktop/aemet-radar-app-planning
docker info --format '{{.ServerVersion}}'
docker compose version
```

Ambos comandos deben terminar correctamente. Si ya tienes `.env` configurado,
úsalo. Si todavía no existe, créalo sin sobrescribir uno anterior:

```bash
if [ ! -f .env ]; then
  cp .env.example .env
fi
chmod 600 .env
```

Edita `.env` con tu editor y configura `AEMET_API_KEY`. El secreto lo recibe
únicamente el worker. Conserva Liberty como estilo. Si tienes un worker nativo
arrancado con `make run-worker`, detenlo con Ctrl+C antes de continuar: debe haber
un solo escritor sobre `data/`.

## 2. Construir y arrancar la prueba

```bash
make container-up
make container-status
```

`container-up` construye las imágenes desde el código actual y arranca ambos
servicios en segundo plano. El primer build necesita descargar las imágenes
base y dependencias. Los siguientes reutilizan la caché de construcción.

Abre **<http://127.0.0.1:8080>**. Es la aplicación con el nginx del contenedor y
los datos reales del worker. Las muestras históricas de `apps/web/public/radar/`
no se incluyen en la imagen web. Ambos servicios usan `./data/` como directorio
persistente; el web lo monta en solo lectura.

Si faltan imágenes al principio, consulta el avance:

```bash
make container-logs
```

El primer ciclo puede tardar varios minutos. Ctrl+C cierra el seguimiento del
log; los contenedores continúan funcionando. Cuando termine el primer ciclo:

```bash
make container-check
```

Debe indicar `Smoke test correcto`. Comprueba las 16 fuentes, sus manifiestos,
las URLs de imágenes y coberturas, las cabeceras de caché y el aislamiento de la
key. `health: starting` puede aparecer durante el arranque. Un estado de datos
`degraded` puede deberse a radares sin datos recientes, aunque los contenedores
estén sanos.

Si el puerto 8080 ya está ocupado, usa el mismo puerto alternativo en los
comandos de esa prueba:

```bash
make container-up RADAR_HTTP_PORT=8081
make container-check RADAR_HTTP_PORT=8081
```

En ese caso abre <http://127.0.0.1:8081>.

## 3. Comprobar los cambios en el navegador

Prueba la ventana de escritorio y la vista de dispositivo de las herramientas
de desarrollo del navegador —por ejemplo, 360 o 393 px de ancho—. El puerto
publicado está limitado al propio Mac: `127.0.0.1` en un teléfono apuntaría al
propio teléfono.

| Acción | Resultado esperado |
| --- | --- |
| Abrir Murcia | Ciudades legibles en la primera vista; Cerca de mí y Nacional visibles. |
| Aumentar zoom | Más poblaciones progresivamente; Liberty conserva carreteras, costa y relieve. |
| Mover/alejar el mapa y pulsar Centrar radar | Recupera centro y zoom iniciales. |
| Explorar una hora y esperar diez minutos o desconectar/reconectar | Conserva encuadre y hora explorada mientras exista; si estabas en la última, sigue la nueva última. |
| Elegir otra hora | Imagen indica la hora realmente dibujada; durante la carga conserva la anterior y avisa. |
| Volver rápidamente de A a B y a A con red lenta | B no aparece después de volver a A. |
| Seleccionar un hueco, si lo hay en los datos actuales | Marca el intervalo sin dato y conserva la imagen anterior con su hora real. |
| Pulsar Ir a la última | Vuelve al extremo más reciente y pausa; el fotograma dice Última. |
| Ver una imagen de fallback sin hora de producto, si la hay | Indica Obtenida, hora del producto desconocida y fuente alternativa. |
| Cerca de mí junto al radar ya seleccionado, dos veces | Conserva el historial; la ubicación se procesa en el dispositivo. |
| Cerca de mí junto a un radar sin imágenes | Va directamente a composición nacional. Un radar con imágenes antiguas sigue siendo consultable y muestra su antigüedad. |
| Opciones → Ver zonas sin cobertura, en nacional | Superpone las zonas marcadas por AEMET para esa imagen, si las hay; no sombrea el fondo claro sin ecos. |
| La misma opción en un regional | Sombrea el exterior del alcance nominal de 240 km. |
| Abrir la leyenda dBZ | Muestra los once umbrales; no convierte a mm/h. |
| Desconectar tras cargar y recargar | Mantiene la copia guardada, informa de la desconexión y no la declara actualizada. |
| Teclado y movimiento reducido | Conserva atajos, foco y reproducción. |

Para comprobar que los datos siguen actualizándose:

```bash
curl -fsS http://127.0.0.1:8080/status/health.json \
  | jq '{generatedAt, status, products: [.products[] | {id, status, lastPollAt, lastFrameTime}]}'
```

Repite tras un ciclo y comprueba que avanza `generatedAt`. La hora del último
fotograma puede permanecer igual si AEMET no ha publicado otro. La calibración
no cambia con el estilo de etiquetas; el control «Ver cobertura» conserva el
perímetro de diagnóstico y el emplazamiento.

## 4. Medir arranque y transporte

En la aplicación de <http://127.0.0.1:8080>, abre la consola del navegador:

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

## 5. Reconstruir, repetir y detener la prueba

**Si ya tenías datos de la versión anterior** y quieres probar inmediatamente
las nuevas URLs y coberturas, puedes regenerarlos desde sus originales dentro
del contenedor. Esto no consulta AEMET ni ejecuta limpieza:

```bash
docker compose stop worker
RADAR_UID="$(id -u)" RADAR_GID="$(id -g)" \
  docker compose run --rm --no-deps worker rebuild-manifests --data-dir /data
make container-up
make container-check
```

Ejecuta este bloque después de haber construido las imágenes con el paso 2.
Si la reconstrucción falla, revisa su error; `make container-up` permite volver
a arrancar el worker. No ejecutes la reconstrucción mientras otro worker esté
escribiendo. Para probar la operación parcial puedes añadir
`--product regional-mu` al comando de reconstrucción: el catálogo debe seguir
teniendo 16 fuentes y la ventana, 230 minutos.

**Después de cambiar código**, vuelve a ejecutar:

```bash
make container-up
make container-check
```

Compose reconstruye y reemplaza los contenedores que cambien. Un simple reinicio
no incorpora cambios de código: estos están dentro de las imágenes.

**Para detener la prueba:**

```bash
make container-down
```

Elimina los contenedores de esta aplicación y su red, conservando `./data/`.
Durante la ejecución, el worker sí aplica la política normal de retención sobre
ese directorio: 24 horas de originales por defecto, protección de imágenes
publicadas y hashes compartidos, y 24 horas adicionales desde que detecta que
un derivado quedó huérfano. La ventana pública es fija de 230 minutos.

La CI se encarga además de lint, formato, tipado, unidades, build, Playwright en
escritorio/móvil y construcción de contenedores. Los resultados del navegador
se guardan siete días como artefacto `browser-results`. Este recorrido local
comprueba la aplicación ejecutándose en contenedores con datos reales.

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
