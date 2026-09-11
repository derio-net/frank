# Journal: 2026-09-11--infer--ovms-rerank-batch-guard

<!-- fr:journal kind=decision scope=spec id=cap-lives-in-model-image created=2026-09-11T10:40:52 -->
### cap-lives-in-model-image · decision · The batch guard lives in the model image, not a deploy-time overlay

Operator chose the Dockerfile export stage post-processing the generated graph.pbtxt, with MODELS_REV 1 to 2 and a PVC reseed, over a kustomize configMapGenerator mounted by subPath over /models/bge-reranker-v2-m3/graph.pbtxt. Single source of truth, and test_models_rev_moves_when_the_dockerfile_changes already enforces the rev bump. Accepted cost: retuning the cap later means a full model rebuild (re-download plus re-quantize both models) and a 2.4 GiB reseed, not a values edit.

<!-- fr:journal kind=decision scope=spec id=raise-limit-support-fifty created=2026-09-11T10:40:53 -->
### raise-limit-support-fifty · decision · Raise the ovms memory limit to 10Gi and support the 50-document batch

Operator chose to make the batch the downstream client actually sends succeed, rather than cap below it and force the client to chunk. limits.memory 6Gi to 10Gi (requests stay 2Gi); max_allowed_chunks set with headroom above 50 from the measured curve. Accepted cost: a larger failure domain on mini-1, which is an etcd member, against the original spike spec's deliberate choice to keep exposure small. Rejected: hold 6Gi and cap at the largest measured-safe batch (24-32); pin at the already-proven 20 with no measurement.

<!-- fr:journal kind=decision scope=spec id=bound-sequence-length-too created=2026-09-11T10:40:55 -->
### bound-sequence-length-too · decision · Bound sequence length as well as document count

Capping documents alone does not bound the worst case: rerank_calculator_ov.cc builds ONE tensor of shape {batch_size, total_tokens_count_per_batch} where T comes from the longest document, up to the model context (about 8194). Operator chose to also set max_position_embeddings to a measured value so long documents are chunked and the chunk total is checked against the same cap. Accepted cost: a long document is scored per-chunk rather than whole, a visible relevance-score change for the downstream client. Rejected: document cap only (guard defeatable by one long document); lowering export-time --max_doc_length (silently truncates the tail instead of scoring it).

<!-- fr:journal kind=decision scope=spec id=measure-live-before-shipping created=2026-09-11T10:40:57 -->
### measure-live-before-shipping · decision · Sweep the live server now to set the cap from measurement

Operator authorised driving the batch sweep against the running ovms-retrieval pod during an early plan phase, accepting several deliberate OOM-kills and roughly ten seconds of refused connections each for the external downstream client. The alternative (ship a first-principles cap, measure post-merge) would have shipped an estimate; a CPU-arm throwaway pod would not produce a GPU-accurate curve.

<!-- fr:journal kind=discovery scope=spec id=fr-acceptance-add-broken-in-this-repo created=2026-09-11T10:45:46 -->
### fr-acceptance-add-broken-in-this-repo · discovery · fr acceptance add cannot append to this repo's matrix (indentation mismatch)

Every 'fr acceptance add' in frank fails and rolls back: 'append produced an invalid matrix'. Cause is purely formatting -- all 66 existing rows sit at indent 0 under 'rows:', while fr appends the new row at indent 2, which YAML rejects mid-sequence. Reproduced with a minimal probe row, so it is not content-dependent. Workaround used here: the three rows were hand-appended at indent 0 and validated with a YAML parse plus 'fr acceptance status' (9 -> 12 not-implemented). Durable fix is either normalising the matrix to indent 2 (a 66-row mechanical diff, out of scope for this goal) or making fr's writer match the file it is appending to. Worth raising upstream in super-fr after checking for an existing issue or PR.
