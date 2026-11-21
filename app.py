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

from planner import EXPIRY, HORIZON, ORIGIN, SAMPLE, SERVICE, Order, check, eligible, metrics, scenario, solve


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
    labels = {"shipped": "To deliver", "short": "Still owed",
              "at_risk": "Stock nearing its limit", "harvest": "To pick"}
    for col, (key, amount) in zip(st.columns(4), metrics(lots, orders, values).items()):
        col.metric(labels[key], f"{amount/100:,.2f} kg")


def set_screen(screen):
    st.session_state.screen = screen
    st.rerun()


def lot_label(lot):
    return {"Stock A": "Earlier harvest · A", "Stock B": "Later harvest · B",
            "Harvest C": "Standing crop · C"}.get(lot.name, lot.name)


def settings_for(lots, orders, slots, priority):
    return {"origin": str(ORIGIN), "priority": priority, "slots": slots,
            "lots": [asdict(lot) for lot in lots], "orders": [asdict(order) for order in orders],
            "sample_version": hashlib.sha256(json.dumps(SAMPLE, sort_keys=True).encode()).hexdigest()}


def generate(lots, orders, slots, priority, life):
    try:
        allocation = solve(lots, orders, slots, priority)
    except (RuntimeError, ValueError) as exc:
        st.error(str(exc))
        return
    state = st.session_state
    state.inputs = (lots, orders, slots, priority, life)
    state.plan = (settings_for(lots, orders, slots, priority), allocation, uuid4().hex)
    state.saved = False
    set_screen("plan")


def start_page():
    lots, orders = scenario()
    st.title("Plan your tomato harvest")
    st.write("Find out what to pick, which batches to pack, and which orders need a follow-up.")
    with st.container(border=True):
        st.subheader("Try a week on the farm")
        st.caption(f"Example week · {day_label(0)} – {day_label(HORIZON-1)}, {ORIGIN.year}")
        st.write("Two customers need tomatoes on Friday, but your crew can dispatch only one order that day. "
                 "Use the example to see which delivery to make and what to harvest next.")
        cols = st.columns(3)
        cols[0].metric("Tomatoes in storage", f"{sum(l.quantity for l in lots if not l.on_vine)/100:,.2f} kg")
        cols[1].metric("Next harvest available", f"{sum(l.quantity for l in lots if l.on_vine)/100:,.2f} kg")
        cols[2].metric("Confirmed orders", len(orders))
        if st.button("Show my example plan", type="primary", key="start_example"):
            generate(lots, orders, 1, SERVICE, 8)
        st.caption("The example is filled in. You can change it after you see the plan.")
    st.subheader("Want to enter your figures?")
    st.write("Have your batch weights, expected harvest and customer order dates ready. "
             "You can change these figures within the example week.")
    if st.button("Enter my planning inputs", key="start_inputs"):
        set_screen("inputs")


def read_orders(records, dates):
    orders = []
    seen = set()
    for row in records:
        raw_name = row["Customer / order"]
        if pd.isna(raw_name) or not str(raw_name).strip():
            raise ValueError("Give each order a customer name or order reference.")
        name = str(raw_name).strip()
        if name.casefold() in seen or name.casefold() == "lot":
            raise ValueError("Use a different reference for each order. 'Lot' is reserved for batch labels.")
        seen.add(name.casefold())
        amount = centikg(row["Ordered kg"])
        if amount == 0:
            raise ValueError(f"Enter a positive quantity for {name}, or remove the row.")
        if row["Delivery day"] not in dates:
            raise ValueError(f"Choose a delivery day for {name}.")
        reserve = Decimal(str(row["Fresh days after delivery"]))
        if not reserve.is_finite() or reserve != reserve.to_integral_value() or not 0 <= reserve <= 12:
            raise ValueError(f"Enter 0 to 12 whole fresh days for {name}.")
        orders.append(Order(name, amount, dates.index(row["Delivery day"]), int(reserve)))
    if not orders:
        raise ValueError("Add at least one customer order to build a plan.")
    return orders


