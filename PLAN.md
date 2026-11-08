# PLAN.md — Prototipo: Calendario de quemas en México (MODIS + VIIRS, 2024)

> Este archivo es la guía de trabajo para el agente (Claude) y para el equipo.
> **Claude: lee este archivo completo antes de empezar. Trabaja una fase a la vez y DETENTE al final de cada fase** para que el equipo revise. No avances a la siguiente fase sin confirmación.

---

## 1. Contexto en dos párrafos

Participamos en el NASA Space Apps Challenge 2026, reto **"Harmonization of MODIS and VIIRS Hot Spots"**. Los satélites detectan focos de calor (fuegos) desde hace más de 20 años, pero con dos instrumentos distintos: **MODIS** (desde 2000, píxel de ~1 km, detecta menos) y **VIIRS** (desde 2012, píxel de ~375 m, detecta más y fuegos más pequeños). Si se juntan sin corregir, parece que hay más incendios solo porque cambió el instrumento.

El reto final pide una app web que armonice ambos registros en un **calendario de actividad de quema** para un área elegida. **Este prototipo es una versión reducida**: solo **México**, solo **un año (2024)**. Sirve para probar el método de armonización y la app completa de punta a punta antes del hackathon.

## 2. Alcance del prototipo

**Sí entra:**
- Datos FIRMS de México, año 2024: MODIS (Terra + Aqua) y VIIRS S-NPP.
- Limpieza, malla hexagonal H3, conteo diario por celda y sensor.
- Armonización v1: expresar VIIRS en "equivalente MODIS" con factores calculados en 2024.
- Exportar JSON estáticos.
- App web: mapa de México con hexágonos → clic en un hexágono → calendario 2024 con conteos diarios.

**No entra (queda para el hackathon):**
- Varios años, climatología y anomalías ("¿este año fue fuera de lo normal?") — con un solo año no se puede calcular lo "normal".
- VIIRS NOAA-20 / NOAA-21.
- Backend / API (FastAPI). En el prototipo todo es estático: Python genera JSON y la web los lee.
- Dibujar polígonos libres. En el prototipo se selecciona haciendo clic en hexágonos.

## 3. Stack (no agregar dependencias fuera de esta lista sin preguntar)

| Parte | Herramientas |
|---|---|
| Entorno Python | `uv`, Python 3.12 |
| Datos | `pandas`, `pyarrow`, `duckdb`, `h3` (v4), `matplotlib` |
| Pruebas | `pytest` |
| Web | Vite + React + TypeScript, `leaflet`, `react-leaflet`, `h3-js`, `echarts`, `echarts-for-react` |
| Despliegue | sitio estático en Vercel o Netlify |

## 4. Estructura del repositorio

```text
fire-calendar/
├── PLAN.md                 este archivo
├── AGENTS.md               resumen corto para cualquier agente (crear en Fase 0)
├── README.md               en INGLÉS (requisito de entrega de Space Apps)
├── LICENSE                 MIT
├── .gitignore              data/raw/, data/interim/, .venv/, node_modules/, .env, dist/
├── pyproject.toml
├── data/
│   ├── raw/                CSV de FIRMS (NO se suben a Git)
│   ├── interim/            Parquet intermedios (NO se suben)
│   └── reports/            reportes .md y gráficas .png (sí se suben)
├── pipeline/
│   ├── config.py           constantes: año, país, resolución H3, umbrales, zona horaria
│   ├── download.py         descarga o verifica los CSV
│   ├── inspect_data.py     reporte de exploración
│   ├── clean.py            filtros y normalización de columnas
│   ├── grid.py             asigna celda H3 y agrega por día
│   ├── harmonize.py        calcula factores y aplica la armonización
│   ├── validate.py         métricas y gráficas de validación
│   └── export.py           escribe los JSON para la web
├── tests/
└── web/
    └── public/data/        aquí van los JSON exportados
```

## 5. Datos de entrada

- **Fuente:** NASA FIRMS, archivos anuales por país ("Country Yearly Summary").
- **Archivos esperados en `data/raw/`:**
  - `modis_2024_Mexico.csv`
  - `viirs-snpp_2024_Mexico.csv`
