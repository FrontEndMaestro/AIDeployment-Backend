import React, { useRef, useEffect } from 'react';
import { Send, Sparkles, ChevronDown, ChevronRight } from 'lucide-react';

interface Message {
  role: 'user' | 'ai';
  content: string;
}

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
}) => {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [logsExpanded, setLogsExpanded] = React.useState(false);
  const [instructionsExpanded, setInstructionsExpanded] = React.useState(false);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey && input.trim()) {
      e.preventDefault();
      onSend();
    }
  };

  return (
    <div className="h-full flex flex-col bg-gray-800 border border-gray-700 rounded-lg">
      {/* Header */}
      <div className="flex-shrink-0 px-4 py-3 border-b border-gray-700 bg-gray-800">
        <div className="flex items-center gap-2">
          <Sparkles size={18} className="text-purple-400" />
          <h3 className="text-sm font-semibold text-white">AI Assistant</h3>
        </div>
        <p className="text-xs text-gray-400 mt-1">Docker deployment help</p>
      </div>

      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto custom-scroll px-3 py-3 space-y-3">
        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={`flex gap-2 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[85%] rounded-lg px-3 py-2 ${
                msg.role === 'user'
                  ? 'bg-cyan-500/10 text-cyan-100 border border-cyan-500/30'
                  : 'bg-gray-900 text-gray-200 border border-gray-700'
              }`}
            >
              <div className="flex items-center gap-2 mb-1">
                {msg.role === 'ai' && (
                  <Sparkles size={12} className="text-purple-400 flex-shrink-0" />
                )}
                <span className="text-[10px] uppercase font-semibold text-gray-400">
                  {msg.role === 'user' ? 'You' : 'Llama 3.1'}
                </span>
              </div>
              <pre className="text-sm whitespace-pre-wrap font-sans leading-relaxed">
                {msg.content}
              </pre>
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="flex-shrink-0 border-t border-gray-700 bg-gray-800">
        {/* Expandable Logs Section */}
        {onLogInputChange && (
          <div className="border-b border-gray-700">
            <button
              onClick={() => setLogsExpanded(!logsExpanded)}
              className="w-full px-4 py-2 flex items-center justify-between hover:bg-gray-700/50 transition-colors"
            >
              <span className="text-xs text-gray-300">Build/Run Logs (optional)</span>
              {logsExpanded ? (
                <ChevronDown size={14} className="text-gray-400" />
              ) : (
                <ChevronRight size={14} className="text-gray-400" />
              )}
            </button>
            {logsExpanded && (
              <div className="px-3 pb-3">
                <textarea
                  value={logInput}
                  onChange={(e) => onLogInputChange(e.target.value)}
                  className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 
                           focus:border-cyan-500 focus:outline-none resize-none"
                  placeholder="Paste error logs here..."
                  rows={3}
                />
              </div>
            )}
          </div>
        )}

        {/* Expandable Instructions Section */}
        {onInstructionsChange && (
          <div className="border-b border-gray-700">
            <button
              onClick={() => setInstructionsExpanded(!instructionsExpanded)}
              className="w-full px-4 py-2 flex items-center justify-between hover:bg-gray-700/50 transition-colors"
            >
              <span className="text-xs text-gray-300">Deploy Instructions (optional)</span>
              {instructionsExpanded ? (
                <ChevronDown size={14} className="text-gray-400" />
              ) : (
                <ChevronRight size={14} className="text-gray-400" />
              )}
            </button>
            {instructionsExpanded && (
              <div className="px-3 pb-3">
                <input
                  type="text"
                  value={instructions}
                  onChange={(e) => onInstructionsChange(e.target.value)}
                  className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 
                           focus:border-cyan-500 focus:outline-none"
                  placeholder="e.g., 'Use multi-stage build'"
                />
              </div>
            )}
          </div>
        )}

        {/* Main Input */}
        <div className="p-3">
          <div className="flex gap-2">
            <textarea
              value={input}
              onChange={(e) => onInputChange(e.target.value)}
              onKeyDown={handleKeyPress}
              className="flex-1 bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white 
                       focus:border-cyan-500 focus:outline-none resize-none"
              placeholder="Ask AI to generate or validate Dockerfiles..."
              rows={2}
              disabled={sending}
            />
            <button
              onClick={onSend}
              disabled={sending || !input.trim()}
              className="flex-shrink-0 w-10 h-full bg-cyan-600 hover:bg-cyan-500 disabled:bg-gray-700 
                       disabled:cursor-not-allowed rounded-lg flex items-center justify-center transition-colors"
              title="Send message"
            >
              {sending ? (
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              ) : (
                <Send size={16} className="text-white" />
              )}
            </button>
          </div>
          <p className="text-[10px] text-gray-500 mt-2">
            Press Enter to send, Shift+Enter for new line
          </p>
        </div>
      </div>
    </div>
  );
};
