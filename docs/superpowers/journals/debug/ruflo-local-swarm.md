# Journal: ruflo-local-swarm

<!-- fr:journal kind=repro scope=debug id=b5c01f9d8940 created=2026-07-25T04:54:39 -->
### b5c01f9d8940 · repro · ruflo hive-mind spawn --claude re-verify (#475)

Re-verifying #475 on CURRENT versions. Original failure (2026-06-05): claude-flow v3.10.37 printed 'Spawned worker MCP config: /home/agent/.claude.json' but never wrote the mcpServers key; Claude Code 2.1.150 rejected it: 'Invalid MCP configuration: mcpServers: Invalid input: expected record, received undefined'. LIVE versions now: ruflo/claude-flow v3.10.46, Claude Code 2.1.163. Pod ruflo-7665cbd6d-t7plr (ns ruflo-system), container ruflo-shell, user agent, home on PVC. Next: attempt spawn --claude and inspect generated MCP config.

<!-- fr:journal kind=finding scope=debug id=9dab0eba6558 created=2026-07-25T04:56:26 state=open -->
### 9dab0eba6558 · finding [open] · Subscription OAuth is dead (blocks the old repro path, not the experiment)

claude -p one-off returns '401 OAuth access token has expired. Re-authenticate to continue.' The /login from 2026-06-05 expired ~same day and the refresh token no longer works after ~7wk. Re-login is interactive (human-only). PIVOT: the consolidated experiment IS to run CC workers on LiteLLM via ANTHROPIC_* (the #472 shim). Using that path re-verifies the #475 schema drift AND exercises #472 without needing the subscription. Proceeding via ANTHROPIC_BASE_URL=LiteLLM.

<!-- fr:journal kind=repro scope=debug id=a8efd2825d35 created=2026-07-25T04:58:06 -->
### a8efd2825d35 · repro · #475 STILL reproduces on claude-flow v3.10.46 + CC 2.1.163

Via the LiteLLM/ANTHROPIC_* path (subscription-free), ran: claude-flow hive-mind spawn --claude --non-interactive -o '...'. Output: '[INFO] Spawned worker MCP config: /home/agent/.claude.json' then 'Error: Invalid MCP configuration: mcpServers: Invalid input: expected record, received undefined' → 'Claude Code exited with code 1'. IDENTICAL to the 2026-06-05 failure. claude-flow auto-detect points CC at ~/.claude.json whose root mcpServers is null (CC 2.x stores MCP per-project, not root). BUT a valid ~/.mcp.json (proper mcpServers record) exists beside it, and spawn now has a --mcp-config flag ('fixes #1748 Issue 2'). Next: test --mcp-config ~/.mcp.json.

<!-- fr:journal kind=hypothesis scope=debug id=0742518bbdba created=2026-07-25T04:58:06 -->
### 0742518bbdba · hypothesis · Passing --mcp-config ~/.mcp.json bypasses the null-mcpServers auto-detect

claude-flow spawn --claude auto-detects ~/.claude.json (null root mcpServers) instead of the valid ~/.mcp.json. The new --mcp-config flag lets us point CC at a file with a real mcpServers record. Hypothesis: spawn --claude --mcp-config /home/agent/.mcp.json launches CC past the MCP validation gate.

<!-- fr:journal kind=ruled-out scope=debug id=81dea2aa5f9d created=2026-07-25T04:58:26 -->
### 81dea2aa5f9d · ruled-out · REFUTED: --mcp-config ~/.mcp.json does not help

spawn --claude --non-interactive --mcp-config /home/agent/.mcp.json STILL logged 'Spawned worker MCP config: /home/agent/.claude.json' and failed identically. The --mcp-config flag is ignored on this code path (the launch still hard-codes/prefers ~/.claude.json). Need to read claude-flow source to find the actual claude invocation + why the flag is inert.

<!-- fr:journal kind=root-cause scope=debug id=06eecf216f09 created=2026-07-25T05:05:14 -->
### 06eecf216f09 · root-cause · #475 root cause: claude-flow auto-detect picks ~/.claude.json (null root mcpServers)

In claude-flow v3.10.46 hive-mind.js the launch resolves the CC --mcp-config from candidates [cwd/.mcp.json, ~/.claude.json, ~/.claude/mcp.json] in order. With no .mcp.json in the launch cwd it falls to ~/.claude.json, whose ROOT mcpServers key is null (CC 2.x stores MCP per-project under projects[cwd].mcpServers, not at root). CC 2.1.163 validates --mcp-config and rejects 'mcpServers: expected record, received undefined'. PROVEN FIX: place a valid .mcp.json (proper mcpServers record — ~/.mcp.json already has one) in the launch cwd → candidate #1 matches → CC launches fully (subtype:init, mcp_servers:[ruflo], model:qwen-coder-14b). Secondary upstream bug: explicit --mcp-config flag is INERT because the parser normalizes mcp-config->mcpConfig (camelCase) but the code reads flags['mcp-config'] (kebab) — same class the #2269 comment fixed for dangerously-skip-permissions but missed here.

<!-- fr:journal kind=finding scope=debug id=984cd5965a65 created=2026-07-25T05:05:14 state=fixed -->
### 984cd5965a65 · finding [fixed] · #472 ANTHROPIC_* shim launches CC workers on local qwen via LiteLLM

With ANTHROPIC_BASE_URL=http://litellm.litellm.svc:4000, ANTHROPIC_AUTH_TOKEN=<litellm vkey>, ANTHROPIC_MODEL=qwen-coder-14b and a valid .mcp.json in cwd, spawn --claude --non-interactive launched CC 2.1.163 fully with apiKeySource:none and model qwen-coder-14b, routing to LiteLLM. Confirms the swarm LAUNCHES on local models — the task's gating condition for wiring #472 is met.

<!-- fr:journal kind=finding scope=debug id=ceb4f835f134 created=2026-07-25T05:05:15 state=open -->
### ceb4f835f134 · finding [open] · Downstream: LiteLLM ollama_chat rejects CC's context_management param (needs drop_params)

After launch, CC's request 400'd: litellm.UnsupportedParamsError: ollama_chat does not support parameters: ['context_management'] (qwen2.5-coder:14b). CC 2.1.x sends context_management (auto-compaction). Fix: LiteLLM drop_params:true (global or per-ollama_chat model). Note this 400 is raised at LiteLLM param-validation BEFORE routing, so it fires even though ollama is currently scaled to 0 (gpu-1 on ComfyUI, GPU timeshare). A full model completion also needs Ollama up (GPU switch) — out of scope for this low-pri experiment; launch + routing is proven.

<!-- fr:journal kind=finding scope=debug id=18c818627dd1 created=2026-07-25T05:08:20 state=open -->
### 18c818627dd1 · finding [open] · Fix design for the consolidated #475+#472 experiment

Deliverables: (1) profile.d shim ConfigMap ruflo-shell-claude-local mounted subPath at /etc/profile.d/61-ruflo-claude-local.sh (numbered after image's 60-banner) — defines bash function claude-local that (a) seeds a valid ./.mcp.json in cwd if absent [the #475 launch fix, candidate #1 of claude-flow's --mcp-config auto-detect], (b) exports ANTHROPIC_BASE_URL=LITELLM, ANTHROPIC_AUTH_TOKEN=<litellm vkey>, ANTHROPIC_MODEL=qwen-coder-14b, ANTHROPIC_SMALL_FAST_MODEL=gemma-12b, then runs the given command (wrapper) or exports into the current shell (no-arg). Switchable per run; default stays subscription OAuth. (2) Add ruflo-llm secretRef to the shell container envFrom (optional) so OPENAI_API_KEY [an existing LiteLLM virtual key] is the token — reuse over minting; dedicated-key ESO is a documented follow-up. (3) LiteLLM litellm_settings.drop_params: true — resolves CC 2.1.x's context_management 400 on ollama_chat. Mirrors apps/hermes-agent-shell BYOK profile.d pattern.

<!-- fr:journal kind=finding scope=debug id=7e3209548944 created=2026-07-25T05:11:30 state=fixed -->
### 7e3209548944 · finding [fixed] · VERIFIED: claude-local shim launches CC swarm workers on local qwen past the #475 gate

Sourced the exact shim ConfigMap script in the ruflo-shell pod (with OPENAI_API_KEY injected to simulate the ruflo-llm envFrom). claude-local claude-flow hive-mind spawn --claude --non-interactive: (1) 'seeded ./.mcp.json (#475 launch fix)'; (2) 'Spawned worker MCP config: /home/agent/shim-e2e/.mcp.json' — now candidate #1, NOT the null ~/.claude.json; (3) CC 2.1.163 launched fully: subtype:init, mcp_servers:[ruflo], model:qwen-coder-14b, apiKeySource:none. #475 MCP validation gate PASSED. Reached LiteLLM/local model; only remaining block is the context_management 400, whose LiteLLM error text prescribes exactly the applied fix (litellm_settings: drop_params: true). Shim function unit-verified too: wrapper form (per-run env isolation), no-arg export form, RUFLO_LOCAL_MODEL override, .mcp.json idempotent seed. NOT observed end-to-end for a full model completion — that needs LiteLLM redeployed (drop_params) AND Ollama scaled up (gpu-1 GPU timeshare currently on ComfyUI); deliberately not disrupting shared infra for a low-pri experiment.
