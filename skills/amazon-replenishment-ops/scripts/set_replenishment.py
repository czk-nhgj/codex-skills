#!/usr/bin/env python3
"""Configure operations-side Amazon replenishment parameters in Feishu."""

from __future__ import annotations

import argparse
import calendar
import datetime as dt
import json
import math
import os
import re
import statistics
import sys
from collections import Counter
from pathlib import Path


PARAM_APP_TOKEN = "RjbibHNtRaIrFes1d6zcMEUknEe"
PARAM_TABLE_ID = "tblcPBSgbpp1fMi7"
RANGE_TABLE_ID = "tbl2ORROaOPR66pz"
SHEET_TOKEN = "T4B8sEPMehlq5Utw3WWcaZAwnUc"
SHEET_RANGE_END_COLUMN = "AN"
SHEET_CHUNK_ROWS = 200
TARGET_UPPER_MARGIN_RATIO = 0.005


def import_feishu_client():
    candidates = []
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        candidates.append(Path(codex_home) / "skills" / "feishu-api" / "scripts")
    candidates.append(Path.home() / ".codex" / "skills" / "feishu-api" / "scripts")
    candidates.append(Path(__file__).resolve().parents[2] / "feishu-api" / "scripts")

    for candidate in candidates:
        if (candidate / "feishu_client.py").exists():
            sys.path.insert(0, str(candidate))
            from feishu_client import (  # noqa: PLC0415
                api_request,
                collect_paginated,
                load_config,
            )

            return api_request, collect_paginated, load_config

    raise RuntimeError(
        "Cannot find feishu_client.py. Install the feishu-api skill first."
    )


api_request, collect_paginated, load_config = import_feishu_client()


def as_float(value):
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def is_true(value):
    if value is True:
        return True
    return str(value or "").strip().lower() in {"true", "1", "yes", "是"}


def parse_rate(value):
    text = str(value).strip()
    if text.endswith("%"):
        rate = float(text[:-1]) / 100
    else:
        rate = float(text)
        if rate > 1:
            rate = rate / 100
    if not 0 < rate <= 1:
        raise ValueError("Target sell-through rate must be in (0, 1].")
    return rate


def normalize_station(value):
    return re.sub(r"[^A-Z0-9]+", "_", str(value).strip().upper()).strip("_")


def station_base(value):
    return re.sub(r"_[12]$", "", normalize_station(value))


def chunked(items, size):
    for index in range(0, len(items), size):
        yield items[index : index + size]


def fetch_sheet_metadata(config):
    data = api_request(
        config,
        "GET",
        f"/sheets/v3/spreadsheets/{SHEET_TOKEN}/sheets/query",
    )
    return data.get("sheets", [])


def resolve_source_sheet(config, station):
    sheets = fetch_sheet_metadata(config)
    target = station_base(station)
    for sheet in sheets:
        sheet_name = normalize_station(sheet.get("title"))
        if sheet_name in {target, f"{target}_TOTAL"}:
            return sheet
    available = sorted(str(sheet.get("title") or "") for sheet in sheets)
    raise RuntimeError(
        f"No source sheet found for station {station}. Available: {available}"
    )


def fetch_sheet_rows(config, sheet):
    sheet_id = sheet["sheet_id"]
    row_count = int(
        (sheet.get("grid_properties") or {}).get("row_count") or 0
    )
    if row_count <= 0:
        raise RuntimeError(f"Source sheet {sheet_id} has no rows.")

    rows = []
    for start in range(1, row_count + 1, SHEET_CHUNK_ROWS):
        end = min(row_count, start + SHEET_CHUNK_ROWS - 1)
        data = api_request(
            config,
            "GET",
            f"/sheets/v2/spreadsheets/{SHEET_TOKEN}/values/"
            f"{sheet_id}!A{start}:{SHEET_RANGE_END_COLUMN}{end}",
        )
        rows.extend(data.get("valueRange", {}).get("values", []))
    return rows


