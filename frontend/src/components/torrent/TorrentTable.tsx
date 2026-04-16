import React from "react";
import { formatBytes, formatSpeed, formatTime } from "../../utils/format";
import { useTorrentStore } from "../../store/useTorrentStore";
import type { TorrentItem } from "../../types/api";

// ── Tune Level Badge ──────────────────────────────────────────────────────────

const TUNE_CONFIG: Record<number, { label: string; color: string; bg: string; tip: string }> = {
  0: { label: "SAFE", color: "#22c55e", bg: "rgba(34,197,94,0.12)",  tip: "Conservative — fewer connections, maximum stability" },
  1: { label: "BAL",  color: "#3b82f6", bg: "rgba(59,130,246,0.12)", tip: "Balanced — moderate speed, good stability" },
  2: { label: "AGG",  color: "#f97316", bg: "rgba(249,115,22,0.12)", tip: "Aggressive — high speed, less stable" },
  3: { label: "EXT",  color: "#ef4444", bg: "rgba(239,68,68,0.12)",  tip: "Extreme — max connections, may stress peers" },
};

const TuneBadge: React.FC<{ level?: number }> = ({ level = 1 }) => {
  const cfg = TUNE_CONFIG[level] ?? TUNE_CONFIG[1];
  return (
    <span
      title={cfg.tip}
      style={{
        display: "inline-block",
        padding: "2px 7px",
        borderRadius: "4px",
        fontSize: "0.72rem",
        fontWeight: 700,
        letterSpacing: "0.04em",
        color: cfg.color,
        backgroundColor: cfg.bg,
        border: `1px solid ${cfg.color}44`,
        cursor: "help",
        userSelect: "none",
      }}
    >
      {cfg.label}
    </span>
  );
};

// ── Torrent Row ───────────────────────────────────────────────────────────────

const TorrentRow: React.FC<{ torrent: TorrentItem, onClick: () => void }> = ({ torrent, onClick }) => {
  const { pauseTorrent, resumeTorrent, removeTorrent } = useTorrentStore();
  const percent = (torrent.progress * 100).toFixed(1);

  return (
    <tr className="torrent-row" onClick={onClick} style={{ cursor: 'pointer' }}>
      <td>
        <div className="cell-name" title={torrent.name}>{torrent.name}</div>
        <div className="cell-size">{formatBytes(torrent.downloaded)} / {formatBytes(torrent.size)}</div>
      </td>
      <td>
        <div>{percent}%</div>
        <div className="progress-container">
          <div 
            className="progress-fill" 
            style={{ 
              width: `${Math.min(Number(percent), 100)}%`,
              backgroundColor: `var(--status-${torrent.status})` 
            }} 
          />
        </div>
      </td>
      <td>
        <div>
          <span className={`status-badge status-${torrent.status}`}>
            {torrent.status}
          </span>
        </div>
        {torrent.error && <div style={{color: 'var(--status-error)', fontSize: '0.75rem', marginTop: 4}}>{torrent.error}</div>}
      </td>
      <td>{torrent.download_speed > 0 ? formatSpeed(torrent.download_speed) : "-"}</td>
      <td>{torrent.upload_speed > 0 ? formatSpeed(torrent.upload_speed) : "-"}</td>
      <td>{torrent.peers} / {torrent.seeds}</td>
      <td><TuneBadge level={torrent.tune_level ?? 1} /></td>
      <td>{torrent.download_speed > 0 || torrent.upload_speed > 0 ? 'Yes' : 'No'}</td>
      <td>{torrent.status === 'downloading' ? formatTime(torrent.eta) : "-"}</td>
      <td>
        <div onClick={(e) => e.stopPropagation()} style={{ display: 'flex', gap: '4px' }}>
          {torrent.status === "downloading" || torrent.status === "checking" ? (
            <button className="btn btn-icon" onClick={() => pauseTorrent(torrent.id)} title="Pause">⏸</button>
          ) : (
            <button className="btn btn-icon" onClick={() => resumeTorrent(torrent.id)} title="Resume">▶</button>
          )}
          <button className="btn btn-icon btn-danger" onClick={() => removeTorrent(torrent.id)} title="Remove">✕</button>
        </div>
      </td>
    </tr>
  );
};

export const TorrentTable: React.FC<{ onRowClick: (id: string) => void }> = ({ onRowClick }) => {
  const torrents = useTorrentStore((state) => state.torrents);

  if (torrents.length === 0) {
    return (
      <div className="empty-state">
        <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
          <polyline points="17 8 12 3 7 8"></polyline>
          <line x1="12" y1="3" x2="12" y2="15"></line>
        </svg>
        <h3>No active torrents</h3>
        <p>Click "Add Torrent" to start downloading.</p>
      </div>
    );
  }

  return (
    <table className="torrent-table">
      <thead>
        <tr>
          <th>Name</th>
          <th>Progress</th>
          <th>Status</th>
          <th>Down Speed</th>
          <th>Up Speed</th>
          <th>Peers / Seeds</th>
          <th>Tune Lvl</th>
          <th>Active</th>
          <th>ETA</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody>
        {torrents.map((t) => (
          <TorrentRow key={t.id} torrent={t} onClick={() => onRowClick(t.id)} />
        ))}
      </tbody>
    </table>
  );
};
