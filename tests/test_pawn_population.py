import copy
import unittest

from engine import Game, RuleError


def position(count):
    g = Game(mode="debug", round=7, turns=[7, 6], deployment=[100, 100])
    for i in range(count):
        g.add(0, "P", (i % 9, 9 - i // 9))
    return g


class PawnPopulationTests(unittest.TestCase):
    def test_six_pawn_boundary_and_progressive_price(self):
        for count, price in ((0, 1), (5, 1), (6, 3), (7, 5), (8, 7)):
            g = position(count)
            self.assertEqual(g.deployment_quote("P"), (price, 1, 0))
            self.assertEqual(g.deployment_quote("R"), (5, 1, 0))

    def test_actual_charges_stack_with_waiver_and_requote(self):
        g = position(6)
        g.deploy("P", (6, 9), waive_ap=True)
        self.assertEqual(g.deployment[0], 96)
        self.assertEqual(g.ap, 3)
        self.assertEqual(g.deployment_quote("P", True), (7, 0, 2))
        g.deploy("P", (7, 9), waive_ap=True)
        self.assertEqual(g.deployment[0], 89)
        self.assertEqual(g.history[-1]["population_fee"], 4)

    def test_only_own_pawns_count_including_crossed_and_cooling(self):
        g = position(5)
        g.add(1, "P", (0, 0))
        self.assertEqual(g.deployment_quote("P")[0], 1)
        g.add(0, "P", (4, 3), delay=3)
        self.assertEqual(g.deployment_quote("P")[0], 3)
        g.current = 1
        self.assertEqual(g.deployment_quote("P")[0], 1)

    def test_pawn_loss_or_promotion_reduces_next_price(self):
        g = position(7)
        self.assertEqual(g.deployment_quote("P")[0], 5)
        g.pieces.pop()
        self.assertEqual(g.deployment_quote("P")[0], 3)
        g.promote(g.pieces[0].uid, "R")
        self.assertEqual(g.deployment_quote("P")[0], 1)

    def test_insufficient_total_price_does_not_mutate_state(self):
        g = position(6)
        g.deployment[0] = 2
        before = copy.deepcopy(g)
        with self.assertRaises(RuleError):
            g.deploy("P", (6, 9))
        self.assertEqual(g, before)

    def test_hidden_failure_charges_population_fee_but_scores_one(self):
        g = position(6)
        g.add(1, "R", (8, 6))
        g.deploy("P", (8, 6))
        self.assertEqual(g.deployment[0], 97)
        self.assertEqual(g.scores[1], 1)
        self.assertEqual(g.deployment_quote("P")[0], 3)


if __name__ == "__main__":
    unittest.main()
