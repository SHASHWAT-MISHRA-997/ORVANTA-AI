'use client';

import React from 'react';
import { useTheme } from './ThemeProvider';
import { Moon, Sun } from 'lucide-react';
import { motion } from 'framer-motion';

export default function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();

  return (
    <button
      onClick={toggleTheme}
      className={`relative inline-flex h-9 w-9 items-center justify-center rounded-xl p-0 transition-all duration-300 focus:outline-none ${
        theme === 'dark' 
          ? 'bg-slate-800 border border-slate-700 shadow-[0_0_15px_rgba(99,102,241,0.2)]' 
          : 'bg-white border border-slate-200 shadow-sm'
      } hover:scale-110 active:scale-95`}
      aria-label="Toggle theme"
    >
      <motion.div
        initial={false}
        animate={{
          rotate: theme === 'dark' ? 360 : 0,
          scale: 1,
        }}
        transition={{
          type: 'spring',
          stiffness: 260,
          damping: 20,
        }}
        className="flex items-center justify-center"
      >
        {theme === 'dark' ? (
          <Moon size={18} className="text-indigo-400 fill-indigo-400/20" />
        ) : (
          <Sun size={18} className="text-amber-500 fill-amber-500/20" />
        )}
      </motion.div>
    </button>
  );
}
