export type PlateSummary = {
  plate: string;
  known_name: string | null;
  count: number;
  cameras: string[];
  latest_event_id: string;
  latest_time: number;
  best_score: number | null;
};

export type PlateSortType = "last_seen" | "count" | "plate";
