from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta

import httpx
from dotenv import load_dotenv

DEFAULT_STYLE_EXAMPLES = [
    "Ajustes finales en la vista de login y cambio de fotos por el video en desktop y mobile",
    "Corrección de estadísticas y merge a la rama dev",
    "Cambios en el flujo de cambio de contraseña y correo electrónico con su PR listo",
    "Rebase de la rama de feature sobre dev, cierre de PR #82 y creación de PR #85",
]


def style_examples() -> list[str]:
    raw = (os.getenv("STYLE_EXAMPLES") or "").strip()
    if not raw:
        return DEFAULT_STYLE_EXAMPLES
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(item).strip() for item in data if str(item).strip()]
    except ValueError:
        pass
    return [line.strip() for line in raw.splitlines() if line.strip()]


def parse_hhmm(value: str) -> datetime:
    hour, minute = map(int, value.strip().split(":")[:2])
    return datetime(2000, 1, 1, hour, minute)


def format_hhmm(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def minutes_between(start: str, end: str) -> int:
    delta = parse_hhmm(end) - parse_hhmm(start)
    total = int(delta.total_seconds() // 60)
    if total <= 0:
        raise ValueError("La hora de fin debe ser posterior a la de inicio.")
    return total


def split_contiguous(start: str, end: str, count: int) -> list[tuple[str, str]]:
    if count < 1:
        count = 1
    total = minutes_between(start, end)
    base = total // count
    extra = total % count
    cursor = parse_hhmm(start)
    blocks: list[tuple[str, str]] = []
    for index in range(count):
        span = base + (1 if index < extra else 0)
        nxt = cursor + timedelta(minutes=span)
        blocks.append((format_hhmm(cursor), format_hhmm(nxt)))
        cursor = nxt
    return blocks


def heuristic_blocks(
    *,
    start: str,
    end: str,
    notes: list[dict],
    done_tasks: list[dict],
) -> list[dict]:
    items: list[dict] = []
    for task in done_tasks:
        items.append(
            {
                "title": task["title"].strip(),
                "description": (task.get("url") or "").strip(),
            }
        )
    if not items:
        for note in notes:
            text = note["content"].strip()
            if not text:
                continue
            items.append({"title": text.split("\n")[0][:180], "description": ""})
    if not items:
        items.append(
            {
                "title": "Trabajo del día",
                "description": "",
            }
        )
    ranges = split_contiguous(start, end, len(items))
    return [
        {
            "start": rng[0],
            "end": rng[1],
            "title": item["title"],
            "description": item["description"],
        }
        for rng, item in zip(ranges, items)
    ]


def _reload_env() -> None:
    load_dotenv(override=True)


def _api_key() -> str:
    _reload_env()
    return (
        os.getenv("DEEPSEEK_API_KEY", "").strip()
        or os.getenv("OPENAI_API_KEY", "").strip()
    )


def ai_configured() -> bool:
    return bool(_api_key())


def ai_provider() -> str:
    if not ai_configured():
        return "none"
    return os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro")


def _extract_json(text: str) -> list[dict]:
    text = text.strip()
    match = re.search(r"\[.*\]", text, re.DOTALL)
    payload = match.group(0) if match else text
    data = json.loads(payload)
    if not isinstance(data, list):
        raise ValueError("La IA no devolvió una lista de bloques.")
    blocks = []
    for item in data:
        blocks.append(
            {
                "start": str(item["start"]),
                "end": str(item["end"]),
                "title": str(item.get("title") or "").strip(),
                "description": str(item.get("description") or "").strip(),
            }
        )
    if not blocks:
        raise ValueError("La IA no devolvió bloques.")
    return blocks


def _message_text(payload: dict) -> str:
    message = payload["choices"][0]["message"]
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content
    if isinstance(content, list):
        parts = [
            part.get("text", "")
            for part in content
            if isinstance(part, dict)
        ]
        joined = "".join(parts).strip()
        if joined:
            return joined
    reasoning = message.get("reasoning_content")
    if isinstance(reasoning, str) and reasoning.strip():
        return reasoning
    raise ValueError("DeepSeek no devolvió texto en la respuesta.")


async def generate_with_ai(
    *,
    start: str,
    end: str,
    notes: list[dict],
    done_tasks: list[dict],
    author: str = "tu nombre",
) -> list[dict]:
    api_key = _api_key()
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY no está configurada.")

    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro")

    notes_txt = "\n".join(f"- {n['content']}" for n in notes) or "(sin notas)"
    tasks_txt = (
        "\n".join(
            f"- {t['title']}" + (f" | {t['url']}" if t.get("url") else "")
            for t in done_tasks
        )
        or "(sin tareas hechas)"
    )
    examples = "\n".join(f"- {s}" for s in style_examples())

    prompt = f"""Eres un asistente que redacta el informe diario de tiempo de {author}.

Ventana de trabajo: {start} a {end}.
Genera bloques de tiempo CONTIGUOS que cubran exactamente ese rango (sin huecos ni solapes).
Cada bloque: start, end (HH:MM 24h), title (una frase de lo hecho, español, estilo de los ejemplos), description (URL de Gitea/issue/PR si existe; si no, vacío).
1 a 4 bloques. No inventes trabajo que no esté en las notas o tareas. Si hay URL en una tarea, ponla en description de ese bloque.
No uses markdown. Responde SOLO un JSON array.

Estilo de títulos (ejemplos reales):
{examples}

Notas del día:
{notes_txt}

Tareas terminadas:
{tasks_txt}
"""

    payload = {
        "model": model,
        "temperature": 0.3,
        "stream": False,
        "thinking": {"type": "disabled"},
        "messages": [
            {
                "role": "system",
                "content": "Devuelves únicamente JSON válido. Sin texto extra.",
            },
            {"role": "user", "content": prompt},
        ],
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        if response.status_code >= 400 and "thinking" in response.text.lower():
            payload.pop("thinking", None)
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if response.status_code >= 400:
            detail = response.text[:400]
            raise RuntimeError(f"DeepSeek {response.status_code}: {detail}")
        content = _message_text(response.json())
    return _extract_json(content)
