import type { Config, DayPayload, PreviewResult, TaskStatus, TimeBlock } from "./types";

async function parseError(res: Response): Promise<string> {
  const data = await res.json().catch(() => null);
  if (data && typeof data.detail === "string") return data.detail;
  if (data && data.detail && typeof data.detail.message === "string") {
    return data.detail.message;
  }
  if (data && typeof data.message === "string") return data.message;
  return res.statusText || "Error de red";
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });
  if (!res.ok) {
    const error = new Error(await parseError(res)) as Error & {
      status: number;
      body?: unknown;
    };
    error.status = res.status;
    throw error;
  }
  return res.json() as Promise<T>;
}

export const api = {
  config: () => request<Config>("/api/config"),
  day: (date: string) => request<DayPayload>(`/api/day?date=${date}`),
  addNote: (day: string, content: string) =>
    request("/api/notes", {
      method: "POST",
      body: JSON.stringify({ day, content }),
    }),
  deleteNote: (id: number) =>
    request(`/api/notes/${id}`, { method: "DELETE" }),
  addTask: (day: string, title: string, url?: string) =>
    request("/api/tasks", {
      method: "POST",
      body: JSON.stringify({ day, title, url: url || null }),
    }),
  patchTask: (
    id: number,
    patch: { title?: string; url?: string | null; status?: TaskStatus; day?: string },
  ) =>
    request(`/api/tasks/${id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  deleteTask: (id: number) =>
    request(`/api/tasks/${id}`, { method: "DELETE" }),
  preview: (payload: {
    date: string;
    start_time: string;
    end_time: string;
    use_ai: boolean;
  }) =>
    request<PreviewResult>("/api/reports/preview", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  export: (payload: {
    date: string;
    start_time: string;
    end_time: string;
    blocks: TimeBlock[];
    overwrite: boolean;
  }) =>
    request<{ ok: boolean; xlsx_path: string; xlsx_name: string }>(
      "/api/reports/export",
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    ),
};
