# Radar AEMET

Base de una aplicación web personal para visualizar productos de radar de AEMET. El
repositorio sigue el desarrollo incremental definido en
[`docs/ROADMAP.md`](docs/ROADMAP.md); la fuente principal de verdad es
[`docs/SPEC.md`](docs/SPEC.md).

La Fase 0 solo proporciona el esqueleto React/TypeScript y el paquete Python del
worker. Todavía no consulta AEMET, no representa mapas y no procesa imágenes.

## Requisitos

- Node.js 22.12 o posterior y npm 10 o posterior.
- Python 3.12 o posterior.
- GNU Make (opcional, pero recomendado para usar los comandos uniformes).

## Instalación reproducible

```bash
make install
```

El frontend se instala con `npm ci` y su `package-lock.json`. El entorno de
desarrollo Python se crea en `.venv` y usa las versiones exactas de
`apps/worker/requirements-dev.lock`.

Sin Make, los comandos equivalentes son:

```bash
npm --prefix apps/web ci
python3 -m venv .venv
.venv/bin/python -m pip install --requirement apps/worker/requirements-dev.lock
```

No hace falta crear un `.env` para trabajar en la Fase 0. Cuando sea necesario,
debe copiarse `.env.example` a `.env` y sustituir los valores localmente. `.env`
está excluido de Git.

## Desarrollo y validación

```bash
make dev-web       # servidor Vite local
make check         # lint, formato, tipado, tests y build
make format        # aplica los formateadores
```

Los criterios de aceptación también se pueden comprobar por separado:

```bash
npm --prefix apps/web test
npm --prefix apps/web run build
.venv/bin/pytest
.venv/bin/ruff check .
```

## Estructura

```text
apps/web/          frontend React + TypeScript + Vite
apps/worker/       paquete Python del worker
config/            configuración futura versionada
data/              datos locales ignorados por Git
deploy/            reservado para la Fase 9
docs/              especificación, decisiones y roadmap
samples/           muestras mínimas y documentadas
scripts/           utilidades reproducibles futuras
```

## Estrategia Git

`main` debe permanecer estable. Cada fase se desarrolla en una rama
`phase/<numero>-<descripcion>`, se valida con `make check` y se integra mediante
una revisión que confirme los criterios de aceptación. Los commits deben ser
pequeños, coherentes y no mezclar trabajo de fases posteriores.

Las decisiones que cambien arquitectura, alcance o comportamiento se registran
como ADR en `docs/DECISIONS.md`; no se reescribe la historia de decisiones.

No debe añadirse una coordenada, radar, proyección o cadencia a producción solo
porque parezca razonable: debe verificarse y documentarse.