- **Descarga:** intentar primero con este patrón de URL (sin MAP_KEY):
  `https://firms.modaps.eosdis.nasa.gov/data/country/modis/2024/modis_2024_Mexico.csv`
  `https://firms.modaps.eosdis.nasa.gov/data/country/viirs-snpp/2024/viirs-snpp_2024_Mexico.csv`
  **Si la descarga falla, NO inventes datos ni uses datos sintéticos como si fueran reales.** Detente y pide al equipo que los descargue a mano desde el sitio de FIRMS (sección de descargas por país) y los coloque en `data/raw/`.
- **Columnas relevantes (verificar en Fase 1, pueden variar):**
  - MODIS: `latitude, longitude, acq_date, acq_time, satellite, confidence (0–100), frp, daynight, type`
  - VIIRS: `latitude, longitude, acq_date, acq_time, satellite, confidence (l/n/h), frp, daynight, type`
  - `type`: 0 = fuego de vegetación presunto, 1 = volcán activo, 2 = otra fuente fija en tierra, 3 = mar adentro.

## 6. Decisiones de método (todas en `pipeline/config.py`)

| Decisión | Valor inicial | Por qué |
|---|---|---|
| Año | 2024 | Año completo y con ambos sensores operando |
| Tipo de detección | solo `type == 0` | Quitar volcanes, industria y plataformas marinas |
| Confianza MODIS | `confidence >= 30` | Excluir la categoría "baja" |
| Confianza VIIRS | `n` o `h` | Excluir "baja" |
| Fecha local | `acq_date` + `acq_time` (UTC) convertidos a UTC-6 fijo | La mayoría de México usa UTC-6; documentar la simplificación |
| Malla | H3 resolución 5 (~250 km² por celda) | Borra la diferencia de píxel 1 km vs 375 m; probar también res 4 |
| Par de referencia | MODIS **Aqua** vs VIIRS **S-NPP** | Pasan a horas parecidas de la tarde, la comparación es más justa |

## 7. Formato de salida (contrato entre datos y web)

Todos los JSON en `web/public/data/`. Tamaño total objetivo: **menos de 15 MB**.

`meta.json`
```json
{
  "country": "Mexico", "year": 2024, "h3_resolution": 5,
  "generated_at": "ISO-8601",
  "filters": { "type": [0], "modis_min_conf": 30, "viirs_conf": ["n", "h"] },
  "harmonization": { "method": "monthly_ratio_v1", "factors": { "2024-01": 0.0, "...": 0.0 } },
  "sources": ["NASA FIRMS MODIS C6.1", "NASA FIRMS VIIRS S-NPP 375 m"]
}
```

`cells.json` — una entrada por celda con al menos una detección (para colorear el mapa)
```json
[ { "h3": "85...", "modis": 12, "viirs": 48, "viirs_h": 13.1 } ]
```

`national.json` — serie diaria de todo el país
```json
[ { "date": "2024-04-15", "modis": 310, "viirs": 1290, "viirs_h": 335.2 } ]
```

`cells/<h3>.json` — serie diaria de una celda, solo días con detecciones
```json
[ { "date": "2024-04-15", "modis": 3, "viirs": 11, "viirs_h": 2.9 } ]
```

## 8. Fases

Cada fase termina con: (a) un resumen corto de lo hecho, (b) lo que queda pendiente o dudoso, (c) cómo verificarlo. Luego **esperar confirmación**.

### Fase 0 — Preparar el repositorio
- Crear la estructura de la sección 4, `pyproject.toml` con las dependencias Python, `.gitignore`, `LICENSE` (MIT).
- Crear `AGENTS.md` (máx. 40 líneas): qué es el proyecto, estructura, contrato JSON (resumen), comandos, reglas (no subir `data/raw`, no inventar datos).
- Crear el proyecto web con Vite (React + TS) en `web/` e instalar dependencias.
- **Listo cuando:** `uv run python -c "import duckdb, h3, pandas"` y `npm run dev` (en `web/`) funcionan.

