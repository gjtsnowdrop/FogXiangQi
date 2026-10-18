import copy
from pathlib import Path
import tempfile
import unittest

from engine import Game
from computer.opponent import choose_action


def empty():
    return Game(mode="debug", round=7, turns=[7, 6], deployment=[20, 20])


def cloud(g, cells):
    g.smoke.append(dict(cells=[list(p) for p in cells], until=[g.turns[0] + 2, g.turns[1] + 3]))


class SmokeCoverTests(unittest.TestCase):
    def test_outside_observer_cannot_see_inside_enemy_or_empty_cells(self):
        g = empty()
        observer = g.add(0, "R", (4, 7))
        enemy = g.add(1, "P", (4, 6))
        cells = {(4, 6), (5, 6), (4, 5), (5, 5)}
        self.assertIn(enemy.pos, g.vision(0))
        cloud(g, cells)
        self.assertFalse(g.piece_vision(observer) & cells)
        self.assertFalse(g.vision(0) & cells)
        self.assertNotIn(enemy.uid, {p.uid for p in g.known(0)})

    def test_inside_friendly_only_reveals_self_not_neighbors(self):
        g = empty()
        friend = g.add(0, "R", (4, 7))
        g.add(0, "C", (4, 9))
        enemy = g.add(1, "P", (5, 7))
        cloud(g, {(4, 7), (5, 7), (4, 6), (5, 6)})
        self.assertEqual(g.piece_vision(friend), {friend.pos})
        self.assertIn(friend.pos, g.vision(0))
        self.assertNotIn(enemy.pos, g.vision(0))
        self.assertNotIn((4, 6), g.vision(0))

    def test_entry_exit_and_reentry_follow_active_area(self):
        g = empty()
        friend = g.add(0, "R", (3, 7))
        cloud(g, {(4, 7), (5, 7), (4, 6), (5, 6)})
        g.relocate(friend, (4, 7), False)
        self.assertTrue(g.smoked(friend))
        self.assertEqual(g.piece_vision(friend), {(4, 7)})
        g.relocate(friend, (3, 7), False)
        self.assertFalse(g.smoked(friend))
        self.assertIn((2, 7), g.piece_vision(friend))
        g.relocate(friend, (4, 7), False)
        self.assertEqual(g.piece_vision(friend), {(4, 7)})

    def test_opening_terrain_scout_and_palace_cannot_bypass_smoke(self):
        g = empty()
        g.round = 1
        observer = g.add(0, "C", (1, 7))
        observer.scout_bonus = 5
        advisor = g.add(0, "A", (3, 9))
        covered = {(4, 8), (5, 8), (4, 7), (5, 7)}
        cloud(g, covered)
        self.assertFalse(g.piece_vision(observer) & covered)
        self.assertFalse(g.piece_vision(advisor) & covered)
        self.assertFalse(g.vision(0) & covered)

    def test_recon_and_enemy_recon_marks_do_not_reveal_smoke(self):
        g = empty()
        observer = g.add(0, "C", (3, 7))
        observer.recon, observer.recon_until, observer.recon_started = "上", 20, 6
        g.add(1, "R", (3, 2))
        cells = {(3, 3), (4, 3), (3, 2), (4, 2)}
        cloud(g, cells)
        self.assertFalse(g.vision(0) & cells)
        for _, _, marks in g.recon_marks(0):
            self.assertFalse(marks & cells)
        for _, _, marks in g.recon_marks(1):
            self.assertTrue((marks & cells) <= {(3, 2)})

    def test_overlapping_clouds_mask_until_all_cover_has_expired(self):
        g = empty()
        g.add(0, "R", (4, 7))
        cloud(g, {(4, 6)})
        g.smoke.append(dict(cells=[[4, 6]], until=[11, 11]))
        g.turns = [9, 9]
        self.assertNotIn((4, 6), g.vision(0))
        g.turns = [11, 11]
        self.assertIn((4, 6), g.vision(0))

    def test_effect_expires_for_each_side_and_legacy_clouds_work(self):
        g = empty()
        observer = g.add(0, "R", (4, 7))
        enemy = g.add(1, "P", (4, 6))
        g.smoke = [dict(cells=[[4, 6]], victims=[], until=[9, 9])]
        self.assertTrue(g.smoked(enemy))
        self.assertNotIn(enemy.pos, g.piece_vision(observer))
        g.turns[0] = 9
        self.assertIn(enemy.pos, g.piece_vision(observer))
        self.assertTrue(g.smoked(enemy))
        g.turns[1] = 9
        self.assertFalse(g.smoked(enemy))

    def test_ai_cannot_see_hidden_enemies_through_smoke(self):
        g = empty()
        g.add(0, "R", (4, 7))
        cloud(g, {(4, 6), (5, 6), (4, 5), (5, 5)})
        hidden = copy.deepcopy(g)
        hidden.add(1, "P", (4, 6))
        self.assertEqual(choose_action(g), choose_action(hidden))

    def test_smoke_cover_survives_save_and_load(self):
        g = empty()
        cannon = g.add(0, "C", (0, 8))
        g.add(0, "R", (4, 7))
        g.add(1, "P", (4, 6))
        g.skill(cannon.uid, 1, dst=(4, 5))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "game.txt"
            g.save(path)
            restored = Game.load(path)
            self.assertEqual(g.vision(0), restored.vision(0))
            self.assertEqual(g.smoke_cells(0), restored.smoke_cells(0))


if __name__ == "__main__":
    unittest.main()