def build_source_index(rows):
    if len(rows) < 2:
        raise RuntimeError("Source sheet does not contain a header row.")

    header = rows[1]
    column = {
        str(name).strip(): index
        for index, name in enumerate(header)
        if name not in (None, "")
    }
    required = {"seller_sku", "asin", "price", "是否热销", "下限", "单月销量偏离度"}
    missing = sorted(required - set(column))
    if missing:
        raise RuntimeError(f"Source sheet is missing columns: {missing}")

    remote_index = column.get("远程配送")
    sales_end = remote_index if remote_index is not None else min(11, len(header))
    sales_indexes = list(range(4, sales_end))
    sales_months = [str(header[index] or "") for index in sales_indexes]

    by_sku = {}
    by_asin = {}
    for raw_row in rows[3:]:
        padded = list(raw_row) + [None] * max(0, len(header) - len(raw_row))
        sku = str(padded[column["seller_sku"]] or "").strip()
        asin = str(padded[column["asin"]] or "").strip()
        if not sku:
            continue
        record = {
            "sku": sku,
            "asin": asin,
            "price": as_float(padded[column["price"]]),
            "hot": str(padded[column["是否热销"]] or "").strip(),
            "source_lower": as_float(padded[column["下限"]]),
            "source_deviation": as_float(
                padded[column["单月销量偏离度"]]
            ),
            "sales": [
                as_float(padded[index]) for index in sales_indexes
            ],
        }
        by_sku[sku] = record
        if asin:
            current = by_asin.get(asin)
            if current is None or sum(record["sales"]) > sum(current["sales"]):
                by_asin[asin] = record

    return {
        "by_sku": by_sku,
        "by_asin": by_asin,
        "sales_months": sales_months,
    }


def resolve_main_views(config, station):
    views = collect_paginated(
        config,
        f"/bitable/v1/apps/{PARAM_APP_TOKEN}/tables/{PARAM_TABLE_ID}/views",
        item_key="items",
        page_size=100,
    )
    target = station_base(station)
    exact = [
        view for view in views if normalize_station(view.get("view_name")) == target
    ]
    if exact:
        return exact

    matched = [
        view
        for view in views
        if station_base(view.get("view_name")) == target
    ]
    if matched:
        return matched

    available = sorted(str(view.get("view_name") or "") for view in views)
    raise RuntimeError(
        f"No main-table view found for station {station}. Available: {available}"
    )


def fetch_station_records(config, views):
    records_by_id = {}
    for view in views:
        records = collect_paginated(
            config,
            f"/bitable/v1/apps/{PARAM_APP_TOKEN}/tables/{PARAM_TABLE_ID}/records",
            params={"view_id": view["view_id"]},
            item_key="items",
            page_size=500,
        )
        for record in records:
            records_by_id[record["record_id"]] = record
    return list(records_by_id.values())


def fetch_range_record(config, station):
    records = collect_paginated(
        config,
        f"/bitable/v1/apps/{PARAM_APP_TOKEN}/tables/{RANGE_TABLE_ID}/records",
        item_key="items",
        page_size=500,
    )
    target = station_base(station)
    for record in records:
        if station_base(record.get("fields", {}).get("备货站点")) == target:
            return record
    available = sorted(
        str(record.get("fields", {}).get("备货站点") or "")
        for record in records
    )
    raise RuntimeError(
        f"No upper-range row found for station {station}. Available: {available}"
    )


def month_projection_factor(label):
    match = re.fullmatch(r"(\d{4})[.\-/](\d{1,2})", str(label).strip())
    if not match:
        return 1.0
    year, month = int(match.group(1)), int(match.group(2))
    today = dt.date.today()
    if year != today.year or month != today.month:
        return 1.0
    days_in_month = calendar.monthrange(year, month)[1]
    return days_in_month / max(today.day, 1)


def linear_slope(values):
    if len(values) < 2:
        return 0.0
    x_mean = (len(values) - 1) / 2
    y_mean = sum(values) / len(values)
    numerator = sum(
        (index - x_mean) * (value - y_mean)
        for index, value in enumerate(values)
    )
    denominator = sum((index - x_mean) ** 2 for index in range(len(values)))
    return numerator / denominator if denominator else 0.0


