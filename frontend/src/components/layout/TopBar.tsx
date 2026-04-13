import { useTorrentStore } from "../../store/useTorrentStore";

interface TopBarProps {
  onAddClick: () => void;
}

export const TopBar: React.FC<TopBarProps> = ({ onAddClick }) => {
  const stats = useTorrentStore((state) => state.stats);
  const toggleAggressiveMode = useTorrentStore((state) => state.toggleAggressiveMode);

  return (
    <header className="topbar">
      <div className="topbar-brand">Sluice Torrent</div>
      
      <div className="topbar-actions" style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
        <button 
          className={`btn ${stats.aggressive_mode ? 'btn-danger' : 'btn-primary'}`} 
          style={stats.aggressive_mode ? { backgroundColor: 'var(--status-error)', borderColor: 'var(--status-error)', boxShadow: '0 4px 12px rgba(239, 71, 111, 0.3)' } : {}}
          onClick={() => toggleAggressiveMode(!stats.aggressive_mode)}
          title={stats.aggressive_mode ? "Forced max bandwidth settings" : "Engine dynamically tuning optimal bandwidth"}
        >
          {stats.aggressive_mode ? '⚡ Aggressive Mode ON' : '🤖 Auto-Tune Mode'}
        </button>

        <button className="btn btn-primary" onClick={onAddClick}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="12" y1="5" x2="12" y2="19"></line>
            <line x1="5" y1="12" x2="19" y2="12"></line>
          </svg>
          Add Torrent
        </button>
      </div>
    </header>
  );
};
