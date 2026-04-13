import React from "react";
import { useTorrentStore } from "../../store/useTorrentStore";
import { formatSpeed } from "../../utils/format";

export const StatsBar: React.FC = () => {
  const stats = useTorrentStore((state) => state.stats);

  return (
    <footer className="statsbar">
      <div className="stat-item">
        <span className="stat-label">Download</span>
        <span className="stat-value">{formatSpeed(stats.global_speed_down)}</span>
      </div>
      <div className="stat-item">
        <span className="stat-label">Upload</span>
        <span className="stat-value">{formatSpeed(stats.global_speed_up)}</span>
      </div>
      <div className="stat-item">
        <span className="stat-label">Peers</span>
        <span className="stat-value">{stats.total_peers}</span>
      </div>
      <div className="stat-item">
        <span className="stat-label">Active</span>
        <span className="stat-value">{stats.active_torrents}</span>
      </div>
      <div className="stat-item">
        <span className="stat-label">Tune Level</span>
        <span className="stat-value" style={stats.aggressive_mode ? {color: 'var(--status-error)'} : {color: 'var(--primary-color)'}}>
          Lvl {stats.aggression_level ?? 0}
        </span>
      </div>
    </footer>
  );
};
