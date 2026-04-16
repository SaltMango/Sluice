import React, { useEffect, useState, useMemo, useCallback, memo } from "react";
import { formatBytes, formatSpeed, formatTime } from "../../utils/format";
import { engineApi } from "../../services/api";
import type { TorrentDetailData, TorrentMetrics } from "../../types/api";
import { useTorrentStore } from "../../store/useTorrentStore";

interface TorrentDetailProps {
  id: string;
  onBack: () => void;
}

// ── Utility formatters ────────────────────────────────────────────────────────

function fmtSecs(secs: number): string {
  if (secs < 0) return "–";
  if (secs < 60) return `${secs.toFixed(1)}s`;
  const m = Math.floor(secs / 60);
  const s = (secs % 60).toFixed(0).padStart(2, "0");
  return `${m}m ${s}s`;
}

function pct(v: number): string {
  return `${(v * 100).toFixed(1)}%`;
}

// ── Sub-components (memoised) ─────────────────────────────────────────────────

// SVG Sparkline — smooth cubic bezier curve, memoised
const SpeedSparkline = memo(({ history, avg, peak, current }: {
  history: number[];
  avg: number;
  peak: number;
  current: number;
}) => {
  const W = 320, H = 80;

  // EMA smoothing so visual noise is suppressed (α=0.25 → strong smoothing)
  const smoothed = useMemo(() => {
    if (!history || history.length < 2) return history ?? [];
    const α = 0.25;
    const out: number[] = [history[0]];
    for (let i = 1; i < history.length; i++) {
      out.push(α * history[i] + (1 - α) * out[i - 1]);
    }
    return out;
  }, [history]);

  // Build a smooth SVG `path` using cubic bezier control points
  const linePath = useMemo(() => {
    if (smoothed.length < 2) return "";
    const maxV = Math.max(...smoothed, 1);
    const pts = smoothed.map((v, i) => ({
      x: (i / (smoothed.length - 1)) * W,
      y: H - (v / maxV) * (H - 12) - 4,
    }));

    let d = `M ${pts[0].x.toFixed(1)},${pts[0].y.toFixed(1)}`;
    for (let i = 1; i < pts.length; i++) {
      const cp1x = pts[i - 1].x + (pts[i].x - pts[i - 1].x) / 3;
      const cp2x = pts[i - 1].x + (2 * (pts[i].x - pts[i - 1].x)) / 3;
      d += ` C ${cp1x.toFixed(1)},${pts[i - 1].y.toFixed(1)} ${cp2x.toFixed(1)},${pts[i].y.toFixed(1)} ${pts[i].x.toFixed(1)},${pts[i].y.toFixed(1)}`;
    }
    return d;
  }, [smoothed]);

  const areaPath = linePath
    ? `${linePath} L ${W},${H} L 0,${H} Z`
    : "";

  return (
    <div className="sparkline-container">
      <div className="sparkline-header">
        <span className="sparkline-title">📈 Download Speed</span>
        <span className="sparkline-live">
          <span className="sparkline-live-dot" />
          Live — {formatSpeed(current)}
        </span>
      </div>

      <svg className="sparkline-svg" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
        <defs>
          <linearGradient id="sparkGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%"   stopColor="var(--status-downloading)" stopOpacity="0.28" />
            <stop offset="100%" stopColor="var(--status-downloading)" stopOpacity="0"   />
          </linearGradient>
        </defs>
        {areaPath && (
          <path d={areaPath} fill="url(#sparkGrad)" />
        )}
        {linePath && (
          <path
            d={linePath}
            fill="none"
            stroke="var(--status-downloading)"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        )}
      </svg>

      <div className="sparkline-speed-row">
        <div className="sparkline-stat">
          <span className="sparkline-stat-label">Current</span>
          <span className="sparkline-stat-value" style={{ color: "var(--status-downloading)" }}>
            {formatSpeed(current)}
          </span>
        </div>
        <div className="sparkline-stat">
          <span className="sparkline-stat-label">Avg 10s</span>
          <span className="sparkline-stat-value">{formatSpeed(avg)}</span>
        </div>
        <div className="sparkline-stat">
          <span className="sparkline-stat-label">Peak</span>
          <span className="sparkline-stat-value" style={{ color: "var(--status-completed)" }}>
            {formatSpeed(peak)}
          </span>
        </div>
      </div>
    </div>
  );
});