def forecast_monthly_rate(sales_months, sales):
    projected = []
    for label, value in zip(sales_months, sales):
        projected.append(value * month_projection_factor(label))

    if not projected:
        return 0.0

    recent = projected[-4:]
    if len(recent) == 1:
        return recent[0]

    slope = linear_slope(recent)
    mean = sum(recent) / len(recent)
    normalized_trend = abs(slope) / max(abs(mean), 1e-9)

    if normalized_trend < 0.08:
        base_weights = [0.20, 0.25, 0.25, 0.30]
    elif slope > 0:
        base_weights = [0.10, 0.20, 0.30, 0.40]
    else:
        base_weights = [0.15, 0.20, 0.30, 0.35]

    weights = base_weights[-len(recent) :]
    weight_total = sum(weights)
    weights = [weight / weight_total for weight in weights]
    return sum(value * weight for value, weight in zip(recent, weights))


def build_monthly_forecast(records, source_index, target_value):
    active = [
        record
        for record in records
        if is_true(record.get("fields", {}).get("是否计算"))
    ]
    if not active:
        raise RuntimeError("No active SKU has 是否计算 = true.")

    rows = []
    for record in active:
        fields = record.get("fields", {})
        sku = str(fields.get("seller_sku") or "").strip()
        asin = str(fields.get("asin1") or "").strip()
        source = source_index["by_sku"].get(sku)
        match_type = "seller_sku"
        if source is None:
            source = source_index["by_asin"].get(asin)
            match_type = "asin" if source is not None else "none"

        if source is None:
            raw_rate = 0.0
            sales = [0.0] * len(source_index["sales_months"])
            hot = ""
            source_lower = 0.0
            source_deviation = 0.0
        else:
            sales = source["sales"]
            raw_rate = forecast_monthly_rate(
                source_index["sales_months"], sales
            )
            hot = source["hot"]
            source_lower = source["source_lower"]
            source_deviation = source["source_deviation"]

        rows.append(
            {
                "record_id": record["record_id"],
                "sku": sku,
                "asin": asin,
                "group": str(fields.get("SKU分组") or ""),
                "price": as_float(fields.get("price")),
                "cycle": as_float(fields.get("补货周期")),
                "logistics_days": as_float(fields.get("物流偏离度")),
                "independent_monthly": as_float(
                    fields.get("独立站月均")
                ),
                "calculate": True,
                "match_type": match_type,
                "sales": sales,
                "raw_rate": raw_rate,
                "hot": hot,
                "is_hot": hot == "热销",
                "source_lower": source_lower,
                "source_deviation": source_deviation,
            }
        )

    base_total = sum(row["price"] * row["raw_rate"] for row in rows)
    if base_total <= 0:
        raise RuntimeError("Historical sales produced zero base goods value.")
    scale = target_value / base_total

    for row in rows:
        row["ai_amazon_monthly"] = round(row["raw_rate"] * scale, 1)
        row["monthly_sales"] = (
            row["ai_amazon_monthly"] + row["independent_monthly"]
        )

    tune_to_target(rows, target_value)
    return rows


def current_ai_value(rows):
    return sum(
        row["price"] * row["ai_amazon_monthly"] for row in rows
    )


def tune_to_target(rows, target_value):
    for _ in range(2000):
        total = current_ai_value(rows)
        delta = target_value - total
        if abs(delta) < 0.5:
            return
        candidates = sorted(
            (row for row in rows if row["price"] > 0 and row["raw_rate"] > 0),
            key=lambda row: row["price"] * row["raw_rate"],
            reverse=True,
        )
        changed = False
        for row in candidates:
            step = 0.1 if delta > 0 else -0.1
            next_value = round(row["ai_amazon_monthly"] + step, 1)
            if next_value < 0:
                continue
            old_value = row["ai_amazon_monthly"]
            row["ai_amazon_monthly"] = next_value
            row["monthly_sales"] = (
                row["ai_amazon_monthly"] + row["independent_monthly"]
            )
            if abs(target_value - current_ai_value(rows)) < abs(delta):
                changed = True
                break
            row["ai_amazon_monthly"] = old_value
            row["monthly_sales"] = (
                row["ai_amazon_monthly"] + row["independent_monthly"]
            )
        if not changed:
            return


