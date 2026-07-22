"""Cost tier mapping (cost.py). Pins the Fable 5 tier added 2026-07-22 and the
'unknown model -> most expensive tier' safety default."""

import config
import cost


def test_tier_maps_each_model_id():
    assert cost._tier("claude-fable-5") == "fable"
    assert cost._tier("claude-opus-4-8") == "opus"
    assert cost._tier("claude-sonnet-4-6") == "sonnet"
    assert cost._tier("claude-haiku-4-5-20251001") == "haiku"


def test_tier_unknown_defaults_to_most_expensive():
    # Fable is now the priciest tier, so an unrecognized id must land there to
    # avoid silently undercounting.
    assert cost._tier("some-future-model") == "fable"
    assert cost._tier("") == "fable"
    assert cost._tier(None) == "fable"


def test_fable_priced_above_opus():
    fable = cost.cost_of("claude-fable-5", 1_000_000, 1_000_000)
    opus = cost.cost_of("claude-opus-4-8", 1_000_000, 1_000_000)
    assert fable == config.FABLE_PRICE_IN + config.FABLE_PRICE_OUT   # 10 + 50
    assert fable == 2 * opus


def test_digest_model_prices_as_fable():
    # The live wiring: digest.CLAUDE_MODEL feeds cost.record; confirm it tiers
    # as fable now that the digest runs on Fable 5.
    import digest
    assert cost._tier(digest.CLAUDE_MODEL) == "fable"
