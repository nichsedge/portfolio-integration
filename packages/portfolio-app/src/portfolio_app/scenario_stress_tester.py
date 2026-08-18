"""
Scenario Stress Testing & Macroeconomic Crisis Simulator
Evaluates portfolio drawdown, emergency liquidity survival, and resilience against macro shocks.
"""

from typing import Dict, Any, List, Optional
import pendulum

# Preset shock parameters for macroeconomic stress scenarios
STRESS_SCENARIOS = {
    "market_crash_and_crypto_winter": {
        "name": "Market Crash & Crypto Winter",
        "description": "Severe global risk-off: Equities -30%, Crypto -60%, Commodities -15%, Fixed Income stable.",
        "shocks": {
            "Equities": -0.30,
            "Crypto": -0.60,
            "Commodities": -0.15,
            "Fixed Income": 0.0,
            "Cash & Equivalents": 0.0,
        },
        "fx_shock_pct": 0.05,        # USD gains 5%
        "expense_shock_pct": 0.0,
    },
    "idr_currency_crisis": {
        "name": "IDR Currency Devaluation & Inflation Spike",
        "description": "USD/IDR surges +25% (to ~22,000), living costs rise +20%, equities drop -15%.",
        "shocks": {
            "Equities": -0.15,
            "Crypto": 0.0,
            "Commodities": 0.20,      # Gold gains 20% in currency crisis
            "Fixed Income": -0.05,
            "Cash & Equivalents": 0.0,
        },
        "fx_shock_pct": 0.25,        # USD/IDR +25%
        "expense_shock_pct": 0.20,   # Living cost +20%
    },
    "zero_income_shock": {
        "name": "Severe Income Loss (0 Income Event)",
        "description": "Complete sudden loss of active income. Evaluates survival strictly on liquid cash reserves.",
        "shocks": {
            "Equities": 0.0,
            "Crypto": 0.0,
            "Commodities": 0.0,
            "Fixed Income": 0.0,
            "Cash & Equivalents": 0.0,
        },
        "fx_shock_pct": 0.0,
        "expense_shock_pct": 0.0,
        "income_override": 0.0,
    },
    "stagflation_and_rate_hike": {
        "name": "Stagflation & Rate Spike",
        "description": "High inflation (+15% expenses), bond yield compression (-8% mark-to-market), equities -20%.",
        "shocks": {
            "Equities": -0.20,
            "Crypto": -0.30,
            "Commodities": 0.15,
            "Fixed Income": -0.08,
            "Cash & Equivalents": 0.0,
        },
        "fx_shock_pct": 0.10,
        "expense_shock_pct": 0.15,
    }
}


def run_stress_test(
    holdings: List[Dict[str, Any]],
    exchange_rate: float,
    live_bank_cash_idr: float = 0.0,
    monthly_burn_idr: float = 4_000_000.0,
) -> Dict[str, Any]:
    """
    Executes stress test simulations across all macroeconomic scenarios.
    """
    total_assets_idr = 0.0
    for h in holdings:
        val_idr = h.get("value_idr") or 0.0
        if val_idr <= 0:
            val_idr = (h.get("value_usd") or 0.0) * exchange_rate
        total_assets_idr += val_idr

    consolidated_nw_idr = total_assets_idr + live_bank_cash_idr
    liquid_portfolio_cash = sum(
        h.get("value_idr", 0.0) for h in holdings if h.get("asset_class") == "Cash & Equivalents"
    )
    total_liquid_reserves = liquid_portfolio_cash + live_bank_cash_idr

    scenario_results = []
    max_drawdown_idr = 0.0
    max_drawdown_pct = 0.0

    for key, scenario in STRESS_SCENARIOS.items():
        shocks = scenario["shocks"]
        fx_multiplier = 1.0 + scenario["fx_shock_pct"]
        simulated_holdings_val_idr = 0.0

        for h in holdings:
            val_idr = h.get("value_idr") or 0.0
            val_usd = h.get("value_usd") or 0.0
            curr = (h.get("currency") or "IDR").upper()
            aclass = h.get("asset_class") or "Other"

            shock_factor = 1.0 + shocks.get(aclass, 0.0)

            # Apply FX shock for USD denominated assets
            if curr == "USD" or aclass == "Commodities" or h.get("category") == "Stablecoin":
                item_val_idr = (val_usd * exchange_rate * fx_multiplier) * shock_factor
            else:
                item_val_idr = val_idr * shock_factor

            simulated_holdings_val_idr += max(0.0, item_val_idr)

        post_shock_nw_idr = simulated_holdings_val_idr + live_bank_cash_idr
        drawdown_idr = max(0.0, consolidated_nw_idr - post_shock_nw_idr)
        drawdown_pct = round((drawdown_idr / consolidated_nw_idr * 100), 1) if consolidated_nw_idr > 0 else 0.0

        if drawdown_idr > max_drawdown_idr:
            max_drawdown_idr = drawdown_idr
            max_drawdown_pct = drawdown_pct

        # Shocked monthly living cost
        shocked_burn = monthly_burn_idr * (1.0 + scenario.get("expense_shock_pct", 0.0))
        liquid_runway_months = round(total_liquid_reserves / shocked_burn, 1) if shocked_burn > 0 else 999.0

        scenario_results.append({
            "scenario_key": key,
            "scenario_name": scenario["name"],
            "description": scenario["description"],
            "post_shock_net_worth_idr": round(post_shock_nw_idr, 0),
            "drawdown_idr": round(drawdown_idr, 0),
            "drawdown_pct": drawdown_pct,
            "shocked_monthly_burn_idr": round(shocked_burn, 0),
            "liquid_runway_months": liquid_runway_months,
            "survival_rating": "Safe" if liquid_runway_months >= 6.0 else "Warning" if liquid_runway_months >= 3.0 else "Vulnerable"
        })

    # Resilience score calculation (0-100)
    # Higher liquid runway + lower max drawdown = higher score
    runway_score = min(50.0, (total_liquid_reserves / monthly_burn_idr) * 3.5) if monthly_burn_idr > 0 else 50.0
    drawdown_penalty = min(50.0, max_drawdown_pct * 1.5)
    resilience_score = round(max(0.0, min(100.0, 50.0 + runway_score - drawdown_penalty)), 0)

    grade = (
        "Fortress (AAA)" if resilience_score >= 90
        else "Robust (AA)" if resilience_score >= 75
        else "Moderate (A)" if resilience_score >= 60
        else "Vulnerable (B)"
    )

    recommendations = []
    if total_liquid_reserves / monthly_burn_idr < 6.0:
        recommendations.append("Increase pure liquid bank / money market reserves to withstand sudden zero-income events.")
    if max_drawdown_pct > 25.0:
        recommendations.append("High drawdown risk detected in severe crash scenario. Consider boosting SBN fixed coupon allocation.")
    else:
        recommendations.append("Portfolio exhibits high macro stability due to heavy SBN and stablecoin weighting.")

    return {
        "baseline_net_worth_idr": round(consolidated_nw_idr, 0),
        "total_liquid_reserves_idr": round(total_liquid_reserves, 0),
        "resilience_score": resilience_score,
        "resilience_grade": grade,
        "max_simulated_drawdown_pct": max_drawdown_pct,
        "max_simulated_drawdown_idr": round(max_drawdown_idr, 0),
        "scenarios": scenario_results,
        "recommendations": recommendations
    }
