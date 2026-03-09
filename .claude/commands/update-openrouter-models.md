# Update OpenRouter Free Models

Refresh the free cloud model list in LiteLLM's values.yaml to match what's currently available on OpenRouter.

## Steps

1. **Fetch current free models** from the OpenRouter API:
   ```bash
   curl -s https://openrouter.ai/api/v1/models | python3 -c "
   import json, sys
   data = json.load(sys.stdin)
   for m in sorted(data.get('data', []), key=lambda x: x['id']):
       pricing = m.get('pricing', {})
       if pricing.get('prompt', '0') == '0' and pricing.get('completion', '0') == '0':
           ctx = m.get('context_length', '?')
           print(f'{m[\"id\"]:60s} ctx={ctx:>8}  {m.get(\"name\", \"?\")}')
   "
   ```

2. **Read current config** at `apps/litellm/values.yaml` and identify the CLOUD MODELS section.

3. **Compare** the configured `openrouter/` model IDs against the fetched list. Flag any that no longer exist as free.

4. **Select replacements** for retired models. Prioritize:
   - Large MoE models (strongest reasoning per free token)
   - Models with 128K+ context
   - Diverse providers (avoid all models from one vendor)
   - Open-weight models where possible (better data privacy)

5. **Update `apps/litellm/values.yaml`** — replace only the CLOUD MODELS entries. Keep the LOCAL MODELS section untouched. Each cloud model entry must follow this format:
   ```yaml
       # <Model Name> — <brief description>, <context length>
       # <strength summary>
       # <data policy: one of ✅ or ⚠> Data: <provider/policy note>
       - model_name: <short-alias>
         litellm_params:
           model: openrouter/<openrouter-model-id>
           api_key: os.environ/OPENROUTER_API_KEY
   ```

6. **Push and sync** — commit, push, then sync the ArgoCD `litellm` app:
   ```bash
   git add apps/litellm/values.yaml
   git commit -m "fix(litellm): update free OpenRouter model list"
   git push
   argocd app sync litellm --port-forward --port-forward-namespace argocd
   ```

7. **Verify** each new model by sending a test request through LiteLLM:
   ```bash
   source .env
   for model in <model1> <model2> ...; do
     echo "--- $model ---"
     curl -s http://192.168.55.206:4000/v1/chat/completions \
       -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
       -H "Content-Type: application/json" \
       -d "{\"model\": \"$model\", \"messages\": [{\"role\": \"user\", \"content\": \"Say hi in one word\"}], \"max_tokens\": 10}" \
       | python3 -c "import json,sys; r=json.load(sys.stdin); print(r.get('choices',[{}])[0].get('message',{}).get('content','') or r.get('error',{}).get('message','UNKNOWN ERROR'))" 2>/dev/null
   done
   ```
   Report which models work and which fail. If any fail, check the model ID against the API list and fix.