// Peer quality stacked bar
const PeerBar = memo(({ peers }: { peers: TorrentMetrics["peers"] }) => {
  const total = Math.max(peers.total, 1);
  const normalCount = Math.max(0, peers.active - peers.fast);
  
  const fastPct   = (peers.fast / total) * 100;
  const normalPct = (normalCount / total) * 100;
  const idlePct   = (peers.slow / total) * 100;

  return (
    <div className="peer-bar-container">
      <div className="peer-bar-header">
        <div>
          <div className="peer-bar-total">{peers.total}</div>
          <div className="peer-bar-sub">total peers</div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div className="metric-card-value" style={{ color: "var(--text-secondary)", fontSize: "0.85rem" }}>
            {formatSpeed(peers.avg_speed)} avg
          </div>
          {peers.fast_threshold > 0 && (
            <div className="metric-card-sub">fast ≥ {formatSpeed(peers.fast_threshold)}</div>
          )}
        </div>
      </div>

      <div className="peer-bar-track">
        <div className="peer-bar-segment peer-seg-fast"   title={`Fast (${peers.fast})`} style={{ width: `${fastPct}%` }} />
        <div className="peer-bar-segment peer-seg-active" title={`Normal (${normalCount})`} style={{ width: `${normalPct}%` }} />
        <div className="peer-bar-segment peer-seg-slow"   title={`Idle (${peers.slow})`} style={{ width: `${idlePct}%` }} />
      </div>

      <div className="peer-bar-legend">
        <div className="peer-legend-item">
          <div className="peer-legend-dot" style={{ background: "var(--status-completed)" }} />
          Fast ({peers.fast})
        </div>
        <div className="peer-legend-item">
          <div className="peer-legend-dot" style={{ background: "var(--status-downloading)" }} />
          Normal ({normalCount})
        </div>
        <div className="peer-legend-item">
          <div className="peer-legend-dot" style={{ background: "rgba(255,255,255,0.15)" }} />
          Idle ({peers.slow})
        </div>
        <div className="peer-legend-item" style={{ marginLeft: "auto" }}>
          Seeds: {peers.seeds}
        </div>
      </div>
    </div>
  );
});

// Circular gauge
const Gauge = memo(({ value, label, color }: { value: number; label: string; color: string }) => {
  const r = 28, circumference = 2 * Math.PI * r;
  const offset = circumference * (1 - Math.min(1, Math.max(0, value)));
  return (
    <div className="gauge-item">
      <svg className="gauge-svg" viewBox="0 0 64 64">
        <circle className="gauge-track" cx="32" cy="32" r={r} />
        <circle
          className="gauge-fill"
          cx="32" cy="32" r={r}
          stroke={color}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
        />
        {/* center text — counter-rotate to undo SVG rotation */}
        <text
          x="32" y="32"
          textAnchor="middle"
          dominantBaseline="middle"
          fontSize="10"
          fontWeight="700"
          fill="var(--text-primary)"
          style={{ transform: "rotate(90deg)", transformOrigin: "32px 32px" }}
        >
          {pct(value)}
        </text>
      </svg>
      <span className="gauge-label">{label}</span>
    </div>
  );
});

// Decision distribution bar row
const DistBar = memo(({ label, value, color }: { label: string; value: number; color: string }) => (
  <div className="dist-row">
    <span className="dist-label">{label}</span>
    <div className="dist-track">
      <div className="dist-fill" style={{ width: `${(value * 100).toFixed(1)}%`, background: color }} />
    </div>
    <span className="dist-pct">{(value * 100).toFixed(0)}%</span>
  </div>
));

// ── Main Dashboard component (memoised) ───────────────────────────────────────

