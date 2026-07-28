# Despliegue

Esta guía cubre dos destinos distintos:

1. una prueba prolongada en el Mac de desarrollo con Docker Compose;
2. producción en Ubuntu/Debian, accesible mediante `ssh remote`, con Podman,
   Quadlet, nginx y `radar.joserabalsegura.com`.

No es una aplicación Next.js ni usa Prisma. El frontend React/Vite se compila
una vez y nginx lo sirve como contenido estático. Un worker Python consulta
AEMET y publica JSON e imágenes en un directorio persistente.

```text
Mac:
navegador -> 127.0.0.1:8080 -> contenedor web
                                   |
                             ./data (solo lectura)
                                   ^
                                   |
                             contenedor worker -> AEMET

Producción:
Internet -> nginx host :80/:443 -> 127.0.0.1:8088 -> contenedor web
                                                           |
                                           /var/lib/aemet-radar/data (ro)
                                                           ^
                                                           |
                                                  contenedor worker -> AEMET
```

La `AEMET_API_KEY` solo entra en el worker. No se usa para construir imágenes,
no está en el contenedor web y no se publica bajo `/radar` ni `/status`.

## 1. Prueba prolongada en el Mac

### Requisitos

- Docker Desktop con el motor iniciado.
- El `.env` local creado desde `.env.example`, con permisos `600` y una key
  real.
- Puertos locales libres; por defecto se usa `127.0.0.1:8080`.

El Compose monta `./data` directamente. Conserva los originales y manifiestos
que ya existen y todo lo que el worker produzca durante la prueba. Los
objetivos de Make ejecutan ambos contenedores con el UID/GID de la cuenta del
Mac, necesario porque la publicación atómica crea archivos con permisos
restrictivos.

Construir y levantar:

```bash
cd /Users/jraba/Desktop/aemet-radar-app-planning

chmod 600 .env
make container-up
make container-status
```

La aplicación queda en:

```text
http://127.0.0.1:8080
```

Validar el HTML, los dos JSON públicos y que el contenedor web no recibe la
key:

```bash
make container-check
```

Ver logs:

```bash
make container-logs
```

`Ctrl-C` solo abandona la vista de logs; los servicios siguen ejecutándose.
Durante una prueba de varias horas conviene revisar al principio y al final:

```bash
make container-status
docker compose logs --since 1h worker
curl -fsS http://127.0.0.1:8080/status/health.json \
  | jq '{generatedAt, status, products: [.products[] | {id, status, lastSuccessAt}]}'
du -sh data
```

`degraded` no implica que el contenedor esté averiado: puede indicar un radar
retrasado o un fallo temporal de AEMET. El healthcheck del worker solo falla si
deja de producir un `health.json` válido durante 30 minutos. El primer ciclo
puede tardar varios minutos porque consulta los 16 productos secuencialmente.

Para usar otro puerto:

```bash
make container-up RADAR_HTTP_PORT=8081
make container-check RADAR_HTTP_PORT=8081
```

Detener sin borrar datos:

```bash
make container-down
```

`container-down` elimina los contenedores y la red de Compose, pero no
`./data`, `.env` ni las imágenes construidas.

## 2. Preparar el cambio en el Mac

Antes de llevar una versión a producción:

```bash
cd /Users/jraba/Desktop/aemet-radar-app-planning

make check
make container-build
make container-up
make container-check
make container-down

git status
git add \
  .dockerignore \
  .env.example \
  .github/workflows/ci.yml \
  Makefile \
  README.md \
  apps/worker/requirements-prod.lock \
  compose.yaml \
  deploy \
  docs/DECISIONS.md \
  docs/DEPLOY.md \
  docs/OPERATIONS.md \
  docs/PHASE_9.md
git diff --cached --check
git diff --cached --stat
git commit -m "Prepare phase 9 container deployment"
git push origin HEAD
```

El repositorio real de esta app es:

```text
https://github.com/jrabalsegura/radar-app.git
```

Los cambios deben estar publicados en la rama que se vaya a desplegar antes de
continuar en el servidor.

## 3. Entrar y preparar el servidor

La guía asume Ubuntu/Debian y acceso mediante:

```bash
ssh remote
```

Actualizar e instalar únicamente herramientas del host; Node y Python viven en
las imágenes:

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y \
  ca-certificates \
  certbot \
  curl \
  dnsutils \
  git \
  jq \
  nginx \
  podman \
  python3-certbot-nginx
