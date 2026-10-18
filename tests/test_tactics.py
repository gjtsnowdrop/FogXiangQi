import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from engine import Game, RuleError, ALL
from tactics import BASE, HEAVY
from computer.opponent import choose_action, apply_action


def game():
    return Game(mode="debug", ruleset="tactics", fog_enabled=False, round=7, turns=[7, 6], deployment=[100, 100], supplies=[100, 100], rng_seed=42)


def cycle(g):
    g.end_turn()
    g.end_turn()


class TacticsTests(unittest.TestCase):
    def test_upgrade_budget_shared_by_side_and_unlimited_levels(self):
        g = game()
        a = g.add(0, "P", (0, 7))
        b = g.add(0, "P", (2, 7))
        enemy = g.add(1, "P", (0, 2))
        g.upgrade(a.uid)
        g.upgrade(b.uid)
        before = copy.deepcopy(g)
        with self.assertRaises(RuleError):
            g.upgrade(a.uid)
        self.assertEqual(g, before)
        g.end_turn()
        g.upgrade(enemy.uid)
        self.assertEqual(g.upgrades_used, [2, 1])
        g.end_turn()
        self.assertEqual(g.upgrades_used, [0, 1])
        for _ in range(6):
            g.upgrade(a.uid)
            g.upgrade(a.uid)
            cycle(g)
        self.assertEqual(a.level, 13)

    def test_global_upgrade_save_and_legacy_migration(self):
        g = game()
        a = g.add(0, "P", (0, 7))
        b = g.add(0, "P", (2, 7))
        g.upgrade(a.uid)
        g.upgrade(b.uid)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "game.txt"
            g.save(path)
            self.assertEqual(Game.load(path).upgrades_used, [2, 0])
            data = json.loads(path.read_text(encoding="utf-8"))
            data["version"] = 4
            del data["upgrades_used"]
            path.write_text(json.dumps(data), encoding="utf-8")
            loaded = Game.load(path)
            self.assertEqual(loaded.upgrades_used, [2, 0])
            with self.assertRaises(RuleError):
                loaded.upgrade(a.uid)
            data["version"], data["upgrades_used"] = 5, [3, 0]
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(RuleError):
                Game.load(path)

    def test_management_descriptions_are_pure_and_show_projection(self):
        for kind in "PCNRBA":
            g = game()
            p = g.add(0, kind, (4, 7))
            g.upgrade(p.uid)
            before = copy.deepcopy(g)
            for option in ("upgrade", "light", "heavy"):
                text = g.management_description(p, option)
                self.assertIn("血量上限", text)
                self.assertIn("特殊效果", text)
                self.assertIn("每级", text)
            self.assertEqual(g, before)
        self.assertIn("后退不能攻击", g.management_description(g.add(0, "P", (0, 7)), "light"))

    def test_light_horse_can_decline_followup_on_current_square(self):
        g = game()
        p = g.add(0, "N", (1, 9))
        g.equip(p.uid, "light")
        target = g.add(1, "R", (3, 8))
        target.hp = target.max_hp = 40
        g.move(p.uid, target.pos)
        hp, ap, pos = p.hp, g.ap, p.pos
        self.assertTrue(p.followup)
        g.followup_move(p.uid, p.pos)
        self.assertFalse(p.followup)
        self.assertEqual((p.hp, g.ap, p.pos), (hp, ap, pos))

    def test_selection_ranges_use_only_known_board_and_do_not_mutate(self):
        g = game()
        p = g.add(0, "R", (0, 9))
        target = g.add(1, "P", (0, 7))
        before = copy.deepcopy(g)
        moves, attacks = g.selection_targets(p.uid)
        self.assertIn((0, 8), moves)
        self.assertIn(target.pos, attacks)
        self.assertNotIn((0, 6), moves)
        self.assertEqual(g, before)
        target.hidden = True
        moves, attacks = g.selection_targets(p.uid)
        self.assertIn((0, 6), moves)
        self.assertIn(target.pos, moves)
        self.assertNotIn(target.pos, attacks)

    def test_new_game_settings_stats_and_starting_supplies(self):
        g = Game.new("local", "tactics", False)
        self.assertEqual(g.supplies, [10, 10])
        self.assertEqual(g.vision(0), ALL)
        for p in g.pieces:
            self.assertEqual((p.hp, p.attack, p.defense), BASE[p.kind][0])
        g.end_turn()
        g.pending_handoff = False
        self.assertEqual(g.supplies, [10, 10])
        g.end_turn()
        self.assertEqual(g.supplies[0], 12)

    def test_fog_off_still_hides_smoke_and_only_shows_own_occupied_cell(self):
        g = game()
        own = g.add(0, "P", (4, 7))
        g.add(1, "P", (5, 7))
        g.smoke = [dict(cells=[[4, 7], [5, 7], [4, 6], [5, 6]], until=[20, 20])]
        self.assertEqual(g.vision(0), (ALL - {(5, 7), (4, 6), (5, 6)}))
        self.assertEqual(g.piece_vision(own), {own.pos})

    def test_all_equipment_stats_inherit_unspecified_values(self):
        for kind in "PCNRBA":
            for equipment in ("light", "heavy"):
                with self.subTest(kind=kind, equipment=equipment):
                    g = game()
                    p = g.add(0, kind, (4, 7))
                    g.equip(p.uid, equipment)
                    expected = HEAVY.get(kind, BASE[kind])[0] if equipment == "heavy" else BASE[kind][0]
                    if equipment == "light" and kind == "B":
                        expected = (20, 15, 4)
                    self.assertEqual((p.max_hp, p.attack, p.defense), expected)
                    self.assertEqual(g.supplies[0], 98)

    def test_upgrade_growth_twice_and_reset_each_own_turn(self):
        for kind in "PCNRBA":
            g = game()
            p = g.add(0, kind, (4, 7))
            g.upgrade(p.uid)
            g.upgrade(p.uid)
            expected = tuple(b + 2*d for b, d in zip(*BASE[kind]))
            self.assertEqual((p.max_hp, p.attack, p.defense), expected)
            with self.assertRaises(RuleError):
                g.upgrade(p.uid)
            cycle(g)
            g.upgrade(p.uid)
            self.assertEqual(p.level, 3)

    def test_heavy_pawn_growth_and_light_bishop_growth(self):
        for kind, equipment, expected in (("P", "heavy", (14, 16.5, 5.5)), ("B", "light", (23, 16, 5))):
            g = game()
            p = g.add(0, kind, (4, 7))
            g.equip(p.uid, equipment)
            g.upgrade(p.uid)
            self.assertEqual((p.max_hp, p.attack, p.defense), expected)

    def test_royals_cannot_upgrade_or_equip_and_enemy_half_management_rejected(self):
        for kind in "KF":
            g = game()
            p = g.add(0, kind, (4, 9))
            with self.assertRaises(RuleError):
                g.upgrade(p.uid)
            with self.assertRaises(RuleError):
                g.equip(p.uid, "light")
        g = game()
        p = g.add(0, "P", (4, 2))
        with self.assertRaises(RuleError):
            g.upgrade(p.uid)

    def test_supply_income_tiers_and_capture_or_logistics_awards(self):
        for r, income in ((7, 2), (30, 4), (50, 8)):
            g = game()
            g.round = r
            g.end_turn()
            self.assertEqual(g.supplies[1], 100+income)
        g = game()
        p = g.add(0, "R", (4, 7))
        target = g.add(1, "P", (4, 6))
        g.capture(p, target)
        self.assertEqual((g.deployment[0], g.supplies[0]), (101, 101))
        advisor = g.add(0, "A", (3, 9))
        g.skill(advisor.uid, 0)
        self.assertEqual((g.deployment[0], g.supplies[0]), (104, 104))

    def test_healing_rates_home_safe_invaded_threatened_and_enemy_half(self):
        g = game()
        p = g.add(0, "P", (4, 9))
        p.hp = 1
        self.assertEqual(g.healing_rate(p), 4)
        g.replenish(p.uid, "half")
        self.assertEqual((p.hp, g.supplies[0]), (6, 98))
        g.add(1, "P", (0, 6))
        self.assertEqual(g.healing_rate(p), 3)
        g.add(1, "R", (4, 6))
        self.assertEqual(g.healing_rate(p), 1)
        g.relocate(p, (4, 2), False)
        self.assertEqual(g.healing_rate(p), .5)
        g.supplies[0], p.hp = 3, 1
        g.replenish(p.uid, "full")
        self.assertEqual((p.hp, g.supplies[0]), (2.5, 0))

    def test_insufficient_supply_heals_corresponding_amount(self):
        g = game()
        p = g.add(0, "R", (4, 7))
        p.hp, g.supplies[0] = 1, 1
        g.replenish(p.uid, "full")
        self.assertEqual((p.hp, g.supplies[0]), (5, 0))

    def test_half_healing_is_exactly_half_of_odd_max_hp(self):
        g = game()
        p = g.add(0, "P", (4, 7))
        g.upgrade(p.uid)
        p.hp = 1
        g.replenish(p.uid, "half")
        self.assertEqual((p.max_hp, p.hp, g.supplies[0]), (11, 6.5, 97))

    def test_deployment_rejection_is_atomic_and_only_if_invader_present(self):
        g = game()
        enemy = g.add(1, "R", (0, 0))
        g.deploy("P", (0, 8))
        self.assertIsNotNone(g.at((0, 8)))
        g.relocate(enemy, (0, 6), False)
        before = copy.deepcopy(g)
        with self.assertRaises(RuleError):
            g.deploy("P", (0, 7), waive_ap=True)
        self.assertEqual(g, before)
        self.assertFalse(g.deploy_locked[0])

    def test_hp_scaled_attack_preview_does_not_consume_rng(self):
        g = game()
        p = g.add(0, "R", (4, 7))
        target = g.add(1, "R", (4, 3))
        p.hp, target.hp, target.max_hp = 7.5, 40, 40
        before = copy.deepcopy(g)
        preview = g.damage_preview(p.uid, target.pos)
        self.assertEqual((preview["damage_min"], preview["damage_max"]), (10, 10))
        self.assertEqual(g, before)

    def test_rounding_uses_even_odds_not_fraction_size(self):
        g = game()
        with patch.object(g, "next_random", return_value=.49):
            self.assertEqual(g.round_damage(4.99), 4)
        with patch.object(g, "next_random", return_value=.51):
            self.assertEqual(g.round_damage(4.01), 5)

    def test_counter_threshold_and_advisor_exception(self):
        for attack, kind, expected in ((16, "P", 15), (15, "P", 14), (16, "A", 8), (21, "A", 15)):
            g = game()
            p = g.add(0, "R", (4, 7))
            p.attack = attack
            target = g.add(1, kind, (4, 6))
            g.combat(p, target)
            self.assertEqual(p.hp, expected)

    def test_knight_stays_when_target_survives_and_rook_stops_adjacent(self):
        g = game()
        knight = g.add(0, "N", (1, 9))
        target = g.add(1, "R", (3, 8))
        target.hp = target.max_hp = 40
        g.move(knight.uid, target.pos)
        self.assertEqual((knight.pos, target.hp), ((1, 9), 25))
        g = game()
        rook = g.add(0, "R", (4, 7))
        target = g.add(1, "R", (4, 3))
        target.hp = target.max_hp = 40
        g.move(rook.uid, target.pos)
        self.assertEqual((rook.pos, target.hp), ((4, 4), 20))

    def test_light_pawn_can_retreat_but_not_attack_backward(self):
        g = game()
        p = g.add(0, "P", (4, 7))
        g.equip(p.uid, "light")
        self.assertTrue(g.legal_base(p, (4, 8)))
        g.add(1, "P", (4, 8))
        self.assertFalse(g.legal_base(p, (4, 8)))

    def test_cannon_movement_limits_and_light_maneuver(self):
        g = game()
        p = g.add(0, "C", (0, 7))
        self.assertTrue(g.legal_base(p, (5, 7)))
        self.assertFalse(g.legal_base(p, (6, 7)))
        g.equip(p.uid, "heavy")
        self.assertFalse(g.legal_base(p, (4, 7)))
        g.equip(p.uid, "light")
        g.skill(p.uid, 3, first=(3, 7), dst=(3, 4))
        self.assertEqual(g.by_id(p.uid).pos, (3, 4))
        self.assertEqual(g.ap, 1)

    def test_cannon_bombardment_profiles_cap_and_heavy_aimed_kill(self):
        for equipment, aimed, lethal in (("normal", False, False), ("light", True, False), ("heavy", False, False), ("heavy", True, True)):
            g = game()
            p = g.add(0, "C", (4, 7))
            if equipment != "normal":
                g.equip(p.uid, equipment)
            p.aimed = aimed
            target = g.add(1, "P", (4, 3))
            target.hp = 2
            with patch.object(g, "next_random", return_value=.99):
                g.combat(p, target, bombard=True)
            if lethal:
                self.assertNotIn(target, g.pieces)
            else:
                self.assertEqual(target.hp, 1)

    def test_royals_immune_to_artillery_and_true_king_regenerates(self):
        g = game()
        p = g.add(0, "C", (4, 7))
        k = g.add(1, "K", (4, 2))
        g.combat(p, k, bombard=True)
        self.assertEqual((k.hp, p.hp), (6, 10))
        k.hp = 3
        g.end_turn()
        self.assertEqual(k.hp, 4)

    def test_light_knight_vision_and_post_attack_step(self):
        g = game()
        p = g.add(0, "N", (1, 9))
        g.equip(p.uid, "light")
        self.assertIn((1, 6), g.piece_vision(p))
        target = g.add(1, "R", (3, 8))
        target.hp = target.max_hp = 40
        g.move(p.uid, target.pos)
        self.assertTrue(p.followup)
        g.followup_move(p.uid, (2, 9))
        self.assertEqual(p.pos, (2, 9))
        with self.assertRaises(RuleError):
            g.followup_move(p.uid, (2, 8))

    def test_light_rook_adjustment_and_movement_bonus(self):
        g = game()
        p = g.add(0, "R", (0, 7))
        g.equip(p.uid, "light")
        target = g.add(1, "P", (4, 7))
        g.skill(p.uid, 2, dst=(1, 7))
        p = g.by_id(p.uid)
        self.assertEqual(g.ap, 3)
        preview = g.damage_preview(p.uid, target.pos)
        self.assertEqual(preview["counter_max"], 0)
        self.assertEqual(p.steps_this_turn, 1)
        target = g.by_id(target.uid)
        target.hp = target.max_hp = 40
        preview = g.damage_preview(p.uid, target.pos)
        self.assertEqual((preview["damage_min"], preview["damage_max"]), (21, 22))
        g.move(p.uid, target.pos)
        self.assertEqual(g.history[-2]["damage"] in (21, 22), True)

    def test_heavy_rook_preview_accounts_for_pushing_target_out_of_guard_range(self):
        g = game()
        p = g.add(0, "R", (0, 7))
        g.equip(p.uid, "heavy")
        target = g.add(1, "P", (4, 7))
        target.hp = target.max_hp = 40
        guard = g.add(1, "B", (3, 6))
        guard.equipment = "light"
        g.apply_tactical_stats(guard, full=True)
        self.assertIs(g.bodyguard(target), guard)
        preview = g.damage_preview(p.uid, target.pos, skill_number=1)
        self.assertEqual((preview["damage_min"], preview["damage_max"]), (22, 22))
        g.skill(p.uid, 1, dst=target.pos)
        self.assertEqual(g.by_id(target.uid).hp, 18)

    def test_heavy_rook_charge_spends_all_and_halves_retaliation(self):
        for blocked in (False, True):
            g = game()
            p = g.add(0, "R", (0, 5))
            g.equip(p.uid, "heavy")
            target = g.add(1, "N", (0, 2))
            target.hp = target.max_hp = 40
            target.defense = 10
            if blocked:
                g.add(1, "P", (0, 1))
            g.skill(p.uid, 1, dst=target.pos)
            p = g.by_id(p.uid)
            self.assertEqual((g.ap, p.hp, p.pos), (0, 12, (0, 3)))
            if blocked:
                self.assertIsNone(g.by_id(target.uid))
            else:
                self.assertEqual(g.by_id(target.uid).pos, (0, 1))

    def test_light_bishop_shares_damage_nearby_and_across_palace(self):
        for guard_pos, target_pos in (((3, 7), (4, 7)), ((3, 9), (5, 7))):
            g = game()
            guard = g.add(0, "B", guard_pos)
            g.equip(guard.uid, "light")
            target = g.add(0, "P", target_pos)
            attacker = g.add(1, "R", (5, 3))
            attacker.attack = 10
            before = guard.hp + target.hp
            g.combat(attacker, target)
            self.assertEqual(before - guard.hp - target.hp, 10)
            self.assertEqual((guard.hp, target.hp), (15, 5))

    def test_heavy_bishop_orthogonal_move_crosses_river(self):
        g = game()
        p = g.add(0, "B", (4, 5))
        g.equip(p.uid, "heavy")
        self.assertTrue(g.legal_base(p, (4, 4)))
        self.assertFalse(g.legal_base(p, (6, 3)))

    def test_light_advisor_extra_supply_every_three_own_turns(self):
        g = game()
        p = g.add(0, "A", (3, 9))
        g.equip(p.uid, "light")
        for _ in range(3):
            cycle(g)
        self.assertEqual(g.supplies[0], 105)

    def test_heavy_advisor_forces_enemy_attack_then_full_defense_damage(self):
        g = game()
        p = g.add(0, "A", (4, 8))
        g.equip(p.uid, "heavy")
        target = g.add(1, "R", (4, 7))
        target.hp = target.max_hp = 30
        g.move(p.uid, target.pos)
        self.assertEqual((p.hp, target.hp), (1, 15))
        self.assertEqual(p.pos, (4, 8))

    def test_fake_king_sacrifice_heals_and_adds_max_hp(self):
        g = game()
        fake = g.add(0, "F", (4, 8))
        friend = g.add(0, "P", (4, 7))
        friend.hp = 1
        distant = g.add(0, "P", (0, 6))
        distant.hp = 1
        outside = g.add(0, "P", (0, 2))
        outside.hp = 1
        g.skill(fake.uid, 0)
        self.assertIsNone(g.by_id(fake.uid))
        self.assertEqual((g.by_id(friend.uid).hp, g.by_id(friend.uid).max_hp), (9, 12))
        self.assertEqual(g.by_id(distant.uid).hp, 6)
        self.assertEqual(g.by_id(outside.uid).hp, 1)
        self.assertEqual(g.scores, [0, 0])
        self.assertEqual(g.ap, 2)

    def test_save_load_preserves_equipment_supply_and_rng_sequence(self):
        g = game()
        p = g.add(0, "P", (4, 7))
        g.equip(p.uid, "heavy")
        g.upgrade(p.uid)
        g.next_random()
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "tactics.txt"
            g.save(path)
            restored = Game.load(path)
            self.assertEqual(g, restored)
            self.assertEqual(g.next_random(), restored.next_random())

    def test_ai_can_play_tactical_turns_without_cheating_or_crashing(self):
        g = Game.new("ai", "tactics", True)
        for _ in range(35):
            if g.winner is not None:
                break
            action = choose_action(g)
            try:
                apply_action(g, action)
            except RuleError:
                g.end_turn()
        self.assertTrue(g.history)


if __name__ == "__main__":
    unittest.main()
