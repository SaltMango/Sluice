export type TorrentID = string;

export type TorrentStatus = "downloading" | "paused" | "completed" | "checking" | "error";

export interface TorrentItem {
  id: TorrentID;
  name: string;
  progress: number;         // 0 - 1
  download_speed: number;   // bytes/sec
  upload_speed: number;     // bytes/sec
  peers: number;
  seeds: number;
  status: TorrentStatus;
  eta: number;              // seconds
  size: number;             // total bytes
  downloaded: number;       // downloaded bytes
  added_at: number;         // unix timestamp
  error?: string | null;
  tune_level?: number;
  save_path?: string | null;
}

export interface ApiResponse<T = any> {
  success: boolean;
  message?: string;
  data?: T;
  error?: string;
}

export interface GlobalStats {
  global_speed_down: number;
  global_speed_up: number;
  total_peers: number;
  active_torrents: number;
  aggressive_mode?: boolean;
  aggression_level?: number;
}

// ── Metric sub-types ─────────────────────────────────────────────────────────

export interface SpeedMetrics {
  current: number;          // bytes/sec right now
  avg_10s: number;          // 10-second rolling average
  peak: number;             // session lifetime max
  variance: number;         // std-dev of window
  history: number[];        // last ≤60 samples — use for sparkline graph
}

export interface PeerMetrics {
  total: number;
  active: number;           // not choked
  fast: number;             // speed ≥ dynamic 75th-percentile threshold
  slow: number;
  seeds: number;
  avg_speed: number;        // bytes/sec mean across all peers
  fast_threshold: number;   // the threshold used to classify fast/slow
}

export interface PieceMetrics {
  total: number;
  completed: number;
  active: number;           // currently requested/downloading
  stalled: number;          // available=0, not complete
  rarest_count: number;     // pieces at minimum availability
  completion_rate: number;  // pieces/sec
  min_availability: number;
  max_availability: number;
  avg_availability: number;
}

export interface SchedulerMetrics {
  mode: "safe" | "balanced" | "aggressive";
  avg_score: number;
  top_score: number;
  low_score: number;
  high_priority_count: number;
  rare_pieces_boosted: number;
  pieces_scored: number;
  decision_distribution: {
    rarity: number;
    speed: number;
    peer: number;
    position: number;
  };
}

export interface HealthMetrics {
  efficiency: number;           // [0–1]  avg_speed / max_possible
  stability: number;            // [0–1]  1 – std_dev / avg
  bandwidth_utilization: number;// [0–1]
  stall_events: number;
  stall_time: number;           // seconds
}

export interface TimeMetrics {
  ttfb: number;               // time to first byte (secs; -1 = not reached)
  t50: number;                // time to 50%       (secs; -1 = not reached)
  session_uptime: number;
}

export interface TorrentMetrics {
  speed: SpeedMetrics;
  peers: PeerMetrics;
  pieces: PieceMetrics;
  scheduler: SchedulerMetrics;
  health: HealthMetrics;
  time: TimeMetrics;
}

// ── Detail page ───────────────────────────────────────────────────────────────

export interface PieceInfo {
  index: number;
  state: string;  // 'available' | 'requested' | 'downloading' | 'complete'
  availability: number;
  is_complete: boolean;
}

export interface PeerDetailInfo {
  endpoint: string;
  client: string;
  download_speed: number;
  is_choked: boolean;
}

export interface TorrentDetailData extends TorrentItem {
  files: { name: string; size: number; progress: number }[];
  trackers: { url: string; status: string }[];
  pieces: PieceInfo[];
  peers_detail: PeerDetailInfo[];
  metrics?: TorrentMetrics;     // structured metrics block (may be absent until first scheduler tick)
}

// ── Debug endpoint ────────────────────────────────────────────────────────────

export interface DebugStats {
  global: {
    active_torrents: number;
    total_speed_down: number;
    total_speed_up: number;
    total_peers: number;
    speed?: SpeedMetrics;
    health?: HealthMetrics;
    time?: TimeMetrics;
  };
  torrents: {
    id: string;
    name: string;
    progress: number;
    metrics?: TorrentMetrics;
  }[];
  scheduler?: {
    mode: string;
    weights: { rarity: number; speed: number; peer: number; position: number };
  };
}
