"""Rebuild the small public replay extract from the team's October data archive."""
import argparse
import csv
import json
from datetime import date, timedelta
from pathlib import Path
from statistics import median


def build(root):
    with (root / "agc2/raw/AICU/Production.csv").open() as stream:
        events = list(csv.DictReader(stream))[:3]
    harvest = [
        {"date": str(date(1899, 12, 30) + timedelta(days=int(r["%time"]))),
         "class_a_kg_m2": float(r["ProdA"])} for r in events
    ]
    folder = root / "demand_quality"
    retail = json.loads((folder / "freshretailnet/train_sample_extracted.json").read_text())
    sales = [
        {"date": r["dt"], "normalized_sales": r["sale_amount"]}
        for r in retail if r["store_id"] == 0 and r["product_id"] == 38
        and "2024-03-28" <= r["dt"] <= "2024-04-26" and r["stock_hour6_22_cnt"] == 0
    ]
    workbook = folder / "mendeley/workbook_cells_extracted.json"
    rows = json.loads(workbook.read_text(encoding="utf-8"))["Planilha1"][1:]
    days = sorted({r[1] for r in rows if r[0] == "T1"})
    quality = [{"storage_day": d, "median_firmness": median(
        r[6] for r in rows if r[0] == "T1" and r[1] == d)} for d in days]
    return {"area_m2": 62.5, "harvest": harvest, "sales": sales, "quality": quality}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="Path to the team's 2026-10-22 data directory")
    args = parser.parse_args()
    target = Path(__file__).with_name("sample.json")
    target.write_text(json.dumps(build(args.archive), indent=2) + "\n", encoding="utf-8")
