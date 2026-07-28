# Fase 9 — Operación, seguridad y despliegue

## Resultado

El despliegue queda dividido en dos contenedores de proceso único:

- `aemet-radar-worker`, Python 3.13, único receptor de `AEMET_API_KEY` y único
  escritor del volumen;
- `aemet-radar-web`, build estático de React servido por nginx sin privilegios
  y con el volumen en solo lectura.

En el Mac, Docker Compose monta `./data` y usa el UID/GID local. En producción,
Podman/Quadlet ejecuta ambos procesos como `10001:10001`, monta
`/var/lib/aemet-radar/data`, publica el web solo en `127.0.0.1:8088` y delega
TLS a nginx en el host.

## Seguridad y persistencia

`.dockerignore` excluye `.env`, `data/`, Git y salidas locales. La key no es un
argumento de build ni entra en el web. Producción la conserva en
`/etc/aemet-radar/worker.env`, propiedad de root y modo `600`.
La imagen web descarta los datos de demostración después de compilar y solo
sirve la publicación del volumen. El runtime del worker no conserva `pip`,
setuptools, wheel ni otras herramientas de build.

Ambas imágenes usan root filesystem de solo lectura, `/tmp` temporal,
`no-new-privileges`, todas las capabilities eliminadas y un usuario no root.
El UID compartido no es opcional: `mkstemp` crea las publicaciones atómicas con
modo `600`, por lo que el lector debe pertenecer al mismo UID sin ampliar
permisos.

El volumen es independiente de checkout, imagen y contenedor. Actualizar o
volver a una imagen anterior no elimina originales ni manifiestos.

## Scheduler y salud

Se mantiene el scheduler monotónico ya probado del worker, con ciclos
secuenciales y parámetros de entorno. Systemd aplica `Restart=always`; no se
añade un timer que pudiera solapar escritores.

El web comprueba `/healthz`. El worker valida estructura, productos y edad de
`/data/status/health.json`; un estado meteorológico `degraded` sigue siendo
saludable si el worker continúa publicando. El arranque concede 15 minutos al
primer ciclo y la edad máxima predeterminada es 30 minutos.

## HTTP, caché y logs

El nginx del contenedor:

- no cachea índice, manifiestos ni salud;
- cachea un año las imágenes y assets con nombre inmutable;
- no expone originales, informes ni listados de directorio;
- añade CSP, política de permisos, `nosniff`, protección de framing y política
  de referrer;
- sirve el service worker y `index.html` con revalidación.

Compose limita los logs JSON a tres ficheros de 10 MB. Quadlet usa `k8s-file`
con máximo de 20 MB. Los logs del nginx del host conservan la rotación del
paquete.

## Backups y rollback

Un timer diario detiene brevemente el escritor y crea un `tar.gz` protegido que
incluye entorno, configuración, máscaras, volumen completo y archivos
operativos instalados. Conserva 14 días; la guía exige una réplica externa
protegida.

Cada build de producción se etiqueta con el SHA corto. `current` es la versión
activa y `rollback` conserva la anterior. Un rollback normal cambia imágenes y
mantiene el volumen. La restauración de datos queda separada como operación
destructiva de desastre.

## Archivos

```text
compose.yaml
deploy/
├── containers/
│   ├── nginx.conf
│   ├── security-headers.conf
│   ├── web.Containerfile
│   ├── worker-healthcheck.py
│   └── worker.Containerfile
├── nginx/
│   └── radar.joserabalsegura.com.conf
├── quadlet/
│   ├── aemet-radar-web.container
│   └── aemet-radar-worker.container
├── scripts/
│   ├── aemet-radar-backup
│   └── smoke-test.sh
└── systemd/
    ├── aemet-radar-backup.service
    └── aemet-radar-backup.timer
```

Los comandos completos están en `docs/DEPLOY.md`; el diagnóstico cotidiano y
la recuperación están en `docs/OPERATIONS.md`.

## Validación realizada

En el Mac ARM64 de desarrollo se verificó:

- build limpio de ambas imágenes con Docker 29.3.1;
- dos ciclos completos del worker, 16 productos y healthcheck saludable;
- recreación del worker conservando `data/`;
- smoke test sobre `127.0.0.1:8080`;
- mounts `/data` de web `ro` y worker `rw`;
- usuario local compartido y metadato de imagen `10001:10001`;
- ausencia de `AEMET_API_KEY` en web e historial de build;
- `404` explícito para `raw`, `processed`, `reports` y `debug`;
- `Cache-Control: no-store` en JSON e `immutable` en imágenes;
- CSP y demás cabeceras de seguridad;
- mapa con lienzo `1231×611`, teselas y controles visibles, sin errores de
  consola;
- sintaxis de nginx interno y virtual host mediante nginx 1.28.0;
- generación de ambos servicios con Podman/Quadlet 5.8.1;
- creación, listado y verificación gzip de un backup aislado;
- `make check`: 28 pruebas de frontend y 104 de worker, además de lint,
  formato, tipado y build.

La validación local no modifica el servidor remoto ni demuestra todavía DNS,
firewall, renovación Certbot o acceso HTTPS externo. Esas comprobaciones se
ejecutan durante el primer despliegue autorizado siguiendo `docs/DEPLOY.md`.
