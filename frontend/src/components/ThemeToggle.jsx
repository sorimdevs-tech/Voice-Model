import React from 'react';
import { HiSun, HiMoon } from 'react-icons/hi';
import useThemeStore from '../store/useThemeStore';

export default function ThemeToggle() {
  const theme = useThemeStore((s) => s.theme);
  const toggleTheme = useThemeStore((s) => s.toggleTheme);
  const isDark = theme === 'dark';

  return (
    <button
      className={`
        relative flex items-center bg-white/[0.05] border border-white/[0.08]
        rounded-[20px] p-0.5 w-14 h-8 cursor-pointer outline-none
        transition-all duration-250 hover:border-gold/30
      `}
      onClick={toggleTheme}
      aria-label="Toggle theme"
      title="Toggle theme"
    >
      {/* Sliding knob */}
      <div
        className={`
          absolute top-0.5 bottom-0.5 left-0.5 w-[26px]
          bg-white/[0.12] rounded-full shadow-[0_2px_8px_rgba(0,0,0,0.2)]
          transition-transform duration-250
          ${isDark ? 'translate-x-6' : 'translate-x-0'}
        `}
      />

      {/* Sun icon */}
      <div className={`flex-1 flex items-center justify-center z-[1] transition-opacity duration-250 ${isDark ? 'opacity-40' : 'opacity-100 text-gold'}`}>
        <HiSun size={16} />
      </div>
      {/* Moon icon */}
      <div className={`flex-1 flex items-center justify-center z-[1] transition-opacity duration-250 ${isDark ? 'opacity-100 text-gold' : 'opacity-40'}`}>
        <HiMoon size={16} />
      </div>
    </button>
  );
}