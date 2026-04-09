'use client';

import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  X, Sparkles, Zap, Shield, Globe, 
  FileText, Aperture, Activity, Trash2 
} from 'lucide-react';

interface UpdateItemProps {
  icon: React.ElementType;
  title: string;
  description: string;
  color: string;
}

const UpdateItem = ({ icon: Icon, title, description, color }: UpdateItemProps) => (
  <div style={{ 
    display: 'flex', 
    gap: '16px', 
    padding: '16px', 
    borderRadius: '12px', 
    background: 'rgba(255, 255, 255, 0.05)', 
    border: '1px solid rgba(255, 255, 255, 0.1)',
    transition: 'background 0.2s ease'
  }}>
    <div style={{ 
      flexShrink: 0, 
      height: '40px', 
      width: '40px', 
      borderRadius: '8px', 
      display: 'flex', 
      alignItems: 'center', 
      justifyContent: 'center', 
      backgroundColor: `${color}20`, 
      color 
    }}>
      <Icon size={20} />
    </div>
    <div>
      <h4 style={{ fontSize: '14px', fontWeight: 'bold', color: 'white', marginBottom: '4px', margin: 0 }}>{title}</h4>
      <p style={{ fontSize: '12px', color: '#9ca3af', fontWeight: '500', lineHeight: '1.4', margin: 0 }}>{description}</p>
    </div>
  </div>
);

export default function WhatIsNewModal({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const updates = [
    {
      icon: Zap,
      title: "AI Wargaming Simulation",
      description: "Direct local Ollama/Mistral integration to run 'What-If' geopolitical impact scenarios instantly.",
      color: "#6366f1"
    },
    {
      icon: Aperture,
      title: "Official-Source Mode",
      description: "Default views now show official-source verified records only, with non-official inputs hidden from the main workflows.",
      color: "#f59e0b"
    },
    {
      icon: Globe,
      title: "Enhanced Global Maps",
      description: "Maps now show exact coordinates only when they are stored, so Google Maps links stay accurate.",
      color: "#06b6d4"
    },
    {
      icon: FileText,
      title: "Provenance Timing",
      description: "Event date, source published/seen time, stored time, and ingest time are now shown separately.",
      color: "#10b981"
    },
    {
      icon: Activity,
      title: "CISA Cyber Correlation",
      description: "Live synchronization with the CISA Cyber RSS feed for verified official threat data correlation.",
      color: "#f43f5e"
    },
    {
      icon: Trash2,
      title: "Organization Clearing",
      description: "Workspace cleanup controls now remove only selected operational records; stored official event integrity remains intact.",
      color: "#a855f7"
    }
  ];

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            style={{
              position: 'fixed',
              inset: 0,
              backgroundColor: 'rgba(0, 0, 0, 0.6)',
              backdropFilter: 'blur(4px)',
              zIndex: 9999,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '16px'
            }}
          >
            {/* Modal */}
            <motion.div
              initial={{ scale: 0.9, opacity: 0, y: 20 }}
              animate={{ scale: 1, opacity: 1, y: 0 }}
              exit={{ scale: 0.9, opacity: 0, y: 20 }}
              onClick={(e) => e.stopPropagation()}
              style={{
                position: 'relative',
                width: '100%',
                maxWidth: '512px',
                backgroundColor: '#0f172a',
                border: '1px solid rgba(255, 255, 255, 0.2)',
                borderRadius: '24px',
                boxShadow: '0 0 50px -12px rgba(99, 102, 241, 0.4)',
                overflow: 'hidden'
              }}
            >
              {/* Header Gradient */}
              <div style={{
                position: 'absolute',
                top: 0,
                left: 0,
                right: 0,
                height: '128px',
                background: 'linear-gradient(to bottom, rgba(99, 102, 241, 0.2), transparent)',
                pointerEvents: 'none'
              }} />
              
              <div style={{ position: 'relative', padding: '32px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '24px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <div style={{ 
                      height: '40px', 
                      width: '40px', 
                      backgroundColor: '#6366f1', 
                      borderRadius: '12px', 
                      display: 'flex', 
                      alignItems: 'center', 
                      justifyContent: 'center',
                      boxShadow: '0 4px 12px rgba(99, 102, 241, 0.2)' 
                    }}>
                      <Sparkles style={{ color: 'white' }} size={24} />
                    </div>
                    <div>
                      <h2 style={{ fontSize: '24px', fontWeight: '900', color: 'white', margin: 0, letterSpacing: '-0.025em' }}>Intelligence Portfolio</h2>
                      <p style={{ fontSize: '11px', color: '#818cf8', fontWeight: 'bold', textTransform: 'uppercase', letterSpacing: '0.1em', margin: 0 }}>Official-Source Provenance Mode</p>
                    </div>
                  </div>
                  <button 
                    onClick={onClose}
                    style={{ 
                      height: '32px', 
                      width: '32px', 
                      borderRadius: '50%', 
                      display: 'flex', 
                      alignItems: 'center', 
                      justifyContent: 'center', 
                      background: 'rgba(255, 255, 255, 0.05)', 
                      color: '#9ca3af', 
                      border: 'none',
                      cursor: 'pointer'
                    }}
                  >
                    <X size={18} />
                  </button>
                </div>

                <div className="custom-scrollbar" style={{ 
                  display: 'flex', 
                  flexDirection: 'column', 
                  gap: '12px', 
                  maxHeight: '60vh', 
                  overflowY: 'auto', 
                  paddingRight: '8px' 
                }}>
                  {updates.map((update, i) => (
                    <motion.div
                      key={update.title}
                      initial={{ opacity: 0, x: -20 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: i * 0.05 }}
                    >
                      <UpdateItem {...update} />
                    </motion.div>
                  ))}
                </div>

                <button 
                  onClick={() => {
                    onClose();
                    window.location.hash = 'explore';
                  }}
                  style={{ 
                    width: '100%', 
                    marginTop: '32px', 
                    padding: '16px', 
                    backgroundColor: '#6366f1', 
                    color: 'white', 
                    fontWeight: 'bold', 
                    borderRadius: '16px', 
                    border: 'none',
                    boxShadow: '0 4px 12px rgba(99, 102, 241, 0.2)',
                    cursor: 'pointer'
                  }}
                >
                  Confirm Operational Status
                </button>
              </div>
            </motion.div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
