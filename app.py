from contextlib import closing, contextmanager
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

import pandas as pd
import streamlit as st

from planner import EXPIRY, HORIZON, ORIGIN, SAMPLE, SERVICE, check, eligible, metrics, scenario, solve


def day_label(day):
    return (ORIGIN + timedelta(days=day)).strftime("%a %d %b")


def centikg(value):
    amount = Decimal(str(value)) * 100
    if not amount.is_finite() or amount < 0 or amount != amount.to_integral_value():
        raise ValueError("Use non-negative quantities with at most two decimal places.")
    return int(amount)


@contextmanager
def connection():
    folder = Path(__file__).resolve().parent / "local"
    folder.mkdir(exist_ok=True)
    with closing(sqlite3.connect(folder / "decisions.sqlite3")) as db, db:
        db.execute("CREATE TABLE IF NOT EXISTS decisions (id TEXT PRIMARY KEY, saved TEXT, payload TEXT)")
        yield db


def summary(lots, orders, values):
    labels = {"shipped": "Scheduled", "short": "Order shortfall",
              "at_risk": "Expiring stock left", "harvest": "Harvest required"}
    for col, (key, amount) in zip(st.columns(4), metrics(lots, orders, values).items()):
        col.metric(labels[key], f"{amount/100:,.2f} kg")


st.set_page_config(page_title="GreenSense | Harvest planning", page_icon="🌱", layout="wide")
st.title("GreenSense")
st.caption(f"Tomato planning · {day_label(0)} – {day_label(6)}, {ORIGIN.year} · Dataset-based simulation")
plan_tab, source_tab, history_tab = st.tabs(["Plan the week", "Data & assumptions", "Saved decisions"])

with plan_tab:
    left, right = st.columns([1, 2])
    with left:
        st.subheader("Planning preferences")
        priority = st.radio("First priority", [SERVICE, EXPIRY])
        slots = st.number_input("Order dispatch slots per day", 1, 3, 1)
        life = st.select_slider("Assumed last usable age (days)",
                                [r["storage_day"] for r in SAMPLE["quality"]], value=8)
        st.caption("One slot serves one order on its due date. Partial fulfilment is allowed.")
    lots, defaults = scenario(life)
    with right:
        st.subheader("Supply available")
        st.dataframe(pd.DataFrame([{
            "Lot": l.name, "Source": "Standing crop" if l.on_vine else "Opening inventory",
            "Available kg": l.quantity/100, "Harvest date": day_label(l.ready),
            "Last usable date¹": day_label(l.last_day)} for l in lots]), hide_index=True)
        st.caption("¹ Scenario assumption. Future harvest uses a recorded harvest event as a replay input.")

    st.subheader("Confirmed orders")
    st.caption("These simulated orders can be edited. Reserve is the number of usable days the customer requires after delivery.")
    names = [o.name for o in defaults]
    table = pd.DataFrame([{"Order": o.name, "Quantity (kg)": o.quantity/100,
                           "Delivery": day_label(o.day), "Reserve (days)": o.reserve_days}
                          for o in defaults])
    dates = [day_label(d) for d in range(HORIZON)]
    order_edits = st.data_editor(table, hide_index=True, disabled=["Order"], key="orders",
        column_config={
            "Quantity (kg)": st.column_config.NumberColumn(min_value=0., max_value=10000., step=.01, required=True),
            "Delivery": st.column_config.SelectboxColumn(options=dates, required=True),
            "Reserve (days)": st.column_config.NumberColumn(min_value=0, max_value=12, step=1, required=True)})
    try:
        orders = [replace(o, quantity=centikg(r["Quantity (kg)"]), day=dates.index(r["Delivery"]),
                          reserve_days=int(r["Reserve (days)"]))
                  for o, r in zip(defaults, order_edits.to_dict("records"))]
    except (ValueError, TypeError, ArithmeticError):
        st.error("Complete the order quantities, dates and reserve values.")
        st.stop()
    settings = {"origin": str(ORIGIN), "priority": priority, "slots": slots,
                "lots": [asdict(l) for l in lots], "orders": [asdict(o) for o in orders],
                "sample_version": hashlib.sha256(json.dumps(SAMPLE, sort_keys=True).encode()).hexdigest()}
    if st.button("Generate plan", type="primary"):
        try:
            values = solve(lots, orders, slots, priority)
            st.session_state.plan = (settings, values, uuid4().hex)
        except (ValueError, RuntimeError) as exc:
            st.session_state.pop("plan", None)
            st.error(str(exc))
    plan = st.session_state.get("plan")
    if plan and plan[0] != settings:
        st.info("Planning inputs changed. Generate a new plan to review the updated allocations.")
    elif plan:
        _, recommended, run_id = plan
        st.subheader("Recommended plan")
        summary(lots, orders, recommended)
        st.caption("Expiring stock left counts opening inventory still unallocated at its assumed deadline this week. Actual disposal is unknown.")
        for j, order in enumerate(orders):
            picks = [f"{row[j]/100:.2f} kg from {l.name}" for l, row in zip(lots, recommended) if row[j]]
            missing = order.quantity - sum(row[j] for row in recommended)
            note = ", ".join(picks) or "No stock scheduled"
            if missing:
                note += f" · {missing/100:.2f} kg short"
            st.write(f"**{order.name} · {day_label(order.day)}** — {note}")
        with st.expander("Why this plan?"):
            st.write(f"The solver first optimizes “{priority}”, then the other goal, then minimizes harvesting. Each day allows {slots} order dispatch slot(s).")
            for order in orders:
                allowed = [l.name for l in lots if eligible(l, order)]
                st.write(f"{order.name} needs stock available by {day_label(order.day)} and usable through "
                         f"{day_label(order.day + order.reserve_days)}. Eligible lots: {', '.join(allowed) or 'none'}.")
            for lot, row in zip(lots, recommended):
                if lot.on_vine:
                    st.write(f"Pick {sum(row)/100:.2f} kg of {lot.name} on {day_label(lot.ready)} for assigned orders.")
        st.subheader("Review decision")
        review = pd.DataFrame([[l.name, *[q/100 for q in row]] for l, row in zip(lots, recommended)],
                              columns=["Lot", *names])
        edited = st.data_editor(review, key="review_"+run_id, hide_index=True, disabled=["Lot"],
            column_config={n: st.column_config.NumberColumn(label=n+" (kg)", min_value=0., step=.01,
                                                          required=True) for n in names})
        try:
            final = [[centikg(r[n]) for n in names] for r in edited.to_dict("records")]
            check(lots, orders, final, slots)
        except (ValueError, ArithmeticError) as exc:
            st.error(str(exc))
        else:
            if final != recommended:
                st.caption("Updated plan after your edits")
                summary(lots, orders, final)
            note = st.text_input("Decision note (optional)", key="note_"+run_id)
            if st.button("Save decision", key="save_"+run_id):
                payload = dict(settings, recommendation=recommended, accepted=final, note=note,
                               status="Modified" if final != recommended else "Accepted",
                               units="0.01 kg", outcome=metrics(lots, orders, final))
                try:
                    with connection() as db:
                        db.execute("INSERT INTO decisions VALUES (?, ?, ?)",
                                   (run_id, datetime.now(timezone.utc).isoformat(), json.dumps(payload)))
                    st.success("Decision saved on this computer.")
                except sqlite3.IntegrityError:
                    st.info("This plan already has a saved decision. Generate a new plan to record another.")

