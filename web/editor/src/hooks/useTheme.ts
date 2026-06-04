import { useState, useEffect } from 'react';

type Theme = 'light' | 'dark' | 'system';

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => {
    const saved = localStorage.getItem('theme');
    return (saved as Theme) || 'system';
  });
  
  const [isDark, setIsDark] = useState(false);
  
  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    
    const updateTheme = () => {
      let dark = false;
      
      if (theme === 'system') {
        dark = mediaQuery.matches;
      } else {
        dark = theme === 'dark';
      }
      
      setIsDark(dark);
      document.documentElement.classList.toggle('dark', dark);
    };
    
    updateTheme();
    
    mediaQuery.addEventListener('change', updateTheme);
    return () => mediaQuery.removeEventListener('change', updateTheme);
  }, [theme]);
  
  useEffect(() => {
    localStorage.setItem('theme', theme);
  }, [theme]);
  
  return {
    theme,
    setTheme,
    isDark,
  };
}
