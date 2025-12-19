import type { FC } from 'react';
import './TypingIndicator.css';

export const TypingIndicator: FC = () => {
    return (
        <div className="typing-wrapper">
            <div className="typing-avatar">
                <span>🤖</span>
            </div>
            <div className="typing-indicator">
                <span className="typing-dot"></span>
                <span className="typing-dot"></span>
                <span className="typing-dot"></span>
            </div>
        </div>
    );
};
