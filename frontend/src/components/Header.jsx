import React from 'react';
import { HiOutlinePlus, HiOutlineMenuAlt2, HiOutlineLogout } from 'react-icons/hi';
import ThemeToggle from './ThemeToggle';
import useAuthStore from '../store/useAuthStore';
import useChatStore from '../store/useChatStore';
import { toast } from 'react-hot-toast';

export default function Header({ onToggleSidebar, onCloseSidebar }) {
  /* ── Store selectors ── */
  const newChat              = useChatStore((s) => s.newChat);
  const activeConversationId = useChatStore((s) => s.activeConversationId);
  const conversations        = useChatStore((s) => s.conversations);
  const logout               = useAuthStore((s) => s.logout);

  /* Start a new chat, notify the user, and close the sidebar if open */
  const handleNewChat = () => {
    newChat();
    toast.success('Started new chat', { id: 'new-chat' });
    onCloseSidebar?.(); // close sidebar whenever a new chat is started from the header
  };

  /*
   * isWelcomeScreen: true when there is no active conversation with messages.
   * Controls which header elements are shown (logo + new-chat button are hidden
   * on the welcome screen to keep the layout clean).
   */
  const isWelcomeScreen =
    !activeConversationId || !conversations[activeConversationId]?.messages?.length;

  return (
    /*
     * Glass header bar.
     * Positioned absolute within the main-content div (which already has ml-[52px]).
     * The ::after pseudo-element creates a soft gradient separator instead of a hard border.
     */
    <div
      className="
        flex justify-between items-center px-4 sm:px-6 py-4 min-h-[64px]
        absolute top-0 left-0 right-0 z-50
        glass-header transition-colors duration-250
        after:content-[''] after:absolute after:bottom-0
        after:left-0 after:right-0 after:h-px
        after:bg-gradient-to-r after:from-transparent after:via-[var(--brd2)] after:to-transparent
      "
      id="app-header"
    >
      {/* ── Left side: sidebar toggle + logo (when in chat) ── */}
      <div className="flex items-center gap-3">
        {/* Hamburger / menu button — opens the conversation sidebar */}
        <button
          id="sidebar-toggle-btn"
          className="
            w-9 h-9 rounded-xl flex items-center justify-center
            bg-[var(--brd)] text-[var(--gold-acc)]
            hover:bg-[var(--brd2)] hover:scale-105 active:scale-95
            transition-all duration-200
            shadow-lg
          "
          onClick={onToggleSidebar}
          aria-label="Toggle sidebar"
          title="Menu"
        >
          <HiOutlineMenuAlt2 size={20} />
        </button>

        {/* Logo + app name — only shown when inside an active chat */}
        {!isWelcomeScreen && (
          <div className="flex items-center gap-2 animate-fade-in">
            {/* Automotive steering wheel logo mark */}
            <svg width="24" height="24" viewBox="0 0 40 40" fill="none">
              <defs>
                <linearGradient id="hdr-logo" x1="0" y1="0" x2="40" y2="40">
                  <stop offset="0%" stopColor="#D4AF37" />
                  <stop offset="100%" stopColor="#F5E6B3" />
                </linearGradient>
              </defs>
              {/* Outer rim */}
              <circle cx="20" cy="20" r="16" stroke="url(#hdr-logo)" strokeWidth="2" fill="none" />
              {/* Center hub */}
              <circle cx="20" cy="20" r="3.5" fill="url(#hdr-logo)" opacity="0.9" />
              {/* Top spoke — 12 o'clock */}
              <line x1="20" y1="7" x2="20" y2="16.5" stroke="url(#hdr-logo)" strokeWidth="2.5" strokeLinecap="round" />
              {/* Bottom-right spoke — 4 o'clock */}
              <line x1="23" y1="22" x2="32" y2="27" stroke="url(#hdr-logo)" strokeWidth="2.5" strokeLinecap="round" />
              {/* Bottom-left spoke — 8 o'clock */}
              <line x1="17" y1="22" x2="8" y2="27" stroke="url(#hdr-logo)" strokeWidth="2.5" strokeLinecap="round" />
            </svg>
            <span className="font-semibold text-sm text-[var(--txt)]">
              VOXA
              {/* Subtitle hidden on small screens to save space */}
              <span className="hidden sm:inline text-xs font-normal">
                {' '}: Voice Enabled AI Assistant
              </span>
            </span>
          </div>
        )}
      </div>

      {/* ── Right side: theme toggle + new-chat button ── */}
      <div className="flex items-center gap-2 bg-[var(--brd)] px-2 py-1.5 rounded-xl">
        {/* Slide toggle that switches between dark and light theme */}
        <ThemeToggle />

        {/* New chat button — only shown when inside an active chat */}
        {!isWelcomeScreen && (
          <button
            id="new-chat-btn"
            className="
              w-9 h-9 rounded-xl flex items-center justify-center
              bg-[var(--brd)] text-[var(--txt)]
              hover:bg-[var(--brd2)] hover:scale-105 active:scale-95
              transition-all duration-200 animate-fade-in
            "
            onClick={handleNewChat}
            aria-label="New chat"
            title="New chat"
          >
            <HiOutlinePlus size={20} />
          </button>
        )}

        {/* Logout button */}
        <button
          id="logout-btn"
          className="
            w-9 h-9 rounded-xl flex items-center justify-center
            bg-[var(--brd)] text-[var(--txt)]
            hover:bg-red-500/20 hover:text-red-400 hover:scale-105 active:scale-95
            transition-all duration-200
          "
          onClick={() => {
            logout();
            toast.success('Logged out');
          }}
          aria-label="Logout"
          title="Logout"
        >
          <HiOutlineLogout size={20} />
        </button>
      </div>
    </div>
  );
}
