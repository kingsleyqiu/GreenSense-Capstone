"""Seven-day C1 demonstration. Integer shipment units are 10 grams."""
from dataclasses import dataclass
from datetime import date, timedelta
from itertools import product
from pathlib import Path
import json

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp


SERVICE = "Fulfil confirmed orders"
EXPIRY = "Use expiring stock"
HORIZON = 7
SAMPLE = json.loads(Path(__file__).with_name("sample.json").read_text())
ORIGIN = date.fromisoformat(SAMPLE["harvest"][1]["date"]) + timedelta(days=1)


@dataclass(frozen=True)
class Lot:
    name: str
    quantity: int
    ready: int
    last_day: int
    on_vine: bool


@dataclass(frozen=True)
class Order:
    name: str
    quantity: int
    day: int
    reserve_days: int


def scenario(life=8):
    lots = []
    for i, event in enumerate(SAMPLE["harvest"]):
        day = (date.fromisoformat(event["date"]) - ORIGIN).days
        quantity = round(100 * event["class_a_kg_m2"] * SAMPLE["area_m2"])
        lots.append(Lot(["Stock A", "Stock B", "Harvest C"][i], quantity,
                        day, day + life, day >= 0))
    sales = [r["normalized_sales"] for r in SAMPLE["sales"] if r["normalized_sales"] > 0]
    peak = lots[1].quantity
    small = round(peak * min(sales) / max(sales))
    return lots, [Order("Local pickup", small, 1, 0), Order("Wholesale", peak, 1, 4),
                  Order("Follow-up", peak, 5, 1)]


def eligible(lot, order):
    return lot.ready <= order.day and order.day + order.reserve_days <= lot.last_day


def metrics(lots, orders, allocations):
    used = [sum(row) for row in allocations]
    shipped = sum(used)
    return {
        "shipped": shipped,
        "short": sum(o.quantity for o in orders) - shipped,
        "at_risk": sum(l.quantity - q for l, q in zip(lots, used)
                       if not l.on_vine and l.last_day < HORIZON),
        "harvest": sum(q for l, q in zip(lots, used) if l.on_vine),
    }


def check(lots, orders, allocations, slots):
    if len(allocations) != len(lots) or any(len(r) != len(orders) for r in allocations):
        raise ValueError("Allocation table dimensions have changed.")
    used_slots = [0] * HORIZON
    for lot, row in zip(lots, allocations):
        if any(type(q) is not int or q < 0 for q in row):
            raise ValueError("Enter non-negative quantities in steps of 0.01 kg.")
        if sum(row) > lot.quantity:
            raise ValueError(f"{lot.name} exceeds its available quantity.")
        for order, q in zip(orders, row):
            if q and not eligible(lot, order):
                raise ValueError(f"{lot.name} cannot meet {order.name}'s date and remaining-life requirement.")
    for j, order in enumerate(orders):
        quantity = sum(row[j] for row in allocations)
        if quantity > order.quantity:
            raise ValueError(f"{order.name} exceeds the confirmed quantity.")
        if quantity:
            used_slots[order.day] += 1
    if max(used_slots) > slots:
        raise ValueError("The plan exceeds the daily number of order dispatch slots.")


def solve(lots, orders, slots, priority):
    """Solve exact successive objectives, fixing each achieved value before the next."""
    if priority not in (SERVICE, EXPIRY) or slots < 1:
        raise ValueError("Choose a valid priority and at least one dispatch slot.")
    if any(o.quantity < 0 or not 0 <= o.day < HORIZON or o.reserve_days < 0 for o in orders):
        raise ValueError("Check the order quantities, dates and remaining-life requirements.")
    n, m = len(lots), len(orders)
    routes = list(product(range(n), range(m)))
    # x[i,j] shipment, y[j] dispatch activation, h[i] picked from future event.
    dispatch = n*m
    harvest = dispatch + m
    size = harvest + n
    hi = np.zeros(size)
    constraints = []
    for k, (i, j) in enumerate(routes):
        if eligible(lots[i], orders[j]):
            hi[k] = min(lots[i].quantity, orders[j].quantity)
    hi[dispatch:harvest] = 1
    for i, lot in enumerate(lots):
        row = np.zeros(size)
        row[i*m:(i+1)*m] = 1
        if lot.on_vine:
            hi[harvest+i] = lot.quantity
            row[harvest+i] = -1
            constraints.append(LinearConstraint(row, 0, 0))
        else:
            constraints.append(LinearConstraint(row, 0, lot.quantity))
    for j, order in enumerate(orders):
        row = np.zeros(size)
        row[j:dispatch:m] = 1
        row[dispatch+j] = -order.quantity
        constraints.append(LinearConstraint(row, -np.inf, 0))
    for day in range(HORIZON):
        row = np.zeros(size)
        row[dispatch:harvest] = [o.day == day for o in orders]
        constraints.append(LinearConstraint(row, 0, slots))
    service = np.zeros(size)
    service[:dispatch] = -1
    expiry = np.zeros(size)
    for k, (i, _) in enumerate(routes):
        if not lots[i].on_vine and lots[i].last_day < HORIZON:
            expiry[k] = -1
    picking = np.zeros(size)
    picking[harvest:] = 1
    objectives = [service, expiry] if priority == SERVICE else [expiry, service]
    for cost in [*objectives, picking]:
        result = milp(cost, integrality=np.ones(size), bounds=Bounds(0, hi),
                      constraints=constraints, options={"mip_rel_gap": 0.0})
        if not result.success:
            raise RuntimeError(f"C1 could not produce a plan: {result.message}")
        value = round(result.fun)
        constraints.append(LinearConstraint(cost, value, value))
    allocations = np.rint(result.x[:dispatch]).reshape(n, m).astype(int).tolist()
    check(lots, orders, allocations, slots)
    return allocations