def calculate_range(target_amazon_value, target_rate, independent_value):
    total_monthly_value = target_amazon_value + independent_value
    minimum = target_amazon_value / target_rate + total_monthly_value / 4
    maximum = target_amazon_value / target_rate + total_monthly_value / 2
    return minimum, maximum


def calculate_target_upper(rows, minimum, maximum):
    weights = []
    for row in rows:
        cycle = row["cycle"]
        weights.append(max(0.0, min(1.0, (cycle - 15) / 15)))
    ratio = sum(weights) / len(weights) if weights else 0.5
    span = maximum - minimum
    margin = span * TARGET_UPPER_MARGIN_RATIO
    return minimum + margin + ratio * max(0.0, span - 2 * margin)


def upper_units(row, lower, deviation, monthly_sales):
    cycle = row["cycle"]
    if cycle <= 0:
        raise RuntimeError(f"SKU {row['sku']} has invalid replenishment cycle.")
    raw = (
        monthly_sales
        + monthly_sales / 30 * row["logistics_days"]
        + deviation / 30 * cycle
        + lower
    )
    return math.ceil(raw)


def recompute_upper(row):
    row["upper"] = upper_units(
        row,
        row["lower"],
        row["deviation"],
        row["monthly_sales"],
    )
    row["upper_value"] = row["upper"] * row["price"]


def current_upper_value(rows):
    return sum(row["upper_value"] for row in rows)


def allocate_limits(rows, target_upper_value, minimum, maximum):
    for row in rows:
        row["lower"] = 0
        row["deviation"] = 0
        recompute_upper(row)

        if not row["is_hot"]:
            deviation_cap = max(0, round(row["monthly_sales"] * 0.20))
            source_cap = max(0, round(row["source_deviation"] * 0.62))
            row["deviation"] = min(deviation_cap, source_cap)
            recompute_upper(row)

    baseline_upper_value = current_upper_value(rows)
    if baseline_upper_value > maximum:
        raise RuntimeError(
            "Baseline AI upper-limit goods value "
            f"{baseline_upper_value:.2f} exceeds the calculated maximum "
            f"{maximum:.2f}. Check independent-site monthly sales or the "
            "target Amazon monthly goods value."
        )

    hot_rows = [
        row
        for row in rows
        if row["is_hot"] and row["monthly_sales"] > 0 and row["price"] > 0
    ]
    hot_monthly_goods = sum(
        row["monthly_sales"] * row["price"] for row in hot_rows
    )
    remaining = target_upper_value - current_upper_value(rows)

    if remaining > 0 and hot_monthly_goods > 0:
        for row in hot_rows:
            effect = remaining * row["monthly_sales"] / hot_monthly_goods
            source_lower_effect = row["source_lower"]
            source_deviation_effect = (
                row["source_deviation"] * row["cycle"] / 30
            )
            source_total = source_lower_effect + source_deviation_effect
            lower_ratio = (
                source_lower_effect / source_total if source_total > 0 else 0.0
            )
            lower_cap = min(
                row["source_lower"] * 1.25,
                row["monthly_sales"] * 0.5,
            )
            lower_effect = min(effect * lower_ratio, lower_cap)
            row["lower"] = max(0, round(lower_effect))
            deviation_effect = max(0.0, effect - row["lower"])
            row["deviation"] = max(
                0, round(deviation_effect * 30 / row["cycle"])
            )
            recompute_upper(row)

    fine_tune_upper(rows, hot_rows, target_upper_value, maximum)

    for row in rows:
        if row["upper"] <= 0:
            row["lower"] = 0
            row["deviation"] = max(
                row["deviation"], math.ceil(30 / row["cycle"])
            )
            recompute_upper(row)

    while current_upper_value(rows) > maximum:
        candidates = sorted(
            hot_rows,
            key=lambda row: row["monthly_sales"] * row["price"],
        )
        reduced = False
        for row in candidates:
            if row["deviation"] <= 0:
                continue
            minimum_deviation = (
                math.ceil(30 / row["cycle"])
                if row["monthly_sales"] == 0
                else 0
            )
            if row["deviation"] <= minimum_deviation:
                continue
            row["deviation"] -= 1
            recompute_upper(row)
            reduced = True
            break
        if not reduced:
            for row in rows:
                if row["deviation"] > 0:
                    minimum_deviation = (
                        math.ceil(30 / row["cycle"])
                        if row["monthly_sales"] == 0
                        else 0
                    )
                    if row["deviation"] <= minimum_deviation:
                        continue
                    row["deviation"] -= 1
                    recompute_upper(row)
                    reduced = True
                    break
                if row["lower"] > 0:
                    row["lower"] -= 1
                    recompute_upper(row)
                    reduced = True
                    break
        if not reduced:
            break
    if current_upper_value(rows) > maximum:
        raise RuntimeError(
            "AI upper-limit goods value cannot be brought inside the "
            "calculated range without breaking active-SKU invariants."
        )


