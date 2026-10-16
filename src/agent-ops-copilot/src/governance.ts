import { appendFile, mkdir } from 'node:fs/promises';
import { dirname } from 'node:path';
import type { PermissionHandler, SessionHooks } from '@github/copilot-sdk';

export const CUSTOM_TOOLS = ['run_evals', 'read_eval_results', 'scaffold_tool', 'open_pr', 'audit_summary'] as const;
const readOnlyCommands = new Set(['git status --short', 'git --no-pager status --short', 'git diff --stat', 'git --no-pager diff --stat', 'pwd', 'Get-Location']);
export const isReadOnlyShell = (command: unknown): boolean => typeof command === 'string' && readOnlyCommands.has(command.trim());
export type Audit = (event: Record<string, unknown>) => Promise<void>;
export function auditWriter(path: string): Audit {
  return async event => {
    await mkdir(dirname(path), { recursive: true });
    await appendFile(path, JSON.stringify({ timestamp: new Date().toISOString(), source: 'agent-ops-copilot', ...event }) + '\n');
  };
}
export function governance(audit: Audit): { onPermissionRequest: PermissionHandler; onPreToolUse: NonNullable<SessionHooks['onPreToolUse']> } {
  return {
    onPermissionRequest: async request => {
      const allowed = !request.managedApprovalRequired && (
        (request.kind === 'custom-tool' && CUSTOM_TOOLS.includes(request.toolName as typeof CUSTOM_TOOLS[number])) ||
        (request.kind === 'shell' && !request.hasWriteFileRedirection && !request.requestSandboxBypass &&
          request.possibleUrls.length === 0 && isReadOnlyShell(request.fullCommandText))
      );
      if (!allowed) await audit({ event: 'permission_denied', kind: request.kind, tool: request.kind === 'custom-tool' ? request.toolName : undefined });
      return allowed ? { kind: 'approved' } : { kind: 'denied-by-permission-request-hook' };
    },
    onPreToolUse: async input => {
      // Hooks cover tools that do not emit a separate permission request.
      const args = input.toolArgs as { command?: unknown } | null;
      const allowed = CUSTOM_TOOLS.includes(input.toolName as typeof CUSTOM_TOOLS[number]) ||
        (['bash', 'powershell', 'shell'].includes(input.toolName) && isReadOnlyShell(args?.command));
      if (!allowed) await audit({ event: 'tool_denied', tool: input.toolName });
      // Do not auto-approve here: managed permission policy must still run.
      return allowed ? {} : { permissionDecision: 'deny', permissionDecisionReason: 'Only workshop custom tools and exact read-only shell commands are allowed.' };
    },
  };
}

