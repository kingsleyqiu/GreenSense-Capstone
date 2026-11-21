# GreenSense-Capstone

GreenSense helps a greenhouse operator plan tomato harvests and allocate lots to dated orders. This proof of concept runs a small seven-day C1 mixed-integer model locally. Inputs replay published data and explicit operating assumptions. The demo measures planned service and stock exposure. Farm waste reduction and forecast accuracy require independent validation.

## Run locally

With Python 3.11 or later, open a terminal in this directory. On Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m streamlit run app.py
```

On macOS or Linux, use `.venv/bin/python` in the last two commands. The packaged sample works offline after installation.

## Try the two priorities

1. Choose **Show my example plan** on the welcome screen. Read what to pick, what to pack and which customer needs a follow-up.
2. Choose **Edit inputs & rebuild**, select **Use expiring stock**, then **Build my plan**. Compare the Friday deliveries. Under delivery capacity, allow two orders per day to remove the conflict.
3. To try your own figures, use **Enter my planning inputs** from the welcome screen. Enter batch weights and expected harvest, then edit or add customer orders within the example week. Review the resulting plan and choose **Save this plan**. Saved plans are kept in the local SQLite database.

Each order may receive a partial shipment on its due date. Picking takes place on the replayed event date. Lot-to-order quantities and harvest quantities are solved in 0.01 kg units; a binary variable activates each order dispatch. The solver fixes the optimum of each objective before optimizing the next one. Priorities switch the order of fulfilled kilograms and expiring opening stock allocated; the final objective minimizes new picking. Remaining stock at its assumed use-by date represents exposure. A disposal record would be needed to count actual waste.

## Data origins and transformations

| Source | Records and use |
|---|---|
| [Wageningen Autonomous Greenhouse Challenge, edition 2](https://doi.org/10.4121/uuid:88d22c60-21b3-4ea8-90db-20249a5be2a7), CC0 | AICU first three Production.csv harvests. Multiply recorded Class A kg/m² by 62.5 m². Carry the first two into simulated stock and replay the third as a known harvest opportunity. Gaps between recorded events do not establish zero production. |
| [Dingdong-Inc, FreshRetailNet-50K](https://huggingface.co/datasets/Dingdong-Inc/FreshRetailNet-50K/tree/c374e85975c82816c495acfa904cc55ab14a47d3), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | Store 0, encoded product 38, training split, 28 March–26 April 2024. Retain dates without flagged stockout hours. Use the minimum positive / maximum sales ratio to size the local order relative to the second harvest. Wholesale and follow-up each use that harvest quantity. The figures simulate order sizes; underlying sales are normalized, with no identified tomato SKU or observed order kg. |
| [Marcelo Jhonatan de Sousa e Sousa, Clarice Aparecida Megguer and Giovana Lopes da Silva, tomato quality data, v1](https://doi.org/10.17632/9wbk3mcryd.1), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | T1 storage ages 1, 4, 8 and 12 days and median firmness in kgf/cm² across three replicates at each age. The operator selects an illustrative last usable age from these observation days. Measured firmness is shown for context; these data do not identify an expiry threshold. |

Scenario day zero falls one day after the second harvest. Deliveries on days 1, 1 and 5, customer reserves of 0, 4 and 1 days, opening-stock carryover, the usable age and daily dispatch slots are simulation assumptions. Customer orders are constructed for a repeatable two-priority demonstration. All three sources come from independent studies. Future harvest values are historical replay inputs and the demo contains no trained forecast model.

The team can rebuild the bundled extract using its October PR2 archive:

```sh
python build_sample.py path/to/data/2026-10-22
python -m unittest -v test_planner
```
