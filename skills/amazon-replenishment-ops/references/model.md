# Amazon Replenishment Operations Model

## Feishu Documents

- Parameter Bitable app token: `RjbibHNtRaIrFes1d6zcMEUknEe`
- Main table: `备货参数汇总` (`tblcPBSgbpp1fMi7`)
- Upper-range table: `计算上限范围` (`tbl2ORROaOPR66pz`)
- Sales/inventory spreadsheet: `T4B8sEPMehlq5Utw3WWcaZAwnUc`

Use the installed `feishu-api` skill for credentials and API access.

## Station Resolution

1. List the views of the main Bitable table.
2. Match the requested station to an exact view name.
3. For a split station such as `VA_US`, combine views whose names match `VA_US`, `VA_US_1`, and `VA_US_2`, then deduplicate records by `record_id`.
4. Match the source sheet by exact title in the spreadsheet.
5. Match the upper-range record by `备货站点`.

Do not guess a station when no matching view, sheet, or range record exists. List available stations instead.

## Operations Parameters

### AI Amazon Monthly

Meaning: estimated average monthly Amazon sales during the future replenishment lead-time window.

Rules:

- Match `seller_sku` first.
- If no exact SKU match exists, match `asin1` to the source sheet `asin`.
- When multiple ASIN rows exist, prefer the row with the longest non-zero sales history.
- The forecast is a monthly rate, not total sales over the full lead-time window.
- Consider recent trend, incomplete current month, Q4/holiday demand, promotions, stockouts, and lifecycle changes.
- Keep one decimal place.
- Scale the station-wide `price × AI亚马逊月均` total to the requested target.

### AI Lower Limit

Meaning: a business floor that operations never wants inventory to fall below.

- Hot SKUs may receive a positive lower limit.
- Non-hot SKUs normally use `0`.
- A SKU with zero recent sales but `是否计算 = true` should normally use `0`, not a positive lower limit.

### AI Monthly Sales Deviation

Meaning: absolute monthly unit upside above the monthly average.

- Use it to protect hot SKUs and to represent possible future sales for currently slow or zero-sales SKUs.
- Non-hot SKU deviations should stay small.
- A currently zero-sales active SKU should usually use a small positive deviation so `AI上限` remains at least 1.

## Upper-Limit Formulas

For a SKU:

```text
AI月均销量 = AI亚马逊月均 + 独立站月均
AI上限 = ceiling(
  AI月均销量
  + AI月均销量 / 30 × 物流偏离度
  + AI销量偏离度 / 30 × 补货周期
  + AI下限
)
AI上限货值 = price × AI上限
```

For the station range:

```text
目标月均总货值 = 目标亚马逊月销货值 + 独立站月销货值
最低上限货值 = 目标亚马逊月销货值 / 目标售出率 + 1/4 × 目标月均总货值
最高上限货值 = 目标亚马逊月销货值 / 目标售出率 + 1/2 × 目标月均总货值
```

Target upper value:

- Compute the share of SKUs whose replenishment cycle is closer to 30 days.
- A station dominated by 30-day SKUs should target near the maximum.
- A station dominated by 15-day SKUs should target near the minimum.
- Keep a small safety margin below the maximum and above the minimum.

## Allocation Heuristic

1. Build the no-buffer upper limit for every active SKU.
2. For non-hot SKUs:
   - Set lower limit to 0.
   - Cap deviation at roughly 20% of monthly sales, and also below the prior company pattern.
3. For hot SKUs:
   - Determine how much additional upper-limit goods value is needed to reach the target upper value.
   - Allocate that value in proportion to each SKU's monthly goods value.
   - Split the added buffer between lower limit and deviation using the prior company pattern as a guide.
   - Cap the lower limit by roughly half a month of sales when that cap is material.
4. Fine-tune using the highest-priced hot SKU so the station total lands just below the maximum.
5. Enforce active-SKU invariants after allocation.

## Validation

Required checks:

- `AI亚马逊月均货值` is close to the Amazon monthly target.
- `AI上限货值` is inside the computed minimum/maximum range.
- Final upper value is near the high or low end according to the cycle mix.
- No record has `是否计算 = true` and `AI上限 = 0`.
- No supply-chain fields or out-of-station records changed.

## Known Limitations

- Carton/package quantity is not present in the current two documents.
- The skill does not set independent-site monthly sales.
- The skill does not alter formulas or replenishment-quantity logic.
- A positive minimum inventory does not guarantee a full carton can be shipped.
