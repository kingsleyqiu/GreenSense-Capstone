from dataclasses import replace
import unittest

from planner import EXPIRY, SERVICE, check, metrics, scenario, solve


class PlanningTests(unittest.TestCase):
    def setUp(self):
        self.lots, self.orders = scenario()

    def plan(self, priority=SERVICE, slots=1):
        return solve(self.lots, self.orders, slots, priority)

    def test_priorities_and_removing_slot_conflict(self):
        service = metrics(self.lots, self.orders, self.plan())
        expiry = metrics(self.lots, self.orders, self.plan(EXPIRY))
        self.assertEqual(service, dict(shipped=6250, short=391, at_risk=750, harvest=3125))
        self.assertEqual(expiry, dict(shipped=3516, short=3125, at_risk=359, harvest=0))
        for priority in [SERVICE, EXPIRY]:
            self.assertEqual(metrics(self.lots, self.orders, self.plan(priority, 2))["short"], 0)

    def test_manual_modifications(self):
        valid = self.plan()
        valid[1][1] -= 100
        check(self.lots, self.orders, valid, 1)
        for i, j, amount in [(0, 1, 100), (2, 1, 100), (1, 1, 4000), (0, 0, 101), (2, 2, -1)]:
            with self.subTest(route=(i, j), amount=amount):
                edited = [row.copy() for row in valid]
                edited[i][j] = amount
                with self.assertRaises(ValueError):
                    check(self.lots, self.orders, edited, 1)

    def test_order_date_and_short_stock(self):
        self.orders[2] = replace(self.orders[2], day=0, quantity=10000)
        result = self.plan(slots=2)
        self.assertEqual(result[2][2], 0)
        self.assertGreater(metrics(self.lots, self.orders, result)["short"], 0)

    def test_zero_demand(self):
        self.orders = [replace(o, quantity=0) for o in self.orders]
        self.assertEqual(sum(map(sum, self.plan())), 0)


if __name__ == "__main__":
    unittest.main()
