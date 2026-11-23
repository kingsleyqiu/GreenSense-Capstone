"""Three small, independently fitted two-hidden-layer models for the terminal demo."""
import json
from pathlib import Path
from statistics import mean

from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

DATA = json.loads(Path(__file__).with_name("sample.json").read_text())


def predict(rows, targets, features):
    model = make_pipeline(StandardScaler(), MLPRegressor(hidden_layer_sizes=(8, 4),
                          activation="tanh", solver="lbfgs", alpha=0.1, max_iter=1500,
                          random_state=24))
    model.fit(rows, targets)
    return float(model.predict([features])[0])


def harvest_signal():
    # Test the last AICU event; all compartments train only on earlier event dates.
    aicu = DATA["harvest"]["AICU"]
    cutoff, actual = aicu[-1]
    rows, targets = [], []
    for series in DATA["harvest"].values():
        for i in range(3, len(series)):
            if series[i][0] < cutoff:
                rows.append([v for _, v in series[i-3:i]])
                targets.append(series[i][1])
    predicted = max(0, predict(rows, targets, [v for _, v in aicu[-4:-1]]))
    area = DATA["area_m2"]
    return {"event": cutoff, "predicted_kg": round(predicted*area, 2),
            "observed_kg": round(actual*area, 2), "area_m2": area, "training_rows": len(rows)}


def storage_signal(age, shipped):
    observations = DATA["firmness"]
    treatments = sorted({r[0] for r in observations})
    def features(treatment, day):
        return [day, *[int(t == treatment) for t in treatments]]
    # Reserve replicate 3 of each treatment/day as a demonstration check.
    training = [r for r in observations if r[2] != 3]
    forecast = predict([features(t, d) for t,d,_,_ in training],
                       [f for _,_,_,f in training], features("T1", age))
    capacity = DATA["area_m2"]
    prior, incoming = [round(v * capacity, 2) for _, v in DATA["harvest"]["AICU"][-3:-1]]
    available = round(prior + incoming - shipped, 2)
    if available < 0:
        raise ValueError(f"Outbound exceeds the scenario stock of {prior+incoming:.2f} kg.")
    reference = next(r[3] for r in observations if r[:3] == ["T1", age, 3])
    return {"storage_age_days": age, "predicted_firmness": round(forecast, 2),
            "held_out_firmness": reference, "firmness_unit": "kgf/cm2",
            "opening_kg": prior, "inbound_kg": incoming, "outbound_kg": shipped,
            "available_kg": available, "training_rows": len(training)}


def market_signal():
    sales = DATA["sales"]
    def features(window):
        return [r[1] for r in window] + [r[2] for r in window]
    # Lagged sales and stockout hours were observable before the target date.
    # Score only an uncensored target. All training targets precede that day.
    end = max(i for i, row in enumerate(sales) if row[2] == 0)
    indices = [i for i in range(3, end) if sales[i][2] == 0]
    previous = sales[end-3:end]
    forecast = max(0, predict([features(sales[i-3:i]) for i in indices],
                              [sales[i][1] for i in indices], features(previous)))
    return {"date": sales[end][0], "predicted_sales_index": round(forecast, 3),
            "previous_3day_mean": round(mean(r[1] for r in previous), 3),
            "observed_sales_index": sales[end][1], "training_rows": len(indices)}