```

Comprobar Podman, cgroups v2 y el generador Quadlet:

```bash
podman --version
podman info --format '{{.Host.CgroupsVersion}}'
test -x /usr/lib/systemd/system-generators/podman-system-generator
```

El segundo comando debe mostrar `v2`. Si el paquete de la distribución no
incluye `podman-system-generator`, instala una versión actual de Podman antes
de seguir; no conviertas los `.container` en servicios escritos a mano.

No es necesario instalar Node.js, npm, Python, `build-essential`, Prisma ni una
base de datos en el host.

## 4. Clonar el repositorio

Se usa `/var/www/aemet-radar` para el checkout y
`/var/lib/aemet-radar/data` para los datos que sobreviven a imágenes,
contenedores y actualizaciones:

```bash
sudo install -d -m 0755 /var/www
sudo install -d -m 0755 -o "$USER" -g "$USER" /var/www/aemet-radar

git clone https://github.com/jrabalsegura/radar-app.git \
  /var/www/aemet-radar
cd /var/www/aemet-radar
```

Si el repositorio fuera privado, configura antes una clave SSH de solo lectura
o el mecanismo de acceso que ya uses en el servidor.

Crear los directorios de estado. El UID `10001` es compartido por worker y web;
el host ejecuta Podman como root, pero los procesos de aplicación no:

```bash
sudo install -d -m 0700 -o 10001 -g 10001 /var/lib/aemet-radar/data
sudo install -d -m 0700 /etc/aemet-radar
sudo install -d -m 0700 /var/backups/aemet-radar
```

## 5. Configurar el secreto fuera del repositorio

Crear el archivo que leerá exclusivamente el Quadlet del worker:

```bash
sudo install -m 0600 -o root -g root /dev/null \
  /etc/aemet-radar/worker.env
sudoedit /etc/aemet-radar/worker.env
```

Contenido:

```dotenv
AEMET_API_KEY=PEGA_AQUI_LA_KEY_REAL
AEMET_POLL_INTERVAL_SECONDS=300
AEMET_RETRY_ATTEMPTS=3
AEMET_RETRY_BACKOFF_SECONDS=1
AEMET_RETENTION_HOURS=24
AEMET_HISTORY_HOURS=3.8333333333333335
AEMET_PRODUCT_DELAY_SECONDS=1
AEMET_HEALTH_MAX_AGE_SECONDS=1800
```

Confirmar permisos sin imprimir el contenido:

```bash
sudo stat -c '%a %U:%G %n' /etc/aemet-radar/worker.env
```

Debe mostrar `600 root:root`. No ejecutes `cat`, `podman inspect` sobre el
entorno del worker ni pegues `docker compose config` en una incidencia: esas
acciones pueden mostrar el secreto.

## 6. Construir imágenes versionadas

No se publica la key como `ARG`, `ENV`, fichero de contexto ni capa. `.env` y
`data/` están excluidos por `.dockerignore`.

```bash
cd /var/www/aemet-radar
release=$(git rev-parse --short=12 HEAD)

sudo podman build --pull=always \
  --file deploy/containers/worker.Containerfile \
  --tag "localhost/aemet-radar-worker:$release" \
  .

sudo podman build --pull=always \
  --file deploy/containers/web.Containerfile \
  --tag "localhost/aemet-radar-web:$release" \
  .

sudo podman tag \
  "localhost/aemet-radar-worker:$release" \
  localhost/aemet-radar-worker:current
sudo podman tag \
  "localhost/aemet-radar-web:$release" \
  localhost/aemet-radar-web:current
```

Comprobar las imágenes:

```bash
sudo podman image inspect localhost/aemet-radar-worker:current \
  --format '{{.Id}} {{.Config.User}}'
sudo podman image inspect localhost/aemet-radar-web:current \
  --format '{{.Id}} {{.Config.User}}'
```

Ambas deben declarar `10001:10001`.

## 7. Instalar y arrancar los Quadlets

Los archivos a instalar están versionados bajo `deploy/quadlet/`:

```bash
cd /var/www/aemet-radar

sudo install -m 0644 \
  deploy/quadlet/aemet-radar-worker.container \
  /etc/containers/systemd/aemet-radar-worker.container
sudo install -m 0644 \
  deploy/quadlet/aemet-radar-web.container \
  /etc/containers/systemd/aemet-radar-web.container
