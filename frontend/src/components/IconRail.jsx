import React from 'react';
import { HiOutlinePlus, HiOutlineChatAlt2, HiOutlineSearch } from 'react-icons/hi';
import useAuthStore from '../store/useAuthStore';
import useChatStore from '../store/useChatStore';
import UserAvatar from './UserAvatar';

/*
 * IconRail — the always-visible narrow icon strip on the left edge.
 * Modelled after the collapsed sidebar style (icon-only navigation).
 * Width: 52px, always dark, sits at z-[80] below the full sidebar (z-[100]).
 * Clicking the chat/list icon or the logo opens the full sidebar drawer.
 */
export default function IconRail({ onToggleSidebar, onNewChat }) {
  const user    = useAuthStore((s) => s.user);
  const newChat = useChatStore((s) => s.newChat);

  /* Shared styles for icon buttons */
  const iconBtn = {
    width:           '36px',
    height:          '36px',
    borderRadius:    '10px',
    display:         'flex',
    alignItems:      'center',
    justifyContent:  'center',
    cursor:          'pointer',
    background:      'transparent',
    border:          'none',
    color:           'var(--sb-txt3)',
    transition:      'background 0.15s, color 0.15s',
    flexShrink:      0,
  };

  const hoverIn  = (e) => {
    e.currentTarget.style.background = 'var(--sb-hover)';
    e.currentTarget.style.color      = '#D4AF37';
  };
  const hoverOut = (e) => {
    e.currentTarget.style.background = 'transparent';
    e.currentTarget.style.color      = 'var(--sb-txt3)';
  };

  return (
    <div
      id="icon-rail"
      className="fixed left-0 top-0 bottom-0 z-[80] flex flex-col items-center py-3 gap-1 transition-colors duration-250"
      style={{
        width:       '52px',
        background:  'var(--sb-bg)',
        borderRight: '1px solid var(--sb-brd)',
      }}
    >
      {/* ── Top: VOXA logo (opens sidebar) ── */}
      <button
        style={iconBtn}
        onMouseEnter={hoverIn}
        onMouseLeave={hoverOut}
        onClick={onToggleSidebar}
        aria-label="Open conversations"
        title="Open conversations"
      >
        {/* Compact VOXA mark */}
        <svg width="20" height="20" viewBox="0 0 40 40" fill="none">
          <defs>
            <linearGradient id="rail-logo" x1="0" y1="0" x2="40" y2="40">
              <stop offset="0%" stopColor="#D4AF37" />
              <stop offset="100%" stopColor="#F5E6B3" />
            </linearGradient>
          </defs>
          <circle cx="20" cy="20" r="18" stroke="url(#rail-logo)" strokeWidth="1.5" fill="none" opacity="0.5" />
          <path d="M14 26 C14 18,20 13,20 13 C20 13,26 18,26 26"
            stroke="url(#rail-logo)" strokeWidth="2" strokeLinecap="round" fill="none" />
          <circle cx="20" cy="14" r="2.5" fill="url(#rail-logo)" />
        </svg>
      </button>

      {/* Thin divider below logo */}
      <div style={{ width: '24px', height: '1px', background: 'var(--sb-brd)', margin: '4px 0' }} />

      {/* ── New Chat button ── */}
      <button
        style={iconBtn}
        onMouseEnter={hoverIn}
        onMouseLeave={hoverOut}
        onClick={onNewChat}
        aria-label="New chat"
        title="New chat"
      >
        <HiOutlinePlus size={19} />
      </button>

      {/* ── Open conversation list ── */}
      <button
        style={iconBtn}
        onMouseEnter={hoverIn}
        onMouseLeave={hoverOut}
        onClick={onToggleSidebar}
        aria-label="Conversations"
        title="Conversations"
      >
        <HiOutlineChatAlt2 size={19} />
      </button>

      {/* ── Search (placeholder — extend later) ── */}
      <button
        style={iconBtn}
        onMouseEnter={hoverIn}
        onMouseLeave={hoverOut}
        onClick={onToggleSidebar}
        aria-label="Search"
        title="Search conversations"
      >
        <HiOutlineSearch size={18} />
      </button>

      {/* ── Spacer pushes avatar to the bottom ── */}
      <div style={{ flex: 1 }} />

      {/* ── User avatar ── */}
      <div
        title={user?.name || 'User'}
        className="mb-1"
      >
        <UserAvatar 
          className="w-8 h-8 rounded-full flex items-center justify-center font-semibold text-[0.75rem] overflow-hidden"
          style={{ background: 'linear-gradient(135deg,#D4AF37,#B8962E)', color: '#0B0B0F' }}
        />
      </div>
    </div>
  );
}
