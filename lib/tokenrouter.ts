import { createOpenAICompatible } from '@ai-sdk/openai-compatible';

const apiKey = process.env.TOKENROUTER_API_KEY;
const baseURL = process.env.TOKENROUTER_BASE_URL ?? 'https://api.tokenrouter.io/v1';

if (!apiKey) {
  throw new Error('TOKENROUTER_API_KEY is not set in environment');
}

export const tokenrouter = createOpenAICompatible({
  name: 'tokenrouter',
  apiKey,
  baseURL,
});

export const defaultModel = process.env.TOKENROUTER_MODEL ?? 'openai/gpt-4o-mini';