def inputs_page():
    lots, orders, slots, priority, life = st.session_state.inputs
    if st.button("Back to my plan" if st.session_state.get("plan") else "Back to start"):
        set_screen("plan" if st.session_state.get("plan") else "start")
    st.title("Your planning inputs")
    st.write(f"Use your records to try a different plan for {day_label(0)} – {day_label(6)}, {ORIGIN.year}. "
             "The fields below already contain the example figures.")
    dates = [day_label(i) for i in range(HORIZON)]
    with st.form("planning_inputs"):
        st.subheader("What do you have available?")
        st.write("Enter the weight already picked for each stored batch, then the amount you expect to pick from the crop.")
        weights = []
        for col, lot in zip(st.columns(len(lots)), lots):
            with col:
                weights.append(st.number_input(lot_label(lot) + " (kg)", min_value=0., max_value=100000.,
                                               value=lot.quantity/100, step=.01))
                st.caption(("Ready to pick" if lot.on_vine else "Picked") + " " + day_label(lot.ready))
        st.subheader("Who needs tomatoes, and when?")
        st.write("Edit a cell to change an order. Use the empty row to add one. "
                 "For a customer who needs tomatoes usable for four more days after arrival, enter 4 in the last column.")
        table = pd.DataFrame([{"Customer / order": o.name, "Ordered kg": o.quantity/100,
                               "Delivery day": day_label(o.day), "Fresh days after delivery": o.reserve_days}
                              for o in orders])
        entered = st.data_editor(table, hide_index=True, num_rows="dynamic", key="customer_orders",
            column_config={
                "Customer / order": st.column_config.TextColumn(required=True),
                "Ordered kg": st.column_config.NumberColumn(min_value=.01, max_value=100000., step=.01, required=True),
                "Delivery day": st.column_config.SelectboxColumn(options=dates, required=True),
                "Fresh days after delivery": st.column_config.NumberColumn(min_value=0, max_value=12, step=1, default=0, required=True)})
        st.subheader("What matters most this week?")
        options = [SERVICE, EXPIRY]
        selected = st.radio("Planning priority", options, index=options.index(priority), horizontal=True)
        st.caption("Choose order fulfilment to ship the most kilos, or expiring stock to use more of the older batches.")
        with st.expander("Delivery capacity and storage assumptions"):
            capacity = st.number_input("How many customer orders can you dispatch per day?", 1, 1000, slots,
                                       help="Each delivery to a customer uses one slot. Partial deliveries are allowed.")
            age = st.select_slider("Last usable age for this example (days)",
                                   [r["storage_day"] for r in SAMPLE["quality"]], value=life)
            st.caption("This sets the assumed last usable date from each harvest date. Check the batch condition on your farm.")
        if st.form_submit_button("Build my plan", type="primary"):
            try:
                revised = read_orders(entered.to_dict("records"), dates)
                dated_lots, _ = scenario(age)
                supply = [replace(l, quantity=centikg(w)) for l, w in zip(dated_lots, weights)]
            except (ValueError, TypeError, ArithmeticError) as exc:
                st.error(str(exc))
            else:
                generate(supply, revised, capacity, selected, age)


