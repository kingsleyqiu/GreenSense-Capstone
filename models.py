"""Public-data models for a greenhouse harvest replay, quality experiment and Ontario market."""
import csv
import json
from pathlib import Path
from statistics import mean

from sklearn.compose import TransformedTargetRegressor
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parent
DATA = json.loads((ROOT / "sample.json").read_text())
MARKET_TARGETS = ("estimated_consumption_kg", "exports_kg", "marketed_kg")


def network(solver="lbfgs"):
    return make_pipeline(
        StandardScaler(),
        MLPRegressor(hidden_layer_sizes=(8, 4), activation="tanh", solver=solver,
                     alpha=0.1, max_iter=1500, random_state=24),
    )


def harvest_signal():
    series = DATA["harvest"]
    aicu = series["AICU"]
    area = DATA["area_m2"]
    checks = []
    for i in range(len(aicu) - 5, len(aicu)):
        cutoff, actual = aicu[i]
        rows, targets = [], []
        for events in series.values():
            for j in range(3, len(events)):
                if events[j][0] < cutoff:
                    rows.append([v for _, v in events[j-3:j]])
                    targets.append(events[j][1])
        window = [v for _, v in aicu[i-3:i]]
        predicted = max(0, network().fit(rows, targets).predict([window])[0])
        checks.append((area * abs(predicted - actual), area * abs(mean(window) - actual)))
    return {"event": cutoff, "area_m2": area, "predicted_kg": round(predicted * area, 2),
            "observed_kg": round(actual * area, 2), "checks": len(checks),
            "mae_kg": mean(x for x, _ in checks), "baseline_mae_kg": mean(x for _, x in checks)}


def storage_signal(age, treatment="T1"):
    observations = DATA["firmness"]
    treatments = sorted({r[0] for r in observations})

    def features(code, day):
        return [day, *[int(t == code) for t in treatments]]

    train = [r for r in observations if r[2] != 3]
    held = [r for r in observations if r[2] == 3]
    model = network().fit([features(t, d) for t, d, _, _ in train], [r[3] for r in train])
    estimates = model.predict([features(t, d) for t, d, _, _ in held])
    checks = []
    result = None
    for (code, day, _, actual), predicted in zip(held, estimates):
        baseline = mean(r[3] for r in train if r[:2] == [code, day])
        checks.append((abs(actual - predicted), abs(actual - baseline)))
        if (code, day) == (treatment, age):
            result = {"treatment": code, "storage_age_days": day, "predicted_firmness": round(predicted, 2),
                      "held_out_firmness": actual}
    if result is None:
        raise ValueError("Choose a treatment and storage day represented in the experiment.")
    return {**result, "checks": len(checks), "mae": mean(x for x, _ in checks),
            "baseline_mae": mean(x for _, x in checks)}


def market_signal():
    with (ROOT / "ontario_market.csv").open(newline="") as stream:
        records = [{key: int(value) for key, value in row.items()} for row in csv.DictReader(stream)]
    # One joint network predicts three quantities. Every input is known in the previous year.
    fields = (*MARKET_TARGETS, "imports_kg")
    inputs = [[r[k] for k in fields] for r in records]
    targets = [[r[k] for k in MARKET_TARGETS] for r in records]

    def forecasts(i):
        model = TransformedTargetRegressor(regressor=network("adam"), transformer=StandardScaler())
        model.fit(inputs[:i-1], targets[1:i])
        neural = model.predict([inputs[i-1]])[0].clip(min=0)
        return neural, targets[i-1]

    years = [r["year"] for r in records]
    checks = {years[i]: forecasts(i) for i in range(years.index(2016), len(years))}
    next_values = forecasts(len(records))
    result = {}
    for col, key in enumerate(MARKET_TARGETS):
        def error(method, start, end):
            return mean(abs(checks[y][method][col] - targets[years.index(y)][col])
                        for y in range(start, end + 1)) / 1000

        method = 0 if error(0, 2016, 2022) < error(1, 2016, 2022) else 1
        result[key] = {"tonnes": round(next_values[method][col] / 1000),
                       "method": ("MLP", "previous year")[method],
                       "test_mae_t": round(error(method, 2023, 2025)),
                       "mlp_mae_t": round(error(0, 2023, 2025)),
                       "baseline_mae_t": round(error(1, 2023, 2025))}
    return {"year": years[-1] + 1, "targets": result}
