import type { FC } from 'react';
import { useState, useEffect, useCallback } from 'react';
import './Sidebar.css';

interface Session {
    id: string;
    user_id: string;
    app_name: string;
    create_time: string;
    update_time: string;
    message_count: number;
}

interface Memory {
    id: string;
    user_id: string;
    content: string;
    tags: string[];
    created_at: string;
    updated_at: string;
}

interface SidebarProps {
    isOpen: boolean;
    activeTab: 'sessions' | 'memories';
    currentUserId: string;
    onTabChange: (tab: 'sessions' | 'memories') => void;
    onClose: () => void;
    onSessionSelect: (sessionId: string) => void;
    onSessionDelete: (sessionId: string) => void;
}

export const Sidebar: FC<SidebarProps> = ({
    isOpen,
    activeTab,
    currentUserId,
    onTabChange,
    onClose,
    onSessionSelect,
    onSessionDelete,
}) => {
    const [users, setUsers] = useState<string[]>([]);
    const [selectedUser, setSelectedUser] = useState<string | null>(null);
    const [sessions, setSessions] = useState<Session[]>([]);
    const [memories, setMemories] = useState<Memory[]>([]);
    const [memoryUsers, setMemoryUsers] = useState<string[]>([]);
    const [selectedMemoryUser, setSelectedMemoryUser] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);

    // Fetch session users
    const fetchUsers = useCallback(async () => {
        try {
            const response = await fetch('/api/sessions');
            const data = await response.json();
            const userList = data.sessions?.map((s: { user_id: string }) => s.user_id) || [];
            setUsers([...new Set(userList)] as string[]);
        } catch (error) {
            console.error('Failed to fetch users:', error);
        }
    }, []);

    // Fetch sessions for a user
    const fetchSessions = useCallback(async (userId: string) => {
        setLoading(true);
        try {
            const response = await fetch(`/api/users/${encodeURIComponent(userId)}/sessions`);
            const data = await response.json();
            setSessions(data.sessions || []);
        } catch (error) {
            console.error('Failed to fetch sessions:', error);
        }
        setLoading(false);
    }, []);

    // Fetch memory users
    const fetchMemoryUsers = useCallback(async () => {
        try {
            const response = await fetch('/api/memories/users');
            const data = await response.json();
            setMemoryUsers(data.users || []);
        } catch (error) {
            console.error('Failed to fetch memory users:', error);
        }
    }, []);

    // Fetch memories for a user
    const fetchMemories = useCallback(async (userId: string) => {
        setLoading(true);
        try {
            const response = await fetch(`/api/memories/${encodeURIComponent(userId)}`);
            const data = await response.json();
            setMemories(data.memories || []);
        } catch (error) {
            console.error('Failed to fetch memories:', error);
        }
        setLoading(false);
    }, []);

    // Delete a memory
    const deleteMemory = useCallback(async (userId: string, memoryId: string) => {
        try {
            await fetch(`/api/memories/${encodeURIComponent(userId)}/${encodeURIComponent(memoryId)}`, {
                method: 'DELETE',
            });
            setMemories(prev => prev.filter(m => m.id !== memoryId));
        } catch (error) {
            console.error('Failed to delete memory:', error);
        }
    }, []);

    // Delete a session
    const handleDeleteSession = useCallback(async (sessionId: string) => {
        if (!confirm('Delete this session and all its messages?')) return;
        try {
            await fetch(`/api/sessions/${encodeURIComponent(sessionId)}`, {
                method: 'DELETE',
            });
            setSessions(prev => prev.filter(s => s.id !== sessionId));
            onSessionDelete(sessionId);
        } catch (error) {
            console.error('Failed to delete session:', error);
        }
    }, [onSessionDelete]);

    // Load data when sidebar opens or tab changes
    useEffect(() => {
        if (isOpen) {
            if (activeTab === 'sessions') {
                fetchUsers();
            } else {
                fetchMemoryUsers();
            }
        }
    }, [isOpen, activeTab, fetchUsers, fetchMemoryUsers]);

    // Load sessions when user is selected
    useEffect(() => {
        if (selectedUser) {
            fetchSessions(selectedUser);
        }
    }, [selectedUser, fetchSessions]);

    // Load memories when memory user is selected
    useEffect(() => {
        if (selectedMemoryUser) {
            fetchMemories(selectedMemoryUser);
        }
    }, [selectedMemoryUser, fetchMemories]);

    // Keyboard shortcut to close sidebar
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Escape' && isOpen) {
                onClose();
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [isOpen, onClose]);

    if (!isOpen) return null;

    return (
        <>
            <div className="sidebar-overlay" onClick={onClose} />
            <aside className="sidebar">
                <div className="sidebar-header">
                    <div className="sidebar-tabs">
                        <button
                            className={`sidebar-tab ${activeTab === 'sessions' ? 'active' : ''}`}
                            onClick={() => onTabChange('sessions')}
                        >
                            📋 Sessions
                        </button>
                        <button
                            className={`sidebar-tab ${activeTab === 'memories' ? 'active' : ''}`}
                            onClick={() => onTabChange('memories')}
                        >
                            🧠 Memories
                        </button>
                    </div>
                    <button className="sidebar-close" onClick={onClose} title="Close (Esc)">
                        ✕
                    </button>
                </div>

                <div className="sidebar-content">
                    {activeTab === 'sessions' ? (
                        <div className="sidebar-section">
                            <div className="user-list">
                                <div className="section-title">Users</div>
                                {users.map(user => (
                                    <button
                                        key={user}
                                        className={`user-item ${selectedUser === user ? 'selected' : ''}`}
                                        onClick={() => setSelectedUser(user)}
                                    >
                                        👤 {user}
                                        {user === currentUserId && <span className="current-badge">current</span>}
                                    </button>
                                ))}
                                {users.length === 0 && (
                                    <div className="empty-state">No sessions found</div>
                                )}
                            </div>

                            {selectedUser && (
                                <div className="session-list">
                                    <div className="section-title">Sessions for {selectedUser}</div>
                                    {loading ? (
                                        <div className="loading">Loading...</div>
                                    ) : (
                                        sessions.map(session => (
                                            <div key={session.id} className="session-item">
                                                <div
                                                    className="session-info"
                                                    onClick={() => onSessionSelect(session.id)}
                                                >
                                                    <div className="session-date">
                                                        {new Date(session.update_time).toLocaleDateString()}
                                                    </div>
                                                    <div className="session-meta">
                                                        {session.message_count} messages
                                                    </div>
                                                </div>
                                                <button
                                                    className="delete-btn"
                                                    onClick={() => handleDeleteSession(session.id)}
                                                    title="Delete session"
                                                >
                                                    🗑️
                                                </button>
                                            </div>
                                        ))
                                    )}
                                    {!loading && sessions.length === 0 && (
                                        <div className="empty-state">No sessions</div>
                                    )}
                                </div>
                            )}
                        </div>
                    ) : (
                        <div className="sidebar-section">
                            <div className="user-list">
                                <div className="section-title">Users with Memories</div>
                                {memoryUsers.map(user => (
                                    <button
                                        key={user}
                                        className={`user-item ${selectedMemoryUser === user ? 'selected' : ''}`}
                                        onClick={() => setSelectedMemoryUser(user)}
                                    >
                                        👤 {user}
                                        {user === currentUserId && <span className="current-badge">current</span>}
                                    </button>
                                ))}
                                {memoryUsers.length === 0 && (
                                    <div className="empty-state">No memories found</div>
                                )}
                            </div>

                            {selectedMemoryUser && (
                                <div className="memory-list">
                                    <div className="section-title">Memories</div>
                                    {loading ? (
                                        <div className="loading">Loading...</div>
                                    ) : (
                                        memories.map(memory => (
                                            <div key={memory.id} className="memory-item">
                                                <div className="memory-content">
                                                    {memory.content.length > 100
                                                        ? memory.content.slice(0, 100) + '...'
                                                        : memory.content}
                                                </div>
                                                {memory.tags.length > 0 && (
                                                    <div className="memory-tags">
                                                        {memory.tags.map(tag => (
                                                            <span key={tag} className="tag">{tag}</span>
                                                        ))}
                                                    </div>
                                                )}
                                                <div className="memory-footer">
                                                    <span className="memory-date">
                                                        {new Date(memory.created_at).toLocaleDateString()}
                                                    </span>
                                                    <button
                                                        className="delete-btn small"
                                                        onClick={() => deleteMemory(selectedMemoryUser, memory.id)}
                                                        title="Delete memory"
                                                    >
                                                        🗑️
                                                    </button>
                                                </div>
                                            </div>
                                        ))
                                    )}
                                    {!loading && memories.length === 0 && (
                                        <div className="empty-state">No memories</div>
                                    )}
                                </div>
                            )}
                        </div>
                    )}
                </div>

                <div className="sidebar-footer">
                    <div className="keyboard-hints">
                        <span><kbd>Esc</kbd> Close</span>
                        <span><kbd>Ctrl</kbd>+<kbd>H</kbd> Toggle</span>
                        <span><kbd>/</kbd> Focus input</span>
                    </div>
                </div>
            </aside>
        </>
    );
};
