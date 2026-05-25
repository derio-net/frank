"""Test environment setup.

`facts.GOATCOUNTER_TOKEN` is captured from the environment at import time and
the GoatCounter helper short-circuits to `{}` when it's empty. The digest
tests assert that GoatCounter is actually queried, so a non-empty token must
be present before `ai_alert_helper.facts` is first imported. Setting it here
(conftest loads before any test module) guarantees that ordering.
"""
import os

os.environ.setdefault("OBS_GOATCOUNTER_API_TOKEN", "test-token")
