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
    </footer>
  );
};
