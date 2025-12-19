import type { FC } from 'react';
import './SessionPicker.css';

interface Session {
    user_id: string;
    session_count: number;
    last_update: string;
}

interface SessionPickerProps {
    sessions: Session[];
    currentUserId: string;
    newUserId: string;
    onNewUserIdChange: (value: string) => void;
    onSelectSession: (userId: string) => void;
    onCreateSession: () => void;
    onClose: () => void;
}

export const SessionPicker: FC<SessionPickerProps> = ({
    sessions,
    currentUserId,
    newUserId,
    onNewUserIdChange,
    onSelectSession,
    onCreateSession,
    onClose,
}) => {
    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="session-picker" onClick={(e) => e.stopPropagation()}>
                <div className="picker-header">
                    <h2>Switch Session</h2>
                    <button className="close-button" onClick={onClose}>✕</button>
                </div>

                <div className="picker-content">
                    <div className="session-list">
                        {sessions.length === 0 ? (
                            <div className="empty-sessions">
                                <span className="empty-icon">📭</span>
                                <p>No existing sessions found</p>
                            </div>
                        ) : (
                            sessions.map((session) => (
                                <button
                                    key={session.user_id}
                                    className={`session-item ${session.user_id === currentUserId ? 'active' : ''}`}
                                    onClick={() => onSelectSession(session.user_id)}
                                >
                                    <div className="session-info">
                                        <span className="session-id">{session.user_id}</span>
                                        <span className="session-meta">
                                            {session.session_count} session{session.session_count !== 1 ? 's' : ''} • {session.last_update}
                                        </span>
                                    </div>
                                    {session.user_id === currentUserId && (
                                        <span className="current-badge">Current</span>
                                    )}
                                </button>
                            ))
                        )}
                    </div>

                    <div className="new-session">
                        <h3>Create New Session</h3>
                        <div className="new-session-input">
                            <input
                                type="text"
                                placeholder="Enter session ID (optional)"
                                value={newUserId}
                                onChange={(e) => onNewUserIdChange(e.target.value)}
                                onKeyPress={(e) => e.key === 'Enter' && onCreateSession()}
                            />
                            <button onClick={onCreateSession}>Create</button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};
