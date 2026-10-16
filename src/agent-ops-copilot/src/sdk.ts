import { defineTool, type ProviderConfig } from '@github/copilot-sdk';
import type { OpsTools } from './tools.js';

export function sdkTools(tools: OpsTools) {
  const empty = { type: 'object', properties: {}, additionalProperties: false };
  return [
    defineTool('run_evals', { description: 'Run KYC evals at threshold 0.8 using the repo .venv; required after scaffolding and before PR creation.', parameters: empty, handler: tools.run_evals }),
    defineTool('read_eval_results', { description: 'Read the latest KYC eval summary JSON (does not authorize a PR).', parameters: empty, handler: tools.read_eval_results }),
    defineTool('scaffold_tool', { description: 'Create a new, unregistered Python function-tool candidate and tests; mock mode writes preview and prints diff only.', parameters: { type: 'object', properties: { name: { type: 'string', pattern: '^[a-z][a-z0-9_]{0,63}$' } }, required: ['name'], additionalProperties: false }, handler: tools.scaffold_tool }),
    defineTool('open_pr', { description: 'Create a PR with gh only after a successful run_evals in this session. Does not commit or push; mock prints command.', parameters: { type: 'object', properties: { title: { type: 'string' } }, additionalProperties: false }, handler: tools.open_pr }),
    defineTool('audit_summary', { description: 'Summarize governance event counts without returning raw customer or audit data.', parameters: empty, handler: tools.audit_summary }),
  ];
}
export function providerFromEnv(env: NodeJS.ProcessEnv): ProviderConfig | undefined {
  if (!env.FOUNDRY_MODEL_URL) return undefined;
  const url = new URL(env.FOUNDRY_MODEL_URL);
  if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash) throw new Error('FOUNDRY_MODEL_URL must be an HTTPS endpoint without embedded credentials, query, or fragment.');
  if (!env.FOUNDRY_API_KEY || !env.COPILOT_MODEL) throw new Error('BYOK requires FOUNDRY_API_KEY and COPILOT_MODEL (deployment name).');
  const type = env.COPILOT_PROVIDER_TYPE ?? 'openai';
  if (type !== 'azure' && type !== 'openai') throw new Error('COPILOT_PROVIDER_TYPE must be openai or azure.');
  const wireApi = env.COPILOT_WIRE_API ?? 'completions';
  if (wireApi !== 'completions' && wireApi !== 'responses') throw new Error('COPILOT_WIRE_API must be completions or responses.');
  return { type, baseUrl: url.toString(), apiKey: env.FOUNDRY_API_KEY, wireApi,
    ...(type === 'azure' && env.AZURE_OPENAI_API_VERSION ? { azure: { apiVersion: env.AZURE_OPENAI_API_VERSION } } : {}) };
}
