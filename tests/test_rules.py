import copy
import json
from pathlib import Path
import tempfile
import unittest

from engine import Game, RuleError, ALL, coord, parse_coord
from computer.opponent import choose_action, apply_action


def empty():
    return Game(mode="debug", round=4, turns=[4, 3], deployment=[100, 100])


def cycle(g):
    g.end_turn()
    g.end_turn()


class RulesTests(unittest.TestCase):
    def test_initial_board_and_coordinate_roundtrip(self):
        g = Game.new()
        self.assertEqual(len(g.pieces), 32)
        self.assertEqual(g.at((4, 9)).kind, "K")
        for pos in ALL:
            self.assertEqual(parse_coord(coord(pos)), pos)

    def test_diamond_vision_and_opening_bonus(self):
        g = empty()
        g.add(0, "B", (4, 7))
        self.assertEqual(g.vision(0), {(4, 7), (4, 6), (4, 8), (3, 7), (5, 7)})
        counts = []
        for r in (1, 2, 3, 4):
            g.round = r
            counts.append(len(g.vision(0)))
        self.assertEqual(counts, sorted(counts, reverse=True))

    def test_river_forces_radius_one(self):
        g = empty()
        g.round = 1
        p = g.add(0, "C", (4, 5))
        self.assertEqual(len(g.vision(0)), 5)
        with self.assertRaises(RuleError):
            g.skill(p.uid, 0, direction="上")

    def test_home_pawn_and_terrain_vision(self):
        g = empty()
        p = g.add(0, "P", (2, 6))
        self.assertIn((2, 3), g.vision(0))
        p.x, p.y = 4, 2
        self.assertEqual(len(g.vision(0)), 5)

    def test_advisor_palace_and_mask(self):
        g = empty()
        g.add(0, "A", (3, 9))
        self.assertTrue({(x, y) for x in (3, 4, 5) for y in (7, 8, 9)} <= g.vision(0))
        g.add(1, "A", (4, 7))
        self.assertNotIn((4, 8), g.vision(0))

    def test_move_cost_capture_and_victory(self):
        g = empty()
        p = g.add(0, "R", (4, 6))
        g.add(1, "K", (4, 5))
        g.move(p.uid, (4, 5))
        self.assertEqual(g.ap, 0)
        self.assertEqual(g.winner, 0)
        self.assertEqual(g.scores, [30, 0])
        self.assertEqual(g.deployment, [130, 100])

    def test_fake_capture_not_victory(self):
        g = empty()
        p = g.add(0, "R", (4, 6))
        g.add(1, "F", (4, 5))
        g.move(p.uid, (4, 5))
        self.assertIsNone(g.winner)
        self.assertEqual(g.scores[0], 15)

    def test_hidden_obstacle_stops_rook(self):
        g = empty()
        p = g.add(0, "R", (0, 8))
        blocker = g.add(1, "P", (0, 4))
        g.move(p.uid, (0, 0))
        self.assertEqual(p.pos, (0, 5))
        self.assertIn(blocker, g.pieces)
        self.assertEqual(g.ap, 0)

    def test_cannon_blind_miss_cooldown(self):
        g = empty()
        p = g.add(0, "C", (1, 7))
        g.add(0, "P", (1, 5))
        g.move(p.uid, (1, 0))
        self.assertEqual(p.pos, (1, 7))
        for _ in range(2):
            cycle(g)
            with self.assertRaises(RuleError):
                g.move(p.uid, (2, 7))
        cycle(g)
        g.move(p.uid, (2, 7))

    def test_cannon_blind_capture(self):
        g = empty()
        p = g.add(0, "C", (1, 7))
        g.add(0, "P", (1, 5))
        g.add(1, "R", (1, 0))
        g.move(p.uid, (1, 0))
        self.assertEqual(p.pos, (1, 0))
        self.assertEqual(g.at((1, 0)).uid, p.uid)
        self.assertEqual(g.scores[0], 5)

    def test_income_schedule(self):
        for r, expected in ((3, 0), (4, 1), (5, 0), (6, 1), (30, 1), (31, 1), (50, 2)):
            g = empty()
            g.round = r
            g.end_turn()
            self.assertEqual(g.deployment[1], 100 + expected)

    def test_deploy_paid_and_delay(self):
        g = empty()
        g.deploy("R", (0, 9))
        self.assertEqual(g.ap, 2)
        self.assertEqual(g.deployment[0], 95)
        p = g.at((0, 9))
        with self.assertRaises(RuleError):
            g.move(p.uid, (0, 8))
        cycle(g)
        g.move(p.uid, (0, 8))

    def test_deploy_ordinary_two_future_turns(self):
        g = empty()
        g.deploy("P", (2, 8))
        p = g.at((2, 8))
        for _ in range(2):
            cycle(g)
            with self.assertRaises(RuleError):
                g.move(p.uid, (2, 7))
        cycle(g)
        g.move(p.uid, (2, 7))

    def test_hidden_deploy_failure_spends_and_scores(self):
        g = empty()
        g.add(1, "R", (0, 6))
        before = g.deployment[0]
        result = g.deploy("N", (0, 8))
        self.assertIn("失败", result)
        self.assertEqual(g.deployment[0], before - 4)
        self.assertEqual(g.scores[1], 4)
        self.assertIsNone(g.at((0, 8)))

    def test_known_deploy_failure_no_spending(self):
        g = empty()
        g.add(0, "P", (1, 6))
        g.add(1, "R", (1, 5))
        with self.assertRaises(RuleError):
            g.deploy("P", (2, 5))
        self.assertEqual(g.deployment[0], 100)

    def test_advisor_outside_palace_immobile(self):
        g = empty()
        p = g.add(0, "A", (2, 8))
        with self.assertRaises(RuleError):
            g.move(p.uid, (3, 9))

    def test_pawn_promotion_surcharge(self):
        g = empty()
        p = g.add(0, "P", (3, 3))
        g.promote(p.uid, "R")
        self.assertEqual(p.kind, "R")
        self.assertEqual(g.deployment[0], 93)
        self.assertEqual(g.ap, 1)

    def test_pawn_adjust_and_skill_limit(self):
        g = empty()
        p = g.add(0, "P", (3, 8))
        g.skill(p.uid, 0, dst=(4, 8))
        self.assertEqual(g.by_id(p.uid).pos, (4, 8))
        with self.assertRaises(RuleError):
            g.skill(p.uid, 1)
        self.assertEqual(g.ap, 2)

    def test_pawn_retreat_blocked(self):
        g = empty()
        p = g.add(0, "P", (3, 6))
        g.add(0, "R", (3, 8))
        g.skill(p.uid, 1)
        self.assertEqual(g.by_id(p.uid).pos, (3, 7))

    def test_recon_direction_and_expiry(self):
        g = empty()
        p = g.add(0, "C", (3, 7))
        g.skill(p.uid, 0, direction="上")
        self.assertIn((3, 0), g.vision(0))
        self.assertNotIn((4, 7), g.vision(0))
        for _ in range(3):
            cycle(g)
            self.assertIn((3, 0), g.vision(0))
        cycle(g)
        self.assertIn((4, 7), g.vision(0))
        self.assertNotIn((3, 0), g.vision(0))

    def test_smoke_zero_vision_then_exit(self):
        g = empty()
        cannon = g.add(0, "C", (0, 8))
        p = g.add(1, "R", (4, 1))
        g.skill(cannon.uid, 1, dst=(4, 1))
        self.assertEqual(g.vision(1), {(4, 1)})
        g.relocate(g.by_id(p.uid), (4, 3), False)
        self.assertTrue(g.vision(1))
        g.relocate(g.by_id(p.uid), (4, 1), False)
        self.assertTrue(g.vision(1))

    def test_smoke_duration(self):
        g = empty()
        cannon = g.add(0, "C", (0, 8))
        g.add(1, "R", (4, 1))
        g.skill(cannon.uid, 1, dst=(4, 1))
        g.end_turn()
        self.assertEqual(g.vision(1), {(4, 1)})
        g.end_turn()
        g.end_turn()
        self.assertEqual(g.vision(1), {(4, 1)})
        g.end_turn()
        g.end_turn()
        self.assertTrue(g.vision(1))

    def test_black_smoke_affects_next_two_red_turns(self):
        g = empty()
        g.current = 1
        g.turns = [4, 4]
        cannon = g.add(1, "C", (0, 1))
        g.add(0, "R", (4, 8))
        g.skill(cannon.uid, 1, dst=(4, 8))
        for _ in range(2):
            g.end_turn()
            self.assertEqual(g.vision(0), {(4, 8)})
            g.end_turn()
        g.end_turn()
        self.assertTrue(g.vision(0))

    def test_hp_extension_preserves_occupied_target_until_killed(self):
        from unittest.mock import patch
        from engine import CONFIG
        g = empty()
        p = g.add(0, "R", (4, 6))
        target = g.add(1, "K", (4, 5))
        target.hp = target.max_hp = 2
        with patch.dict(CONFIG, instant_kill=False):
            g.move(p.uid, (4, 5))
            self.assertEqual(target.hp, 1)
            self.assertEqual(p.pos, (4, 6))
            self.assertIsNone(g.winner)
            cycle(g)
            g.move(p.uid, (4, 5))
            self.assertEqual(g.winner, 0)

    def test_rook_exit(self):
        g = empty()
        p = g.add(0, "R", (0, 9))
        g.add(0, "N", (0, 8))
        g.skill(p.uid, 0, dst=(0, 6))
        self.assertEqual(g.by_id(p.uid).pos, (0, 6))
        self.assertEqual(g.ap, 1)

    def test_rook_push_and_block(self):
        for blocked in (False, True):
            g = empty()
            p = g.add(0, "R", (0, 9))
            target = g.add(1, "P", (0, 6))
            if blocked:
                g.add(1, "P", (0, 5))
            g.skill(p.uid, 1, dst=(0, 6))
            self.assertEqual(g.by_id(p.uid).pos, (0, 7))
            self.assertEqual(g.by_id(target.uid).pos, (0, 6) if blocked else (0, 5))

    def test_knight_double_move_and_block(self):
        g = empty()
        p = g.add(0, "N", (1, 9))
        g.skill(p.uid, 0, first=(2, 7), dst=(4, 6))
        self.assertEqual(g.by_id(p.uid).pos, (4, 6))
        g = empty()
        p = g.add(0, "N", (1, 9))
        g.add(1, "P", (3, 7))
        g.skill(p.uid, 0, first=(2, 7), dst=(4, 6))
        self.assertEqual(g.by_id(p.uid).pos, (2, 7))
        self.assertEqual(g.by_id(p.uid).ready_at, 7)

    def test_knight_ignore_leg(self):
        g = empty()
        p = g.add(0, "N", (1, 9))
        g.add(0, "P", (1, 8))
        g.skill(p.uid, 1, dst=(2, 7))
        self.assertEqual(g.by_id(p.uid).pos, (2, 7))
        self.assertEqual(g.ap, 2)

    def test_bishop_stealth_and_reveal(self):
        g = empty()
        p = g.add(0, "B", (2, 9))
        g.add(1, "R", (2, 8))
        g.skill(p.uid, 0)
        self.assertNotIn((2, 9), g.vision(1))
        cycle(g)
        g.move(p.uid, (4, 7))
        self.assertFalse(g.by_id(p.uid).hidden)

    def test_bishop_transform_atomic_failure(self):
        g = empty()
        p = g.add(0, "B", (2, 9))
        before = copy.deepcopy(g.__dict__)
        with self.assertRaises(RuleError):
            g.skill(p.uid, 1, kind="R", dst=(3, 8))
        self.assertEqual(g.__dict__, before)
        g.skill(p.uid, 1, kind="R", dst=(2, 7))
        self.assertEqual(g.by_id(p.uid).kind, "R")
        self.assertEqual(g.by_id(p.uid).pos, (2, 7))
        self.assertEqual(g.scores[1], 1)
        self.assertEqual(g.deployment, [95, 101])

    def test_logistics_growth_and_disguise_once(self):
        g = empty()
        p = g.add(0, "A", (3, 9))
        g.skill(p.uid, 0)
        self.assertEqual(g.deployment[0], 102)
        cycle(g)
        g.skill(p.uid, 1, dst=(4, 9))
        self.assertEqual(g.at((4, 9)).kind, "F")
        cycle(g)
        with self.assertRaises(RuleError):
            g.skill(p.uid, 1, dst=(5, 9))

    def test_king_deploy_all_terrain(self):
        g = empty()
        p = g.add(0, "K", (4, 9))
        g.skill(p.uid, 0)
        soldiers = [q for q in g.pieces if q.kind == "P"]
        self.assertEqual(len(soldiers), 7)
        self.assertEqual(g.deployment[0], 98)
        self.assertEqual(g.at((1, 7)).ready_at, 5)
        self.assertEqual(g.at((0, 6)).ready_at, 7)

    def test_flying_king_kill_or_stop(self):
        g = empty()
        p = g.add(0, "K", (4, 9))
        g.add(1, "K", (4, 0))
        g.skill(p.uid, 1)
        self.assertEqual(g.winner, 0)
        self.assertEqual(g.by_id(p.uid).pos, (4, 0))
        g = empty()
        p = g.add(0, "K", (4, 9))
        g.add(1, "P", (4, 3))
        g.skill(p.uid, 1)
        self.assertEqual(g.by_id(p.uid).pos, (4, 4))
        cycle(g)
        with self.assertRaises(RuleError):
            g.move(p.uid, (4, 3))

    def test_crossed_king_moves_in_enemy_palace(self):
        g = empty()
        p = g.add(0, "K", (4, 9))
        g.skill(p.uid, 1)
        cycle(g)
        g.move(p.uid, (5, 0))
        self.assertEqual(g.by_id(p.uid).pos, (5, 0))

    def test_handoff_blocks_all_actions(self):
        g = Game.new()
        g.end_turn()
        self.assertTrue(g.pending_handoff)
        with self.assertRaises(RuleError):
            g.end_turn()
        g.pending_handoff = False
        g.end_turn()
        self.assertEqual(g.round, 2)

    def test_save_roundtrip_all_state(self):
        g = empty()
        p = g.add(0, "C", (1, 7))
        g.add(1, "P", (2, 2))
        g.skill(p.uid, 1, dst=(2, 2))
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "game.txt"
            g.save(path)
            self.assertEqual(g, Game.load(path))
            data = json.loads(path.read_text(encoding="utf-8"))
            data["pieces"][0]["x"] = 10
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(RuleError):
                Game.load(path)

    def test_ratings_priority_and_half(self):
        g = empty()
        g.winner = 0
        for scores, label in (([31, 10], "不可思议的胜利"), ([21, 10], "压倒性完胜"),
                              ([11, 10], "不错的胜利"), ([5, 10], "胶着的胜利"), ([4, 10], "损失惨重的胜利")):
            g.scores = scores
            self.assertEqual(g.rating(0), label)

    def test_ai_never_peeks_hidden_or_fake_identity(self):
        g = empty()
        g.add(0, "R", (0, 8))
        h = copy.deepcopy(g)
        h.add(1, "R", (8, 0))
        self.assertEqual(choose_action(g), choose_action(h))
        g.add(1, "F", (0, 7))
        h = copy.deepcopy(g)
        h.at((0, 7)).kind = "K"
        self.assertEqual(choose_action(g), choose_action(h))

    def test_ai_plays_multiple_turns(self):
        g = Game.new("ai")
        for _ in range(40):
            if g.winner is not None:
                break
            action = choose_action(g)
            try:
                apply_action(g, action)
            except RuleError:
                g.end_turn()
        self.assertGreater(g.round, 1)
        self.assertTrue(g.history)


if __name__ == "__main__":
    unittest.main()
