"""telegram-bridge — the alert-agent's sole owner of the Telegram bot token.

Inbound: long-poll getUpdates, route allowlisted messages through the persistent
agent session (POST /session/send), reply. Outbound: the deterministic sender the
cron/webhook handlers use to post agent narratives (with a fallback when the agent
times out). Single process = single getUpdates consumer (replicas:1 + Recreate).
"""
