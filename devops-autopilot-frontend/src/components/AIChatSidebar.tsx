import React, { useRef, useEffect } from 'react';
import { Send, Sparkles, ChevronDown, ChevronRight, Bot, User, ChevronUp } from 'lucide-react';

interface Message {
  role: 'user' | 'ai';
  content: string;
}

const MODELS = [
  { id: 'gemini-2.5-flash',         label: 'Gemini 2.5 Flash',         tag: 'Fast',     color: '#22d3ee' },
  { id: 'gemini-2.5-pro',           label: 'Gemini 2.5 Pro',           tag: 'Powerful', color: '#a78bfa' },
  { id: 'gemini-2.0-flash',         label: 'Gemini 2.0 Flash',         tag: 'Stable',   color: '#34d399' },
  { id: 'gemini-1.5-pro',           label: 'Gemini 1.5 Pro',           tag: 'Legacy',   color: '#fb923c' },
];

interface AIChatSidebarProps {
  messages: Message[];
  input: string;
  onInputChange: (value: string) => void;
  onSend: () => void;
  sending: boolean;
  logInput?: string;
  onLogInputChange?: (value: string) => void;
  instructions?: string;
  onInstructionsChange?: (value: string) => void;
  selectedModel?: string;
  onModelChange?: (model: string) => void;
}

