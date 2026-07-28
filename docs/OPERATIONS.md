# Operación

Esta guía cubre la instalación de producción descrita en `docs/DEPLOY.md`. En
el Mac, los comandos equivalentes son `make container-status`,
`make container-logs`, `make container-check` y `make container-down`.

## Estado rápido

```bash
ssh remote

sudo systemctl status aemet-radar-worker.service
sudo systemctl status aemet-radar-web.service
sudo systemctl status nginx

sudo podman ps --format \
  'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
curl -fsS http://127.0.0.1:8088/healthz
curl -fsS http://127.0.0.1:8088/status/health.json \
  | jq '{generatedAt, status, products: [.products[] | {id, status, dataStatus}]}'
```

Hay dos conceptos diferentes:

- la salud del contenedor comprueba que el proceso web responde o que el
  worker continúa publicando JSON válido;
- el campo público `status` describe AEMET y la edad de sus productos. Puede
  ser `degraded` aunque el software funcione correctamente.

El healthcheck permite 30 minutos sin una publicación nueva. Ese margen cubre
un ciclo secuencial lento, pero detecta un worker bloqueado. Se ajusta con
`AEMET_HEALTH_MAX_AGE_SECONDS` en `/etc/aemet-radar/worker.env`.

Ejecutar los checks manualmente:

```bash
sudo podman healthcheck run aemet-radar-worker
sudo podman healthcheck run aemet-radar-web
sudo podman inspect aemet-radar-worker \
  --format '{{json .State.Health}}' | jq
sudo podman inspect aemet-radar-web \
  --format '{{json .State.Health}}' | jq
```

## Logs y rotación

Los Quadlets usan el driver `k8s-file` con un límite de 20 MB por contenedor.
Podman conserva la salida para `podman logs` sin dejar crecer indefinidamente
un único fichero:

```bash
sudo podman logs --since 1h aemet-radar-worker
sudo podman logs --since 1h aemet-radar-web
sudo podman logs --follow aemet-radar-worker
```

Systemd registra creación, reinicios y fallos de unidad:

```bash
sudo journalctl -u aemet-radar-worker.service --since today
sudo journalctl -u aemet-radar-web.service --since today
sudo journalctl -u nginx --since today
```

nginx del host escribe:

```text
/var/log/nginx/radar.joserabalsegura.com.access.log
/var/log/nginx/radar.joserabalsegura.com.error.log
```

El paquete nginx instala su política en `/etc/logrotate.d/nginx`. Comprobarla
sin forzar rotación:

```bash
sudo logrotate --debug /etc/logrotate.d/nginx
```

## Entender `health.json`

Por producto, `status` puede ser:

- `current`: último ciclo y dato actuales;
- `delayed`: el dato supera dos veces la cadencia esperada;
- `no-data`: AEMET declara que no hay producto, sin tratarlo como avería;
- `error`: falló la consulta o validación.

`dataStatus` describe solo la edad del último fotograma. Un fallo temporal no
vacía un manifiesto válido. La fuente primaria es el visor público de AEMET;
OpenData, que sí necesita la key, permanece como fallback.

Revisar errores resumidos:

```bash
curl -fsS http://127.0.0.1:8088/status/health.json \
  | jq '.products[] | select(.status == "error" or .status == "delayed")'
```

Los diagnósticos seguros del worker están en:

```text
/var/lib/aemet-radar/data/reports/phase-2/failures/
```

No contienen la key ni el cuerpo inválido.

## Reiniciar sin perder datos

Reiniciar un servicio:

```bash
sudo systemctl restart aemet-radar-worker.service
sudo systemctl restart aemet-radar-web.service
```

Los contenedores son reemplazables; el estado vive en
`/var/lib/aemet-radar/data`. No uses `podman rm --volumes`, no borres ese
directorio y no cambies recursivamente sus permisos. Worker y web comparten el
UID/GID `10001:10001` porque los ficheros atómicos son deliberadamente
restrictivos.

Tras reiniciar el servidor:

```bash
sudo systemctl is-active aemet-radar-worker.service
sudo systemctl is-active aemet-radar-web.service
sudo podman ps
```

## Forzar un ciclo o reconstruir manifiestos

Un ciclo puntual dentro del contenedor activo crearía un segundo escritor y no
debe ejecutarse mientras el scheduler principal está en marcha.

Para forzarlo de forma controlada:

```bash
sudo systemctl stop aemet-radar-worker.service
sudo podman run --rm \
  --env-file /etc/aemet-radar/worker.env \
  --user 10001:10001 \
  --volume /var/lib/aemet-radar/data:/data:rw,z \
  localhost/aemet-radar-worker:current \
  run --cycles 1 --data-dir /data
sudo systemctl start aemet-radar-worker.service
```

Para regenerar JSON e imágenes derivadas desde originales, sin consultar AEMET
y sin pasar la key:

```bash
sudo systemctl stop aemet-radar-worker.service
sudo podman run --rm \
  --user 10001:10001 \
  --volume /var/lib/aemet-radar/data:/data:rw,z \
  localhost/aemet-radar-worker:current \
  rebuild-manifests --data-dir /data
sudo systemctl start aemet-radar-worker.service
```

Detener antes el servicio garantiza un único escritor sobre la publicación
atómica.

## Retención y espacio

El worker conserva por defecto 24 horas de originales y al menos el último
fotograma válido de cada producto. Publica una ventana de 3 horas y 50 minutos.
Los valores efectivos están en `/etc/aemet-radar/worker.env`.

