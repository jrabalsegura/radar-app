# Despliegue

Artefactos de la Fase 9:

- `containers/`: imágenes del worker y web, nginx interno y healthcheck;
- `quadlet/`: servicios Podman administrados por systemd;
- `nginx/`: virtual host público del servidor;
- `scripts/`: smoke test y backup protegido;
- `systemd/`: servicio y timer del backup.

La instalación paso a paso está en [`docs/DEPLOY.md`](../docs/DEPLOY.md) y la
guía cotidiana en [`docs/OPERATIONS.md`](../docs/OPERATIONS.md).
