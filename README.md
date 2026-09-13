# TimeTracker

App local para anotar el día y generar el Excel oficial `YYYY-MM-DD <autor>.xlsx` (hoja **sencillo**) a partir de una plantilla configurable.

Usa **uv** en el backend y **Bun** en el frontend. La IA es configurable (DeepSeek por defecto).

## Arranque

```bash
cp .env.example .env
# pega tu clave en DEEPSEEK_API_KEY y tu nombre en REPORT_AUTHOR
./dev.sh
```

O en dos terminales:

```bash
uv sync
uv run uvicorn server.main:app --reload --port 8000
```

```bash
cd web
bun install
bun run dev
```

Abre [http://127.0.0.1:5173](http://127.0.0.1:5173).

## Configuración

En `.env`:

```bash
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-pro
REPORT_AUTHOR=Solji
TEMPLATE_NAME=yyyy-mm-dd nombre.xlsx
```

- `REPORT_AUTHOR`: nombre que aparece en la UI y en el nombre del Excel (`YYYY-MM-DD Solji.xlsx`). Sin definir, se usa "tu nombre".
- `TEMPLATE_NAME`: plantilla Excel de la que se parte (debe existir en la raíz del proyecto).
- `STYLE_EXAMPLES` (opcional): ejemplos de estilo para el prompt de la IA, como JSON array o una línea por ejemplo.

Sin clave, el informe reparte el rango 13:00–20:00 entre las tareas hechas (o las notas). Siempre hay preview editable antes de escribir el Excel.

Los informes se guardan en esta misma carpeta.
