import pytest
from app.services.token_tracker import calculate_claude_cost, record_claude_usage

class MockUsage:
    def __init__(self, input_tokens=0, output_tokens=0, cache_creation_input_tokens=0, cache_read_input_tokens=0):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_creation_input_tokens = cache_creation_input_tokens
        self.cache_read_input_tokens = cache_read_input_tokens

def test_calculate_claude_cost_standard():
    # 1,000,000 input @ $3.00/MTok = $3.00
    # 1,000,000 output @ $15.00/MTok = $15.00
    cost = calculate_claude_cost(1_000_000, 1_000_000, 0, 0)
    assert abs(cost - 18.0) < 1e-6

def test_calculate_claude_cost_with_caching():
    # 500,000 regular input @ $3.00/M = $1.50
    # 200,000 cache write @ $3.75/M = $0.75
    # 1,000,000 cache read @ $0.30/M = $0.30
    # 100,000 output @ $15.00/M = $1.50
    # Total = 1.50 + 0.75 + 0.30 + 1.50 = $4.05
    cost = calculate_claude_cost(500_000, 100_000, 200_000, 1_000_000)
    assert abs(cost - 4.05) < 1e-6

def test_record_claude_usage_aggregation():
    usage = MockUsage(
        input_tokens=1500,
        output_tokens=350,
        cache_creation_input_tokens=500,
        cache_read_input_tokens=2000
    )
    res = record_claude_usage(usage, model="claude-sonnet-4-6")
    assert res is not None
    # total input tokens reported in console = regular input + cache creation + cache read
    assert res["total_input_tokens"] == 1500 + 500 + 2000
    assert res["output_tokens"] == 350
    expected_cost = (1500 * 3.00 / 1e6) + (500 * 3.75 / 1e6) + (2000 * 0.30 / 1e6) + (350 * 15.00 / 1e6)
    assert abs(res["cost_usd"] - expected_cost) < 1e-6
