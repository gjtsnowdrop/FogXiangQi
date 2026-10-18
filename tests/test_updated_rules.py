import copy
import json
from pathlib import Path
import tempfile
import unittest

from engine import Game, RuleError, ALL, SKILLS, SKILL_INFO, skill_cost
from computer.opponent import choose_action


def empty():
    return Game(mode="debug", round=4, turns=[4, 3], deployment=[100, 100])


def cycle(g):
    g.end_turn()
    g.end_turn()


class UpdatedRulesTests(unittest.TestCase):
    def test_three_ap_normal_move_and_skills_keep_explicit_costs(self):
        g = empty()
        pawn = g.add(0, "P", (3, 8))
        self.assertEqual(g.ap, 3)
        g.skill(pawn.uid, 0, dst=(4, 8))
        self.assertEqual(g.ap, 2)
        with self.assertRaises(RuleError):
            g.move(pawn.uid, (4, 7))
        cycle(g)
        g.move(pawn.uid, (4, 7))
        self.assertEqual(g.ap, 0)
        self.assertEqual(skill_cost("R", 0), 2)
        self.assertEqual(skill_cost("N", 0), 2)
        self.assertEqual(skill_cost("C", 2), 1)

    def test_cannon_normal_capture_can_kill_king_and_lands_on_target(self):
        for kind in ("P", "K", "F"):
            g = empty()
            cannon = g.add(0, "C", (4, 7))
            g.add(0, "P", (4, 6))
            g.add(1, kind, (4, 0))
            g.move(cannon.uid, (4, 0))
            self.assertEqual(cannon.pos, (4, 0))
            self.assertEqual(g.winner, 0 if kind == "K" else None)
            self.assertEqual(g.deployment[1], 100)

    def test_bombardment_stationary_refund_only_non_pawns(self):
        for kind in ("P", "R", "C", "N", "B", "A"):
            g = empty()
            g.round = 7
            cannon = g.add(0, "C", (4, 7))
            g.add(0, "P", (4, 6))
            g.add(1, kind, (4, 0))
            g.skill(cannon.uid, 2, dst=(4, 0))
            self.assertEqual(g.by_id(cannon.uid).pos, (4, 7))
            self.assertIsNone(g.at((4, 0)))
            self.assertEqual(g.deployment[1], 100 if kind == "P" else 101)
            self.assertEqual(g.scores[0], g.cost(kind))
            self.assertEqual(g.ap, 2)
            with self.assertRaises(RuleError):
                g.skill(cannon.uid, 0, direction="上")

    def test_bombardment_refuses_real_and_fake_king_atomically(self):
        for kind in ("K", "F"):
            g = empty()
            g.round = 7
            cannon = g.add(0, "C", (4, 7))
            g.add(0, "P", (4, 6))
            g.add(1, kind, (4, 0))
            before = copy.deepcopy(g)
            with self.assertRaises(RuleError):
                g.skill(cannon.uid, 2, dst=(4, 0))
            self.assertEqual(g, before)

    def test_bombardment_miss_costs_one_and_cools_down(self):
        g = empty()
        g.round = 7
        cannon = g.add(0, "C", (4, 7))
        g.add(0, "P", (4, 6))
        g.skill(cannon.uid, 2, dst=(4, 0))
        self.assertEqual(g.by_id(cannon.uid).ready_at, 7)
        self.assertEqual(g.ap, 2)
        self.assertEqual(g.by_id(cannon.uid).pos, (4, 7))

    def test_smoke_only_self_enemy_adjacent_invisible(self):
        g = empty()
        cannon = g.add(0, "C", (0, 8))
        affected = g.add(1, "R", (4, 1))
        enemy = g.add(0, "P", (5, 1))
        g.skill(cannon.uid, 1, dst=(4, 1))
        self.assertEqual(g.piece_vision(g.by_id(affected.uid)), {(4, 1)})
        self.assertNotIn(enemy.uid, {p.uid for p in g.known(1)})

    def test_recon_marks_start_second_owner_turn_and_are_clipped(self):
        g = empty()
        cannon = g.add(0, "C", (3, 7))
        g.add(1, "R", (3, 2))
        invisible = g.add(0, "P", (3, 6))
        g.skill(cannon.uid, 0, direction="上")
        before = g.vision(1)
        self.assertFalse(g.recon_marks(1))
        cycle(g)
        marks = g.recon_marks(1)
        self.assertTrue(marks)
        self.assertTrue(all(cells <= before for _, _, cells in marks))
        self.assertEqual(g.vision(1), before)
        self.assertNotIn(invisible.uid, {p.uid for p in g.known(1)})

    def test_recon_cancels_on_move_and_on_normal_or_skill_attack(self):
        for operation in ("move", "capture", "bombardment", "miss"):
            g = empty()
            g.round = 7
            cannon = g.add(0, "C", (3, 7))
            if operation != "move":
                g.add(0, "P", (3, 5))
                if operation != "miss":
                    g.add(1, "R", (3, 0))
            g.skill(cannon.uid, 0, direction="上")
            cycle(g)
            if operation == "move":
                g.move(cannon.uid, (4, 7))
            elif operation == "bombardment":
                g.skill(cannon.uid, 2, dst=(3, 0))
            else:
                g.move(cannon.uid, (3, 0))
            self.assertIsNone(g.by_id(cannon.uid).recon)
            self.assertFalse(g.recon_marks(1))

    def test_recon_four_turns_for_black_also(self):
        g = empty()
        g.current, g.turns = 1, [4, 4]
        cannon = g.add(1, "C", (3, 2))
        g.skill(cannon.uid, 0, direction="下")
        for _ in range(3):
            cycle(g)
            self.assertIn((3, 9), g.vision(1))
        cycle(g)
        self.assertNotIn((3, 9), g.vision(1))

    def test_hidden_deployment_needs_both_enemy_vision_and_attack(self):
        g = empty()
        g.add(1, "R", (0, 0))
        self.assertIn((0, 8), g.threats(1))
        self.assertNotIn((0, 8), g.vision(1))
        g.deploy("N", (0, 8))
        self.assertIsNotNone(g.at((0, 8)))
        self.assertFalse(g.deploy_locked[0])
        g = empty()
        g.add(1, "R", (0, 6))
        g.deploy("N", (0, 8))
        self.assertIsNone(g.at((0, 8)))
        self.assertTrue(g.deploy_locked[0])
        self.assertEqual(g.scores[1], 4)

    def test_hidden_enemy_vision_without_threat_allows_deployment(self):
        g = empty()
        cannon = g.add(1, "C", (0, 0))
        cannon.recon, cannon.recon_until, cannon.recon_started = "下", 7, 3
        self.assertIn((0, 8), g.vision(1))
        self.assertNotIn((0, 8), g.threats(1))
        g.deploy("P", (0, 8))
        self.assertIsNotNone(g.at((0, 8)))

    def test_deployment_lock_prevents_retry_and_resets_next_own_turn(self):
        g = empty()
        g.add(1, "R", (0, 6))
        king = g.add(0, "K", (4, 9))
        g.deploy("N", (0, 8))
        before = g.deployment[:]
        with self.assertRaises(RuleError):
            g.deploy("P", (8, 9))
        with self.assertRaises(RuleError):
            g.skill(king.uid, 0)
        self.assertEqual(g.deployment, before)
        g.end_turn()
        self.assertTrue(g.deploy_locked[0])
        g.end_turn()
        self.assertFalse(g.deploy_locked[0])
        g.deploy("P", (8, 9))

    def test_rook_cross_three_diagonal_one_and_river_override(self):
        g = empty()
        rook = g.add(0, "R", (4, 7))
        visible = g.piece_vision(rook)
        self.assertIn((1, 7), visible)
        self.assertIn((4, 4), visible)
        self.assertIn((5, 8), visible)
        self.assertNotIn((0, 7), visible)
        self.assertNotIn((6, 9), visible)
        self.assertNotIn((6, 8), visible)
        rook.y = 5
        self.assertEqual(len(g.piece_vision(rook)), 5)

    def test_scout_permanent_stacking_and_enemy_blocks_extra(self):
        g = empty()
        advisor = g.add(0, "A", (3, 9))
        knight = g.add(0, "N", (4, 7))
        g.add(1, "P", (4, 6))
        g.skill(advisor.uid, 2, dst=knight.pos)
        knight = g.by_id(knight.uid)
        visible = g.piece_vision(knight)
        self.assertIn((4, 6), visible)
        self.assertNotIn((4, 5), visible)
        self.assertIn((6, 7), visible)
        cycle(g)
        g.skill(advisor.uid, 2, dst=knight.pos)
        self.assertEqual(g.by_id(knight.uid).scout_bonus, 2)
        self.assertEqual(g.deployment[0], 99)
        knight = g.by_id(knight.uid)
        g.relocate(knight, (4, 3), False)
        self.assertIn((4, 1), g.piece_vision(knight))
        g.relocate(knight, (4, 5), False)
        self.assertEqual(len(g.piece_vision(knight)), 5)

    def test_scout_cannot_initially_select_enemy_half_or_enemy(self):
        for side, dst in ((0, (4, 2)), (1, (4, 7))):
            g = empty()
            advisor = g.add(0, "A", (3, 9))
            g.add(side, "N", dst)
            before = copy.deepcopy(g)
            with self.assertRaises(RuleError):
                g.skill(advisor.uid, 2, dst=dst)
            self.assertEqual(g, before)

    def test_every_skill_has_description(self):
        for kind, names in SKILLS.items():
            self.assertEqual(len(names), len(SKILL_INFO[kind]))
            self.assertTrue(all(SKILL_INFO[kind]))

    def test_new_states_save_roundtrip_and_legacy_load(self):
        g = empty()
        cannon = g.add(0, "C", (3, 7))
        g.skill(cannon.uid, 0, direction="上")
        g.by_id(cannon.uid).scout_bonus = True
        g.deploy_locked[0] = True
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "game.txt"
            g.save(path)
            self.assertEqual(g, Game.load(path))
            data = json.loads(path.read_text(encoding="utf-8"))
            data["version"] = 1
            data.pop("deploy_locked")
            for p in data["pieces"]:
                p.pop("scout_bonus")
                p.pop("recon_started")
            path.write_text(json.dumps(data), encoding="utf-8")
            legacy = Game.load(path)
            self.assertEqual(legacy.deploy_locked, [False, False])
            self.assertFalse(legacy.pieces[0].scout_bonus)

    def test_ai_respects_deployment_lock_and_uses_bombardment(self):
        g = empty()
        g.round = 7
        cannon = g.add(0, "C", (3, 7))
        g.add(0, "P", (3, 5))
        g.add(1, "R", (3, 4))
        g.ap = 2
        action = choose_action(g)
        self.assertEqual(action["type"], "skill")
        self.assertEqual(action["number"], 2)
        g = empty()
        g.ap = 0
        g.deploy_locked[0] = True
        self.assertEqual(choose_action(g)["type"], "end")


if __name__ == "__main__":
    unittest.main()
