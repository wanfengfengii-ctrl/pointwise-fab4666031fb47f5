import unittest
from dataclasses import asdict

from tests.fixture import WallTestCase

SPARE_SCREEN = "panel-spare"


def prepare(case):
    frames = {}
    for label, value in (("A", 21), ("B", 82), ("C", 143)):
        pixels = [[[value, 0, 0], [0, 0, 0]], [[0, value, 0], [0, 0, 0]]]
        revision = case.artwork(pixels, f"replacement-{label}")
        frames[label] = case.sheet(revision)["left_frame_id"]

    order_a = case.dispatch("left", frames["A"], "swap-a")
    before = case.pulse(9)
    case.hold_loads = True
    case.hold_receipts = True
    order_b = case.dispatch("left", frames["B"], "swap-b")
    load_b = case.envelopes.pop()
    case.load(load_b)
    receipt_b = case.receipts.pop()
    order_c = case.dispatch("left", frames["C"], "swap-c")
    load_c = case.envelopes.pop()
    return {"frames": frames, "orders": {"A": order_a, "B": order_b, "C": order_c},
            "before": before, "load_b": load_b, "receipt_b": receipt_b, "load_c": load_c}


class ReplacementSetupTests(WallTestCase):
    def test_first_delivery_after_pulse(self):
        scene = prepare(self)
        a, b, c = (scene["orders"][label]["dispatch_id"] for label in ("A", "B", "C"))
        self.assertEqual(self.front()["dispatch_id"], a)
        self.assertEqual([self.order(number)["status"] for number in (b, c)], ["pending", "pending"])
        self.assertEqual(self.counts("load_receipts"), (2,))
        self.load(scene["load_c"], "panel-R", status=409)
        self.assertEqual(self.load(scene["load_b"]), asdict(scene["receipt_b"]))
        self.assertEqual(self.counts("load_receipts"), (2,))
        self.assertEqual([(row["screen_id"], row["dispatch_id"]) for row in self.pulse(10)["shown"]],
                         [("panel-L", b)])
        self.load(scene["load_c"])
        self.assertTrue(self.app.acknowledge(scene["receipt_b"]))
        self.assertEqual(self.order(b)["status"], "confirmed")
        self.assertEqual([(row["screen_id"], row["dispatch_id"]) for row in self.pulse(11)["shown"]],
                         [("panel-L", c)])
        self.assertEqual(self.pulse(9), scene["before"])

    def test_first_delivery_before_pulse(self):
        scene = prepare(self)
        c = scene["orders"]["C"]["dispatch_id"]
        self.load(scene["load_c"])
        self.assertEqual(self.load(scene["load_b"]), asdict(scene["receipt_b"]))
        self.assertEqual([(row["screen_id"], row["dispatch_id"]) for row in self.pulse(10)["shown"]],
                         [("panel-L", c)])
        self.assertEqual(self.pulse(11)["shown"], [])


if __name__ == "__main__":
    unittest.main()