with source_tab:
    st.subheader("How the example was built")
    st.markdown("**Supply · AGC2.** Three Class A harvest records from the AICU compartment, multiplied by the documented area of 62.5 m². The simulation carries the first two events into opening inventory and makes the third available on its observed date. Inventory carryover and advance knowledge are scenario assumptions. [Dataset](https://doi.org/10.4121/uuid:88d22c60-21b3-4ea8-90db-20249a5be2a7)")
    st.dataframe(SAMPLE["harvest"], hide_index=True)
    st.markdown("**Order sizes · FreshRetailNet-50K.** Store 0, product 38, training records from 28 March–26 April 2024. We exclude days flagged for stockouts. The smallest positive and largest normalized sales anchor a size ratio. Simulated wholesale and follow-up orders each equal Stock B; local pickup equals Stock B × the ratio. These are constructed kilogram orders. [Dataset](https://huggingface.co/datasets/Dingdong-Inc/FreshRetailNet-50K)")
    st.dataframe(SAMPLE["sales"], hide_index=True)
    st.markdown("**Quality · Tomato storage experiment.** The slider uses the study’s sampled ages. The table shows median measured firmness for treatment T1 at each age. Choosing age 8 as a usable cutoff is an editable scenario assumption. The experiment does not establish a marketability or safety deadline. [Dataset](https://doi.org/10.17632/9wbk3mcryd.1)")
    st.dataframe(SAMPLE["quality"], hide_index=True)
    st.write("The seven-day replay starts the day after the second harvest. Order dates, customer reserves, opening stock carryover and dispatch slots are operating assumptions for exploring a conflict between two orders. Sources describe different operations and years.")

with history_tab:
    st.subheader("Saved decisions")
    with connection() as db:
        rows = db.execute("SELECT saved, payload FROM decisions ORDER BY saved DESC").fetchall()
    if not rows:
        st.caption("Reviewed plans saved on this computer will appear here.")
    for saved, payload in rows:
        decision = json.loads(payload)
        with st.expander(f"{decision['status']} · {decision['priority']} · {saved[:19]} UTC"):
            st.write(decision["note"] or "No decision note.")
            st.dataframe(pd.DataFrame([[l["name"], *[q/100 for q in row]]
                for l, row in zip(decision["lots"], decision["accepted"])],
                columns=["Lot", *[o["name"]+" (kg)" for o in decision["orders"]]]), hide_index=True)
            st.json(decision, expanded=False)
