# Fixtures sintéticos

Las pruebas generan GIF diminutos y sintéticos mediante Pillow. No contienen
imágenes, logos, textos ni datos descargados de AEMET.

Las respuestas HTTP simuladas usan rutas y hashes inventados. La cadena usada
como API key es ficticia y sirve para comprobar que nunca aparece en mensajes,
informes o logs.

La Fase 3 añade `reflectivity/source.gif`, una máscara binaria y dos golden PNG
de `6×5` píxeles. Incluyen las once clases de la paleta observada, un amarillo
válido, dos amarillos fijos descartados y un color inequívoco descartado por
máscara. Se regeneran sin utilizar código de producción mediante:

```bash
.venv/bin/python scripts/generate_phase3_test_fixtures.py
```
