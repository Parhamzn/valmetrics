"""Piotroski F-Score — 9-point fundamental-health checklist.

Joseph Piotroski's 2000 paper showed that a simple 9-point binary scoring
system applied to value (high book-to-market) stocks earned a ~7.5% annual
abnormal return, with most of the excess concentrated in firms with high
F-Scores. The score is the sum of nine 0/1 signals across three dimensions:
profitability (4), leverage / liquidity / source of funds (3), and operating
efficiency (2).

Source: Piotroski, J., "Value Investing: The Use of Historical Financial
Statement Information to Separate Winners from Losers", Journal of Accounting
Research 38 (Supplement, 2000), pp. 1-41;
https://www.investopedia.com/terms/p/piotroski-score.asp.
"""

from __future__ import annotations

from apps.valuation.engine.types_piotroski import (
    PiotroskiCriterion,
    PiotroskiInputs,
    PiotroskiOutputs,
)


# Small buffer applied to the "no new shares" criterion to absorb rounding in
# diluted-share counts; Piotroski himself disqualifies any net issuance.
_DILUTION_TOLERANCE = 1.01


def _fmt_money(value: float | None) -> str:
    """Human-readable money formatter for explanation strings (B/M/K)."""
    if value is None:
        return "n/a"
    sign = "-" if value < 0 else ""
    a = abs(value)
    if a >= 1e12:
        return f"{sign}${a / 1e12:.2f}T"
    if a >= 1e9:
        return f"{sign}${a / 1e9:.2f}B"
    if a >= 1e6:
        return f"{sign}${a / 1e6:.2f}M"
    if a >= 1e3:
        return f"{sign}${a / 1e3:.2f}K"
    return f"{sign}${a:.2f}"


def _fmt_ratio(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.3f}"


def _classify(score: int) -> str:
    """Bucket the 0-9 score into Piotroski's standard interpretive bands."""
    if score >= 8:
        return "Strong (8-9)"
    if score >= 4:
        return "Neutral (4-7)"
    return "Weak (0-3)"


