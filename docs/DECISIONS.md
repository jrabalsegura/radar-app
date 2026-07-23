# DECISIONS.md — Registro inicial de decisiones

Las decisiones se numerarán como `ADR-XXX`. No se borrarán cuando cambien: se marcarán como sustituidas.

---

## ADR-001 — Arquitectura sin base de datos para el MVP

**Estado:** aceptada provisionalmente.

Se utilizarán archivos originales, derivados y manifiestos JSON publicados atómicamente. Una base de datos solo se añadirá si aparece una necesidad concreta que no pueda resolverse de forma fiable con este modelo.

**Motivo:** el producto es de lectura, tiene poca cardinalidad, conserva una ventana temporal pequeña y debe ser fácil de operar en un servidor personal.

---

## ADR-002 — La API key solo vive en el worker

**Estado:** aceptada.

El navegador no llamará directamente a AEMET. El worker descargará y publicará recursos derivados. La clave se inyectará mediante entorno y nunca se incluirá en el repositorio.

---

## ADR-003 — Conservar originales

**Estado:** aceptada.

Se almacenará temporalmente el GIF original junto con el resultado procesado. Esto permitirá reprocesar cuando cambie la máscara, paleta o georreferenciación sin volver a consultar AEMET.

---

## ADR-004 — Procesadores regional y nacional independientes

**Estado:** aceptada.

La composición nacional no se obligará a compartir geometría, máscaras o transformación con los radares regionales. Compartirán interfaces y utilidades, pero podrán utilizar implementaciones distintas.

---

## ADR-005 — No interpolar reflectividad en el MVP

**Estado:** aceptada.

Las transiciones de opacidad solo suavizarán el cambio visual. No se generarán observaciones meteorológicas intermedias.

---

## ADR-006 — Murcia como radar piloto

**Estado:** aceptada.

Murcia será el primer radar regional para desarrollar y validar ingesta, separación de reflectividad, georreferenciación y timeline.

---

## ADR-007 — MapLibre con estilo configurable

**Estado:** aceptada.

MapLibre será el motor de mapa. La URL del estilo se configurará mediante entorno para no acoplar el proyecto desde el principio a un proveedor concreto de teselas.
