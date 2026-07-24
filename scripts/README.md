# Scripts

Utilidades reproducibles del proyecto. Los comandos de uso habitual siguen
centralizados en el `Makefile`.

## Utilidades reproducibles

`generate_phase3_test_fixtures.py` regenera los GIF y PNG sintéticos diminutos
de los golden tests de extracción. No descarga datos ni usa la API key.

```bash
.venv/bin/python scripts/generate_phase3_test_fixtures.py
```
