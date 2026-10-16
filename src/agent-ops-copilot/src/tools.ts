import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { access, mkdir, readFile, realpath, stat, writeFile } from 'node:fs/promises';
import { delimiter, dirname, join, relative, resolve, sep } from 'node:path';
import { auditWriter, type Audit } from './governance.js';

export interface CommandResult { code: number | null; stdout: string; stderr: string }
export type Runner = (file: string, args: string[], options: { cwd: string; env: NodeJS.ProcessEnv }) => Promise<CommandResult>;
export const runCommand: Runner = (file, args, options) => new Promise(resolveResult => {
  const child = spawn(file, args, { ...options, shell: false, windowsHide: true });
  let stdout = '', stderr = '', settled = false;
  const finish = (code: number | null) => { if (!settled) { settled = true; resolveResult({ code, stdout, stderr }); } };
  const timer = setTimeout(() => { stderr += '\nCommand timed out'; child.kill(); }, 120_000);
  child.stdout.on('data', chunk => { stdout = (stdout + String(chunk)).slice(-100_000); });
  child.stderr.on('data', chunk => { stderr = (stderr + String(chunk)).slice(-100_000); });
  child.on('error', error => { clearTimeout(timer); stderr = error.message; finish(null); });
  child.on('close', code => { clearTimeout(timer); finish(code); });
});
export interface ToolOptions { root: string; mode: 'mock' | 'live'; runner?: Runner; log?: (text: string) => void; audit?: Audit }
const digest = (text: string) => createHash('sha256').update(text).digest('hex');
const reservedNames = new Set(['tools', 'evals', 'agent', 'config', 'test', 'and', 'as', 'assert', 'async', 'await', 'break', 'class', 'continue', 'def', 'del', 'elif', 'else', 'except', 'finally', 'for', 'from', 'global', 'if', 'import', 'in', 'is', 'lambda', 'nonlocal', 'not', 'or', 'pass', 'raise', 'return', 'try', 'while', 'with', 'yield']);
export function createTools({ root, mode, runner = runCommand, log = console.log, audit = auditWriter(join(root, '.data', 'audit.jsonl')) }: ToolOptions) {
  const resultsPath = join(root, '.data', 'eval-results.json');
  let passingDigest: string | undefined;
  async function results() { return JSON.parse(await readFile(resultsPath, 'utf8')) as unknown; }
  async function run_evals() {
    passingDigest = undefined;
    const python = join(root, '.venv', process.platform === 'win32' ? 'Scripts' : 'bin', process.platform === 'win32' ? 'python.exe' : 'python');
    const args = ['-m', 'kyc_agent.evals', '--mode', mode, '--threshold', '0.8'];
    try { await access(python); await access(join(root, 'src', 'foundry-kyc-agent', 'kyc_agent', 'evals.py')); }
    catch { return { passed: false, status: 'unavailable', message: 'Set up repo .venv and src/foundry-kyc-agent first; no PR will be opened.' }; }
    const started = Date.now();
    const outcome = await runner(python, args, { cwd: root, env: { ...process.env, DEMO_MODE: mode,
      PYTHONPATH: [join(root, 'src', 'foundry-kyc-agent'), join(root, 'shared', 'kyc_core'), process.env.PYTHONPATH].filter(Boolean).join(delimiter) } });
    try {
      const text = await readFile(resultsPath, 'utf8');
      const summary: unknown = JSON.parse(text);
      const fresh = (await stat(resultsPath)).mtimeMs >= started;
      const passed = outcome.code === 0 && fresh;
      if (passed) passingDigest = digest(text);
      await audit({ event: 'eval_completed', passed, mode, exit_code: outcome.code });
      return { passed, status: fresh ? 'completed' : 'stale-results', exitCode: outcome.code, summary, stderr: outcome.stderr };
    } catch {
      await audit({ event: 'eval_completed', passed: false, mode, exit_code: outcome.code });
      return { passed: false, status: 'missing-or-invalid-results', exitCode: outcome.code, stderr: outcome.stderr };
    }
  }
  async function read_eval_results() {
    try { return { status: 'available', summary: await results() }; }
    catch { return { status: 'unavailable', message: 'No readable eval-results.json; run run_evals first.' }; }
  }
  async function scaffold_tool(input: { name: string }) {
    if (!input || typeof input.name !== 'string' || !/^[a-z][a-z0-9_]{0,63}$/.test(input.name) || reservedNames.has(input.name)) throw new Error('Use a new snake_case tool name, at most 64 characters.');
    const name = input.name;
    const files = [
      { path: join('src', 'foundry-kyc-agent', 'kyc_agent', `${name}.py`), text: `"""Generated candidate stub; review and register through ToolPolicy before use."""\n\n\ndef ${name}(customer_name: str) -> dict[str, object]:\n    """Return no screening conclusion until a reviewed provider is implemented."""\n    if not customer_name.strip():\n        raise ValueError("customer_name is required")\n    return {"status": "not_implemented", "requires_review": True}\n` },
      { path: join('src', 'foundry-kyc-agent', 'tests', `test_${name}.py`), text: `from kyc_agent.${name} import ${name}\n\n\ndef test_${name}_requires_review():\n    result = ${name}("Synthetic Customer")\n    assert result["status"] == "not_implemented"\n    assert result["requires_review"] is True\n\n\ndef test_${name}_rejects_empty_name():\n    import pytest\n    with pytest.raises(ValueError):\n        ${name}(" ")\n` },
    ];
    const output: string[] = [];
    passingDigest = undefined;
    for (const file of files) {
      const target = join(root, ...(mode === 'mock' ? ['.data', 'preview'] : []), file.path);
      await mkdir(dirname(target), { recursive: true });
      // Refuse directory links escaping the repository or preview tree.
      const boundary = await realpath(mode === 'mock' ? join(root, '.data', 'preview') : root);
      const parent = await realpath(dirname(target));
      const inside = relative(boundary, parent);
      if (inside === '..' || inside.startsWith(`..${sep}`) || resolve(boundary, inside) !== parent) throw new Error('Scaffold path escapes allowed tree');
      await writeFile(target, file.text, { flag: 'wx' }).catch(async error => {
        if (mode !== 'mock' || (error as NodeJS.ErrnoException).code !== 'EEXIST' || await readFile(target, 'utf8') !== file.text) throw error;
      });
      output.push(target);
      log(`--- /dev/null\n+++ b/${file.path.replaceAll('\\', '/')}\n@@ -0,0 +1,${file.text.trimEnd().split('\n').length} @@\n${file.text.trimEnd().split('\n').map(line => '+' + line).join('\n')}`);
    }
    await audit({ event: 'tool_scaffolded', tool: name, mode, preview: mode === 'mock' });
    return { status: mode === 'mock' ? 'preview' : 'created', files: output, registered: false, message: 'Stub only; implement screening and register with KYC ToolPolicy/audit before production use.' };
  }
  async function open_pr(input: { title?: string } = {}) {
    const title = input.title ?? 'Add adverse-media screening candidate';
    if (typeof title !== 'string' || !title.trim() || title.length > 200) throw new Error('PR title must be 1–200 characters');
    let current: string;
    try { current = await readFile(resultsPath, 'utf8'); } catch { return { status: 'blocked', reason: 'Run passing evals in this session first.' }; }
    if (!passingDigest || digest(current) !== passingDigest) return { status: 'blocked', reason: 'Run passing evals after the latest scaffold change; stale or changed results are not accepted.' };
    const args = ['pr', 'create', '--title', title, '--body', 'Workshop candidate: review generated stub, policy registration, and passing KYC eval results before merging.'];
    const command = ['gh', ...args.map(arg => JSON.stringify(arg))].join(' ');
    if (mode === 'mock') { log(`[mock] ${command}`); return { status: 'preview', command, warning: 'Evals cover the existing agent, not the unregistered preview stub.' }; }
    const outcome = await runner('gh', args, { cwd: root, env: { ...process.env, GH_PROMPT_DISABLED: '1' } });
    await audit({ event: 'pr_create', mode, success: outcome.code === 0 });
    return { status: outcome.code === 0 ? 'created' : 'failed', ...outcome };
  }
  async function audit_summary() {
    let text: string;
    try { text = await readFile(join(root, '.data', 'audit.jsonl'), 'utf8'); }
    catch { return { total: 0, malformed: 0, events: {}, denials: 0 }; }
    const events: Record<string, number> = Object.create(null) as Record<string, number>;
    let total = 0, malformed = 0, denials = 0;
    for (const line of text.split(/\r?\n/).filter(line => line.trim())) {
      try {
        const entry = JSON.parse(line) as Record<string, unknown>;
        if (!entry || typeof entry !== 'object' || Array.isArray(entry)) throw new Error('Invalid event');
        const key = String(entry.event ?? entry.action ?? 'unknown');
        events[key] = (events[key] ?? 0) + 1; total++;
        if (/denied|blocked|reject/i.test(key) || entry.allowed === false || entry.decision === 'denied' || entry.outcome === 'denied') denials++;
      } catch { malformed++; }
    }
    return { total, malformed, events, denials };
  }
  return { run_evals, read_eval_results, scaffold_tool, open_pr, audit_summary };
}
export type OpsTools = ReturnType<typeof createTools>;

