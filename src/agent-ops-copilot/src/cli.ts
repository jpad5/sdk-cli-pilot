import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createTools, type OpsTools } from './tools.js';
import { auditWriter, CUSTOM_TOOLS, governance } from './governance.js';

export const DEMO_PROMPT = 'Add an adverse-media screening tool, run evals, open a PR if they pass';
export async function mockPlan(tools: OpsTools, log: (text: string) => void = console.log) {
  log('[mock] Deterministic workshop plan; prompt is not sent to a model. Copilot runtime and GitHub are not contacted.');
  log(JSON.stringify(await tools.scaffold_tool({ name: 'adverse_media_screening' }), null, 2));
  const evaluation = await tools.run_evals();
  log(JSON.stringify(evaluation, null, 2));
  log(JSON.stringify(await tools.read_eval_results(), null, 2));
  if (evaluation.passed) log(JSON.stringify(await tools.open_pr(), null, 2));
  else log('[mock] PR skipped: evaluations did not pass or evaluator is unavailable.');
  log(JSON.stringify(await tools.audit_summary(), null, 2));
}
export async function main(args = process.argv.slice(2)) {
  const mode = process.env.DEMO_MODE ?? 'mock';
  if (mode !== 'mock' && mode !== 'live') throw new Error('DEMO_MODE must be mock or live');
  // Source and compiled entrypoints both resolve the repo independently of cwd.
  const here = dirname(fileURLToPath(import.meta.url));
  const root = resolve(here, ...(here.includes(`${join('dist', 'src')}`) ? ['..', '..', '..', '..'] : ['..', '..', '..']));
  const prompt = args.includes('--demo') ? DEMO_PROMPT : args.join(' ').trim();
  if (!prompt) throw new Error('Usage: npm run ops -- "<prompt>" or npm run demo');
  const audit = auditWriter(join(root, '.data', 'audit.jsonl'));
  const tools = createTools({ root, mode, audit });
  if (mode === 'mock') { await mockPlan(tools); return; }
  // Dynamic import guarantees mock mode never initializes the SDK/runtime.
  const [{ CopilotClient }, { sdkTools, providerFromEnv }] = await Promise.all([import('@github/copilot-sdk'), import('./sdk.js')]);
  const policy = governance(audit);
  const client = new CopilotClient({ workingDirectory: root });
  let session: Awaited<ReturnType<typeof client.createSession>> | undefined;
  try {
    session = await client.createSession({
      ...(process.env.COPILOT_MODEL ? { model: process.env.COPILOT_MODEL } : {}),
      provider: providerFromEnv(process.env),
      tools: sdkTools(tools),
      availableTools: [...CUSTOM_TOOLS, 'powershell', 'bash'],
      onPermissionRequest: policy.onPermissionRequest,
      hooks: { onPreToolUse: policy.onPreToolUse },
      streaming: true,
      systemMessage: { mode: 'append', content: 'You are Agent Ops Copilot for a synthetic FSI KYC/AML workshop. Use only provided custom tools or exact read-only shell commands. Never execute arbitrary code, access network tools, change policy, or bypass approvals. Scaffold only candidate stubs; do not claim screening is implemented. Run evals AFTER scaffolding. Open a PR only when evals pass and the user requested one. Do not commit or push; ask users to prepare a pushed branch before live PR creation. Report unavailable evaluations honestly. Do not expose secrets or customer data.' },
    });
    let streamed = false;
    session.on(event => {
      if (event.type === 'assistant.message_delta') { streamed = true; process.stdout.write(event.data.deltaContent); }
      if (event.type === 'session.error') console.error('Copilot session error:', event.data.message);
    });
    const response = await session.sendAndWait({ prompt }, 180_000);
    if (!streamed && response) console.log(response.data.content);
    else console.log();
  } finally {
    try { await session?.disconnect(); } finally { await client.stop(); }
  }
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch(error => { console.error(error instanceof Error ? error.message : String(error)); process.exitCode = 1; });
}

