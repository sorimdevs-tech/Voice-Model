import React from 'react';
import { HiMicrophone, HiStop } from 'react-icons/hi';
import AudioWaveform from './AudioVisualizer';
import useVoiceStore from '../store/useVoiceStore';

/**
 * Compact voice button for the chat input bar.
 * Shows a small waveform + duration counter when recording.
 */
export default function VoiceButton({ onRecordComplete, disabled = false }) {
  const isRecording = useVoiceStore((s) => s.isRecording);
  const isTranscribing = useVoiceStore((s) => s.isTranscribing);
  const recordingDuration = useVoiceStore((s) => s.recordingDuration);

  const formatDuration = (sec) => {
    const m = Math.floor(sec / 60).toString().padStart(2, '0');
    const s = (sec % 60).toString().padStart(2, '0');
    return `${m}:${s}`;
  };

  const state = isTranscribing ? 'transcribing' : isRecording ? 'recording' : 'idle';

  return (
    <div
      className="flex items-center gap-2 flex-shrink-0 rounded-full transition-all duration-250"
      id="voice-button-container"
    >
      {state === 'transcribing' ? (
        /* Compact orbital loader for chat input bar */
        <div
          className="transcribing-loader w-9 h-9 min-w-[36px] min-h-[36px] flex-shrink-0"
          aria-label="Transcribing audio"
          aria-busy="true"
        >
          <div className="orbit-ring" />
          <div className="orbit-ring-inner" />
          <div className="orbit-dot" />
        </div>
      ) : (
        <button
          id="voice-record-btn"
          className={`
            vb-${state}
            w-9 h-9 min-w-[36px] min-h-[36px] flex-shrink-0
            flex items-center justify-center cursor-pointer text-white
            transition-all duration-200 border-none outline-none
            disabled:opacity-40 disabled:cursor-not-allowed disabled:!transform-none disabled:!animate-none
            ${state === 'idle'
              ? 'bg-gold-gradient shadow-[0_3px_12px_rgba(212,175,55,0.3)] hover:scale-110 active:scale-95'
              : 'bg-red-500 shadow-[0_4px_12px_rgba(239,68,68,0.35)] border-2 border-[var(--surf)] animate-pulse-beat'}
          `}
          style={{ borderRadius: '9999px' }}
          onClick={onRecordComplete}
          disabled={disabled}
          aria-label={isRecording ? 'Stop recording' : 'Start recording'}
          title={isRecording ? 'Stop' : 'Speak'}
        >
          {state === 'recording' ? <HiStop size={18} /> : <HiMicrophone size={20} />}
        </button>
      )}

      {/* Inline waveform + duration when recording */}
      {isRecording && (
        <div className="flex items-center gap-3 animate-fade-in">
          <AudioWaveform width={100} height={24} />
          <span className="text-[0.8125rem] font-bold text-red-400 tabular-nums whitespace-nowrap tracking-wide">
            {formatDuration(recordingDuration)}
          </span>
        </div>
      )}
    </div>
  );
}