```

Validar la generación antes de arrancar:

```bash
sudo env QUADLET_UNIT_DIRS=/etc/containers/systemd \
  /usr/lib/systemd/system-generators/podman-system-generator --dryrun
```

Después:

```bash
sudo systemctl daemon-reload
sudo systemctl start aemet-radar-worker.service
sudo systemctl start aemet-radar-web.service

sudo systemctl status aemet-radar-worker.service
sudo systemctl status aemet-radar-web.service
```

Los `.container` ya contienen `WantedBy=multi-user.target`; Quadlet genera las
dependencias de arranque. No se usa `systemctl enable` sobre los servicios
generados. Tras un reinicio, systemd recrea los contenedores y el bind mount
recupera los datos.

El web solo publica:

```text
127.0.0.1:8088 -> contenedor:8080
```

No abras `8088` en el firewall.

## 8. Instalar nginx del host

```bash
cd /var/www/aemet-radar

sudo install -m 0644 \
  deploy/nginx/radar.joserabalsegura.com.conf \
  /etc/nginx/sites-available/radar.joserabalsegura.com
sudo ln -s \
  /etc/nginx/sites-available/radar.joserabalsegura.com \
  /etc/nginx/sites-enabled/radar.joserabalsegura.com

sudo nginx -t
sudo systemctl reload nginx
```

Antes de solicitar el certificado, el DNS debe apuntar a este servidor:

```bash
dig +short A radar.joserabalsegura.com
dig +short AAAA radar.joserabalsegura.com
```

Un registro `AAAA` incorrecto también rompe la validación desde clientes IPv6;
elimínalo si el servidor no ofrece IPv6.

Si UFW está activo:

```bash
sudo ufw status
sudo ufw allow 'Nginx Full'
```

No actives ni cambies UFW a ciegas en una sesión SSH. Antes confirma que la
regla de SSH existente permite volver a entrar.

## 9. Activar HTTPS

Cuando HTTP y DNS respondan:

```bash
sudo certbot --nginx \
  --redirect \
  -d radar.joserabalsegura.com
```

Certbot modifica el site del host y configura la renovación. Validarla:

```bash
sudo certbot renew --dry-run
systemctl list-timers | grep certbot
```

Solo se solicita el nombre indicado. No se añade
`www.radar.joserabalsegura.com` porque no forma parte del DNS requerido.

## 10. Instalar backups automáticos

El backup incluye:

- `/etc/aemet-radar`;
- configuración y máscaras versionadas;
- todo el volumen persistente, incluidos originales, derivados, manifiestos y
  `health.json`;
- los archivos operativos instalados de nginx, Quadlet y systemd.

```bash
cd /var/www/aemet-radar

sudo install -m 0755 \
  deploy/scripts/aemet-radar-backup \
  /usr/local/sbin/aemet-radar-backup
sudo install -m 0644 \
  deploy/systemd/aemet-radar-backup.service \
  /etc/systemd/system/aemet-radar-backup.service
sudo install -m 0644 \
  deploy/systemd/aemet-radar-backup.timer \
  /etc/systemd/system/aemet-radar-backup.timer

sudo systemctl daemon-reload
sudo systemctl enable --now aemet-radar-backup.timer
sudo systemctl start aemet-radar-backup.service
sudo systemctl status aemet-radar-backup.service
sudo ls -lh /var/backups/aemet-radar
```

El timer se ejecuta diariamente y conserva 14 días. Para obtener una copia
coherente, detiene brevemente el worker y lo vuelve a iniciar incluso si `tar`
falla; el web continúa sirviendo la última publicación. Un backup en el mismo
servidor no sustituye a una copia externa: sincroniza periódicamente ese
directorio con tu sistema de backups sin exponer `worker.env`.

## 11. Comprobar el primer despliegue

Primero desde el servidor:

```bash
curl -fsS http://127.0.0.1:8088/healthz
deploy/scripts/smoke-test.sh http://127.0.0.1:8088

sudo podman ps --format \
  'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
