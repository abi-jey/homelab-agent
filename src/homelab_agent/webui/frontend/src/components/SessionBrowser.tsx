import { useState, useEffect, useCallback } from 'react';
import type { FC } from 'react';
import './SessionBrowser.css';

interface Session {
    user_id: string;
    session_count: number;
    last_update: string;
}

interface SessionDetail {
    id: string;
    user_id: string;
    app_name: string;
    create_time: string;
    update_time: string;
    message_count: number;
}

interface MessageEvent {
    id: string;
    session_id: string;
    author: string;
    content: string | null;
    timestamp: string;
    role: string | null;
    text: string | null;
    is_tool_call: boolean;
    tool_name: string | null;
    is_tool_response: boolean;
}

interface SessionBrowserProps {
    onClose: () => void;
}

export const SessionBrowser: FC<SessionBrowserProps> = ({ onClose }) => {
    const [users, setUsers] = useState<Session[]>([]);
    const [selectedUser, setSelectedUser] = useState<string | null>(null);
    const [userSessions, setUserSessions] = useState<SessionDetail[]>([]);
    const [selectedSession, setSelectedSession] = useState<string | null>(null);
    const [messages, setMessages] = useState<MessageEvent[]>([]);
    const [loading, setLoading] = useState(false);
    const [messagesTotal, setMessagesTotal] = useState(0);

    // Fetch users list
    const fetchUsers = useCallback(async () => {
        try {
            const response = await fetch('/api/sessions');
            const data = await response.json();
            setUsers(data.sessions || []);
        } catch (error) {
            console.error('Failed to fetch users:', error);
        }
    }, []);

    // Fetch sessions for a user
    const fetchUserSessions = useCallback(async (userId: string) => {
        setLoading(true);
        try {
            const response = await fetch(`/api/users/${encodeURIComponent(userId)}/sessions`);
            const data = await response.json();
            setUserSessions(data.sessions || []);
        } catch (error) {
            console.error('Failed to fetch user sessions:', error);
        } finally {
            setLoading(false);
        }
    }, []);

    // Fetch messages for a session
    const fetchMessages = useCallback(async (sessionId: string) => {
        setLoading(true);
        try {
            const response = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/messages?limit=200`);
            const data = await response.json();
            setMessages(data.messages || []);
            setMessagesTotal(data.total || 0);
        } catch (error) {
            console.error('Failed to fetch messages:', error);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchUsers();
    }, [fetchUsers]);

    const handleUserClick = (userId: string) => {
        setSelectedUser(userId);
        setSelectedSession(null);
        setMessages([]);
        fetchUserSessions(userId);
    };

    const handleSessionClick = (sessionId: string) => {
        setSelectedSession(sessionId);
        fetchMessages(sessionId);
    };

    const handleBack = () => {
        if (selectedSession) {
            setSelectedSession(null);
            setMessages([]);
        } else if (selectedUser) {
            setSelectedUser(null);
            setUserSessions([]);
        }
    };

    const formatTimestamp = (ts: string) => {
        try {
            const date = new Date(ts);
            return date.toLocaleString();
        } catch {
            return ts;
        }
    };

    const getMessageIcon = (msg: MessageEvent) => {
        if (msg.is_tool_call) return '🔧';
        if (msg.is_tool_response) return '📤';
        if (msg.role === 'user') return '👤';
        if (msg.author === 'user') return '👤';
        return '🤖';
    };

    const getMessageClass = (msg: MessageEvent) => {
        if (msg.is_tool_call || msg.is_tool_response) return 'tool';
        if (msg.role === 'user' || msg.author === 'user') return 'user';
        return 'assistant';
    };

    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="session-browser" onClick={(e) => e.stopPropagation()}>
                <div className="browser-header">
                    <div className="header-left">
                        {(selectedUser || selectedSession) && (
                            <button className="back-button" onClick={handleBack}>
                                ← Back
                            </button>
                        )}
                        <h2>
                            {selectedSession
                                ? `Messages (${messagesTotal})`
                                : selectedUser
                                    ? `Sessions for ${selectedUser}`
                                    : 'Session Browser'}
                        </h2>
                    </div>
                    <button className="close-button" onClick={onClose}>✕</button>
                </div>

                <div className="browser-content">
                    {loading && (
                        <div className="loading">
                            <span className="spinner">⏳</span> Loading...
                        </div>
                    )}

                    {/* Users List */}
                    {!selectedUser && !loading && (
                        <div className="users-list">
                            {users.length === 0 ? (
                                <div className="empty-state">
                                    <span className="empty-icon">📭</span>
                                    <p>No sessions found</p>
                                </div>
                            ) : (
                                users.map((user) => (
                                    <button
                                        key={user.user_id}
                                        className="list-item user-item"
                                        onClick={() => handleUserClick(user.user_id)}
                                    >
                                        <div className="item-icon">👤</div>
                                        <div className="item-info">
                                            <span className="item-title">{user.user_id}</span>
                                            <span className="item-meta">
                                                {user.session_count} session{user.session_count !== 1 ? 's' : ''} • Last: {user.last_update}
                                            </span>
                                        </div>
                                        <span className="item-arrow">→</span>
                                    </button>
                                ))
                            )}
                        </div>
                    )}

                    {/* Sessions List */}
                    {selectedUser && !selectedSession && !loading && (
                        <div className="sessions-list">
                            {userSessions.length === 0 ? (
                                <div className="empty-state">
                                    <span className="empty-icon">📭</span>
                                    <p>No sessions found for this user</p>
                                </div>
                            ) : (
                                userSessions.map((session) => (
                                    <button
                                        key={session.id}
                                        className="list-item session-item"
                                        onClick={() => handleSessionClick(session.id)}
                                    >
                                        <div className="item-icon">💬</div>
                                        <div className="item-info">
                                            <span className="item-title">
                                                {session.id.substring(0, 8)}...
                                            </span>
                                            <span className="item-meta">
                                                {session.message_count} messages • Created: {session.create_time}
                                            </span>
                                            <span className="item-meta">
                                                Last update: {session.update_time}
                                            </span>
                                        </div>
                                        <span className="item-arrow">→</span>
                                    </button>
                                ))
                            )}
                        </div>
                    )}

                    {/* Messages List */}
                    {selectedSession && !loading && (
                        <div className="messages-list">
                            {messages.length === 0 ? (
                                <div className="empty-state">
                                    <span className="empty-icon">📭</span>
                                    <p>No messages in this session</p>
                                </div>
                            ) : (
                                messages.map((msg) => (
                                    <div
                                        key={msg.id}
                                        className={`message-item ${getMessageClass(msg)}`}
                                    >
                                        <div className="message-header">
                                            <span className="message-icon">{getMessageIcon(msg)}</span>
                                            <span className="message-author">
                                                {msg.author}
                                                {msg.tool_name && ` (${msg.tool_name})`}
                                            </span>
                                            <span className="message-time">
                                                {formatTimestamp(msg.timestamp)}
                                            </span>
                                        </div>
                                        <div className="message-content">
                                            {msg.text || (
                                                <span className="no-content">[No text content]</span>
                                            )}
                                        </div>
                                    </div>
                                ))
                            )}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};