def fine_tune_upper(rows, hot_rows, target, maximum):
    for _ in range(3000):
        total = current_upper_value(rows)
        delta = target - total
        if abs(delta) < 20:
            return
        step = 1 if delta > 0 else -1
        changed = False
        candidates = sorted(
            hot_rows,
            key=lambda row: row["monthly_sales"] * row["price"],
            reverse=True,
        )
        for row in candidates:
            if step < 0 and row["deviation"] <= 0:
                continue
            old_deviation = row["deviation"]
            old_upper = row["upper"]
            old_value = row["upper_value"]
            row["deviation"] = max(0, old_deviation + step)
            recompute_upper(row)
            next_total = current_upper_value(rows)
            if (
                next_total <= maximum
                and abs(target - next_total) < abs(delta)
            ):
                changed = True
                break
            row["deviation"] = old_deviation
            row["upper"] = old_upper
            row["upper_value"] = old_value
        if not changed:
            return


def batch_update(config, records, fields_key):
    updated = 0
    for batch in chunked(records, 500):
        payload = {
            "records": [
                {
                    "record_id": row["record_id"],
                    "fields": fields_key(row),
                }
                for row in batch
            ]
        }
        response = api_request(
            config,
            "POST",
            f"/bitable/v1/apps/{PARAM_APP_TOKEN}/tables/"
            f"{PARAM_TABLE_ID}/records/batch_update",
            body=payload,
        )
        updated += len(response.get("records", []))
    return updated


def apply_changes(
    config,
    rows,
    range_record,
    target_amazon_value,
    target_rate,
):
    monthly_updated = batch_update(
        config,
        rows,
        lambda row: {"AI亚马逊月均": row["ai_amazon_monthly"]},
    )
    ranges_updated = api_request(
        config,
        "POST",
        f"/bitable/v1/apps/{PARAM_APP_TOKEN}/tables/"
        f"{RANGE_TABLE_ID}/records/batch_update",
        body={
            "records": [
                {
                    "record_id": range_record["record_id"],
                    "fields": {
                        "目标亚马逊月销货值": target_amazon_value,
                        "目标售出率": target_rate,
                    },
                }
            ]
        },
    )
    limits_updated = batch_update(
        config,
        rows,
        lambda row: {
            "AI下限": int(row["lower"]),
            "AI销量偏离度": int(row["deviation"]),
        },
    )
    return {
        "monthly_records": monthly_updated,
        "range_records": len(ranges_updated.get("records", [])),
        "limit_records": limits_updated,
    }