def piotroski_f_score(inputs: PiotroskiInputs) -> PiotroskiOutputs:
    """Compute the 9-criterion F-Score from latest- and prior-year fundamentals.

    For each criterion: if any required input is ``None`` (or a denominator is
    zero), award 0 and explain "Data unavailable". Otherwise apply the binary
    test exactly as specified in Piotroski (2000).

    Source: Piotroski (2000), Journal of Accounting Research.
    """
    criteria: list[PiotroskiCriterion] = []

    # -- 1. Positive net income ------------------------------------------------
    ni = inputs.net_income
    if ni is None:
        criteria.append(PiotroskiCriterion(
            name="Positive net income",
            description="Net income > 0 in the most recent year.",
            score=0, value=None, prior_value=None,
            explanation="Data unavailable",
        ))
    else:
        score = 1 if ni > 0 else 0
        criteria.append(PiotroskiCriterion(
            name="Positive net income",
            description="Net income > 0 in the most recent year.",
            score=score, value=ni, prior_value=None,
            explanation=(
                f"Net income is positive at {_fmt_money(ni)}"
                if score else f"Net income is non-positive at {_fmt_money(ni)}"
            ),
        ))

    # -- 2. Positive return on assets -----------------------------------------
    ta = inputs.total_assets
    if ni is None or ta is None or ta == 0:
        criteria.append(PiotroskiCriterion(
            name="Positive return on assets",
            description="ROA = net income / total assets > 0.",
            score=0, value=None, prior_value=None,
            explanation="Data unavailable",
        ))
    else:
        roa = ni / ta
        score = 1 if roa > 0 else 0
        criteria.append(PiotroskiCriterion(
            name="Positive return on assets",
            description="ROA = net income / total assets > 0.",
            score=score, value=roa, prior_value=None,
            explanation=(
                f"ROA is positive at {roa * 100:.2f}%"
                if score else f"ROA is non-positive at {roa * 100:.2f}%"
            ),
        ))

    # -- 3. Positive operating cash flow --------------------------------------
    cfo = inputs.operating_cash_flow
    if cfo is None:
        criteria.append(PiotroskiCriterion(
            name="Positive operating cash flow",
            description="Operating cash flow > 0 in the most recent year.",
            score=0, value=None, prior_value=None,
            explanation="Data unavailable",
        ))
    else:
        score = 1 if cfo > 0 else 0
        criteria.append(PiotroskiCriterion(
            name="Positive operating cash flow",
            description="Operating cash flow > 0 in the most recent year.",
            score=score, value=cfo, prior_value=None,
            explanation=(
                f"Operating cash flow is positive at {_fmt_money(cfo)}"
                if score else
                f"Operating cash flow is non-positive at {_fmt_money(cfo)}"
            ),
        ))

    # -- 4. Earnings quality: CFO > NI ----------------------------------------
    if cfo is None or ni is None:
        criteria.append(PiotroskiCriterion(
            name="Earnings quality (CFO > NI)",
            description="Cash from operations exceeds net income (accruals quality).",
            score=0, value=None, prior_value=None,
            explanation="Data unavailable",
        ))
    else:
        score = 1 if cfo > ni else 0
        criteria.append(PiotroskiCriterion(
            name="Earnings quality (CFO > NI)",
            description="Cash from operations exceeds net income (accruals quality).",
            score=score, value=cfo, prior_value=ni,
            explanation=(
                f"CFO {_fmt_money(cfo)} exceeds net income {_fmt_money(ni)}"
                if score else
                f"CFO {_fmt_money(cfo)} does not exceed net income {_fmt_money(ni)}"
            ),
        ))

    # -- 5. Long-term debt decreased YoY --------------------------------------
    ltd = inputs.long_term_debt
    pltd = inputs.prior_long_term_debt
    if ltd is None or pltd is None:
        criteria.append(PiotroskiCriterion(
            name="Long-term debt decreased YoY",
            description="Long-term debt fell relative to the prior year.",
            score=0, value=None, prior_value=None,
            explanation="Data unavailable",
        ))
    else:
        score = 1 if ltd < pltd else 0
        criteria.append(PiotroskiCriterion(
            name="Long-term debt decreased YoY",
            description="Long-term debt fell relative to the prior year.",
            score=score, value=ltd, prior_value=pltd,
            explanation=(
                f"Long-term debt fell from {_fmt_money(pltd)} to {_fmt_money(ltd)}"
                if score else
                f"Long-term debt did not fall (prior {_fmt_money(pltd)} -> current {_fmt_money(ltd)})"
            ),
        ))

    # -- 6. Current ratio increased YoY ---------------------------------------
    ca, cl = inputs.current_assets, inputs.current_liabilities
    pca, pcl = inputs.prior_current_assets, inputs.prior_current_liabilities
    if (
        ca is None or cl is None or pca is None or pcl is None
        or cl == 0 or pcl == 0
    ):
        criteria.append(PiotroskiCriterion(
            name="Current ratio increased YoY",
            description="Current assets / current liabilities improved.",
            score=0, value=None, prior_value=None,
            explanation="Data unavailable",
        ))
    else:
        cur = ca / cl
        prior_cur = pca / pcl
        score = 1 if cur > prior_cur else 0
        criteria.append(PiotroskiCriterion(
            name="Current ratio increased YoY",
            description="Current assets / current liabilities improved.",
            score=score, value=cur, prior_value=prior_cur,
            explanation=(
                f"Current ratio improved from {_fmt_ratio(prior_cur)} to {_fmt_ratio(cur)}"
                if score else
                f"Current ratio did not improve ({_fmt_ratio(prior_cur)} -> {_fmt_ratio(cur)})"
            ),
        ))

    # -- 7. No new shares issued ----------------------------------------------
    sh, psh = inputs.diluted_shares, inputs.prior_diluted_shares
    if sh is None or psh is None:
        criteria.append(PiotroskiCriterion(
            name="No new shares issued",
            description="Diluted share count did not increase YoY.",
            score=0, value=None, prior_value=None,
            explanation="Data unavailable",
        ))
    else:
        score = 1 if sh <= psh * _DILUTION_TOLERANCE else 0
        criteria.append(PiotroskiCriterion(
            name="No new shares issued",
            description="Diluted share count did not increase YoY.",
            score=score, value=sh, prior_value=psh,
            explanation=(
                f"Diluted shares ~flat or down (prior {psh:,.0f} -> current {sh:,.0f})"
                if score else
                f"Diluted shares increased (prior {psh:,.0f} -> current {sh:,.0f})"
            ),
        ))

    # -- 8. Gross margin improved YoY ----------------------------------------
    gp, rev = inputs.gross_profit, inputs.total_revenue
    pgp, prev = inputs.prior_gross_profit, inputs.prior_total_revenue
    if (
        gp is None or rev is None or pgp is None or prev is None
        or rev == 0 or prev == 0
    ):
        criteria.append(PiotroskiCriterion(
            name="Gross margin improved YoY",
            description="Gross profit / revenue improved relative to the prior year.",
            score=0, value=None, prior_value=None,
            explanation="Data unavailable",
        ))
    else:
        gm = gp / rev
        prior_gm = pgp / prev
        score = 1 if gm > prior_gm else 0
        criteria.append(PiotroskiCriterion(
            name="Gross margin improved YoY",
            description="Gross profit / revenue improved relative to the prior year.",
            score=score, value=gm, prior_value=prior_gm,
            explanation=(
                f"Gross margin improved from {prior_gm * 100:.2f}% to {gm * 100:.2f}%"
                if score else
                f"Gross margin did not improve ({prior_gm * 100:.2f}% -> {gm * 100:.2f}%)"
            ),
        ))

    # -- 9. Asset turnover improved YoY ---------------------------------------
    pta = inputs.prior_total_assets
    if (
        rev is None or ta is None or prev is None or pta is None
        or ta == 0 or pta == 0
    ):
        criteria.append(PiotroskiCriterion(
            name="Asset turnover improved YoY",
            description="Revenue / total assets improved relative to the prior year.",
            score=0, value=None, prior_value=None,
            explanation="Data unavailable",
        ))
    else:
        at = rev / ta
        prior_at = prev / pta
        score = 1 if at > prior_at else 0
        criteria.append(PiotroskiCriterion(
            name="Asset turnover improved YoY",
            description="Revenue / total assets improved relative to the prior year.",
            score=score, value=at, prior_value=prior_at,
            explanation=(
                f"Asset turnover improved from {_fmt_ratio(prior_at)} to {_fmt_ratio(at)}"
                if score else
                f"Asset turnover did not improve ({_fmt_ratio(prior_at)} -> {_fmt_ratio(at)})"
            ),
        ))

    total = sum(c.score for c in criteria)
    return PiotroskiOutputs(
        criteria=criteria,
        total_score=total,
        classification=_classify(total),
    )
