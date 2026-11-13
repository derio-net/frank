<!-- fr:journal-schema=4 -->
# Journal: agent-images-bump-digest-pins

<!-- fr:journal kind=root-cause scope=debug id=017fe840ec29 created=2026-11-13T17:50:24+00:00 -->
### 017fe840ec29 · root-cause · tag-only sed keeps @sha256

agent-images-bump.yml sed rewrote only the hex tag; a digest-pinned ref kept its old @sha256 (bump PR #965 paired upstream-session:dbdf5f69 with 1f893195's digest 8dcb0ece). Runtimes pull by digest -> old image under a new tag.