export const AIChatSidebar: React.FC<AIChatSidebarProps> = ({
  messages,
  input,
  onInputChange,
  onSend,
  sending,
  logInput = '',
  onLogInputChange,
  instructions = '',
  onInstructionsChange,
  selectedModel = 'gemini-2.5-flash',
  onModelChange,
}) => {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [logsExpanded, setLogsExpanded] = React.useState(false);
  const [instructionsExpanded, setInstructionsExpanded] = React.useState(false);
  const [modelMenuOpen, setModelMenuOpen] = React.useState(false);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey && input.trim()) {
      e.preventDefault();
      onSend();
    }
  };

  const SURFACE = 'rgba(13,17,23,0.9)';
  const BORDER = 'rgba(255,255,255,0.07)';

  const activeModel = MODELS.find(m => m.id === selectedModel) || MODELS[0];

  return (
    <div
      className="flex flex-col rounded-xl overflow-hidden"
      style={{ background: SURFACE, border: `1px solid ${BORDER}`, height: '100%', minHeight: 0, display: 'flex', flexDirection: 'column' }}
    >
      {/* Header */}
      <div
        className="flex-shrink-0 px-4 py-3 flex items-center gap-2.5"
        style={{ borderBottom: `1px solid ${BORDER}`, background: 'rgba(22,27,34,0.6)' }}
      >
        <div
          className="w-7 h-7 rounded-lg flex items-center justify-center"
          style={{ background: 'rgba(168,85,247,0.15)', border: '1px solid rgba(168,85,247,0.25)' }}
        >
          <Sparkles size={14} className="text-purple-400" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-white leading-tight">AI Assistant</p>
          <p className="text-[10px] text-gray-600 leading-tight truncate">Docker &amp; Deploy Expert</p>
        </div>

        {/* Model selector */}
        <div className="relative">
          <button
            onClick={() => setModelMenuOpen(v => !v)}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-widest transition-all hover:bg-white/10"
            style={{
              background: 'rgba(255,255,255,0.05)',
              border: `1px solid ${activeModel.color}40`,
              color: activeModel.color,
            }}
          >
            <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: activeModel.color }} />
            {activeModel.tag}
            {modelMenuOpen ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
          </button>

          {modelMenuOpen && (
            <div
              className="absolute right-0 top-full mt-2 z-50 rounded-xl overflow-hidden shadow-2xl"
              style={{ background: 'rgba(13,17,23,0.98)', border: `1px solid ${BORDER}`, minWidth: '200px' }}
            >
              <p className="px-3 py-2 text-[9px] font-black uppercase tracking-widest text-gray-600 border-b border-white/5">
                Select AI Model
              </p>
              {MODELS.map(model => (
                <button
                  key={model.id}
                  onClick={() => {
                    onModelChange?.(model.id);
                    setModelMenuOpen(false);
                  }}
                  className="w-full px-3 py-2.5 flex items-center gap-3 text-left hover:bg-white/5 transition-colors"
                >
                  <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: model.color }} />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-semibold text-white truncate">{model.label}</p>
                    <p className="text-[9px] text-gray-600 uppercase tracking-widest">{model.tag}</p>
                  </div>
                  {selectedModel === model.id && (
                    <span className="text-[9px] font-black uppercase" style={{ color: model.color }}>Active</span>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>

        <div
          className="flex items-center gap-1 px-2 py-0.5 rounded-full"
          style={{ background: 'rgba(16,185,129,0.1)', border: '1px solid rgba(16,185,129,0.2)' }}
        >
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-[10px] font-semibold text-emerald-400">Ready</span>
        </div>
      </div>

      {/* Messages — this is the ONLY thing that scrolls */}
      <div className="flex-1 overflow-y-auto custom-scroll px-3 py-3 space-y-2.5 min-h-0">
        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={`flex gap-2 animate-fade-in ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            {msg.role === 'ai' && (
              <div
                className="w-6 h-6 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5"
                style={{ background: 'rgba(168,85,247,0.15)', border: '1px solid rgba(168,85,247,0.2)' }}
              >
                <Bot size={12} className="text-purple-400" />
              </div>
            )}
            <div
              className="max-w-[82%] rounded-xl px-3 py-2"
              style={
                msg.role === 'user'
                  ? { background: 'rgba(34,211,238,0.1)', border: '1px solid rgba(34,211,238,0.2)', color: '#cffafe' }
                  : { background: 'rgba(22,27,34,0.8)', border: '1px solid rgba(255,255,255,0.07)', color: '#c9d1d9' }
              }
            >
              <p className="text-[10px] font-semibold uppercase tracking-wider mb-1" style={{ opacity: 0.5 }}>
                {msg.role === 'user' ? 'You' : activeModel.label}
              </p>
              <pre className="text-xs whitespace-pre-wrap font-['JetBrains_Mono',monospace] leading-relaxed">
                {msg.content || <span className="opacity-40 italic">Thinking...</span>}
              </pre>
            </div>
            {msg.role === 'user' && (
              <div
                className="w-6 h-6 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5"
                style={{ background: 'rgba(34,211,238,0.12)', border: '1px solid rgba(34,211,238,0.2)' }}
              >
                <User size={12} className="text-cyan-400" />
              </div>
            )}
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Bottom controls — NEVER scroll, always visible */}
      <div className="flex-shrink-0" style={{ borderTop: `1px solid ${BORDER}` }}>
        {onLogInputChange && (
          <div style={{ borderBottom: `1px solid ${BORDER}` }}>
            <button
              onClick={() => setLogsExpanded(!logsExpanded)}
              className="w-full px-4 py-2 flex items-center justify-between text-xs text-gray-500 hover:text-gray-300 hover:bg-white/[0.02] transition-colors"
            >
              Build / Run logs (optional)
              {logsExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            </button>
            {logsExpanded && (
              <div className="px-3 pb-2.5">
                <textarea
                  value={logInput}
                  onChange={(e) => onLogInputChange(e.target.value)}
                  className="w-full bg-black/30 border border-white/[0.08] rounded-lg px-3 py-2 text-xs text-gray-300 focus:border-cyan-500/50 focus:outline-none resize-none custom-scroll font-mono"
                  placeholder="Paste error logs here..."
                  rows={3}
                />
              </div>
            )}
          </div>
        )}

        {onInstructionsChange && (
          <div style={{ borderBottom: `1px solid ${BORDER}` }}>
            <button
              onClick={() => setInstructionsExpanded(!instructionsExpanded)}
              className="w-full px-4 py-2 flex items-center justify-between text-xs text-gray-500 hover:text-gray-300 hover:bg-white/[0.02] transition-colors"
            >
              Deploy instructions (optional)
              {instructionsExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            </button>
            {instructionsExpanded && (
              <div className="px-3 pb-2.5">
                <input
                  type="text"
                  value={instructions}
                  onChange={(e) => onInstructionsChange(e.target.value)}
                  className="w-full bg-black/30 border border-white/[0.08] rounded-lg px-3 py-2 text-xs text-gray-300 focus:border-cyan-500/50 focus:outline-none font-mono"
                  placeholder="e.g. Use multi-stage build"
                />
              </div>
            )}
          </div>
        )}

        <div className="p-3">
          <div className="flex gap-2">
            <textarea
              value={input}
              onChange={(e) => onInputChange(e.target.value)}
              onKeyDown={handleKeyPress}
              className="flex-1 rounded-xl px-3 py-2 text-sm text-white focus:outline-none resize-none custom-scroll"
              style={{
                background: 'rgba(5,8,16,0.8)',
                border: '1px solid rgba(255,255,255,0.08)',
                transition: 'border-color 0.2s',
              }}
              onFocus={(e) => (e.currentTarget.style.borderColor = 'rgba(34,211,238,0.4)')}
              onBlur={(e) => (e.currentTarget.style.borderColor = 'rgba(255,255,255,0.08)')}
              placeholder="Ask AI to generate or validate Dockerfiles..."
              rows={2}
              disabled={sending}
            />
            <button
              onClick={onSend}
              disabled={sending || !input.trim()}
              className="flex-shrink-0 w-10 rounded-xl flex items-center justify-center transition-all disabled:opacity-30 disabled:cursor-not-allowed"
              style={{
                background:
                  sending || !input.trim()
                    ? 'rgba(255,255,255,0.05)'
                    : 'linear-gradient(135deg, #22d3ee, #3b82f6)',
                boxShadow:
                  sending || !input.trim() ? 'none' : '0 0 16px rgba(34,211,238,0.3)',
              }}
            >
              {sending ? (
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <Send size={15} className="text-white" />
              )}
            </button>
          </div>
          <p className="text-[9px] text-gray-700 mt-1.5 text-center">
            Enter to send · Shift+Enter newline · Model: <span style={{ color: activeModel.color }}>{activeModel.label}</span>
          </p>
        </div>
      </div>
    </div>
  );
};
