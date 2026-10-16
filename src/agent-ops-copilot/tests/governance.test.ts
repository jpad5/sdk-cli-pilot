import { test } from 'node:test';
import assert from 'node:assert/strict';
import type { PermissionRequest, SessionHooks } from '@github/copilot-sdk';
import { CUSTOM_TOOLS, governance, isReadOnlyShell } from '../src/governance.js';
const invocation = { sessionId: 'test-session' };
function shell(command: string): Extract<PermissionRequest, { kind: 'shell' }> {
  return { kind: 'shell', fullCommandText: command, canOfferSessionApproval: false, commands: [], hasWriteFileRedirection: false, intention: 'test', possiblePaths: [], possibleUrls: [] };
}
test('allows only named custom tools and exact read-only commands', async () => {
  const events: unknown[] = []; const policy = governance(async event => { events.push(event); });
  for (const name of CUSTOM_TOOLS) assert.equal((await policy.onPermissionRequest({ kind: 'custom-tool', toolName: name, toolDescription: 'test' }, invocation)).kind, 'approved');
  assert.equal((await policy.onPermissionRequest(shell('git --no-pager status --short'), invocation)).kind, 'approved');
  assert.equal(events.length, 0);
});
test('denies arbitrary tools, shell injection, network, managed approval, and sandbox escape; logs denials', async () => {
  const events: unknown[] = []; const policy = governance(async event => { events.push(event); });
  for (const command of ['git status --short; curl https://example.invalid', 'pwd > file', 'Get-Location\nRemove-Item file', 'git -c alias.status=!calc status', 'python -c "print(1)"', 'git diff --output=file', 'curl https://example.invalid', 'git status --short && whoami', '$(pwd)', 'pwd | bash', 'PWD']) {
    assert.equal(isReadOnlyShell(command), false);
    assert.equal((await policy.onPermissionRequest(shell(command), invocation)).kind, 'denied-by-permission-request-hook');
  }
  assert.equal((await policy.onPermissionRequest({ kind: 'custom-tool', toolName: 'delete_all', toolDescription: '' }, invocation)).kind, 'denied-by-permission-request-hook');
  assert.equal((await policy.onPermissionRequest({ ...shell('pwd'), managedApprovalRequired: true }, invocation)).kind, 'denied-by-permission-request-hook');
  assert.equal((await policy.onPermissionRequest({ ...shell('pwd'), requestSandboxBypass: true }, invocation)).kind, 'denied-by-permission-request-hook');
  assert.equal((await policy.onPermissionRequest({ ...shell('pwd'), hasWriteFileRedirection: true }, invocation)).kind, 'denied-by-permission-request-hook');
  assert.equal(events.length, 15);
});
test('unknown permission kinds fail closed', async () => {
  const policy = governance(async () => {});
  assert.equal((await policy.onPermissionRequest({ kind: 'future-kind' } as unknown as PermissionRequest, invocation)).kind, 'denied-by-permission-request-hook');
});
test('pre-tool hook does not bypass managed approvals; denies built-in writes and unrecognized commands', async () => {
  const events: unknown[] = []; const policy = governance(async event => { events.push(event); });
  const hook = async (toolName: string, toolArgs: unknown) => policy.onPreToolUse({ toolName, toolArgs, timestamp: new Date(), sessionId: 'test-session', workingDirectory: '.' } as Parameters<NonNullable<SessionHooks['onPreToolUse']>>[0], invocation);
  assert.deepEqual(await hook('run_evals', {}), {});
  assert.deepEqual(await hook('powershell', { command: 'Get-Location' }), {});
  assert.equal((await hook('edit', {}))?.permissionDecision, 'deny');
  assert.equal((await hook('bash', { command: 'rm -rf .' }))?.permissionDecision, 'deny');
  assert.equal((await hook('bash', null))?.permissionDecision, 'deny');
  assert.equal(events.length, 3);
});

