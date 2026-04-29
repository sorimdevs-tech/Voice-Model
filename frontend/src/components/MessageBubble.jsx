import React, { useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { 
  HiMicrophone, HiOutlineClipboardCopy, HiOutlineThumbUp, HiOutlineThumbDown, 
  HiCheck, HiOutlineRefresh, HiOutlinePencilAlt, HiOutlineX
} from 'react-icons/hi';
import { toast } from 'react-hot-toast';

import UserAvatar from './UserAvatar';
import DashboardResponse from './DashboardResponse';

/**
 * Strict message schema expected:
 * { id, role, content, type: 'text'|'voice', createdAt, isError }
 */
export default function MessageBubble({ message, onRetry, onRegenerate, onEdit, isStreaming }) {
  const { role, content, type, createdAt, isError } = message;
  const isUser = role === 'user';
  const isVoice = type === 'voice';

  const [copied, setCopied] = useState(false);
  const [feedback, setFeedback] = useState(null);
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState(content);

  const handleCopy = () => {
    if (!content || isStreaming) return;
    navigator.clipboard.writeText(content).then(() => {
      setCopied(true);
      toast.success('Copied to clipboard');
      setTimeout(() => setCopied(false), 2000);
    }).catch(err => {
      console.error('Failed to copy:', err);
      toast.error('Failed to copy');
    });
  };

  const handleFeedback = (type) => {
    setFeedback(type === feedback ? null : type);
  };

  const handleEditSubmit = () => {
    if (editContent.trim() && editContent !== content) {
      onEdit(message.id, editContent.trim());
    }
    setIsEditing(false);
  };

  const handleEditKeyDown = (e) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      handleEditSubmit();
    }
    if (e.key === 'Escape') {
      setIsEditing(false);
      setEditContent(content);
    }
  };

  const formattedTime = useMemo(() => {
    if (!createdAt) return '';
    return new Date(createdAt).toLocaleTimeString('en-US', {
      hour: 'numeric', minute: '2-digit', hour12: true,
    });
  }, [createdAt]);

  return (
    <div
      id={`message-${message.id}`}
      className={`
        group flex gap-2 sm:gap-3 py-1.5 sm:py-2 max-w-[820px] w-full mx-auto animate-fade-in-up
        ${isUser ? 'flex-row-reverse' : ''}
        ${message.isStale ? 'message-stale' : ''}
      `}
    >
      {/* Avatar — smaller on mobile */}
      {isUser ? (
        <UserAvatar 
          className="flex-shrink-0 w-7 h-7 sm:w-8 sm:h-8 rounded-full flex items-center justify-center text-[0.65rem] sm:text-xs font-bold mt-0.5 overflow-hidden shadow-lg"
          style={{ background: 'linear-gradient(135deg, #D4AF37, #B8962E)', color: '#0B0B0F' }}
        />
      ) : (
        <div className="flex-shrink-0 w-7 h-7 sm:w-8 sm:h-8 rounded-full flex items-center justify-center bg-[var(--surf)] border border-gold/[0.18] mt-0.5">
          <svg width="18" height="18" viewBox="0 0 28 28" fill="none">
            <defs>
              <linearGradient id={`ai-grad-${message.id}`} x1="0" y1="0" x2="28" y2="28">
                <stop offset="0%" stopColor="#D4AF37" />
                <stop offset="100%" stopColor="#F5E6B3" />
              </linearGradient>
            </defs>
            <circle cx="14" cy="14" r="13" stroke={`url(#ai-grad-${message.id})`} strokeWidth="2" fill="none" />
            <path d="M10 18 C10 12, 14 9, 14 9 C14 9, 18 12, 18 18" stroke={`url(#ai-grad-${message.id})`} strokeWidth="2" strokeLinecap="round" fill="none" />
            <circle cx="14" cy="10" r="2" fill={`url(#ai-grad-${message.id})`} />
          </svg>
        </div>
      )}

      {/* Content wrapper */}
      <div className={`flex flex-col gap-0.5 sm:gap-1 max-w-[calc(100%-44px)] sm:max-w-[calc(100%-52px)] min-w-0 ${isUser ? 'items-end' : ''}`}>
        {/* Bubble */}
        <div
          className={`
            px-3 sm:px-4 py-2 sm:py-3 rounded-xl
            text-[0.8375rem] sm:text-[0.9375rem] leading-[1.6] sm:leading-[1.65] break-words
            ${isUser
              ? 'bg-gold-gradient text-black rounded-br-sm shadow-[0_4px_15px_rgba(212,175,55,0.25)]'
              : `bg-[var(--surf)] border border-gold/[0.15] rounded-bl-sm shadow-[0_2px_8px_rgba(0,0,0,0.3)]
                 ${isError ? '!bg-red-500/10 !border-red-500/40' : ''}`}
            ${isEditing ? 'w-full !p-0' : ''}
          `}
        >
          {/* Voice badge */}
          {isUser && isVoice && !isEditing && (
            <div className="inline-flex items-center gap-1 text-xs opacity-75 mb-1">
              <HiMicrophone size={12} />
              <span>Voice message</span>
            </div>
          )}

          {isEditing ? (
            <div className="flex flex-col w-full min-w-[200px] sm:min-w-[320px] bg-white/10 rounded-lg overflow-hidden border border-black/10">
              <textarea
                autoFocus
                className="w-full bg-transparent text-black outline-none border-none p-4 resize-none font-sans text-sm sm:text-base selection:bg-black/20"
                rows={Math.max(2, editContent.split('\n').length)}
                value={editContent}
                onChange={e => setEditContent(e.target.value)}
                onKeyDown={handleEditKeyDown}
              />
              <div className="flex items-center justify-end gap-3 p-3 bg-black/5 border-t border-black/10">
                <button 
                  onClick={() => {
                    setIsEditing(false);
                    setEditContent(content);
                  }}
                  className="px-3 py-1.5 text-[11px] font-bold uppercase tracking-wider text-black/60 hover:text-black transition-colors"
                >
                  Cancel
                </button>
                <button 
                  onClick={handleEditSubmit}
                  className="px-4 py-1.5 text-[11px] font-black uppercase tracking-widest bg-[#0B0B0F] text-[#D4AF37] rounded-lg hover:bg-black transition-all shadow-md active:scale-95"
                >
                  Send
                </button>
              </div>
            </div>
          ) : isUser ? (
            <p>{content}</p>
          ) : (
            <div className={`prose-gold overflow-x-auto ${isError ? 'text-red-400' : ''}`}>
              {(() => {
                const c = content || '';
                let displayContent = c;
                let extractedHtml = '';
                
                const lowerC = c.toLowerCase();
                const htmlStartIndex = lowerC.indexOf('<!doctype html>');
                const htmlEndIndex = lowerC.indexOf('</html>');
                
                if (htmlStartIndex !== -1 && htmlEndIndex !== -1) {
                  const fullEndIndex = htmlEndIndex + '</html>'.length;
                  extractedHtml = c.substring(htmlStartIndex, fullEndIndex);
                  
                  // Extract content before and after the HTML block
                  const beforeHtml = c.substring(0, htmlStartIndex).replace(/```[a-z]*\s*$/i, '').trim();
                  const afterHtml = c.substring(fullEndIndex).replace(/^\s*```/i, '').trim();

                  return (
                    <>
                      {beforeHtml && (
                        <ReactMarkdown
                          remarkPlugins={[remarkGfm]}
                          components={{
                            table: ({ node, ...props }) => (
                              <div className="table-glass">
                                <table {...props} />
                              </div>
                            )
                          }}
                        >
                          {beforeHtml}
                        </ReactMarkdown>
                      )}

                      <div className="w-full bg-white rounded-xl overflow-hidden my-4 border border-gold/[0.3] shadow-lg animate-fade-in-scale" style={{ height: '650px', maxWidth: '1000px', display: 'block' }}>
                        <iframe
                          srcDoc={extractedHtml}
                          style={{ width: '100%', height: '100%', border: 'none', display: 'block' }}
                          title="Dashboard Response"
                        />
                      </div>

                      {afterHtml && (
                        <ReactMarkdown
                          remarkPlugins={[remarkGfm]}
                          components={{
                            table: ({ node, ...props }) => (
                              <div className="table-glass">
                                <table {...props} />
                              </div>
                            )
                          }}
                        >
                          {afterHtml}
                        </ReactMarkdown>
                      )}
                    </>
                  );
                }

                return (
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={{
                      table: ({ node, ...props }) => (
                        <div className="table-glass">
                          <table {...props} />
                        </div>
                      )
                    }}
                  >
                    {displayContent}
                  </ReactMarkdown>
                );
              })()}
            </div>
          )}

          {/* Streaming cursor */}
          {isStreaming && (
            <span className="inline-block text-gold animate-pulse-beat ml-0.5" aria-hidden="true">▊</span>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center gap-2 mt-0.5">
          <span className="text-xs text-[var(--txt3)] px-1">{formattedTime}</span>

          {/* User actions: Edit */}
          {isUser && !isEditing && onEdit && (
             <div className="flex items-center gap-1 opacity-100 md:opacity-0 md:group-hover:opacity-100 transition-opacity duration-150">
                <button
                  className="w-6 h-6 rounded flex items-center justify-center text-[var(--txt3)] hover:bg-[var(--surf-hover)] hover:text-[var(--txt2)] transition-all duration-150"
                  onClick={() => setIsEditing(true)}
                  title="Edit message"
                >
                  <HiOutlinePencilAlt size={14} />
                </button>
             </div>
          )}

          {!isUser && !isStreaming && (
            /* Actions — always visible on touch, hover on desktop */
            <div className="flex items-center gap-1 opacity-100 md:opacity-0 md:group-hover:opacity-100 transition-opacity duration-150">
              {isError && onRetry && (
                <button
                  className="w-6 h-6 rounded flex items-center justify-center text-red-400 hover:bg-red-500/10 transition-all duration-150"
                  onClick={onRetry}
                  title="Retry response"
                >
                  <HiOutlineRefresh size={14} />
                </button>
              )}
              {!isError && onRegenerate && (
                <button
                  className="w-6 h-6 rounded flex items-center justify-center text-[var(--txt3)] hover:bg-[var(--surf-hover)] hover:text-[var(--txt2)] transition-all duration-150"
                  onClick={onRegenerate}
                  title="Regenerate response"
                  disabled={isStreaming}
                >
                  <HiOutlineRefresh size={14} />
                </button>
              )}
              <button
                className="w-6 h-6 rounded flex items-center justify-center text-[var(--txt3)] hover:bg-[var(--surf-hover)] hover:text-[var(--txt2)] transition-all duration-150"
                onClick={handleCopy}
                title="Copy response"
              >
                {copied ? <HiCheck size={14} className="text-emerald-400" /> : <HiOutlineClipboardCopy size={14} />}
              </button>
              <button
                className={`w-6 h-6 rounded flex items-center justify-center transition-all duration-150
                  ${feedback === 'up' ? 'text-emerald-400' : 'text-[var(--txt3)] hover:bg-[var(--surf-hover)] hover:text-[var(--txt2)]'}`}
                onClick={() => handleFeedback('up')}
                title="Good response"
              >
                <HiOutlineThumbUp size={14} />
              </button>
              <button
                className={`w-6 h-6 rounded flex items-center justify-center transition-all duration-150
                  ${feedback === 'down' ? 'text-red-400' : 'text-[var(--txt3)] hover:bg-[var(--surf-hover)] hover:text-[var(--txt2)]'}`}
                onClick={() => handleFeedback('down')}
                title="Bad response"
              >
                <HiOutlineThumbDown size={14} />
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * Typing indicator shown while waiting for first token
 */
export function TypingIndicator() {
  return (
    <div className="flex gap-3 py-2 max-w-[820px] w-full mx-auto animate-fade-in-up" id="typing-indicator">
      <div className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center bg-[var(--surf)] border border-gold/[0.18] mt-0.5">
        <svg width="18" height="18" viewBox="0 0 28 28" fill="none">
          <defs>
            <linearGradient id="ai-grad-typing" x1="0" y1="0" x2="28" y2="28">
              <stop offset="0%" stopColor="#D4AF37" />
              <stop offset="100%" stopColor="#F5E6B3" />
            </linearGradient>
          </defs>
          <circle cx="14" cy="14" r="13" stroke="url(#ai-grad-typing)" strokeWidth="2" fill="none" />
          <path d="M10 18 C10 12, 14 9, 14 9 C14 9, 18 12, 18 18" stroke="url(#ai-grad-typing)" strokeWidth="2" strokeLinecap="round" fill="none" />
          <circle cx="14" cy="10" r="2" fill="url(#ai-grad-typing)" />
        </svg>
      </div>
      <div className="flex flex-col gap-1 max-w-[calc(100%-52px)] min-w-0">
        <div className="px-4 py-3 rounded-xl rounded-bl-sm bg-[var(--surf)] border border-gold/[0.15] shadow-[0_2px_8px_rgba(0,0,0,0.3)]">
          <div className="flex gap-1.5 py-1">
            <span className="w-2 h-2 rounded-full bg-[var(--txt3)] animate-typing-dot" style={{ animationDelay: '0s' }} />
            <span className="w-2 h-2 rounded-full bg-[var(--txt3)] animate-typing-dot" style={{ animationDelay: '0.15s' }} />
            <span className="w-2 h-2 rounded-full bg-[var(--txt3)] animate-typing-dot" style={{ animationDelay: '0.3s' }} />
          </div>
        </div>
      </div>
    </div>
  );
}
