import React, { useState, useRef, useEffect } from 'react';
import { HiPaperAirplane } from 'react-icons/hi2';

export default function TextInput({ onSend, disabled = false }) {
  const [text, setText] = useState('');
  const textareaRef = useRef(null);

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = 'auto';
      el.style.height = Math.min(el.scrollHeight, 120) + 'px';
    }
  }, [text]);

  const handleSend = () => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setText('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <>
      <textarea
        ref={textareaRef}
        id="text-input-field"
        className="text-input-field flex-1 resize-none bg-transparent border-none outline-none text-[var(--txt)] text-[0.9375rem] leading-6 py-1.5 h-9 max-h-9 overflow-hidden font-sans disabled:opacity-50 placeholder:text-[var(--txt3)] focus-visible:outline-none"
        placeholder="Type a message..."
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        rows={1}
        aria-label="Type a message"
      />
      <button
        id="text-send-btn"
        className={`
          text-send-btn flex items-center justify-center w-9 h-9 rounded-full flex-shrink-0 transition-all duration-150
          ${text.trim()
            ? 'bg-gold-gradient text-black hover:scale-110 hover:shadow-[0_2px_12px_rgba(212,175,55,0.35)] active:scale-95'
            : 'bg-[var(--surf)] text-[var(--txt3)] opacity-40 cursor-not-allowed'}
        `}
        onClick={handleSend}
        disabled={!text.trim() || disabled}
        aria-label="Send message"
        title="Send"
      >
        <HiPaperAirplane size={18} />
      </button>
    </>
  );
}
