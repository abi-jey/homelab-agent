import type { FC, RefObject } from 'react';
import { useCallback } from 'react';
import './InputArea.css';

interface InputAreaProps {
    value: string;
    onChange: (value: string) => void;
    onSend: () => void;
    onForget: () => void;
    isConnected: boolean;
    inputRef?: RefObject<HTMLTextAreaElement | null>;
}

export const InputArea: FC<InputAreaProps> = ({
    value,
    onChange,
    onSend,
    onForget,
    isConnected,
    inputRef,
}) => {
    const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            onSend();
        }
    }, [onSend]);

    const handleInput = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
        onChange(e.target.value);
        // Auto-resize
        const textarea = e.target;
        textarea.style.height = 'auto';
        textarea.style.height = Math.min(textarea.scrollHeight, 150) + 'px';
    }, [onChange]);

    return (
        <footer className="input-area">
            <div className="input-wrapper">
                <textarea
                    ref={inputRef}
                    className="message-input"
                    value={value}
                    onChange={handleInput}
                    onKeyDown={handleKeyDown}
                    placeholder={isConnected ? "Type a message... (press / to focus)" : "Connecting..."}
                    disabled={!isConnected}
                    rows={1}
                    autoFocus
                />

                <div className="input-actions">
                    <button
                        className="action-button forget-button"
                        onClick={onForget}
                        disabled={!isConnected}
                        title="Clear conversation"
                    >
                        <span className="button-icon">🗑️</span>
                    </button>

                    <button
                        className="action-button send-button"
                        onClick={onSend}
                        disabled={!isConnected || !value.trim()}
                        title="Send message"
                    >
                        <span className="button-icon">➤</span>
                    </button>
                </div>
            </div>

            <div className="input-footer">
                <span className="input-hint">Enter to send • Shift+Enter for new line • Ctrl+H for sidebar</span>
            </div>
        </footer>
    );
};
