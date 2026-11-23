"""Export compact source observations from the October 22 PR2 archive."""
import argparse
import csv
from datetime import date, timedelta
import json
from pathlib import Path


def build(root):
    harvest = {}
    for file in sorted((root / "agc2/raw").glob("*/Production.csv")):
        records = []
        with file.open() as stream:
            for row in csv.DictReader(stream):
                day = date(1899, 12, 30) + timedelta(days=int(row["%time"]))
                if day.year == 2020:  # Exclude the documented Reference timestamp anomaly.
                    records.append([day.isoformat(), float(row["ProdA"])])
        harvest[file.parent.name] = records
    folder = root / "demand_quality"
    retail = json.loads((folder / "freshretailnet/train_sample_extracted.json").read_text())
    sales = [[r["dt"], r["sale_amount"], r["stock_hour6_22_cnt"]] for r in retail
             if r["store_id"] == 0 and r["product_id"] == 38]
    workbook = folder / "mendeley/workbook_cells_extracted.json"
    rows = json.loads(workbook.read_text(encoding="utf-8"))["Planilha1"][1:]
    firmness = [[r[0], r[1], r[2], r[6]] for r in rows]
    return {"area_m2": 62.5, "harvest": harvest, "sales": sorted(sales), "firmness": firmness}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    path = Path(__file__).with_name("sample.json")
    path.write_text(json.dumps(build(parser.parse_args().archive), indent=1) + "\n", encoding="utf-8")
