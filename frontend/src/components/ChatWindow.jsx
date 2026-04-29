import React, { useRef, useEffect, useCallback } from 'react';
import useChatStore from '../store/useChatStore';
import useVoiceStore from '../store/useVoiceStore';
import useVoiceRecorder from '../hooks/useVoiceRecorder';
import { transcribeAudio, streamMessage, closeStream } from '../services/api';
import { toast } from 'react-hot-toast';
import useAppStatus from '../hooks/useAppStatus';
import MessageBubble, { TypingIndicator } from './MessageBubble';
import VoiceButton from './VoiceButton';
import TextInput from './TextInput';
import WelcomeScreen from './WelcomeScreen';
import Dashboard from './Dashboard';

/**
 * Returns true if user is scrolled near the bottom (within 150px).
 */
function isNearBottom(el) {
  if (!el) return true;
  return el.scrollHeight - el.scrollTop - el.clientHeight < 150;
}

export default function ChatWindow() {
  /* ── DOM refs ── */
  const messagesContainerRef = useRef(null);   // scroll container
  const messagesEndRef       = useRef(null);   // invisible sentinel at the bottom
  const streamHandleRef      = useRef(null);   // holds the active stream handle for cancellation
  const shouldAutoScrollRef  = useRef(true);   // tracks if user is near the bottom

  /* ── Chat store selectors ── */
  const activeConversationId = useChatStore((s) => s.activeConversationId);
  const conversations        = useChatStore((s) => s.conversations);
  const isLoading            = useChatStore((s) => s.isLoading);
  const isStreaming           = useChatStore((s) => s.isStreaming);
  const streamingText        = useChatStore((s) => s.streamingText);
  const addMessage           = useChatStore((s) => s.addMessage);
  const startStreaming        = useChatStore((s) => s.startStreaming);
  const appendToken          = useChatStore((s) => s.appendToken);
  const finalizeStream       = useChatStore((s) => s.finalizeStream);
  const cancelStream         = useChatStore((s) => s.cancelStream);
  const setLoading           = useChatStore((s) => s.setLoading);
  const createConversation   = useChatStore((s) => s.createConversation);
  const removeMessage        = useChatStore((s) => s.removeMessage);
  const currentDashboardData = useChatStore((s) => s.currentDashboardData);
  const setDashboardData     = useChatStore((s) => s.setDashboardData);

  /* ── Voice store selectors ── */
  const isRecording    = useVoiceStore((s) => s.isRecording);
  const audioBlob      = useVoiceStore((s) => s.audioBlob);
  const isTranscribing = useVoiceStore((s) => s.isTranscribing);
  const setTranscribing    = useVoiceStore((s) => s.setTranscribing);
  const setTranscribedText = useVoiceStore((s) => s.setTranscribedText);
  const resetVoice         = useVoiceStore((s) => s.reset);

  const { startRecording, stopRecording } = useVoiceRecorder();

  /* ── Derived state ── */
  const activeConversation = activeConversationId ? conversations[activeConversationId] : null;
  const messages   = activeConversation?.messages || [];
  const hasMessages = messages.length > 0;

  /* ── Dashboard Parsing Logic ── */
  useEffect(() => {
    // When streaming finishes or a new message is added, check for dashboard JSON
    const lastMessage = messages[messages.length - 1];
    const textToParse = isStreaming ? streamingText : lastMessage?.content;

    if (textToParse) {
      const match = /```dashboard\s*([\s\S]*?)\s*```/.exec(textToParse);
      if (match && match[1]) {
        try {
          const data = JSON.parse(match[1].trim());
          setDashboardData(data);
        } catch (e) {
          // Partial JSON during streaming, ignore
        }
      }
    }
  }, [messages, streamingText, isStreaming, setDashboardData]);

  /* ── Initial Load Logic ── */
  useEffect(() => {
    if (!hasMessages && !isLoading && !isStreaming) {
      // Auto-fetch weekly report on first visit
      handleTextSend("Provide dashboard report for this week");
    }
  }, []);

  /*
   * Smart auto-scroll: only scrolls to the bottom when the user is already
   * near the bottom (<150px away). If the user has scrolled up to read history,
   * we don't hijack their scroll position.
   */
  const handleScroll = useCallback(() => {
    shouldAutoScrollRef.current = isNearBottom(messagesContainerRef.current);
  }, []);

  useEffect(() => {
    if (shouldAutoScrollRef.current && messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages.length, streamingText]);

  /* ── Keyboard shortcuts ── */
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && (isStreaming || isLoading)) {
        e.preventDefault();
        handleCancelStream();
      }
      if (e.key === ' ' && e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
        e.preventDefault();
        handleVoiceToggle();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isRecording, isStreaming, isLoading]);

  const handleCancelStream = useCallback(() => {
    closeStream();
    if (streamHandleRef.current) {
      streamHandleRef.current.close();
      streamHandleRef.current = null;
    }
    cancelStream();
  }, [cancelStream]);

  useEffect(() => {
    return () => {
      closeStream();
      if (streamHandleRef.current) streamHandleRef.current.close();
    };
  }, []);

  const sendTextAndStream = useCallback((text, type = 'text') => {
    handleCancelStream();
    if (useChatStore.getState().isStreaming) handleCancelStream();

    let convId = activeConversationId;
    if (!convId) convId = createConversation();

    addMessage(convId, { role: 'user', content: text, type });
    setLoading(true);

    const streamId = Date.now().toString();
    streamHandleRef.current = streamMessage(
      text,
      convId,
      (token) => {
        if (useChatStore.getState().isLoading) startStreaming(streamId);
        appendToken(token, streamId);
      },
      () => {
        finalizeStream(streamId);
        streamHandleRef.current = null;
      },
      (err) => {
        console.error('Stream error:', err);
        cancelStream();
        setLoading(false);
        addMessage(convId, {
          role: 'assistant',
          content: `Sorry, something went wrong: ${err.message || 'Unknown error'}. Please try again.`,
          type: 'text',
          isError: true,
        });
        streamHandleRef.current = null;
      }
    );
  }, [activeConversationId, createConversation, addMessage, setLoading, startStreaming, appendToken, finalizeStream, cancelStream, handleCancelStream]);

  const handleVoiceToggle = useCallback(() => {
    if (isLoading || isStreaming) return;
    if (isRecording) stopRecording();
    else startRecording();
  }, [isRecording, isLoading, isStreaming, startRecording, stopRecording]);

  useEffect(() => {
    if (!audioBlob || isRecording) return;
    const processAudio = async () => {
      setTranscribing(true);
      try {
        const result = await transcribeAudio(audioBlob);
        const text = (result.text || '').trim();
        if (!text) {
          setTranscribing(false);
          toast('No speech detected. Please speak clearly.', { duration: 3000 });
          return;
        }

        setTranscribedText(text);
        setTranscribing(false);
        sendTextAndStream(text, 'voice');
      } catch (err) {
        console.error('Transcription error:', err);
        setTranscribing(false);
        toast.error('Couldn\'t transcribe audio. Please try again.');
      } finally {
        /* Always reset voice state so the text input is re-enabled */
        setTimeout(() => resetVoice(), 400);
      }
    };
    processAudio();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [audioBlob, isRecording]);

  const handleTextSend = useCallback((text) => sendTextAndStream(text, 'text'), [sendTextAndStream]);
  const handleQueryClick = useCallback((text) => sendTextAndStream(text, 'text'), [sendTextAndStream]);

  const appStatus = useAppStatus();
  /* 'error' is intentionally excluded — a voice error must not freeze the text input */
  const isBusy = ['recording', 'transcribing', 'streaming', 'loading'].includes(appStatus);

  const handleRetry = useCallback((messageId, mode = 'retry') => {
    if (!activeConversationId) return;
    if (useChatStore.getState().isStreaming) handleCancelStream();

    const store = useChatStore.getState();
    const conv = store.conversations[activeConversationId];
    if (!conv) return;

    const targetMsg = conv.messages.find(m => m.id === messageId);
    if (!targetMsg) return;

    const prevUserMsg = store.getPreviousUserMessage(activeConversationId, messageId);
    if (!prevUserMsg) return;

    handleCancelStream();

    if (mode === 'retry') {
      removeMessage(activeConversationId, messageId);
    } else if (mode === 'regenerate') {
      store.markMessageStale(activeConversationId, messageId);
    }

    sendTextAndStream(prevUserMsg.content, prevUserMsg.type);
  }, [activeConversationId, removeMessage, sendTextAndStream, handleCancelStream]);

  const handleEditMessage = useCallback((messageId, newContent) => {
    if (!activeConversationId) return;
    const store = useChatStore.getState();
    
    handleCancelStream();
    
    // 1. Update the message content in place
    store.updateMessage(activeConversationId, messageId, newContent);
    
    // 2. Truncate history after this message (remove all subsequent messages)
    store.truncateHistory(activeConversationId, messageId);
    
    // 3. Resend without adding a duplicate message bubble
    setLoading(true);
    const streamId = Date.now().toString();
    
    // Get updated history for the stream
    const updatedConv = useChatStore.getState().conversations[activeConversationId];
    const history = updatedConv?.messages || [];

    streamHandleRef.current = streamMessage(
      newContent,
      activeConversationId,
      (token) => {
        if (useChatStore.getState().isLoading) startStreaming(streamId);
        appendToken(token, streamId);
      },
      () => {
        finalizeStream(streamId);
        streamHandleRef.current = null;
      },
      (err) => {
        console.error('Stream error:', err);
        cancelStream();
        setLoading(false);
        addMessage(activeConversationId, {
          role: 'assistant',
          content: `Sorry, something went wrong: ${err.message || 'Unknown error'}. Please try again.`,
          type: 'text',
          isError: true,
        });
        streamHandleRef.current = null;
      },
      history.slice(0, -1) // Send history excluding the message we just updated as 'current query'
    );
  }, [activeConversationId, addMessage, setLoading, startStreaming, appendToken, finalizeStream, cancelStream, handleCancelStream]);

  const [chatExpanded, setChatExpanded] = React.useState(false);

  return (
    <div className="flex flex-col flex-1 h-full overflow-hidden bg-[var(--db-bg-base)]" id="chat-window">
      {/* ── DASHBOARD AREA (Primary) ── */}
      <div className="flex-1 overflow-y-auto px-6 py-4 scroll-smooth hide-scrollbar relative">
        {currentDashboardData ? (
          <Dashboard data={currentDashboardData} />
        ) : (
          <div className="flex items-center justify-center h-full opacity-50">
            <div className="text-center">
              <div className="transcribing-loader w-12 h-12 mx-auto mb-4">
                <div className="orbit-ring"></div>
                <div className="orbit-dot"></div>
              </div>
              <p className="text-gold-gradient text-sm font-medium">Initializing Dashboard...</p>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* ── CHAT OVERLAY (Optional/Collapsible) ── */}
      {hasMessages && (
        <div className={`absolute bottom-[100px] left-1/2 -translate-x-1/2 w-full max-w-[800px] px-4 transition-all duration-300 z-20 ${chatExpanded ? 'h-[400px]' : 'h-auto'}`}>
          <div className="glass-dark border border-[var(--db-border)] rounded-2xl shadow-2xl overflow-hidden flex flex-col">
            <div className="px-4 py-2 flex items-center justify-between border-bottom border-[var(--db-border)] bg-[var(--db-bg-card)]">
               <span className="text-[10px] font-bold uppercase tracking-widest text-[var(--db-text-muted)]">Insights & Conversation</span>
               <button onClick={() => setChatExpanded(!chatExpanded)} className="text-[var(--db-text-muted)] hover:text-white transition-colors">
                 {chatExpanded ? '▼' : '▲'}
               </button>
            </div>
            <div className={`overflow-y-auto p-4 space-y-4 ${chatExpanded ? 'flex-1' : 'max-h-[120px]'}`}>
              {messages.filter(m => !m.content.includes('```dashboard')).map((msg) => (
                <MessageBubble
                  key={msg.id}
                  message={msg}
                  onRetry={msg.isError ? () => handleRetry(msg.id, 'retry') : null}
                  onEdit={msg.role === 'user' ? handleEditMessage : null}
                />
              ))}
              {isStreaming && streamingText && !streamingText.includes('```dashboard') && (
                <MessageBubble
                  message={{ id: 'streaming', role: 'assistant', content: streamingText, type: 'text', createdAt: Date.now() }}
                  isStreaming
                />
              )}
              {isLoading && !isStreaming && <TypingIndicator />}
            </div>
          </div>
        </div>
      )}

      {/* ── INPUT AREA (Fixed at Bottom) ── */}
      <div
        className="
          flex-shrink-0 bg-[var(--db-bg-base)] flex flex-col items-center gap-2 w-full z-30
          px-4 pb-[calc(16px+env(safe-area-inset-bottom,0px))] pt-2
          border-t border-[var(--db-border)]
        "
        id="chat-input-area"
      >
        <div
          className={`
            chat-input-row max-w-[760px] w-full flex items-center gap-2 relative
            bg-[var(--db-bg-card)] border border-[var(--db-border)] rounded-full
            px-3 py-2 shadow-2xl transition-all duration-150
            ${isRecording ? "recording-pill ring-2 ring-red-500/50" : ""}
          `}
        >
          <VoiceButton onRecordComplete={handleVoiceToggle} disabled={isLoading || isStreaming} />
          <TextInput onSend={handleTextSend} disabled={isBusy} placeholder="Ask about production, forecasts, or alerts..." />
        </div>
      </div>
    </div>
  );
}
