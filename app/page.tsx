'use client';

import { useChat } from '@ai-sdk/react';
import { DefaultChatTransport } from 'ai';
import { useState } from 'react';

const MODELS = [
  'anthropic/claude-opus-4.7',
  'anthropic/claude-sonnet-4.6',
];

export default function Home() {
  const [model, setModel] = useState(MODELS[0]);
  const [input, setInput] = useState('');

  const { messages, sendMessage, status, error } = useChat({
    transport: new DefaultChatTransport({ api: '/api/chat' }),
  });

  const isStreaming = status === 'streaming' || status === 'submitted';

  return (
    <main className="mx-auto flex h-dvh max-w-3xl flex-col gap-4 p-4">
      <header className="flex items-center justify-between border-b border-black/10 pb-3 dark:border-white/10">
        <h1 className="text-lg font-semibold">TokenRouter Agent</h1>
        <select
          value={model}
          onChange={(e) => setModel(e.target.value)}
          className="rounded-md border border-black/10 bg-transparent px-2 py-1 text-sm dark:border-white/10"
        >
          {MODELS.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      </header>

      <div className="flex-1 space-y-4 overflow-y-auto">
        {messages.length === 0 && (
          <div className="text-sm opacity-60">
            Try: <em>&ldquo;What time is it?&rdquo;</em> or{' '}
            <em>&ldquo;Calculate (47 * 13) + 9&rdquo;</em>
          </div>
        )}

        {messages.map((m) => (
          <div key={m.id} className="space-y-2">
            <div className="text-xs uppercase tracking-wide opacity-50">{m.role}</div>
            {m.parts.map((part, i) => {
              if (part.type === 'text') {
                return (
                  <div key={i} className="whitespace-pre-wrap text-sm leading-relaxed">
                    {part.text}
                  </div>
                );
              }
              if (part.type.startsWith('tool-')) {
                const toolPart = part as {
                  type: string;
                  state?: string;
                  input?: unknown;
                  output?: unknown;
                };
                return (
                  <div
                    key={i}
                    className="rounded-md border border-black/10 bg-black/[0.03] p-2 text-xs dark:border-white/10 dark:bg-white/[0.03]"
                  >
                    <div className="font-mono opacity-70">
                      🔧 {part.type.replace('tool-', '')}{' '}
                      {toolPart.state ? `· ${toolPart.state}` : ''}
                    </div>
                    {toolPart.input != null && (
                      <pre className="mt-1 overflow-x-auto opacity-80">
                        {JSON.stringify(toolPart.input, null, 2)}
                      </pre>
                    )}
                    {toolPart.output != null && (
                      <pre className="mt-1 overflow-x-auto opacity-80">
                        {JSON.stringify(toolPart.output, null, 2)}
                      </pre>
                    )}
                  </div>
                );
              }
              return null;
            })}
          </div>
        ))}

        {error && (
          <div className="rounded-md border border-red-500/40 bg-red-500/10 p-2 text-sm text-red-600 dark:text-red-400">
            {error.message}
          </div>
        )}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (!input.trim() || isStreaming) return;
          sendMessage({ text: input }, { body: { model } });
          setInput('');
        }}
        className="flex gap-2 border-t border-black/10 pt-3 dark:border-white/10"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask anything…"
          className="flex-1 rounded-md border border-black/10 bg-transparent px-3 py-2 text-sm outline-none focus:border-black/30 dark:border-white/10 dark:focus:border-white/30"
          disabled={isStreaming}
        />
        <button
          type="submit"
          disabled={isStreaming || !input.trim()}
          className="rounded-md bg-foreground px-4 py-2 text-sm text-background disabled:opacity-50"
        >
          {isStreaming ? '…' : 'Send'}
        </button>
      </form>
    </main>
  );
}