### Fase 1 — Conseguir y explorar los datos
- `download.py`: descargar o verificar que existen los dos CSV (ver sección 5).
- `inspect_data.py`: generar `data/reports/01_exploracion.md` con: filas por sensor y satélite, columnas y tipos, distribución de `type`, `confidence` y `daynight`, detecciones por mes (tabla + gráfica PNG), rango de fechas y bounding box.
- **Listo cuando:** el reporte existe y el equipo lo revisó. Señalar cualquier sorpresa en los datos.

### Fase 2 — Limpieza y malla H3
- `clean.py`: aplicar filtros de la sección 6, normalizar columnas a un esquema común (`sensor`, `satellite`, `lat`, `lon`, `date_local`, `frp`, `daynight`) y guardar `data/interim/detections.parquet`.
- `grid.py`: asignar celda H3 y agregar a `data/interim/daily_cell.parquet` con columnas `h3, date, sensor, satellite, n, frp_sum`.
- Pruebas en `tests/`: filtros, conversión de fecha, que la suma de `n` agregada coincida con las filas limpias.
- **Listo cuando:** `uv run pytest` pasa y se reporta cuántas filas quedaron tras cada filtro.

### Fase 3 — Armonización v1 y validación
- `harmonize.py`, método `monthly_ratio_v1`:
  1. Tomar solo celdas-día donde **ambos** (MODIS Aqua y VIIRS S-NPP) tienen al menos una detección.
  2. Factor por mes: `f_mes = suma(MODIS Aqua) / suma(VIIRS S-NPP)` en esas celdas-día.
  3. `viirs_h = viirs × f_mes` (VIIRS expresado en "equivalente MODIS Aqua").
  4. Si un mes tiene muy pocos datos (menos de 30 celdas-día comunes), usar el factor anual.
- `validate.py` → `data/reports/03_validacion.md` con:
  - Factores por mes (tabla).
  - Serie nacional diaria: MODIS vs VIIRS crudo vs VIIRS armonizado (gráfica).
  - Correlación y error medio entre MODIS Aqua y VIIRS armonizado, a nivel celda-semana.
  - Validación cruzada simple: calcular factores sin un mes y evaluar en ese mes.
  - Limitaciones en lenguaje simple.
- **Listo cuando:** el reporte existe. **Detenerse aquí con más cuidado**: el método es lo que más pesa con los jueces y el equipo debe entenderlo y aprobarlo.

### Fase 4 — Exportar JSON
- `export.py`: generar los archivos de la sección 7 en `web/public/data/`.
- Agregar un comando único que corra todo el pipeline: `uv run python -m pipeline.run_all`.
- **Listo cuando:** los JSON validan contra el contrato, el tamaño total está dentro del objetivo y se reporta cuántas celdas hay.

### Fase 5 — App web
- Mapa Leaflet centrado en México con hexágonos (límites calculados con `h3-js`), coloreados por `viirs_h` total (escala secuencial con leyenda).
- Clic en un hexágono → panel con:
  - Calendario ECharts de 2024 (tipo heatmap) con conteos diarios.
  - Selector: MODIS / VIIRS crudo / VIIRS armonizado.
  - Totales y las 3 semanas con más actividad.
- Vista inicial (sin selección): mismo calendario con `national.json`.
- Textos de la interfaz en inglés.
- **Listo cuando:** `npm run build` funciona sin errores y la app carga los JSON reales.

### Fase 6 — Pulir y publicar
- README en inglés: qué es, capturas, cómo correr el pipeline y la web, datos usados, método de armonización, limitaciones.
- Desplegar `web/` como sitio estático (Vercel o Netlify) y anotar la URL en el README.
- Extra si sobra tiempo: seleccionar varios hexágonos a la vez y sumar sus series.

## 9. Reglas para el agente

- Conversa con el equipo en **español**; código, comentarios, README e interfaz en **inglés**.
- Nunca inventes datos ni resultados. Si algo falla, dilo y detente.
- No subas `data/raw/` ni `data/interim/` a Git. Nunca escribas claves en el código.
- Commits pequeños con mensajes claros, uno o más por fase.
- Antes de agregar una dependencia no listada en la sección 3, pregunta.
- Si una decisión de la sección 6 no funciona con los datos reales, propón el cambio y explica por qué, pero no lo apliques sin confirmación.
- Mantén las respuestas al final de cada fase cortas: qué hiciste, qué verificar, qué decidir.