const MetricsDashboard = memo(({ m }: { m: TorrentMetrics }) => {
  const pieceHealthClass = useMemo(() => {
    const stallRatio = m.pieces.total > 0 ? m.pieces.stalled / m.pieces.total : 0;
    if (stallRatio > 0.1) return "metric-card-error";
    if (stallRatio > 0.04) return "metric-card-warn";
    return "metric-card-good";
  }, [m.pieces.stalled, m.pieces.total]);

  const modeClass = useMemo(() => `mode-badge mode-badge-${m.scheduler.mode}`, [m.scheduler.mode]);

  return (
    <div className="metrics-dashboard">

      {/* ── 1. Speed + Peer row ─────────────────────────────────── */}
      <div className="metrics-panel-row">
        <SpeedSparkline
          history={m.speed.history}
          avg={m.speed.avg_10s}
          peak={m.speed.peak}
          current={m.speed.current}
        />
        <PeerBar peers={m.peers} />
      </div>

      {/* ── 2. Piece health ─────────────────────────────────────── */}
      <div className="metrics-panel">
        <div className="metrics-section-header">
          <span className="section-icon">🧩</span> Piece Health
        </div>
        <div className="metric-grid metric-grid-4">
          <div className={`metric-card metric-card-good`}>
            <span className="metric-card-label">Completed</span>
            <span className="metric-card-value">{m.pieces.completed}</span>
            <span className="metric-card-sub">of {m.pieces.total} total</span>
          </div>
          <div className="metric-card metric-card-accent">
            <span className="metric-card-label">Active</span>
            <span className="metric-card-value">{m.pieces.active}</span>
            <span className="metric-card-sub">downloading now</span>
          </div>
          <div className={`metric-card ${pieceHealthClass}`}>
            <span className="metric-card-label">Stalled</span>
            <span className="metric-card-value">{m.pieces.stalled}</span>
            <span className="metric-card-sub">availability = 0</span>
          </div>
          <div className="metric-card">
            <span className="metric-card-label">Rarest</span>
            <span className="metric-card-value">{m.pieces.rarest_count}</span>
            <span className="metric-card-sub">
              avail {m.pieces.min_availability}–{m.pieces.max_availability} (avg {m.pieces.avg_availability.toFixed(1)})
            </span>
          </div>
        </div>
        <div style={{ marginTop: "10px", display: "flex", alignItems: "center", gap: "6px", fontSize: "0.75rem", color: "var(--text-tertiary)" }}>
          <span>Completion rate:</span>
          <strong style={{ color: "var(--text-primary)" }}>
            {m.pieces.completion_rate > 0 ? `${m.pieces.completion_rate.toFixed(3)} pieces/s` : "–"}
          </strong>
        </div>
      </div>

      {/* ── 3. Scheduler + Efficiency ───────────────────────────── */}
      <div className="metrics-panel-row">

        {/* Scheduler panel */}
        <div className="metrics-panel" style={{ margin: 0 }}>
          <div className="metrics-section-header">
            <span className="section-icon">🧠</span> Scheduler
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "16px" }}>
            <span className={modeClass}>
              <span className="mode-badge-dot" />
              {m.scheduler.mode}
            </span>
            <span style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
              {m.scheduler.pieces_scored} pieces scored
            </span>
          </div>

          <div className="metric-grid metric-grid-3" style={{ marginBottom: "16px" }}>
            <div className="metric-card">
              <span className="metric-card-label">Avg Score</span>
              <span className="metric-card-value">{m.scheduler.avg_score.toFixed(3)}</span>
            </div>
            <div className="metric-card metric-card-good">
              <span className="metric-card-label">Top Score</span>
              <span className="metric-card-value">{m.scheduler.top_score.toFixed(3)}</span>
            </div>
            <div className="metric-card">
              <span className="metric-card-label">High Priority</span>
              <span className="metric-card-value">{m.scheduler.high_priority_count}</span>
              <span className="metric-card-sub">{m.scheduler.rare_pieces_boosted} rare boosted</span>
            </div>
          </div>

          <div style={{ fontSize: "0.7rem", color: "var(--text-tertiary)", marginBottom: "6px", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Decision Distribution
          </div>
          <div className="decision-dist">
            <DistBar label="Rarity"   value={m.scheduler.decision_distribution.rarity}   color="var(--status-checking)" />
            <DistBar label="Speed"    value={m.scheduler.decision_distribution.speed}    color="var(--status-error)" />
            <DistBar label="Peer"     value={m.scheduler.decision_distribution.peer}     color="var(--status-downloading)" />
            <DistBar label="Position" value={m.scheduler.decision_distribution.position} color="var(--status-completed)" />
          </div>
        </div>

        {/* Efficiency & Health panel */}
        <div className="metrics-panel" style={{ margin: 0 }}>
          <div className="metrics-section-header">
            <span className="section-icon">🎯</span> Efficiency & Health
          </div>

          <div className="gauge-group" style={{ marginBottom: "20px" }}>
            <Gauge value={m.health.efficiency}            label="Efficiency"  color="var(--status-completed)" />
            <Gauge value={m.health.stability}             label="Stability"   color="var(--status-downloading)" />
            <Gauge value={m.health.bandwidth_utilization} label="BW Util"     color="var(--accent-color)" />
          </div>

          <div className="metric-grid metric-grid-2">
            <div className={`metric-card ${m.health.stall_events > 0 ? "metric-card-warn" : "metric-card-good"}`}>
              <span className="metric-card-label">Stall Events</span>
              <span className="metric-card-value">{m.health.stall_events}</span>
              <span className="metric-card-sub">{m.health.stall_time.toFixed(1)}s total stalled</span>
            </div>
            <div className="metric-card">
              <span className="metric-card-label">Variance</span>
              <span className="metric-card-value">{formatSpeed(m.speed.variance)}</span>
              <span className="metric-card-sub">speed std-dev</span>
            </div>
          </div>

          {/* Insight callout */}
          {m.health.efficiency < 0.5 && (
            <div style={{ marginTop: "12px", padding: "10px 12px", borderRadius: "6px", background: "rgba(239,71,111,0.08)", border: "1px solid rgba(239,71,111,0.2)", fontSize: "0.75rem", color: "var(--status-error)" }}>
              ⚠️ Low efficiency ({pct(m.health.efficiency)}) — consider switching to <strong>aggressive</strong> mode or adding peers.
            </div>
          )}
          {m.pieces.stalled > 5 && (
            <div style={{ marginTop: "8px", padding: "10px 12px", borderRadius: "6px", background: "rgba(242,166,90,0.08)", border: "1px solid rgba(242,166,90,0.2)", fontSize: "0.75rem", color: "var(--status-paused)" }}>
              ⚠️ {m.pieces.stalled} stalled pieces — rare-piece starvation risk. Increase rarity weight.
            </div>
          )}
        </div>
      </div>

      {/* ── 4. Time milestones ──────────────────────────────────── */}
      <div className="metrics-panel">
        <div className="metrics-section-header">
          <span className="section-icon">⏱️</span> Time Milestones
        </div>
        <div className="time-milestones">
          <div className="milestone-chip">
            <span className="milestone-label">Time to First Byte</span>
            <span className="milestone-value">{fmtSecs(m.time.ttfb)}</span>
          </div>
          <div className="milestone-chip">
            <span className="milestone-label">Time to 50%</span>
            <span className="milestone-value">{fmtSecs(m.time.t50)}</span>
          </div>
          <div className="milestone-chip">
            <span className="milestone-label">Session Uptime</span>
            <span className="milestone-value">{fmtSecs(m.time.session_uptime)}</span>
          </div>
        </div>
      </div>

    </div>
  );
});

