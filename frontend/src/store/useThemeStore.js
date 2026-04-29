import { create } from 'zustand';

/**
 * Theme priority:
 * 1. localStorage (user's explicit choice)
 * 2. System preference (prefers-color-scheme)
 * 3. Default: dark
 */
function getSystemPreference() {
  if (typeof window !== 'undefined' && window.matchMedia) {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  return 'dark';
}

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
}

const useThemeStore = create((set, get) => ({
  theme: 'dark',

  toggleTheme: () => {
    const newTheme = get().theme === 'dark' ? 'light' : 'dark';
    get().setTheme(newTheme);
  },

  setTheme: (theme) => {
    applyTheme(theme);
    localStorage.setItem('voice-ai-theme', theme);
    set({ theme });
  },

  loadTheme: () => {
    const saved = localStorage.getItem('voice-ai-theme');
    const systemTheme = getSystemPreference();
    const theme = saved || systemTheme;
    
    applyTheme(theme);
    set({ theme });

    // Listen for system changes if no manual preference is saved
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = (e) => {
      if (!localStorage.getItem('voice-ai-theme')) {
        const newTheme = e.matches ? 'dark' : 'light';
        get().setTheme(newTheme);
      }
    };
    
    mediaQuery.addEventListener('change', handler);
    return () => mediaQuery.removeEventListener('change', handler);
  },
}));

export default useThemeStore;
