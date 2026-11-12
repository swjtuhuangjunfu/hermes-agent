"""Claude Haiku 5.5 has a 1M-token window
(https://platform.claude.com/docs/en/models/haiku-5-5/overview). Without a live lookup it must not
fall through to the 200K "claude" catch-all (or Bedrock's 128K default) — #154406. Haiku 4.5 keeps
its 200K window."""

import pytest

from agent.bedrock_adapter import get_bedrock_context_length
from agent.model_metadata import DEFAULT_CONTEXT_LENGTHS, _longest_key_match


@pytest.mark.parametrize("model", ["claude-haiku-5-5", "claude-haiku-5-5-20261007", "claude-haiku-5"])
def test_haiku_5_offline_window_is_1m(model):
    hit = _longest_key_match(DEFAULT_CONTEXT_LENGTHS, model)
    assert hit is not None and hit[1] == 1_000_000


@pytest.mark.parametrize("model", ["claude-haiku-4-5", "claude-haiku-4-5-20251001", "claude-3-5-haiku"])
def test_older_haiku_keeps_200k(model):
    hit = _longest_key_match(DEFAULT_CONTEXT_LENGTHS, model)
    assert hit is not None and hit[1] == 200_000


@pytest.mark.parametrize("scope", ["", "us.", "global."])
def test_haiku_5_bedrock_window_is_1m(scope):
    assert get_bedrock_context_length(f"{scope}anthropic.claude-haiku-5-5", probe=False) == 1_000_000
    assert get_bedrock_context_length(f"{scope}anthropic.claude-haiku-4-5", probe=False) == 200_000
