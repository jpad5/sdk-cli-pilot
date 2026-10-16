import { test, type TestContext } from 'node:test';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { access, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { createTools, runCommand, type Runner } from '../src/tools.js';
import { auditWriter } from '../src/governance.js';
import { mockPlan } from '../src/cli.js';
import { providerFromEnv, sdkTools } from '../src/sdk.js';

async function fixture(t: TestContext, mode: 'mock' | 'live' = 'mock', code = 0) {
  const root = resolve('.test-work', randomUUID());
  await mkdir(root, { recursive: true });
  t.after(async () => { await rm(root, { recursive: true, force: true }); });
  const calls: { file: string; args: string[]; env: NodeJS.ProcessEnv }[] = [];
  const log: string[] = [];
  const runner: Runner = async (file, args, options) => {
    calls.push({ file, args, env: options.env });
    if (file === 'gh') return { code, stdout: 'https://example.invalid/pr/1', stderr: '' };
    await mkdir(join(root, '.data'), { recursive: true });
    // Ensure a strictly newer artifact, including coarse filesystem timestamps.
    await new Promise(resolveDelay => setTimeout(resolveDelay, 20));
    await writeFile(join(root, '.data', 'eval-results.json'), JSON.stringify({ pass_rate: code ? 0.5 : 1, passed: code === 0 }));
    return { code, stdout: '', stderr: '' };
  };
  async function enableEval() {
    for (const path of [join(root, '.venv', process.platform === 'win32' ? 'Scripts' : 'bin', process.platform === 'win32' ? 'python.exe' : 'python'), join(root, 'src', 'foundry-kyc-agent', 'kyc_agent', 'evals.py')]) {
      await mkdir(dirname(path), { recursive: true }); await writeFile(path, '');
    }
  }
  return { root, calls, log, enableEval, tools: createTools({ root, mode, runner, log: text => log.push(text) }) };
}
test('mock scaffold writes candidate + test only in preview and emits a diff; reruns are deterministic', async t => {
  const f = await fixture(t);
  const result = await f.tools.scaffold_tool({ name: 'adverse_media_screening' });
  assert.equal(result.status, 'preview'); assert.equal(result.registered, false);
  assert.equal(result.files.length, 2);
  for (const path of result.files) { assert.ok(path.startsWith(join(f.root, '.data', 'preview'))); assert.ok((await readFile(path, 'utf8')).includes('adverse_media_screening')); }
  assert.match(f.log.join('\n'), /\+def adverse_media_screening/);
  await assert.rejects(access(join(f.root, 'src', 'foundry-kyc-agent', 'kyc_agent', 'adverse_media_screening.py')));
  await f.tools.scaffold_tool({ name: 'adverse_media_screening' });
  assert.equal(f.calls.length, 0);
});
test('rejects traversal and invalid or reserved scaffold names', async t => {
  const f = await fixture(t);
  for (const name of ['../escape', '..\\escape', 'UPPER', 'foo.py', 'tools', 'class', 'async', 'return', 'a;echo', 'a'.repeat(65)]) await assert.rejects(f.tools.scaffold_tool({ name }));
});
test('live scaffold is non-overwriting and remains an explicitly unregistered stub', async t => {
  const f = await fixture(t, 'live');
  const result = await f.tools.scaffold_tool({ name: 'screen_media' });
  assert.equal(result.status, 'created');
  assert.match(await readFile(result.files[0]!, 'utf8'), /not_implemented/);
  await assert.rejects(f.tools.scaffold_tool({ name: 'screen_media' }), /EEXIST/);
});
test('missing eval CLI is graceful and cannot open a PR', async t => {
  const f = await fixture(t);
  assert.equal((await f.tools.run_evals()).status, 'unavailable');
  assert.equal((await f.tools.open_pr()).status, 'blocked');
  assert.equal((await f.tools.read_eval_results()).status, 'unavailable');
  assert.equal(f.calls.length, 0);
});
test('successful eval uses fixed args, mode and repo venv; mock PR never invokes gh', async t => {
  const f = await fixture(t); await f.enableEval();
  assert.equal((await f.tools.run_evals()).passed, true);
  assert.deepEqual(f.calls[0]?.args, ['-m', 'kyc_agent.evals', '--mode', 'mock', '--threshold', '0.8']);
  assert.equal(f.calls[0]?.env.DEMO_MODE, 'mock');
  assert.ok(f.calls[0]?.file.includes('.venv'));
  assert.equal((await f.tools.open_pr()).status, 'preview');
  assert.equal(f.calls.length, 1); assert.match(f.log.join('\n'), /gh "pr" "create"/);
});
test('PR gate blocks failing evals, tampered results, and scaffolds after passing evals', async t => {
  const failed = await fixture(t, 'mock', 1); await failed.enableEval();
  assert.equal((await failed.tools.run_evals()).passed, false); assert.equal((await failed.tools.open_pr()).status, 'blocked');
  const f = await fixture(t); await f.enableEval(); await f.tools.run_evals();
  await writeFile(join(f.root, '.data', 'eval-results.json'), '{"passed":true,"tampered":true}');
  assert.equal((await f.tools.open_pr()).status, 'blocked');
  await f.tools.run_evals(); await f.tools.scaffold_tool({ name: 'new_candidate' });
  assert.equal((await f.tools.open_pr()).status, 'blocked');
});
test('stale or malformed artifacts never pass even when subprocess exits zero', async t => {
  const f = await fixture(t); await f.enableEval();
  await mkdir(join(f.root, '.data'), { recursive: true });
  await writeFile(join(f.root, '.data', 'eval-results.json'), '{"passed":true}');
  await new Promise(resolveDelay => setTimeout(resolveDelay, 30));
  const tools = createTools({ root: f.root, mode: 'mock', runner: async () => ({ code: 0, stdout: '', stderr: '' }) });
  assert.equal((await tools.run_evals()).passed, false);
  await writeFile(join(f.root, '.data', 'eval-results.json'), 'invalid-json');
  assert.equal((await tools.run_evals()).status, 'missing-or-invalid-results');
});
test('live PR invokes gh without shell and reports command failure', async t => {
  const f = await fixture(t, 'live'); await f.enableEval(); await f.tools.run_evals();
  const title = 'Candidate; this is a literal argument';
  assert.equal((await f.tools.open_pr({ title })).status, 'created');
  assert.equal(f.calls[1]?.file, 'gh'); assert.equal(f.calls[1]?.args[3], title);
  const tools = createTools({ root: f.root, mode: 'live', runner: async (file, args, options) => file === 'gh' ? { code: 1, stdout: '', stderr: 'push your branch first' } : (await f.tools.run_evals(), { code: 0, stdout: '', stderr: '' }) });
  await tools.run_evals(); assert.equal((await tools.open_pr()).status, 'failed');
});
test('audit summary counts malformed entries and denies without exposing event contents', async t => {
  const f = await fixture(t);
  const audit = auditWriter(join(f.root, '.data', 'audit.jsonl'));
  await audit({ event: 'permission_denied', secret: 'must-not-be-returned' });
  await audit({ action: 'screen_name', allowed: false });
  await writeFile(join(f.root, '.data', 'audit.jsonl'), (await readFile(join(f.root, '.data', 'audit.jsonl'), 'utf8')) + 'oops\nnull\n');
  const result = await f.tools.audit_summary();
  assert.equal(result.total, 2); assert.equal(result.malformed, 2); assert.equal(result.denials, 2);
  assert.ok(!JSON.stringify(result).includes('must-not-be-returned'));
});
test('deterministic mock demo completes safely without evaluator', async t => {
  const f = await fixture(t); const output: string[] = [];
  await mockPlan(f.tools, text => output.push(text));
  assert.match(output.join('\n'), /PR skipped/); assert.equal(f.calls.length, 0);
});
test('process runner captures spawn errors without throwing', async () => {
  const result = await runCommand('definitely-not-a-real-kyc-command', [], { cwd: process.cwd(), env: process.env });
  assert.equal(result.code, null); assert.match(result.stderr, /ENOENT/);
});
test('SDK definitions expose exactly the five tool handlers', async t => {
  const f = await fixture(t);
  assert.deepEqual(sdkTools(f.tools).map(tool => tool.name), ['run_evals', 'read_eval_results', 'scaffold_tool', 'open_pr', 'audit_summary']);
});
test('Foundry BYOK validates configuration and supports openai/v1 and native azure', () => {
  assert.equal(providerFromEnv({}), undefined);
  assert.throws(() => providerFromEnv({ FOUNDRY_MODEL_URL: 'http://example.invalid/' }), /HTTPS/);
  assert.throws(() => providerFromEnv({ FOUNDRY_MODEL_URL: 'https://example.invalid/' }), /requires/);
  const env = { FOUNDRY_MODEL_URL: 'https://resource.openai.azure.com/openai/v1/', FOUNDRY_API_KEY: 'test-only', COPILOT_MODEL: 'deployment' };
  assert.equal(providerFromEnv(env)?.type, 'openai');
  assert.equal(providerFromEnv({ ...env, COPILOT_PROVIDER_TYPE: 'azure', AZURE_OPENAI_API_VERSION: '2024-10-21' })?.azure?.apiVersion, '2024-10-21');
  assert.throws(() => providerFromEnv({ ...env, COPILOT_WIRE_API: 'typo' }), /WIRE_API/);
});

