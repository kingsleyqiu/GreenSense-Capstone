# GreenSense | Tomato greenhouse decision support

This PowerShell proof of concept helps a grower review a planting decision, an upcoming harvest and stored-fruit quality using public observations. The three sources represent different operations, places and dates.

## Present from Windows PowerShell

Use Windows x64 and Python 3.11-3.14. From the repository directory run the following once.

~~~powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python setup_advisor.py
~~~

Run the default outlook, then compare a different storage age from the same experiment.

~~~powershell
.\.venv\Scripts\python demo.py
.\.venv\Scripts\python demo.py --storage-days 12
~~~

Use --treatment T1 through T6 and --storage-days 1, 4, 8 or 12 to select a published experimental condition. Setup installs a local Windows CPU runtime and about 398 MB of Qwen weights. After setup the demo runs offline. The earlier --shipped-kg simulated ledger has been retired.

## Questions a grower can ask

| Decision | Public evidence and validation |
|---|---|
| How large might next year's Ontario market be? | Show estimated fresh consumption, international exports and marketed production separately in tonnes per year. An 8/4-hidden-unit neural network predicts the three quantities from the preceding year's values and imports. Inputs and targets are standardized using training data only. Select the network or the previous-year forecast per target by rolling mean absolute error in 2016-2022. Report the separate 2023-2025 rolling test using the fixed selection, then fit through 2025 for 2026. Each historical forecast uses only earlier reference years from the current workbook vintage. |
| How much could the next pick yield in the public example? | Use three previous Class A harvests to predict kg per square metre. Convert to kg for the documented 62.5 m2 AICU compartment. Replay its final five recorded harvests, fitting the network on earlier dates across six compartments and comparing to the previous three-pick average. Dates are observed event dates. |
| How might stored quality change? | An independent network estimates firmness from treatment and storage day. Train on repeats 1 and 2 and score all 24 third repeats. Compare to the mean of the two training repeats at the same treatment and day. These checks cover the same experiment. Firmness alone has no validated mapping to expiry, safe use or discarded kg. |

Ontario's estimated fresh consumption equals marketed fresh production plus international imports minus international exports. The workbook estimates interprovincial shipments separately. The consumption series is a supply-balance indicator. Imports have suppliers already. Annual totals do not identify unmet orders, seasonal patterns or an individual farm's reachable sales.

Actual planting area, stock, committed sales, processing or own-use capacity, waste and financial loss remain unknown. Sizing a crop requires a sales volume accessible to the farm and its marketable yield per unit area for the same growing period. Recording the final use of each batch would distinguish unsold fruit from discarded fruit. Qwen selects a summary and a planning or allocation action from the available evidence.

## Data provenance

- Government of Ontario, [Aggregated Ontario greenhouse vegetable production](https://data.ontario.ca/en/dataset/aggregated-ontario-greenhouse-vegetable-production), Open Government Licence - Ontario. The [supply-disposition workbook](https://data.ontario.ca/dataset/c01555d1-96ee-46c3-a0a9-3a307bcb8a6f/resource/7216b164-d2e3-4c7d-bc62-d5bf79446da2/download/ontario_greenhouse_vegetable_supply-disposition.xlsx) provides the 2005-2025 extract in ontario_market.csv. On the Tomato sheet, columns D through X are consecutive years. Rows 1, 9, 34, 22 and 56 give year, fresh marketed kg, imported kg, exported kg and estimated fresh consumption kg, respectively. Published values are rounded to the nearest kg in the extract.
- Wageningen University & Research, [Autonomous Greenhouse Challenge 2](https://doi.org/10.4121/uuid:88d22c60-21b3-4ea8-90db-20249a5be2a7), CC0. Harvest dates and Class A kg per square metre for six compartments.
- Sousa, Megguer and Silva, [tomato postharvest quality experiment](https://doi.org/10.17632/9wbk3mcryd.1), CC BY 4.0. The sample contains 72 published firmness measurements. To rebuild sample.json from the team archive, run python build_sample.py path/to/data/2026-10-22.
- Local advice uses [llama.cpp](https://github.com/ggml-org/llama.cpp) and [quantized Qwen2.5-0.5B-Instruct](https://huggingface.co/bartowski/Qwen2.5-0.5B-Instruct-GGUF). setup_advisor.py pins and verifies the downloaded files.
