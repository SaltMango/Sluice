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
  added_at: number;         // timestamp
  error?: string | null;    // error message if status === "error"
  tune_level?: number;
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

export interface DebugStats {
  scheduler_mode: string;
  active_pieces: number;
  average_peer_speed: number;
  fast_peers: number;
  slow_peers: number;
  bandwidth_utilization_percent: number;
}

export interface PieceInfo {
  index: number;
  state: string; // 'available', 'requested', 'downloading', 'complete'
  availability: number;
  is_complete: boolean;
}

export interface PeerInfo {
  endpoint: string;
  client: string;
  download_speed: number;
  is_choked: boolean;
}

export interface TorrentDetailData extends TorrentItem {
  files: {name: string, size: number, progress: number}[];
  trackers: {url: string, status: string}[];
  pieces: PieceInfo[];
  peers_detail: PeerInfo[];
}