```bash
sudo du -sh /var/lib/aemet-radar/data
sudo du -sh /var/lib/aemet-radar/data/raw/*
sudo df -h /var/lib/aemet-radar/data
```

No añadas una limpieza externa sobre `data/raw`: el propio worker elimina el
original y su informe como una pareja y protege el último válido. Los backups
sí tienen una retención independiente de 14 días.

## Backups

Estado y siguiente ejecución:

```bash
sudo systemctl status aemet-radar-backup.timer
sudo systemctl list-timers aemet-radar-backup.timer
sudo journalctl -u aemet-radar-backup.service
sudo ls -lh /var/backups/aemet-radar
```

Crear uno bajo demanda:

```bash
sudo systemctl start aemet-radar-backup.service
sudo journalctl -u aemet-radar-backup.service -n 20
```

El script pausa el worker durante la lectura para evitar una carrera con la
retención o una nueva publicación, y recupera su estado activo al terminar. El
contenedor web no se detiene.

Validar un archivo sin extraerlo:

```bash
backup=/var/backups/aemet-radar/aemet-radar-AAAAMMDDTHHMMSSZ.tar.gz
sudo tar -tzf "$backup" | sed -n '1,80p'
sudo gzip -t "$backup"
```

La copia incluye el secreto. Mantén `/var/backups/aemet-radar` con permisos
`700` y replica sus archivos solo hacia almacenamiento igualmente protegido.

### Restauración de desastre

La restauración sobrescribe estado y requiere una ventana de mantenimiento.
Antes de ejecutarla, guarda un backup del estado actual y revisa el contenido
del archivo. Después:

```bash
sudo systemctl stop aemet-radar-worker.service
sudo systemctl stop aemet-radar-web.service
sudo systemctl start aemet-radar-backup.service

backup=/var/backups/aemet-radar/aemet-radar-AAAAMMDDTHHMMSSZ.tar.gz
sudo gzip -t "$backup"
sudo tar -tzf "$backup" | less
```

Solo tras confirmar de forma explícita el backup elegido:

```bash
sudo tar -xzf "$backup" -C /
sudo chown -R 10001:10001 /var/lib/aemet-radar/data
sudo chmod 0700 /etc/aemet-radar
sudo chmod 0600 /etc/aemet-radar/worker.env

sudo systemctl daemon-reload
sudo nginx -t
sudo systemctl start aemet-radar-worker.service
sudo systemctl start aemet-radar-web.service

cd /var/www/aemet-radar
deploy/scripts/smoke-test.sh http://127.0.0.1:8088
```

## Rotar la API key

1. Editar el archivo sin imprimirlo:

   ```bash
   sudoedit /etc/aemet-radar/worker.env
   ```

2. Confirmar `600 root:root`.
3. Reiniciar solo el worker:

   ```bash
   sudo systemctl restart aemet-radar-worker.service
   ```

4. Esperar un ciclo y comprobar que `lastSuccessAt` avanza.

No hace falta reconstruir imágenes ni reiniciar el web. No inspecciones el
entorno del worker: la key es visible para root dentro de su configuración OCI.

Comprobar de forma segura que el web no recibe una variable con ese nombre:

```bash
sudo podman exec aemet-radar-web \
  sh -c 'test -z "${AEMET_API_KEY+x}"'
```

## HTTPS y nginx

```bash
sudo nginx -t
sudo systemctl status nginx
sudo certbot certificates
sudo certbot renew --dry-run
curl -I https://radar.joserabalsegura.com/
```

El puerto `8088` permanece enlazado a loopback. La única entrada pública es
nginx en `80/443`.

Si se cambia `VITE_MAP_STYLE_URL` a otro dominio, también debe actualizarse la
CSP en `deploy/containers/security-headers.conf`, reconstruirse el web y
verificarse en un navegador. Un bloqueo CSP se diagnostica en la consola del
navegador, no relajando globalmente la política.

## Actualización y rollback

El procedimiento completo, incluido el etiquetado `current`/`rollback`, está en
`docs/DEPLOY.md`. Reglas operativas:

- construir ambas imágenes antes de reiniciar;
- crear backup antes del cambio;
- mover ambas etiquetas antes de reiniciar cualquiera;
- no reemplazar `/var/lib/aemet-radar/data`;
- validar primero `127.0.0.1:8088` y después HTTPS;
- conservar al menos el release anterior hasta terminar la observación.

## Diagnóstico por síntoma

| Síntoma | Comprobación inicial | Acción habitual |
| --- | --- | --- |
| `502 Bad Gateway` | `systemctl status aemet-radar-web` y `curl 127.0.0.1:8088/healthz` | reiniciar o hacer rollback del web |
| UI abre pero no hay radares | `curl .../radar/index.json` y permisos de `data` | revisar worker y UID `10001` |
| Worker `unhealthy` | edad de `generatedAt` y `podman logs` | distinguir ciclo lento de bloqueo |
| Estado `degraded` | productos retrasados/error en `health.json` | observar AEMET; no borrar datos |
| Mapa base vacío | consola CSP y acceso a OpenFreeMap | revisar dominio de estilo/CSP |
| Certificado próximo a caducar | `certbot renew --dry-run` y timer | reparar renovación antes de caducar |
| Disco creciendo | `du`, retención efectiva y backups | revisar configuración, no borrar raw a mano |
