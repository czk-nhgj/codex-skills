---
name: amazon-replenishment-ops
description: Configure operations-side Amazon replenishment parameters in Feishu for a specified station using a target Amazon monthly goods value and target sell-through rate. Do not use for supply-chain parameters, formula changes, or order placement.
---

# Amazon Replenishment Ops

Set the three operations-side parameters for one Feishu replenishment station:

- `AI亚马逊月均`
- `AI下限`
- `AI销量偏离度`

The workflow uses the matching station view in 《AI填写运营备货参数》, the station sheet in 《销售库存表》, and the station row in 《计算上限范围》.

## Required Inputs

Require all three inputs:

- Station, for example `NE_US`
- Target Amazon monthly goods value, for example `40000`
- Target sell-through rate, for example `50%`

If the station or either target is missing, ask for it before running the script.

## Read First

Before calculating or editing, read [references/model.md](references/model.md). It contains the Feishu tokens, field meanings, formulas, matching rules, invariants, and known limitations.

This skill depends on the installed `$feishu-api` skill for credentials and API access. Do not print or copy the Feishu app secret.

## Workflow

1. Run a preview. The script defaults to read-only mode.
2. Review the proposed monthly goods value, upper-limit value range, target upper value, cycle mix, hot/non-hot allocation, and validation warnings.
3. Show the user a concise summary. Ask for explicit confirmation before writing.
4. Only after confirmation, run the same command with `--apply`.
5. Verify the written records again. Report actual totals and any remaining assumptions.

Preview:

```bash
python scripts/set_replenishment.py \
  --station NE_US \
  --target-amazon-value 40000 \
  --target-sell-through "50%" \
  --preview
```

Apply after confirmation:

```bash
python scripts/set_replenishment.py \
  --station NE_US \
  --target-amazon-value 40000 \
  --target-sell-through "50%" \
  --apply
```

If `python` is unavailable, use the Codex bundled Python runtime.

## Parameter Rules

### AI Amazon Monthly

- Match historical sales by `seller_sku` first.
- If there is no exact SKU match, match by the same `ASIN`.
- If neither exists, keep monthly sales at `0.0`; a later minimum deviation will keep the SKU active.
- Use recent months rather than a fixed historical average. Adjust weighting for stability, trend, incomplete current month, promotions, seasonality, and obvious anomalies.
- Calculate goods value as `price × AI亚马逊月均`.
- Scale the station total to the target monthly goods value. Keep one decimal place.

### Upper-Limit Range

- Write `目标亚马逊月销货值` and `目标售出率` to the station row in 《计算上限范围》.
- Read or compute `最低上限货值` and `最高上限货值`.
- Place the final `AI上限货值` total inside that range.
- More 30-day replenishment-cycle SKUs means closer to the maximum.
- More 15-day SKUs means closer to the minimum.

### Lower Limit and Monthly Sales Deviation

- Hot SKUs: prioritize avoiding stockouts. Allocate more buffer to SKUs with larger monthly goods value.
- Non-hot SKUs: prioritize avoiding overstock. Keep `AI下限 = 0` and use a small deviation only.
- Use `SKU理论售出率` as a guardrail. Hot SKUs may have lower theoretical sell-through, but high-volume SKUs should not be left underprotected.
- If recent sales are zero but `是否计算 = true`, use `AI下限 = 0` and a small positive `AI销量偏离度` rather than a positive lower limit.

## Hard Invariants

After calculation and after any write:

- Every SKU with `是否计算 = true` must have `AI上限 >= 1`.
- Do not change supply-chain parameters: `补货时长`, `补货周期`, `物流偏离度`.
- Do not modify records outside the selected station.
- Do not include the independent-site monthly value in this skill's writes; the existing value remains an input to the upper-range formula.
- Keep package/carton quantity validation out of scope for this version. State that limitation if an upper limit is very small.

## Final Response

Report:

- Station and targets
- Number of SKUs updated
- `AI亚马逊月均货值` total
- Upper-limit value range
- Final `AI上限货值` total
- Zero-upper invariant result
- Any unresolved assumptions, especially packaging or independent-site values