// ── Top-level detail page ─────────────────────────────────────────────────────

export const TorrentDetail: React.FC<TorrentDetailProps> = ({ id, onBack }) => {
  const [detail, setDetail] = useState<TorrentDetailData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const { pauseTorrent, resumeTorrent, removeTorrent } = useTorrentStore();

  const fetchDetail = useCallback(async () => {
    try {
      const res = await engineApi.getTorrentDetail(id);
      if (res.success && res.data) {
        setDetail(res.data as TorrentDetailData);
      } else {
        setError(res.error || "Failed to fetch detail");
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    let mounted = true;
    const fetch = async () => {
      if (!mounted) return;
      await fetchDetail();
    };
    fetch();
    const interval = setInterval(fetch, 2000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, [fetchDetail]);

  const percent = useMemo(() => detail ? (detail.progress * 100).toFixed(1) : "0.0", [detail?.progress]);

  if (loading && !detail) {
    return (
      <div style={{ padding: "24px", display: "flex", alignItems: "center", gap: "10px" }}>
        <div className="sparkline-live-dot" />
        Loading torrent data…
      </div>
    );
  }

  if (error || !detail) {
    return (
      <div style={{ padding: "24px" }}>
        <button className="btn" onClick={onBack} style={{ marginBottom: "16px" }}>← Back</button>
        <div style={{ color: "var(--status-error)" }}>{error || "Torrent not found"}</div>
      </div>
    );
  }

  return (
    <div className="torrent-detail" style={{ padding: "20px", maxWidth: "100%", overflowX: "hidden" }}>
      <button className="btn" onClick={onBack} style={{ marginBottom: "24px" }}>← Back to List</button>

      {/* ── Header card ────────────────────────────────────────── */}
      <div style={{ backgroundColor: "var(--bg-surface)", padding: "20px", borderRadius: "8px", marginBottom: "24px", border: "1px solid var(--border-glass)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "16px" }}>
          <div>
            <h2 style={{ margin: "0 0 8px 0", fontSize: "1.5rem", wordBreak: "break-all" }}>{detail.name}</h2>
            <div style={{ display: "flex", gap: "16px", color: "var(--text-secondary)", fontSize: "0.9rem", flexWrap: "wrap" }}>
              <span>{formatBytes(detail.downloaded)} / {formatBytes(detail.size)}</span>
              <span className={`status-badge status-${detail.status}`}>{detail.status}</span>
              {detail.save_path && (
                <span style={{ fontSize: "0.8rem", color: "var(--text-tertiary)", fontFamily: "monospace" }}>
                  📁 {detail.save_path}
                </span>
              )}
            </div>
          </div>
          <div style={{ display: "flex", gap: "8px", flexShrink: 0 }}>
            <button className="btn" onClick={() => engineApi.openFolder(detail.id)}>📁 Open</button>
            {detail.status === "downloading" || detail.status === "checking" ? (
              <button className="btn" onClick={() => pauseTorrent(detail.id)}>⏸ Pause</button>
            ) : (
              <button className="btn" onClick={() => resumeTorrent(detail.id)}>▶ Resume</button>
            )}
            <button className="btn btn-danger" onClick={() => { removeTorrent(detail.id); onBack(); }}>✕ Remove</button>
          </div>
        </div>

        <div className="progress-container" style={{ height: "12px", marginBottom: "8px" }}>
          <div
            className="progress-fill"
            style={{ width: `${Math.min(Number(percent), 100)}%`, backgroundColor: `var(--status-${detail.status})` }}
          />
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.85rem" }}>
          <span>{percent}% Complete</span>
          <span>ETA: {detail.status === "downloading" ? formatTime(detail.eta) : "–"}</span>
        </div>

        {/* Speed/Peers summary */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: "12px", marginTop: "20px" }}>
          <div className="metric-card metric-card-accent">
            <span className="metric-card-label">Download</span>
            <span className="metric-card-value">{formatSpeed(detail.download_speed)}</span>
          </div>
          <div className="metric-card">
            <span className="metric-card-label">Upload</span>
            <span className="metric-card-value">{formatSpeed(detail.upload_speed)}</span>
          </div>
          <div className="metric-card">
            <span className="metric-card-label">Peers / Seeds</span>
            <span className="metric-card-value">{detail.peers} / {detail.seeds}</span>
          </div>
        </div>
      </div>

      {/* ── Metrics Dashboard ───────────────────────────────────── */}
      <div style={{ marginBottom: "24px" }}>
        <h3 style={{ margin: "0 0 4px 0", fontSize: "1.1rem" }}>
          📊 Performance Metrics
          <span style={{ fontSize: "0.7rem", color: "var(--text-tertiary)", fontWeight: 400, marginLeft: "10px" }}>
            updates every 2s
          </span>
        </h3>
        {detail.metrics ? (
          <MetricsDashboard m={detail.metrics} />
        ) : (
          <div style={{ padding: "32px", textAlign: "center", color: "var(--text-tertiary)", fontSize: "0.85rem", background: "var(--bg-surface)", borderRadius: "8px", marginTop: "12px", border: "1px solid var(--border-glass)" }}>
            ⏳ Collecting metrics… (available after first scheduler tick, ~15s)
          </div>
        )}
      </div>

      {/* ── Swarm debug tables ──────────────────────────────────── */}
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) minmax(0,1fr)", gap: "24px", marginTop: "8px" }}>

        {/* Peer table */}
        <div style={{ backgroundColor: "var(--bg-surface)", padding: "16px", borderRadius: "8px", border: "1px solid var(--border-glass)" }}>
          <h4 style={{ marginTop: 0, marginBottom: "16px", fontSize: "1rem" }}>🌐 Swarm Peer Analysis</h4>
          <div style={{ maxHeight: "260px", overflowY: "auto" }}>
            <table className="torrent-table" style={{ margin: 0, width: "100%", fontSize: "0.83rem" }}>
              <thead style={{ position: "sticky", top: 0, zIndex: 1, backgroundColor: "var(--bg-surface)" }}>
                <tr>
                  <th>Endpoint</th>
                  <th>Client</th>
                  <th>Speed</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {!detail.peers_detail || detail.peers_detail.length === 0 ? (
                  <tr><td colSpan={4} style={{ textAlign: "center", opacity: 0.5 }}>No active peers</td></tr>
                ) : (
                  detail.peers_detail.map((p, i) => (
                    <tr key={i}>
                      <td style={{ fontFamily: "monospace", fontSize: "0.78rem" }}>{p.endpoint}</td>
                      <td style={{ maxWidth: "110px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={p.client}>
                        {p.client || "Unknown"}
                      </td>
                      <td style={{ color: p.download_speed > 0 ? "var(--status-downloading)" : "inherit" }}>
                        {formatSpeed(p.download_speed)}
                      </td>
                      <td>
                        {p.is_choked ? (
                          <span style={{ color: "var(--status-error)", fontSize: "0.75rem" }}>Choked</span>
                        ) : (
                          <span style={{ color: "var(--status-completed)", fontSize: "0.75rem" }}>Active</span>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          <div style={{ marginTop: "10px", fontSize: "0.75rem", color: "var(--text-tertiary)" }}>
            <i>* Choked peers are throttled by the remote to optimise swarm.</i>
          </div>
        </div>

        {/* Piece map */}
        <div style={{ backgroundColor: "var(--bg-surface)", padding: "16px", borderRadius: "8px", border: "1px solid var(--border-glass)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "14px" }}>
            <h4 style={{ margin: 0, fontSize: "1rem" }}>🗺️ Piece Map</h4>
            <div style={{ display: "flex", gap: "8px", fontSize: "0.72rem" }}>
              <span style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                <div style={{ width: "8px", height: "8px", backgroundColor: "var(--status-completed)" }} /> Done
              </span>
              <span style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                <div style={{ width: "8px", height: "8px", backgroundColor: "var(--status-downloading)" }} /> Active
              </span>
              <span style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                <div style={{ width: "8px", height: "8px", backgroundColor: "rgba(255,255,255,0.1)" }} /> Available
              </span>
            </div>
          </div>
          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(8px, 1fr))",
            gap: "2px",
            maxHeight: "220px",
            overflowY: "auto",
          }}>
            {!detail.pieces || detail.pieces.length === 0 ? (
              <div style={{ gridColumn: "1 / -1", textAlign: "center", opacity: 0.4, padding: "20px 0" }}>
                Loading piece data…
              </div>
            ) : detail.pieces.map((piece, i) => {
              let bg = "rgba(255,255,255,0.08)";
              if (piece.is_complete) bg = "var(--status-completed)";
              else if (piece.state === "requested" || piece.state === "downloading") bg = "var(--status-downloading)";
              return (
                <div
                  key={i}
                  title={`Piece ${piece.index} | ${piece.state} | avail: ${piece.availability}`}
                  style={{ aspectRatio: "1/1", backgroundColor: bg, borderRadius: "1px" }}
                />
              );
            })}
          </div>
          {detail.pieces && detail.pieces.length > 0 && (
            <div style={{ marginTop: "10px", fontSize: "0.75rem", color: "var(--text-tertiary)", textAlign: "right" }}>
              {Math.min(detail.pieces.length, 2000)} pieces shown
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
