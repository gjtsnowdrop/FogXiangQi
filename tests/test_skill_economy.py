import copy
import json
from pathlib import Path
import tempfile
import unittest

from engine import Game, RuleError
from computer.opponent import choose_action, apply_action


def empty():
    return Game(mode="debug", round=7, turns=[7, 6], deployment=[100, 100])


def cycle(g):
    g.end_turn()
    g.end_turn()


class SkillEconomyTests(unittest.TestCase):
    def test_scout_stack_cost_sequence_and_per_target_independence(self):
        g = empty()
        advisors = [g.add(0, "A", (x, 9)) for x in (3, 4, 5)]
        target = g.add(0, "N", (4, 7))
        other = g.add(0, "N", (8, 7))
        for advisor, expected_fee in zip(advisors, (0, 1, 2)):
            before = g.deployment[0]
            g.skill(advisor.uid, 2, dst=target.pos)
            self.assertEqual(before - g.deployment[0], expected_fee)
        target = g.by_id(target.uid)
        self.assertEqual(target.scout_bonus, 3)
        self.assertIn((4, 3), g.piece_vision(target))
        cycle(g)
        before = g.deployment[0]
        g.skill(advisors[0].uid, 2, dst=other.pos)
        self.assertEqual(g.deployment[0], before)
        self.assertEqual(g.by_id(other.uid).scout_bonus, 1)

    def test_scout_insufficient_points_is_atomic_and_river_stays_one(self):
        g = empty()
        advisor = g.add(0, "A", (3, 9))
        target = g.add(0, "N", (4, 7))
        target.scout_bonus = 3
        g.deployment[0] = 2
        before = copy.deepcopy(g)
        with self.assertRaises(RuleError):
            g.skill(advisor.uid, 2, dst=target.pos)
        self.assertEqual(g, before)
        g.relocate(target, (4, 5), False)
        self.assertEqual(len(g.piece_vision(target)), 5)

    def test_deploy_normal_cost_one_and_waivers_escalate(self):
        g = empty()
        g.deploy("P", (0, 9))
        self.assertEqual((g.ap, g.deployment[0]), (2, 99))
        for x, fee in ((1, 1), (2, 2), (3, 3)):
            before = g.deployment[0]
            g.deploy("P", (x, 9), waive_ap=True)
            self.assertEqual(before - g.deployment[0], 1 + fee)
            self.assertEqual(g.ap, 2)
        self.assertEqual(g.deployment_waivers, [3, 0])
        g.deploy("P", (4, 9))
        self.assertEqual(g.ap, 1)
        self.assertEqual(g.deployment_quote("P", True), (5, 0, 4))
        g.end_turn()
        self.assertEqual(g.deployment_waivers, [3, 0])
        g.deploy("P", (0, 0), waive_ap=True)
        self.assertEqual(g.deployment_waivers, [3, 1])
        g.end_turn()
        self.assertEqual(g.deployment_waivers, [0, 1])

    def test_zero_ap_only_waiver_and_insufficient_or_invalid_is_atomic(self):
        g = empty()
        g.ap = 0
        before = copy.deepcopy(g)
        with self.assertRaises(RuleError):
            g.deploy("P", (0, 9))
        self.assertEqual(g, before)
        g.deploy("P", (0, 9), waive_ap=True)
        self.assertEqual(g.ap, 0)
        g.deployment[0] = 2
        before = copy.deepcopy(g)
        with self.assertRaises(RuleError):
            g.deploy("P", (1, 9), waive_ap=True)
        self.assertEqual(g, before)
        with self.assertRaises(RuleError):
            g.deploy("K", (1, 9), waive_ap=True)
        self.assertEqual(g, before)

    def test_failed_discount_deployment_charges_and_counts_attempt(self):
        g = empty()
        g.add(1, "R", (0, 6))
        g.ap = 0
        g.deploy("P", (0, 8), waive_ap=True)
        self.assertEqual(g.deployment[0], 98)
        self.assertEqual(g.scores[1], 1)
        self.assertEqual(g.deployment_waivers[0], 1)
        self.assertTrue(g.deploy_locked[0])
        with self.assertRaises(RuleError):
            g.deploy("P", (8, 9), waive_ap=True)

    def test_bombardment_first_six_rounds_locked_other_skills_work(self):
        for round_number in range(1, 7):
            g = empty()
            g.round = round_number
            cannon = g.add(0, "C", (3, 7))
            g.add(0, "P", (3, 5))
            self.assertFalse(g.skill_ready(cannon, 2))
            self.assertTrue(g.skill_ready(cannon, 0))
            before = copy.deepcopy(g)
            with self.assertRaises(RuleError):
                g.skill(cannon.uid, 2, dst=(3, 0))
            self.assertEqual(g, before)
        g.round = 7
        self.assertTrue(g.skill_ready(cannon, 2))

    def test_bombardment_cooldown_allows_only_one_turn_recon(self):
        g = empty()
        cannon = g.add(0, "C", (3, 7))
        g.add(0, "P", (3, 5))
        g.skill(cannon.uid, 2, dst=(3, 0))
        self.assertEqual(g.by_id(cannon.uid).cooldown_reason, "bombardment")
        self.assertFalse(g.skill_ready(g.by_id(cannon.uid), 0))
        for _ in range(2):
            cycle(g)
            p = g.by_id(cannon.uid)
            self.assertTrue(g.skill_ready(p, 0))
            self.assertFalse(g.skill_ready(p, 1))
            self.assertFalse(g.skill_ready(p, 2))
            with self.assertRaises(RuleError):
                g.move(p.uid, (4, 7))
            g.skill(p.uid, 0, direction="上")
            self.assertEqual(g.by_id(p.uid).recon_until, g.turns[0] + 1)
        cycle(g)
        p = g.by_id(cannon.uid)
        self.assertFalse(g.recon_active(p))
        self.assertTrue(g.skill_ready(p, 1))
        g.skill(p.uid, 0, direction="上")
        self.assertEqual(g.by_id(p.uid).recon_until, g.turns[0] + 4)

    def test_normal_cannon_miss_keeps_full_cooldown_restriction(self):
        g = empty()
        cannon = g.add(0, "C", (3, 7))
        g.add(0, "P", (3, 5))
        g.move(cannon.uid, (3, 0))
        cycle(g)
        self.assertFalse(g.skill_ready(g.by_id(cannon.uid), 0))

    def test_bishop_guard_friendly_swap_retains_both_without_scores(self):
        g = empty()
        bishop = g.add(0, "B", (2, 9))
        rook = g.add(0, "R", (4, 7))
        g.skill(bishop.uid, 2, dst=rook.pos)
        self.assertEqual(g.by_id(bishop.uid).pos, (4, 7))
        self.assertEqual(g.by_id(rook.uid).pos, (2, 9))
        self.assertEqual(g.scores, [0, 0])
        self.assertEqual(g.ap, 2)

    def test_bishop_guard_enemy_swap_then_enemy_eats_bishop(self):
        g = empty()
        bishop = g.add(0, "B", (2, 9))
        enemy = g.add(1, "P", (4, 7))
        g.skill(bishop.uid, 2, dst=enemy.pos)
        self.assertIsNone(g.by_id(bishop.uid))
        self.assertEqual(g.by_id(enemy.uid).pos, (2, 9))
        self.assertEqual(g.scores, [0, 3])
        self.assertEqual(g.deployment, [100, 103])
        self.assertIsNone(g.winner)

    def test_bishop_guard_requires_target_attack_range_and_clear_eye(self):
        for target_pos, blocked in (((3, 8), False), ((4, 7), True), ((2, 3), False)):
            g = empty()
            bishop = g.add(0, "B", (2, 9))
            g.add(0, "R", target_pos)
            if blocked:
                g.add(0, "P", (3, 8))
            before = copy.deepcopy(g)
            with self.assertRaises(RuleError):
                g.skill(bishop.uid, 2, dst=target_pos)
            self.assertEqual(g, before)

    def test_bishop_guard_updates_smoke_and_stealth_state(self):
        g = empty()
        bishop = g.add(0, "B", (2, 9))
        cannon = g.add(0, "C", (4, 7))
        bishop.hidden = True
        cannon.recon, cannon.recon_until = "上", 20
        g.smoke = [dict(cells=[[2, 9]], victims=[bishop.uid], until=[20, 20])]
        g.skill(bishop.uid, 2, dst=cannon.pos)
        self.assertFalse(g.by_id(bishop.uid).hidden)
        self.assertFalse(g.smoked(g.by_id(bishop.uid)))
        self.assertIsNone(g.by_id(cannon.uid).recon)

    def test_new_state_save_roundtrip_and_legacy_boolean_scout_upgrade(self):
        g = empty()
        cannon = g.add(0, "C", (3, 7))
        g.add(0, "P", (3, 5))
        g.skill(cannon.uid, 2, dst=(3, 0))
        g.by_id(cannon.uid).scout_bonus = 3
        g.deployment_waivers = [2, 1]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "game.txt"
            g.save(path)
            self.assertEqual(g, Game.load(path))
            data = json.loads(path.read_text(encoding="utf-8"))
            data["version"] = 2
            data.pop("deployment_waivers")
            for p in data["pieces"]:
                p.pop("cooldown_reason")
                p["scout_bonus"] = True
            path.write_text(json.dumps(data), encoding="utf-8")
            legacy = Game.load(path)
            self.assertEqual(legacy.deployment_waivers, [0, 0])
            self.assertEqual(legacy.pieces[0].scout_bonus, 1)

    def test_ai_handles_waivers_and_special_recon_cooldown(self):
        g = empty()
        cannon = g.add(0, "C", (3, 7))
        g.cool_down(cannon, "bombardment")
        g.deployment[0] = 0
        action = choose_action(g)
        self.assertEqual((action["type"], action["number"]), ("skill", 0))
        apply_action(g, action)
        self.assertEqual(g.by_id(cannon.uid).recon_until, g.turns[0] + 1)
        g = empty()
        g.ap = 0
        g.add(0, "K", (4, 9))
        action = choose_action(g)
        self.assertEqual(action["type"], "deploy")
        self.assertTrue(action["waive_ap"])
        apply_action(g, action)
        self.assertEqual(g.deployment_waivers[0], 1)


if __name__ == "__main__":
    unittest.main()