sudo podman healthcheck run aemet-radar-worker
sudo podman healthcheck run aemet-radar-web
```

Después por HTTPS:

```bash
deploy/scripts/smoke-test.sh https://radar.joserabalsegura.com
curl -I https://radar.joserabalsegura.com/
curl -I https://radar.joserabalsegura.com/radar/index.json
```

Finalmente abre en un navegador externo:

```text
https://radar.joserabalsegura.com
```

Comprueba mapa, composición nacional, un radar regional, reproducción,
pantalla completa, recarga y registro de la PWA.

## 12. Actualizar en el futuro

En el Mac:

```bash
cd /Users/jraba/Desktop/aemet-radar-app-planning
make check
git status --short
# Añade solo los archivos revisados para ese cambio.
git add ruta/al/archivo
git diff --cached
git commit -m "mensaje"
git push origin HEAD
```

En el servidor, primero crea un backup y actualiza el checkout sin mezclar
cambios locales:

```bash
ssh remote
sudo systemctl start aemet-radar-backup.service

cd /var/www/aemet-radar
git status --short
git pull --ff-only origin main
release=$(git rev-parse --short=12 HEAD)
```

Si producción despliega otra rama estable, sustituye `main` explícitamente. Un
`git status --short` no vacío debe investigarse; no uses `reset --hard`.

Construir las dos imágenes nuevas antes de tocar los servicios:

```bash
sudo podman build --pull=always \
  --file deploy/containers/worker.Containerfile \
  --tag "localhost/aemet-radar-worker:$release" \
  .
sudo podman build --pull=always \
  --file deploy/containers/web.Containerfile \
  --tag "localhost/aemet-radar-web:$release" \
  .
```

Guardar las imágenes actuales como rollback y mover `current`:

```bash
if sudo podman image exists localhost/aemet-radar-worker:current; then
  sudo podman tag \
    localhost/aemet-radar-worker:current \
    localhost/aemet-radar-worker:rollback
fi
if sudo podman image exists localhost/aemet-radar-web:current; then
  sudo podman tag \
    localhost/aemet-radar-web:current \
    localhost/aemet-radar-web:rollback
fi

sudo podman tag \
  "localhost/aemet-radar-worker:$release" \
  localhost/aemet-radar-worker:current
sudo podman tag \
  "localhost/aemet-radar-web:$release" \
  localhost/aemet-radar-web:current
```

Reinstalar archivos operativos versionados, validar y reiniciar:

```bash
sudo install -m 0644 \
  deploy/quadlet/aemet-radar-worker.container \
  /etc/containers/systemd/aemet-radar-worker.container
sudo install -m 0644 \
  deploy/quadlet/aemet-radar-web.container \
  /etc/containers/systemd/aemet-radar-web.container
sudo install -m 0644 \
  deploy/nginx/radar.joserabalsegura.com.conf \
  /etc/nginx/sites-available/radar.joserabalsegura.com

sudo systemctl daemon-reload
sudo nginx -t
sudo systemctl restart aemet-radar-worker.service
sudo systemctl restart aemet-radar-web.service
sudo systemctl reload nginx

deploy/scripts/smoke-test.sh http://127.0.0.1:8088
deploy/scripts/smoke-test.sh https://radar.joserabalsegura.com
```

El volumen `/var/lib/aemet-radar/data` no se reemplaza durante la actualización.

## 13. Rollback

Un rollback normal cambia las dos imágenes, no los datos:

```bash
sudo podman image exists localhost/aemet-radar-worker:rollback
sudo podman image exists localhost/aemet-radar-web:rollback

sudo podman tag \
  localhost/aemet-radar-worker:rollback \
  localhost/aemet-radar-worker:current
sudo podman tag \
  localhost/aemet-radar-web:rollback \
  localhost/aemet-radar-web:current

sudo systemctl restart aemet-radar-worker.service
sudo systemctl restart aemet-radar-web.service

cd /var/www/aemet-radar
deploy/scripts/smoke-test.sh http://127.0.0.1:8088
```

Si el release también cambió Quadlet o nginx, recupera esos archivos desde el
commit anterior, instálalos de nuevo y valida `podman-system-generator
--dryrun` y `nginx -t` antes de reiniciar.

Restaurar un backup de datos es una operación distinta y potencialmente
destructiva. Solo se usa ante pérdida o corrupción, después de conservar una
copia del estado actual; el procedimiento está en `docs/OPERATIONS.md`.

## Referencias operativas

- [Quadlet y unidades systemd de Podman](https://docs.podman.io/en/latest/markdown/podman-systemd.unit.5.html)
- [Uso básico de Quadlet](https://docs.podman.io/en/latest/markdown/podman-quadlet-basic-usage.7.html)
- [Directivas de ficheros estáticos de nginx](https://nginx.org/en/docs/http/ngx_http_core_module.html)
