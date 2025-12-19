import type { FC } from 'react';
import './Header.css';

interface HeaderProps {
    userId: string;
    isConnected: boolean;
    onSessionClick: () => void;
    onSidebarClick: () => void;
}

export const Header: FC<HeaderProps> = ({ userId, isConnected, onSessionClick, onSidebarClick }) => {
    return (
        <header className="header">
            <div className="header-brand">
                <div className="header-logo">
                    <span className="logo-icon">🏠</span>
                    <div className="logo-text">
                        <h1>HAL</h1>
                        <span className="logo-subtitle">Homelab Agent</span>
                    </div>
                </div>
            </div>

            <div className="header-actions">
                <button
                    className="sidebar-button"
                    onClick={onSidebarClick}
                    title="Open sidebar (Ctrl+H)"
                >
                    <span className="sidebar-icon">☰</span>
                </button>

                <button
                    className="session-button"
                    onClick={onSessionClick}
                    title="Switch session"
                >
                    <span className="session-icon">👤</span>
                    <span className="session-name">{userId}</span>
                    <span className="session-chevron">▼</span>
                </button>

                <div className={`connection-status ${isConnected ? 'connected' : 'disconnected'}`}>
                    <span className="status-dot"></span>
                    <span className="status-text">{isConnected ? 'Connected' : 'Disconnected'}</span>
                </div>
            </div>
        </header>
    );
};
