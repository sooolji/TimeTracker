import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { api } from "./api";
import type { Config, DayPayload, Task, TaskStatus, TimeBlock } from "./types";

function todayIso() {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

const STATUS_LABEL: Record<TaskStatus, string> = {
  todo: "Pendiente",
  doing: "En curso",
  done: "Hecha",
};

export default function App() {
  const [date, setDate] = useState(todayIso);
  const [start, setStart] = useState("13:00");
  const [end, setEnd] = useState("20:00");
  const [config, setConfig] = useState<Config | null>(null);
  const [day, setDay] = useState<DayPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [busyLabel, setBusyLabel] = useState("Generando…");

  const [noteDraft, setNoteDraft] = useState("");
  const [taskTitle, setTaskTitle] = useState("");
  const [taskUrl, setTaskUrl] = useState("");

  const [previewOpen, setPreviewOpen] = useState(false);
  const [blocks, setBlocks] = useState<TimeBlock[]>([]);
  const [previewMeta, setPreviewMeta] = useState<{
    source: string;
    warning: string | null;
    xlsx_exists: boolean;
    xlsx_name: string;
  } | null>(null);
  const [overwrite, setOverwrite] = useState(false);
  const [savedName, setSavedName] = useState<string | null>(null);

  const load = useCallback(async (selected = date) => {
    setError(null);
    try {
      const payload = await api.day(selected);
      setDay(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo cargar el día.");
    }
  }, [date]);

  useEffect(() => {
    api.config().then((cfg) => {
      setConfig(cfg);
      setStart(cfg.default_start);
      setEnd(cfg.default_end);
    }).catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    void load(date);
  }, [date, load]);

  const doneCount = useMemo(
    () => day?.tasks.filter((t) => t.status === "done" && t.day === date).length ?? 0,
    [day, date],
  );

  async function addNote(e: FormEvent) {
    e.preventDefault();
    if (!noteDraft.trim()) return;
    await api.addNote(date, noteDraft.trim());
    setNoteDraft("");
    await load();
  }

  async function addTask(e: FormEvent) {
    e.preventDefault();
    if (!taskTitle.trim()) return;
    await api.addTask(date, taskTitle.trim(), taskUrl.trim());
    setTaskTitle("");
    setTaskUrl("");
    await load();
  }

  async function setStatus(task: Task, status: TaskStatus) {
    await api.patchTask(task.id, {
      status,
      day: status === "done" ? date : task.day,
    });
    await load();
  }

  async function generate() {
    setBusy(true);
    setBusyLabel("Consultando DeepSeek V4 Pro…");
    setError(null);
    setSavedName(null);
    try {
      const cfg = await api.config();
      setConfig(cfg);
      const result = await api.preview({
        date,
        start_time: start,
        end_time: end,
        use_ai: true,
      });
      setBlocks(result.blocks);
      setPreviewMeta({
        source: result.source,
        warning: result.warning,
        xlsx_exists: result.xlsx_exists,
        xlsx_name: result.xlsx_name,
      });
      setOverwrite(false);
      setPreviewOpen(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo generar el preview.");
    } finally {
      setBusy(false);
      setBusyLabel("Generando…");
    }
  }

  function updateBlock(index: number, patch: Partial<TimeBlock>) {
    setBlocks((current) =>
      current.map((block, i) => (i === index ? { ...block, ...patch } : block)),
    );
  }

  async function confirmExport() {
    setBusy(true);
    setError(null);
    try {
      const result = await api.export({
        date,
        start_time: start,
        end_time: end,
        blocks,
        overwrite,
      });
      setSavedName(result.xlsx_name);
      setPreviewOpen(false);
      await load();
    } catch (err) {
      const status = (err as Error & { status?: number }).status;
      if (status === 409) {
        setOverwrite(true);
        setPreviewMeta((meta) =>
          meta ? { ...meta, xlsx_exists: true, warning: err instanceof Error ? err.message : meta.warning } : meta,
        );
      } else {
        setError(err instanceof Error ? err.message : "No se pudo guardar el Excel.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app">
      <header className="top">
        <div className="brand">
          <h1>TimeTracker</h1>
          <p>
            Notas y tareas del día → Excel de {config?.author ?? "Jonathan"}
            {config?.ai_available
              ? ` · IA ${config.ai_provider}`
              : " · sin IA (reparto automático)"}
          </p>
        </div>
        <div className="controls">
          <label className="field">
            <span>Fecha</span>
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </label>
          <label className="field">
            <span>Inicio</span>
            <input type="time" value={start} onChange={(e) => setStart(e.target.value)} />
          </label>
          <label className="field">
            <span>Fin</span>
            <input type="time" value={end} onChange={(e) => setEnd(e.target.value)} />
          </label>
          <button className="btn" disabled={busy} onClick={() => void generate()}>
            {busy ? busyLabel : "Generar informe"}
          </button>
        </div>
      </header>

      {error ? <p className="banner error">{error}</p> : null}
      {savedName ? (
        <p className="banner">Informe guardado: {savedName}</p>
      ) : null}
      {day?.xlsx_exists ? (
        <p className="banner">Ya hay un Excel para este día: {day.xlsx_name}</p>
      ) : null}

      <div className="columns">
        <section className="panel">
          <h2>Notas</h2>
          <p className="hint">Apunta lo que vas haciendo. Entran en el informe del día.</p>
          <form className="composer" onSubmit={(e) => void addNote(e)}>
            <textarea
              rows={3}
              placeholder="Rebase del PR, ajuste responsive, reunión…"
              value={noteDraft}
              onChange={(e) => setNoteDraft(e.target.value)}
            />
            <button className="btn" type="submit">
              Guardar nota
            </button>
          </form>
          <div className="list">
            {day?.notes.length ? (
              day.notes.map((note) => (
                <article className="item" key={note.id}>
                  <div className="body">
                    <p>{note.content}</p>
                    <div className="meta">{note.created_at.replace("T", " ").slice(0, 16)}</div>
                  </div>
                  <button
                    className="btn danger"
                    type="button"
                    onClick={() => void api.deleteNote(note.id).then(() => load())}
                  >
                    Borrar
                  </button>
                </article>
              ))
            ) : (
              <p className="empty">Sin notas para este día.</p>
            )}
          </div>
        </section>

        <section className="panel">
          <h2>Tareas</h2>
          <p className="hint">
            Las hechas ({doneCount}) se usan al generar. Las pendientes siguen visibles.
          </p>
          <form className="composer" onSubmit={(e) => void addTask(e)}>
            <input
              placeholder="Título de la tarea"
              value={taskTitle}
              onChange={(e) => setTaskTitle(e.target.value)}
            />
            <div className="row">
              <input
                placeholder="URL (issue o PR, opcional)"
                value={taskUrl}
                onChange={(e) => setTaskUrl(e.target.value)}
              />
              <button className="btn" type="submit">
                Añadir
              </button>
            </div>
          </form>
          <div className="list">
            {day?.tasks.length ? (
              day.tasks.map((task) => (
                <article className="item" key={task.id}>
                  <div className="body">
                    <h3>{task.title}</h3>
                    {task.url ? (
                      <a href={task.url} target="_blank" rel="noreferrer">
                        {task.url}
                      </a>
                    ) : null}
                    <div className="meta">
                      {task.day !== date ? `Desde ${task.day} · ` : null}
                      {STATUS_LABEL[task.status]}
                    </div>
                    <div className="status">
                      {(["todo", "doing", "done"] as TaskStatus[]).map((status) => (
                        <button
                          key={status}
                          type="button"
                          className={`chip ${status} ${task.status === status ? "active" : ""}`}
                          onClick={() => void setStatus(task, status)}
                        >
                          {STATUS_LABEL[status]}
                        </button>
                      ))}
                    </div>
                  </div>
                  <button
                    className="btn danger"
                    type="button"
                    onClick={() => void api.deleteTask(task.id).then(() => load())}
                  >
                    Borrar
                  </button>
                </article>
              ))
            ) : (
              <p className="empty">Sin tareas.</p>
            )}
          </div>
        </section>
      </div>

      {previewOpen && previewMeta ? (
        <div className="overlay">
          <div className="modal">
            <h2>Revisar informe</h2>
            <p className="hint">
              Fuente:{" "}
              {previewMeta.source === "ai"
                ? "DeepSeek V4 Pro"
                : "reparto automático (la IA no se usó)"}
              . Edita los bloques antes de escribir {previewMeta.xlsx_name}.
            </p>
            {previewMeta.warning ? <p className="banner error">{previewMeta.warning}</p> : null}
            {previewMeta.xlsx_exists ? (
              <p className="banner">
                {previewMeta.xlsx_name} ya existe. Vuelve a confirmar para sobrescribir.
              </p>
            ) : null}
            <table className="blocks">
              <thead>
                <tr>
                  <th>Inicio</th>
                  <th>Fin</th>
                  <th>Tarea</th>
                  <th>Descripción</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {blocks.map((block, index) => (
                  <tr key={index}>
                    <td className="time">
                      <input
                        type="time"
                        value={block.start}
                        onChange={(e) => updateBlock(index, { start: e.target.value })}
                      />
                    </td>
                    <td className="time">
                      <input
                        type="time"
                        value={block.end}
                        onChange={(e) => updateBlock(index, { end: e.target.value })}
                      />
                    </td>
                    <td>
                      <input
                        value={block.title}
                        onChange={(e) => updateBlock(index, { title: e.target.value })}
                      />
                    </td>
                    <td>
                      <input
                        value={block.description}
                        onChange={(e) => updateBlock(index, { description: e.target.value })}
                      />
                    </td>
                    <td>
                      <button
                        className="btn danger"
                        type="button"
                        onClick={() => setBlocks((current) => current.filter((_, i) => i !== index))}
                      >
                        Quitar
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="modal-actions">
              <button
                className="btn ghost"
                type="button"
                onClick={() =>
                  setBlocks((current) => [
                    ...current,
                    { start: end, end, title: "", description: "" },
                  ])
                }
              >
                Añadir bloque
              </button>
              <button className="btn ghost" type="button" onClick={() => setPreviewOpen(false)}>
                Cancelar
              </button>
              <button className="btn" disabled={busy || blocks.length === 0} onClick={() => void confirmExport()}>
                {previewMeta.xlsx_exists || overwrite ? "Sobrescribir Excel" : "Guardar Excel"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