def plan_page():
    settings, recommended, run_id = st.session_state.plan
    lots, orders, slots, priority, life = st.session_state.inputs
    if st.button("Edit inputs & rebuild", key="edit_inputs"):
        set_screen("inputs")
    st.title("Your harvest and delivery plan")
    st.caption(f"{day_label(0)} – {day_label(6)} · {priority} · {slots} order(s) per dispatch day")
    summary(lots, orders, recommended)
    harvests = [(lot, sum(row)/100) for lot, row in zip(lots, recommended) if lot.on_vine]
    st.subheader("What to pick")
    for lot, amount in harvests:
        if amount:
            st.write(f"Pick **{amount:,.2f} kg** on **{day_label(lot.ready)}** from {lot_label(lot)} for the orders below.")
        else:
            st.write(f"The plan calls for **no additional picking** from {lot_label(lot)} on {day_label(lot.ready)}.")
    st.subheader("What to pack")
    delivery_rows, alerts = [], []
    for j in sorted(range(len(orders)), key=lambda k: orders[k].day):
        order = orders[j]
        shipped = sum(row[j] for row in recommended)
        picks = [f"{row[j]/100:,.2f} kg · {lot_label(lot)}" for lot, row in zip(lots, recommended) if row[j]]
        delivery_rows.append({"Delivery": day_label(order.day), "Customer / order": order.name,
                              "Ordered (kg)": order.quantity/100, "Pack from": " + ".join(picks) or "No delivery scheduled"})
        if shipped < order.quantity:
            alerts.append(f"Contact {order.name} about the {(order.quantity-shipped)/100:,.2f} kg shortfall on {day_label(order.day)}.")
    st.dataframe(pd.DataFrame(delivery_rows), hide_index=True)
    for lot, row in zip(lots, recommended):
        remaining = (lot.quantity-sum(row))/100
        if not lot.on_vine and remaining > 0 and lot.last_day < HORIZON:
            alerts.append(f"Check {lot_label(lot)}: {remaining:,.2f} kg has no order by its assumed last usable date ({day_label(lot.last_day)}).")
    if alerts:
        st.subheader("Needs your attention")
        for alert in alerts:
            st.warning(alert, icon="⚠️")
    with st.expander("Why were these batches chosen?"):
        st.write(f"This plan prioritizes “{priority}”, checks which batches can meet each delivery date and freshness requirement, "
                 f"and allows {slots} customer dispatch(es) per day. When these goals tie, it chooses the plan requiring less picking.")
        for order in orders:
            allowed = [lot_label(l) for l in lots if eligible(l, order) and l.quantity > 0]
            st.text(f"{order.name}: usable through {day_label(order.day+order.reserve_days)}. Eligible batches: {', '.join(allowed) or 'none'}.")
    st.subheader("Confirm your decision")
    if st.session_state.saved:
        st.success("Saved on this computer. Open Saved plans to see your decision.")
        return
    st.write("Save the recommendation as shown, or adjust how many kilograms to send from each batch.")
    names = [o.name for o in orders]
    with st.expander("Adjust batch quantities or add a note"):
        st.caption("Each cell is the weight to send from that batch to that customer. Your changes are checked before saving.")
        review = pd.DataFrame([[lot_label(l), *[q/100 for q in row]] for l, row in zip(lots, recommended)],
                              columns=["Lot", *names])
        edited = st.data_editor(review, key="review_"+run_id, hide_index=True, disabled=["Lot"],
            column_config={n: st.column_config.NumberColumn(label=n+" (kg)", min_value=0., step=.01,
                                                          required=True) for n in names})
        note = st.text_input("Decision note (optional)", key="note_"+run_id)
    try:
        final = [[centikg(r[n]) for n in names] for r in edited.to_dict("records")]
        check(lots, orders, final, slots)
    except (ValueError, ArithmeticError) as exc:
        st.error(str(exc))
        return
    if final != recommended:
        st.write("Your adjusted totals")
        summary(lots, orders, final)
    if st.button("Save this plan", type="primary", key="save_"+run_id):
        payload = dict(settings, recommendation=recommended, accepted=final, note=note,
                       status="Modified" if final != recommended else "Accepted",
                       units="0.01 kg", outcome=metrics(lots, orders, final))
        try:
            with connection() as db:
                db.execute("INSERT INTO decisions VALUES (?, ?, ?)",
                           (run_id, datetime.now(timezone.utc).isoformat(), json.dumps(payload)))
        except sqlite3.IntegrityError:
            st.info("This decision has already been saved.")
        st.session_state.saved = True
        st.rerun()


st.set_page_config(page_title="GreenSense | Tomato planner", page_icon="🌱", layout="wide")
st.html("""
<style>
.stMainBlockContainer {max-width: 1140px; padding-top: 4.5rem;}
.gs-brand {display:flex;align-items:center;gap:.6rem;font:650 1.15rem/1.5 system-ui;color:#234e36;}
.gs-mark {background:#d7eacc;color:#245637;padding:.18rem .52rem;border-radius:.55rem;}
[data-testid="stMetric"] {padding:.65rem .85rem;background:#eff5e9;color:#244c35;border-radius:.65rem;}
[data-testid="stMetric"] label {color:#385742;}
</style>
<div class="gs-brand"><span class="gs-mark" aria-hidden="true">🌱</span> GreenSense</div>
""")
if "inputs" not in st.session_state:
    initial_lots, initial_orders = scenario()
    st.session_state.inputs = (initial_lots, initial_orders, 1, SERVICE, 8)
    st.session_state.screen = "start"
plan_tab, history_tab, source_tab = st.tabs(["Farm planner", "Saved plans", "Example data"])
with plan_tab:
    if st.session_state.screen == "start":
        start_page()
    elif st.session_state.screen == "inputs":
        inputs_page()
    else:
        plan_page()

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
