import { useState, useEffect, useRef, useCallback } from 'react';
import { Header, ChatContainer, InputArea, SessionPicker, Sidebar } from './components';
import type { MessageData } from './components';
import './App.css';

interface WSMessage {
  type: 'message' | 'typing' | 'tool';
  sender?: 'user' | 'assistant' | 'system' | 'tool';
  content?: string;
  timestamp?: string;
  typing?: boolean;
}

interface Session {
  user_id: string;
  session_count: number;
  last_update: string;
}

function App() {
  const [messages, setMessages] = useState<MessageData[]>([]);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [userId, setUserId] = useState(() => 'web_' + Math.random().toString(36).substr(2, 9));
  const [sessions, setSessions] = useState<Session[]>([]);
  const [showSessionPicker, setShowSessionPicker] = useState(false);
  const [showSidebar, setShowSidebar] = useState(false);
  const [sidebarTab, setSidebarTab] = useState<'sessions' | 'memories'>('sessions');
  const [newUserId, setNewUserId] = useState('');

  const wsRef = useRef<WebSocket | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  // Fetch available sessions
  const fetchSessions = useCallback(async () => {
    try {
      const response = await fetch('/api/sessions');
      const data = await response.json();
      setSessions(data.sessions || []);
    } catch (error) {
      console.error('Failed to fetch sessions:', error);
    }
  }, []);

  const connect = useCallback((targetUserId: string) => {
    // Close existing connection
    if (wsRef.current) {
      wsRef.current.close();
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const ws = new WebSocket(`${protocol}//${host}/ws/${targetUserId}`);

    ws.onopen = () => {
      setIsConnected(true);
      console.log('WebSocket connected as', targetUserId);
    };

    ws.onclose = () => {
      setIsConnected(false);
      console.log('WebSocket disconnected');
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    ws.onmessage = (event) => {
      const data: WSMessage = JSON.parse(event.data);

      if (data.type === 'message' && data.content) {
        const newMessage: MessageData = {
          id: Date.now().toString() + Math.random().toString(36),
          sender: data.sender || 'assistant',
          content: data.content,
          timestamp: data.timestamp ? new Date(data.timestamp) : new Date(),
        };
        setMessages(prev => [...prev, newMessage]);
        setIsTyping(false);
      } else if (data.type === 'typing') {
        setIsTyping(data.typing || false);
      } else if (data.type === 'tool' && data.content) {
        // Tool call notification
        const toolMessage: MessageData = {
          id: Date.now().toString() + Math.random().toString(36),
          sender: 'tool',
          content: data.content,
          timestamp: data.timestamp ? new Date(data.timestamp) : new Date(),
        };
        setMessages(prev => [...prev, toolMessage]);
      }
    };

    wsRef.current = ws;
  }, []);

  useEffect(() => {
    connect(userId);

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [userId, connect]);

  // Global keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ctrl+H or Cmd+H to toggle sidebar
      if ((e.ctrlKey || e.metaKey) && e.key === 'h') {
        e.preventDefault();
        setShowSidebar(prev => !prev);
      }

      // Ctrl+Shift+S or Cmd+Shift+S to open sessions tab
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'S') {
        e.preventDefault();
        setShowSidebar(true);
        setSidebarTab('sessions');
      }

      // Ctrl+Shift+M or Cmd+Shift+M to open memories tab
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'M') {
        e.preventDefault();
        setShowSidebar(true);
        setSidebarTab('memories');
      }

      // Ctrl+N or Cmd+N for new session
      if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
        e.preventDefault();
        const newId = 'web_' + Math.random().toString(36).substr(2, 9);
        switchSession(newId);
      }

      // / to focus input when not already focused
      if (e.key === '/' && document.activeElement?.tagName !== 'TEXTAREA' && document.activeElement?.tagName !== 'INPUT') {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const switchSession = useCallback((newId: string) => {
    setMessages([]);
    setUserId(newId);
    setShowSessionPicker(false);
  }, []);

  const handleNewSession = useCallback(() => {
    const id = newUserId.trim() || 'web_' + Math.random().toString(36).substr(2, 9);
    switchSession(id);
    setNewUserId('');
  }, [newUserId, switchSession]);

  const sendMessage = useCallback(() => {
    const content = input.trim();
    if (!content || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

    // Add user message immediately
    const userMessage: MessageData = {
      id: Date.now().toString() + Math.random().toString(36),
      sender: 'user',
      content,
      timestamp: new Date(),
    };
    setMessages(prev => [...prev, userMessage]);

    // Send to server
    wsRef.current.send(JSON.stringify({ type: 'message', content }));
    setInput('');
    setIsTyping(true);
  }, [input]);

  const forgetSession = useCallback(() => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ type: 'forget' }));
    setMessages([]);
  }, []);

  const handleSessionClick = useCallback(() => {
    fetchSessions();
    setShowSessionPicker(true);
  }, [fetchSessions]);

  const handleSidebarClick = useCallback(() => {
    setShowSidebar(true);
  }, []);

  const handleSessionSelect = useCallback((sessionId: string) => {
    // For now, just close the sidebar - in future could load session messages
    console.log('Selected session:', sessionId);
    setShowSidebar(false);
  }, []);

  const handleSessionDelete = useCallback((sessionId: string) => {
    console.log('Deleted session:', sessionId);
    // Session already removed from list in Sidebar component
  }, []);

  return (
    <div className="app">
      <Header
        userId={userId}
        isConnected={isConnected}
        onSessionClick={handleSessionClick}
        onSidebarClick={handleSidebarClick}
      />

      {showSessionPicker && (
        <SessionPicker
          sessions={sessions}
          currentUserId={userId}
          newUserId={newUserId}
          onNewUserIdChange={setNewUserId}
          onSelectSession={switchSession}
          onCreateSession={handleNewSession}
          onClose={() => setShowSessionPicker(false)}
        />
      )}

      <Sidebar
        isOpen={showSidebar}
        activeTab={sidebarTab}
        currentUserId={userId}
        onTabChange={setSidebarTab}
        onClose={() => setShowSidebar(false)}
        onSessionSelect={handleSessionSelect}
        onSessionDelete={handleSessionDelete}
      />

      <ChatContainer
        messages={messages}
        isTyping={isTyping}
      />

      <InputArea
        value={input}
        onChange={setInput}
        onSend={sendMessage}
        onForget={forgetSession}
        isConnected={isConnected}
        inputRef={inputRef}
      />
    </div>
  );
}

export default App;
