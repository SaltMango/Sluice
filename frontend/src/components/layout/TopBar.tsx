import React from 'react';

interface TopBarProps {
  onAddClick: () => void;
}

export const TopBar: React.FC<TopBarProps> = ({ onAddClick }) => {
  return (
    <header className="topbar">
      <div className="topbar-brand">Sluice Torrent</div>
      
      <div className="topbar-actions" style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
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
