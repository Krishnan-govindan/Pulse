import { convertToModelMessages, stepCountIs, streamText, tool, type UIMessage } from 'ai';
import { z } from 'zod';
import { tokenrouter, defaultModel } from '@/lib/tokenrouter';

export const maxDuration = 60;

export async function POST(req: Request) {
  const { messages, model }: { messages: UIMessage[]; model?: string } = await req.json();

  const result = streamText({
    model: tokenrouter.chatModel(model ?? defaultModel),
    system:
      'You are a concise, helpful agent. Use tools when they help. Keep answers tight unless asked to elaborate.',
    messages: await convertToModelMessages(messages),
    stopWhen: stepCountIs(5),
    tools: {
      currentTime: tool({
        description: 'Get the current server time as an ISO string.',
        inputSchema: z.object({}),
        execute: async () => ({ now: new Date().toISOString() }),
      }),
      calculate: tool({
        description:
          'Evaluate a basic arithmetic expression. Supports + - * / ( ) and decimals.',
        inputSchema: z.object({
          expression: z.string().describe('e.g. "(12 + 5) * 3.2"'),
        }),
        execute: async ({ expression }) => {
          if (!/^[\d+\-*/().\s]+$/.test(expression)) {
            return { error: 'Only numbers and + - * / ( ) are allowed.' };
          }
          try {
            const value = Function(`"use strict"; return (${expression});`)();
            return { result: value };
          } catch (e) {
            return { error: (e as Error).message };
          }
        },
      }),
    },
  });

  return result.toUIMessageStreamResponse();
}
