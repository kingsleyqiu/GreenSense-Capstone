# GreenSense | Greenhouse decision support

PowerShell proof of concept for a tomato grower. Three independently fitted neural networks estimate the next harvest, stored-fruit firmness and the direction of retail sales. A local Qwen language model reads their outputs, summarizes the situation and selects an advisory action. The grower decides what to do.

## Present from Windows PowerShell

Use Windows x64 and Python 3.11–3.14. From this checkout, run the following once. The setup downloads and verifies the Windows CPU runtime and about 398 MB of quantized model weights.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python setup_advisor.py
```

Run the default case and then change one condition for the supervisor:

```powershell
.\.venv\Scripts\python demo.py
.\.venv\Scripts\python demo.py --shipped-kg 95.63
```

The first case has stock available. In the second the grower has shipped all available stock. Watch the stock ledger and advisory action change while the harvest and market inputs stay fixed. To explore the quality model separately, run `demo.py --storage-days 12` with the same interpreter. Valid study ages are 1, 4, 8 and 12 days. All inference runs on the presenting computer after setup. No browser or API key is needed.

## What the backend computes

Each numeric component fits its own small multilayer perceptron with two hidden layers (8 and 4 units), standardized features and a fixed seed. Every run fits the three networks from the included extract. The final section displays one held-out observation per output for inspection. These individual examples do not establish general predictive accuracy.

| Component | Input and output | Evidence boundary |
|---|---|---|
| Pre-harvest | The previous three Class A harvest events predict the next recorded event's kg/m². Multiplication by 62.5 m² gives compartment kg. | Uses five other compartments and AICU history before the final AICU event date. The event date comes from the replay. Timing, maturity and a seven-day harvest schedule are future work. |
| Storage | Coded treatment and storage age predict firmness in kgf/cm². A separate ledger calculates opening + inbound − outbound. | Replicates 1 and 2 train the network and replicate 3 is held out within the same experiment. Two past AICU events supply example ledger weights. Their combination and shipping activity are scenario assumptions. Firmness has no validated mapping to days before expiry. |
| Market | Three preceding days of normalized sales and stockout hours predict the next day's sales index. Compare with the previous three-day mean. | A single encoded retail product and store form a sales proxy. Fit only on earlier targets with zero flagged stockout hours. Neither a confirmed order quantity nor a price forecast can be inferred from this index. |
| Advice | Qwen receives all three signals and chooses an evidence-grounded summary and an inventory-feasible advisory action. | The demo constrains wording to calculated facts to keep the units and comparisons accurate. Held-out measurements are excluded from the prompt. The grower reviews the suggestion. |

The sources are from different years and operations. Combining them demonstrates the proposed information flow. There is no linked farm history or measured reduction in discarded kilograms.

## Reproduce the extract

`sample.json` contains source observations. With the team's October archive, run `python build_sample.py path/to/data/2026-10-22` to rebuild it.

- Wageningen University & Research, [Autonomous Greenhouse Challenge, edition 2](https://doi.org/10.4121/uuid:88d22c60-21b3-4ea8-90db-20249a5be2a7), CC0. Harvest date and Class A kg/m², all six compartments. Excludes the previously documented out-of-season Reference timestamp.
- Dingdong-Inc, [FreshRetailNet-50K](https://huggingface.co/datasets/Dingdong-Inc/FreshRetailNet-50K/tree/c374e85975c82816c495acfa904cc55ab14a47d3), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Store 0, encoded product 38, training split. Extracts date, normalized sales and stockout-hour count.
- Marcelo Jhonatan de Sousa e Sousa, Clarice Aparecida Megguer and Giovana Lopes da Silva, [tomato postharvest quality dataset, v1](https://doi.org/10.17632/9wbk3mcryd.1), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Selects treatment, storage day, replicate and firmness for all 72 measurements. The demonstration uses the T1 treatment label.
- Local inference uses [llama.cpp](https://github.com/ggml-org/llama.cpp) and the [bartowski quantization of Qwen2.5-0.5B-Instruct](https://huggingface.co/bartowski/Qwen2.5-0.5B-Instruct-GGUF). Versioned URLs and SHA-256 checksums are in `setup_advisor.py`. The process binds to loopback for the duration of the briefing.
