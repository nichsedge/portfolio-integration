"""
Unit tests for MCP Server and JSON-RPC dispatching.
"""

from portfolio_app.mcp_server import (
    TOOLS_SCHEMA,
    tool_get_fire_simulation,
    tool_get_passive_income_projection,
    tool_get_rebalancing_plan,
    tool_get_scenario_stress_test,
    tool_get_tax_efficiency_audit,
)


def test_mcp_tools_schema():
    assert len(TOOLS_SCHEMA) >= 10
    tool_names = [t["name"] for t in TOOLS_SCHEMA]
    assert "get_portfolio_overview" in tool_names
    assert "get_holdings_breakdown" in tool_names
    assert "get_rebalancing_plan" in tool_names
    assert "get_passive_income_projection" in tool_names
    assert "get_fire_simulation" in tool_names
    assert "get_tax_efficiency_audit" in tool_names
    assert "get_scenario_stress_test" in tool_names
    assert "get_cashflow_analysis" in tool_names
    assert "get_unified_financial_state" in tool_names
    assert "crypto_get_token_prices" in tool_names
    assert "crypto_screen_yields" in tool_names
    assert "crypto_audit_protocol" in tool_names
    assert "crypto_stablecoin_summary" in tool_names


def test_mcp_rebalancing_and_passive_income_tools():
    # If snapshot data is available in data dir, verify responses
    reb = tool_get_rebalancing_plan(monthly_deposit_idr=10000000.0)
    if "error" not in reb:
        assert "rebalancing_plan" in reb
        assert reb["rebalancing_plan"]["deposit_amount_idr"] == 10000000.0

    pi = tool_get_passive_income_projection()
    if "error" not in pi:
        assert "passive_income_projection" in pi
        assert "projected_monthly_passive_income_idr" in pi["passive_income_projection"]

    fire_res = tool_get_fire_simulation()
    if "error" not in fire_res:
        assert "fire_simulation" in fire_res
        assert "fire_number_idr" in fire_res["fire_simulation"]

    tax_res = tool_get_tax_efficiency_audit()
    if "error" not in tax_res:
        assert "tax_audit" in tax_res
        assert "tax_efficiency_score" in tax_res["tax_audit"]

    stress_res = tool_get_scenario_stress_test()
    if "error" not in stress_res:
        assert "stress_test" in stress_res
        assert "resilience_score" in stress_res["stress_test"]


def test_mcp_stdio_server_protocol(monkeypatch):
    import io
    import json

    from portfolio_app.mcp_server import run_mcp_stdio_server

    input_data = (
        '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}\n'
        '{"jsonrpc": "2.0", "method": "notifications/initialized"}\n'
        '{"jsonrpc": "2.0", "id": 2, "method": "ping"}\n'
        '{"jsonrpc": "2.0", "id": 3, "method": "tools/list"}\n'
    )
    fake_stdin = io.StringIO(input_data)
    fake_stdout = io.StringIO()

    monkeypatch.setattr("sys.stdin", fake_stdin)
    monkeypatch.setattr("sys.stdout", fake_stdout)

    run_mcp_stdio_server()

    output_lines = [json.loads(line) for line in fake_stdout.getvalue().strip().split("\n") if line.strip()]
    assert len(output_lines) == 3

    # Check initialize response
    assert output_lines[0]["jsonrpc"] == "2.0"
    assert output_lines[0]["id"] == 1
    assert "serverInfo" in output_lines[0]["result"]

    # Check ping response
    assert output_lines[1]["jsonrpc"] == "2.0"
    assert output_lines[1]["id"] == 2
    assert output_lines[1]["result"] == {}

    # Check tools/list response
    assert output_lines[2]["jsonrpc"] == "2.0"
    assert output_lines[2]["id"] == 3
    assert "tools" in output_lines[2]["result"]

