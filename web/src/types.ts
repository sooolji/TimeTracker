export type TaskStatus = "todo" | "doing" | "done";

export type Note = {
  id: number;
  content: string;
  day: string;
  created_at: string;
};

export type Task = {
  id: number;
  title: string;
  url: string | null;
  status: TaskStatus;
  day: string;
  created_at: string;
  completed_at: string | null;
};

export type TimeBlock = {
  start: string;
  end: string;
  title: string;
  description: string;
};

export type DayPayload = {
  date: string;
  notes: Note[];
  tasks: Task[];
  reports: Array<{
    id: number;
    date: string;
    start_time: string;
    end_time: string;
    xlsx_path: string;
    generated_at: string;
  }>;
  xlsx_exists: boolean;
  xlsx_name: string;
};

export type Config = {
  author: string;
  ai_available: boolean;
  ai_provider: string;
  default_start: string;
  default_end: string;
};

export type PreviewResult = {
  source: "ai" | "heuristic";
  warning: string | null;
  blocks: TimeBlock[];
  xlsx_exists: boolean;
  xlsx_name: string;
};