def verify_written_state(config, station):
    views = resolve_main_views(config, station)
    records = fetch_station_records(config, views)
    active = [
        record
        for record in records
        if is_true(record.get("fields", {}).get("是否计算"))
    ]
    amazon_value = sum(
        as_float(record.get("fields", {}).get("price"))
        * as_float(record.get("fields", {}).get("AI亚马逊月均"))
        for record in active
    )
    upper_value = sum(
        as_float(record.get("fields", {}).get("price"))
        * as_float(record.get("fields", {}).get("AI上限"))
        for record in active
    )
    zero_upper = [
        str(record.get("fields", {}).get("seller_sku") or "")
        for record in active
        if as_float(record.get("fields", {}).get("AI上限")) <= 0
    ]
    return {
        "active_records": len(active),
        "ai_amazon_monthly_goods_value": round(amazon_value, 2),
        "ai_upper_limit_goods_value": round(upper_value, 2),
        "zero_upper_calculating_skus": zero_upper,
    }


def build_summary(
    station,
    target_amazon_value,
    target_rate,
    rows,
    range_record,
    minimum,
    maximum,
    target_upper,
):
    cycle_counts = Counter(str(int(row["cycle"])) for row in rows)
    hot_count = sum(row["is_hot"] for row in rows)
    non_hot_count = len(rows) - hot_count
    return {
        "station": station,
        "target_amazon_monthly_goods_value": target_amazon_value,
        "target_sell_through_rate": target_rate,
        "active_sku_count": len(rows),
        "hot_sku_count": hot_count,
        "non_hot_sku_count": non_hot_count,
        "cycle_counts": dict(cycle_counts),
        "minimum_upper_limit_goods_value": round(minimum, 2),
        "maximum_upper_limit_goods_value": round(maximum, 2),
        "target_upper_limit_goods_value": round(target_upper, 2),
        "planned_ai_amazon_monthly_goods_value": round(
            current_ai_value(rows), 2
        ),
        "planned_ai_upper_limit_goods_value": round(
            current_upper_value(rows), 2
        ),
        "independent_site_monthly_goods_value": round(
            as_float(
                range_record.get("fields", {}).get("独立站月销货值")
            ),
            2,
        ),
    }


def print_preview(summary, rows):
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("\nsku\thot\tprice\tmonthly\tlower\tdeviation\tupper\tupper_value")
    for row in sorted(
        rows,
        key=lambda item: item["upper_value"],
        reverse=True,
    ):
        print(
            "\t".join(
                [
                    row["sku"],
                    "hot" if row["is_hot"] else "non-hot",
                    f"{row['price']:.2f}",
                    f"{row['ai_amazon_monthly']:.1f}",
                    str(row["lower"]),
                    str(row["deviation"]),
                    str(row["upper"]),
                    f"{row['upper_value']:.2f}",
                ]
            )
        )


def main():
    parser = argparse.ArgumentParser(
        description="Configure Amazon operations replenishment parameters."
    )
    parser.add_argument("--station", required=True)
    parser.add_argument("--target-amazon-value", required=True, type=float)
    parser.add_argument("--target-sell-through", required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--preview", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    station = normalize_station(args.station)
    target_rate = parse_rate(args.target_sell_through)
    config = load_config()

    source_sheet = resolve_source_sheet(config, station)
    source_rows = fetch_sheet_rows(config, source_sheet)
    source_index = build_source_index(source_rows)

    main_views = resolve_main_views(config, station)
    station_records = fetch_station_records(config, main_views)
    range_record = fetch_range_record(config, station)

    rows = build_monthly_forecast(
        station_records,
        source_index,
        args.target_amazon_value,
    )

    independent_value = as_float(
        range_record.get("fields", {}).get("独立站月销货值")
    )
    minimum, maximum = calculate_range(
        args.target_amazon_value,
        target_rate,
        independent_value,
    )
    target_upper = calculate_target_upper(rows, minimum, maximum)
    allocate_limits(rows, target_upper, minimum, maximum)

    summary = build_summary(
        station,
        args.target_amazon_value,
        target_rate,
        rows,
        range_record,
        minimum,
        maximum,
        target_upper,
    )
    print_preview(summary, rows)

    if args.apply:
        write_result = apply_changes(
            config,
            rows,
            range_record,
            args.target_amazon_value,
            target_rate,
        )
        verification = verify_written_state(config, station)
        print(
            json.dumps(
                {
                    "write_result": write_result,
                    "verification": verification,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
    except (RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        exit_code = 1
    raise SystemExit(exit_code)
