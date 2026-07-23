# Worker

Paquete Python base del worker de Radar AEMET.

La Fase 1 añade una ingesta puntual de originales para Murcia y la composición
nacional. No procesa reflectividad ni genera manifiestos.

La API key solo se lee de `AEMET_API_KEY`. La CLI también puede cargar un `.env`
local ignorado por Git; una variable ya exportada tiene prioridad.

```bash
.venv/bin/aemet-radar fetch-once
.venv/bin/aemet-radar fetch-once --product regional-mu
.venv/bin/aemet-radar check-inventory
```

La salida estándar contiene únicamente un resumen JSON sin URLs efímeras ni
credenciales. Los originales e informes se guardan bajo `data/`, que está
ignorado por Git.

`check-inventory` consulta secuencialmente la pasarela con una pausa de un
segundo y no descarga los GIF regionales.
