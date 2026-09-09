# TimeTracker

App local para anotar el día y generar el Excel oficial `YYYY-MM-DD Jonathan.xlsx` (hoja **sencillo**) a partir de la plantilla `yyyy-mm-dd nombre.xlsx`.

Usa **uv** en el backend y **Bun** en el frontend. La IA es **DeepSeek V4 Pro**.

## Arranque

```bash
cp .env.example .env
# pega tu clave en DEEPSEEK_API_KEY
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

## IA (DeepSeek V4 Pro)

En `.env`:

```
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-pro
```

Sin clave, el informe reparte el rango 13:00–20:00 entre las tareas hechas (o las notas). Siempre hay preview editable antes de escribir el Excel.

Los informes se guardan en esta misma carpeta.
