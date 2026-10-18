"""Tactical combat, equipment and supply rules shared by the desktop and AI."""
from __future__ import annotations

import copy
import math
import random


# Entries are (HP, attack, retaliation), followed by per-level growth.
BASE = {
    "P": ((10, 11, 1), (1, 1, .5)),
    "C": ((10, 20, 0), (1, 2, 0)),
    "N": ((10, 15, 1), (1, 2, 1)),
    "R": ((15, 20, 5), (2, 2, 1)),
    "B": ((12, 15, 4), (2, 1, 1)),
    "A": ((10, 5, 7), (2, 1, 2)),
    "K": ((6, 999, 20), (0, 0, 0)),
    "F": ((6, 999, 20), (0, 0, 0)),
}
HEAVY = {
    "P": ((12, 15, 4), (2, 1.5, 1.5)),
    "C": ((15, 25, 2), BASE["C"][1]),
    "N": ((15, 17, 4), (2, 2, 2)),
    "R": ((17, 22, 6), BASE["R"][1]),
    "A": ((15, 5, 15), BASE["A"][1]),
}


class TacticsRules:
    def apply_tactical_stats(self, p, full=False):
        base, growth = BASE[p.kind]
        if p.equipment == "heavy":
            base, growth = HEAVY.get(p.kind, (base, growth))
        elif p.equipment == "light" and p.kind == "B":
            base, growth = (20, 15, 4), (3, 1, 1)
        missing = max(0, p.max_hp - p.hp)
        p.max_hp, p.attack, p.defense = [b + p.level * g for b, g in zip(base, growth)]
        p.max_hp += p.bonus_hp
        p.hp = p.max_hp if full else max(.5, p.max_hp - missing)

    def award_deployment(self, side, amount):
        self.deployment[side] += amount
        if self.ruleset == "tactics":
            self.supplies[side] += amount

    def tactical_skill_names(self, p):
        from engine import SKILLS
        names = list(SKILLS[p.kind])
        if self.ruleset != "tactics":
            return names
        if p.kind == "C":
            names[0], names[2] = "瞄准", "炮击"
            if p.equipment == "light":
                names.append("机动")
        if p.kind == "R" and p.equipment == "light":
            names.append("调整")
        if p.kind == "F":
            names[0] = "牺牲"
        return names

    def tactical_skill_cost(self, p, number):
        from engine import skill_cost
        if self.ruleset == "tactics":
            if p.kind == "F" and number == 0:
                return 1
            if p.kind == "C" and number == 3:
                return 2
            if p.kind == "R" and number == 2:
                return 0
            if p.kind == "R" and p.equipment == "heavy" and number == 1:
                return max(3, self.ap)
        return skill_cost(p.kind, number)

    def tactical_skill_description(self, p, number):
        from engine import SKILL_INFO
        if self.ruleset == "tactics":
            if p.kind == "C" and number == 0:
                return "保留定向侦察效果并进入瞄准状态，移动或攻击取消瞄准。瞄准提高炮击倍率。"
            if p.kind == "C" and number == 2:
                return "第7轮解锁，隔一个炮架原地炮击。普通/轻炮未瞄准5%–50%，瞄准45%–85%，目标最低1血。重炮未瞄准25%–50%，瞄准60%–90%且可以消灭目标。将和假将免疫。落空恢复规则沿用轰击。"
            if p.kind == "C" and number == 3:
                return "仅限己方棋盘，连续移动两次，每步受炮移动力限制；不能攻击。两步完成后统一更新视野。"
            if p.kind == "R" and number == 2:
                return "本回合未移动或攻击时，上下左右移动1格，不消耗行动点，不能攻击；计入轻车移动增伤。"
            if p.kind == "R" and p.equipment == "heavy" and number == 1:
                return "消耗全部行动点（至少3），推撞敌军并造成伤害，只受50%反击。后方没有空位时，强制承受50%反击并消灭目标。"
            if p.kind == "F" and number == 0:
                return "牺牲假将，为己方棋盘内所有友军回复5血，九宫内额外1血，假将周围8格额外2血且最大血量+2。"
        return SKILL_INFO[p.kind][number]

    def require_management(self, uid, own_half=True):
        from engine import RuleError, home
        self.require()
        p = self.by_id(uid)
        if self.ruleset != "tactics" or not p or p.side != self.current:
            raise RuleError("请选择己方战棋模式棋子")
        if own_half and not home(p.side, p.pos):
            raise RuleError("升级和换装只能在己方棋盘进行")
        return p

    def upgrade(self, uid):
        from engine import RuleError
        p = self.require_management(uid)
        used = self.upgrades_used[p.side]
        if p.kind in "KF":
            raise RuleError("将和假将不能普通升级")
        if used >= 2 or self.supplies[p.side] < 1:
            raise RuleError("每方每回合合计限普通升级2次，且需要1军需点；棋子等级无上限")
        self.supplies[p.side] -= 1
        self.upgrades_used[p.side] += 1
        p.upgrades_this_turn = (p.upgrades_this_turn if p.upgrade_turn == self.turns[p.side] else 0) + 1
        p.upgrade_turn = self.turns[p.side]
        p.level += 1
        self.apply_tactical_stats(p)
        self.log("普通升级", uid=uid, level=p.level)
        return f"普通升级完成：等级{p.level}"

    def management_description(self, p, option):
        if p.kind in "KF":
            return "将和假将不能普通升级或换装。"
        projected = copy.copy(p)
        if option == "upgrade":
            projected.level += 1
        else:
            projected.equipment = option
        self.apply_tactical_stats(projected)
        growth = copy.copy(projected)
        growth.level += 1
        self.apply_tactical_stats(growth)
        stats = (f"血量上限 {p.max_hp:g} → {projected.max_hp:g}；攻击 {p.attack:g} → {projected.attack:g}；"
                 f"防御 {p.defense:g} → {projected.defense:g}。保留已损失血量。\n"
                 f"每级：血量+{growth.max_hp-projected.max_hp:g}、攻击+{growth.attack-projected.attack:g}、"
                 f"防御+{growth.defense-projected.defense:g}。")
        effects = {
            ("P", "light"): "可始终上下左右走1格，后退不能攻击。",
            ("P", "heavy"): "强化基础血量、攻击、防御及升级成长；移动规则不变。",
            ("C", "light"): "移动力5格；增加技能机动：己方棋盘消耗2行动点连续移动两次，不能攻击。炮击不能消灭目标。",
            ("C", "heavy"): "移动力3格；未瞄准炮击25%~50%且不能消灭目标，瞄准后60%~90%且可以消灭目标。将和假将免疫。",
            ("N", "light"): "基础视野+1、可被遮挡的额外视野+1；攻击后可上下左右移动1格，不能攻击，点选原位放弃。",
            ("N", "heavy"): "强化基础属性及升级成长；攻击未消灭目标时保持原位。",
            ("R", "light"): "本回合每移动1格，本次攻击额外+0.5攻击；新增免费技能调整，未移动或攻击前可移动相邻1格，计入增伤。",
            ("R", "heavy"): "冲击消耗全部行动点（至少3），推撞并造成伤害，承受50%反击；目标后方无空位时强制承受反击并消灭目标。",
            ("B", "light"): "替周围8格友军分担50%伤害；己方九宫内为整个己方九宫分担伤害。",
            ("B", "heavy"): "改为上下左右每次移动或攻击1格，可以过河。",
            ("A", "light"): "换装后每隔3个己方回合额外获得1军需点。",
            ("A", "heavy"): "可在九宫内上下左右走1格；攻击时先承受目标攻击（自身最低1血），再造成满额防御伤害。",
        }
        effect = effects.get((p.kind, projected.equipment), "沿用普通棋子的移动与技能规则。")
        return stats + "\n特殊效果：" + effect

    def equip(self, uid, equipment):
        from engine import RuleError
        p = self.require_management(uid)
        if p.kind in "KF" or equipment not in ("light", "heavy"):
            raise RuleError("将和假将不能换装，请选择轻装或重装")
        if p.equipment == equipment or self.supplies[p.side] < 2:
            raise RuleError("已是该装备，或军需点不足2点")
        self.supplies[p.side] -= 2
        p.equipment, p.equipped_turn = equipment, self.turns[p.side]
        self.apply_tactical_stats(p)
        self.log("装备升级", uid=uid, equipment=equipment)
        return "已换装为" + ("轻装" if equipment == "light" else "重装")

    def healing_rate(self, p):
        from engine import home
        if not home(p.side, p.pos):
            return .5
        invaders = [q for q in self.pieces if q.side != p.side and home(p.side, q.pos)]
        if not invaders:
            return 4
        return 1 if p.pos in self.threats(1 - p.side) else 3

    def replenish(self, uid, amount):
        from engine import RuleError
        p = self.require_management(uid, own_half=False)
        if amount not in ("half", "full"):
            raise RuleError("请选择回复一半或回满血")
        wanted = min(p.max_hp - p.hp, p.max_hp / 2 if amount == "half" else p.max_hp)
        if wanted <= 0 or self.supplies[p.side] <= 0:
            raise RuleError("棋子已满血，或没有军需点")
        rate = self.healing_rate(p)
        cost = min(self.supplies[p.side], math.ceil(wanted / rate))
        healed = min(wanted, cost * rate)
        self.supplies[p.side] -= cost
        p.hp += healed
        self.log("军队补员", uid=uid, cost=cost, healed=healed)
        return f"消耗{cost}军需点，回复{healed:g}血"

    def tactics_start_turn(self):
        if self.ruleset != "tactics":
            return
        side = self.current
        self.upgrades_used[side] = 0
        if self.turns[side] > 1:
            self.supplies[side] += 8 if self.round >= 50 else 4 if self.round >= 30 else 2
        for p in self.pieces:
            if p.side != side:
                continue
            p.steps_this_turn, p.acted_this_turn, p.followup = 0, False, False
            if p.kind == "K":
                p.hp = min(p.max_hp, p.hp + 1)
            elapsed = self.turns[side] - p.equipped_turn
            if p.kind == "A" and p.equipment == "light" and elapsed > 0 and elapsed % 3 == 0:
                self.supplies[side] += 1

    def tactical_geometry(self, p, dst, collection):
        """Return None for inherited geometry, otherwise the tactical override."""
        from engine import home, palace
        dx, dy = dst[0] - p.x, dst[1] - p.y
        if p.kind == "P" and p.equipment == "light":
            backward = dy == (1 if p.side == 0 else -1)
            return abs(dx) + abs(dy) == 1 and not (backward and any(q.pos == dst for q in collection))
        if p.kind == "B" and p.equipment == "heavy":
            return abs(dx) + abs(dy) == 1
        if p.kind == "A" and p.equipment == "heavy":
            return palace(p.pos) and palace(dst) and home(0 if p.y >= 7 else 1, dst) and abs(dx) + abs(dy) == 1
        if p.kind == "C" and max(abs(dx), abs(dy)) > (3 if p.equipment == "heavy" else 5):
            return False
        return None

    def deployment_forbidden(self, side, dst):
        from engine import home
        invaders = [p for p in self.pieces if p.side != side and home(side, p.pos)]
        return bool(invaders) and dst in self.attack_squares(1 - side)

    def attack_squares(self, side):
        from engine import ALL, Piece
        result = set()
        for p in self.pieces:
            if p.side != side:
                continue
            for dst in ALL - {p.pos}:
                pieces = [q for q in self.pieces if q.pos != dst]
                pieces.append(Piece(-1, 1 - side, "P", *dst))
                if self.legal_base(p, dst, pieces):
                    result.add(dst)
        return result

    def next_random(self):
        value = random.Random(self.rng_seed + self.rng_counter).random()
        self.rng_counter += 1
        return value

    def round_damage(self, value):
        low = math.floor(value)
        return low if value == low or self.next_random() < .5 else math.ceil(value)

    def effective_attack(self, p, steps=0):
        bonus = .5 * (p.steps_this_turn + steps) if p.kind == "R" and p.equipment == "light" else 0
        return max(0, (p.attack + bonus) * p.hp / p.max_hp)

    def artillery_profile(self, p):
        if p.equipment == "heavy":
            return (.6, .9, True) if p.aimed else (.25, .5, False)
        return (.45, .85, False) if p.aimed else (.05, .5, False)

    def bodyguard(self, target):
        from engine import palace, home
        choices = []
        for p in self.pieces:
            if p.uid == target.uid or p.side != target.side or p.kind != "B" or p.equipment != "light":
                continue
            nearby = max(abs(p.x - target.x), abs(p.y - target.y)) <= 1
            headquarters = palace(p.pos) and palace(target.pos) and home(p.side, p.pos) and home(p.side, target.pos)
            if nearby or headquarters:
                choices.append(p)
        return min(choices, key=lambda p: p.uid) if choices else None

    def deal_damage(self, source, target, damage, floor_hp=0):
        damage = max(0, min(damage, max(0, target.hp - floor_hp))) if floor_hp else max(0, damage)
        guard = self.bodyguard(target)
        shared = self.round_damage(damage * .5) if guard else 0
        target.hp -= damage - shared
        if guard:
            guard.hp -= shared
            if guard.hp <= 0:
                self.capture(source, guard)
        if target.hp <= 0:
            self.capture(source, target)
        return damage - shared, shared

    def combat(self, attacker, target, bombard=False, counter_factor=1, force_kill=False):
        from engine import line
        path = line(attacker.pos, target.pos)
        steps = len(path) if path is not None and attacker.kind == "R" else 0
        value = self.effective_attack(attacker, steps)
        old_hp = target.hp
        floor_hp = 0
        immune = attacker.kind == "C" and target.kind in "KF"
        if bombard:
            low, high, lethal = self.artillery_profile(attacker)
            value *= low + (high - low) * self.next_random()
            floor_hp = 0 if lethal else 1
        damage = 0 if immune else self.round_damage(value)
        threshold = 10 if target.kind == "A" else 5
        retaliation = not immune and (force_kill or damage <= old_hp + threshold)
        counter = self.round_damage(target.defense * counter_factor) if retaliation else 0
        attacker.hidden, attacker.recon, attacker.aimed = False, None, False
        attacker.acted_this_turn = True
        if attacker.kind == "A" and attacker.equipment == "heavy" and not bombard:
            incoming = self.round_damage(self.effective_attack(target))
            actual, _ = self.deal_damage(target, attacker, incoming, floor_hp=1)
            damage, counter = self.round_damage(attacker.defense), actual
            self.deal_damage(attacker, target, damage)
        else:
            if force_kill:
                self.capture(attacker, target)
            elif not immune:
                self.deal_damage(attacker, target, damage, floor_hp)
            if counter and attacker in self.pieces:
                self.deal_damage(target, attacker, counter)
        if attacker in self.pieces and attacker.kind == "N" and attacker.equipment == "light":
            attacker.followup = True
        self.log("战棋攻击", attacker=attacker.uid, target=target.uid, damage=damage, counter=counter, bombard=bombard)
        return target not in self.pieces

    def damage_preview(self, uid, dst, bombard=False, skill_number=None):
        from engine import RuleError, line, ALL
        p, target = self.by_id(uid), self.at(dst)
        if not p or not target or p.side != self.current or target.side == p.side or target not in self.known(p.side):
            raise RuleError("没有可预览的攻击目标")
        view = copy.deepcopy(self)
        view.pieces = view.known(p.side)
        p, target = view.by_id(uid), view.by_id(target.uid)
        path = line(p.pos, dst)
        if bombard:
            legal = path is not None and sum(view.at(q) is not None for q in path) == 1
        else:
            legal = view.legal_base(p, dst, ignore_leg=p.kind == "N" and skill_number == 1)
        if not legal:
            raise RuleError("目标不在攻击范围")
        if self.ruleset != "tactics":
            return dict(damage_min=target.hp, damage_max=target.hp, counter_min=0, counter_max=0, shared=False)
        distance = max(abs(dst[0] - p.x), abs(dst[1] - p.y)) - 1 if p.kind == "R" else 0
        attack = view.effective_attack(p, max(0, distance))
        charge_blocked = False
        if p.kind == "R" and path is not None:
            dx = (dst[0] > p.x) - (dst[0] < p.x)
            dy = (dst[1] > p.y) - (dst[1] < p.y)
            p.x, p.y = dst[0] - dx, dst[1] - dy
            if p.equipment == "heavy" and skill_number == 1:
                pushed = dst[0] + dx, dst[1] + dy
                charge_blocked = pushed not in ALL or view.at(pushed) is not None
                if not charge_blocked:
                    target.x, target.y = pushed
        low = high = attack
        lethal = True
        if bombard:
            a, b, lethal = view.artillery_profile(p)
            low, high = attack * a, attack * b
        immune = p.kind == "C" and target.kind in "KF"
        lo, hi = (0, 0) if immune else (math.floor(low), math.ceil(high))
        if not lethal:
            lo, hi = min(lo, max(0, target.hp - 1)), min(hi, max(0, target.hp - 1))
        threshold = 10 if target.kind == "A" else 5
        counter_lo = math.floor(target.defense) if math.ceil(high) <= target.hp + threshold and not immune else 0
        counter_hi = math.ceil(target.defense) if math.floor(low) <= target.hp + threshold and not immune else 0
        if p.kind == "A" and p.equipment == "heavy" and not bombard:
            lo, hi = math.floor(p.defense), math.ceil(p.defense)
            counter_lo = min(max(0, p.hp - 1), math.floor(view.effective_attack(target)))
            counter_hi = min(max(0, p.hp - 1), math.ceil(view.effective_attack(target)))
        guarded = view.bodyguard(target) is not None
        if p.kind == "R" and p.equipment == "heavy" and skill_number == 1:
            counter_lo, counter_hi = math.floor(counter_lo / 2), math.ceil(counter_hi / 2)
            if charge_blocked:
                lo = hi = target.hp
                counter_lo, counter_hi = math.floor(target.defense/2), math.ceil(target.defense/2)
                guarded = False
        if guarded:
            lo, hi = math.floor(lo / 2), math.ceil(hi / 2)
        counter_guard = view.bodyguard(p) is not None
        if counter_guard:
            counter_lo, counter_hi = math.floor(counter_lo/2), math.ceil(counter_hi/2)
        return dict(damage_min=min(target.hp, lo), damage_max=min(target.hp, hi), counter_min=counter_lo, counter_max=counter_hi, shared=guarded or counter_guard)

    def followup_move(self, uid, dst):
        from engine import RuleError, neighbors
        p = self.require_management(uid, own_half=False)
        if p.followup and dst == p.pos:
            p.followup = False
            self.log("放弃轻马追移动", uid=uid)
            return "已放弃轻装马攻击后移动"
        if not p.followup or dst not in neighbors(p.pos) or self.at(dst):
            raise RuleError("轻装马攻击后仅可额外移动相邻空位一次")
        p.followup = False
        self.relocate(p, dst, False)
        self.log("轻马追移动", uid=uid, target=dst)
        return "轻装马攻击后移动完成"

    def special_tactical_skill(self, p, number, options):
        """Return None to use the inherited skill implementation."""
        from engine import RuleError, home, neighbors, palace, line, coord
        if self.ruleset != "tactics":
            return None
        dst = tuple(options.get("dst", p.pos))
        if p.kind == "C" and number == 3:
            if not home(p.side, p.pos):
                raise RuleError("机动只能在己方棋盘发动")
            for dest in (tuple(options.get("first", p.pos)), dst):
                if self.at(dest) or not self.legal_base(p, dest):
                    raise RuleError("机动的两步均须合法且不能攻击")
                self.relocate(p, dest, False)
            return "机动完成"
        if p.kind == "R" and number == 2:
            if p.acted_this_turn or dst not in neighbors(p.pos) or self.at(dst):
                raise RuleError("调整只可在本回合移动或攻击前使用，目标须为相邻空位")
            self.relocate(p, dst, False)
            return "调整完成，移动增伤已累计"
        if p.kind == "F" and number == 0:
            position = p.pos
            self.pieces.remove(p)
            for q in self.pieces:
                if q.side != p.side or not home(p.side, q.pos):
                    continue
                adjacent = max(abs(q.x - position[0]), abs(q.y - position[1])) <= 1
                healing = 5 + bool(palace(q.pos)) + 2 * adjacent
                if adjacent:
                    q.max_hp += 2
                    q.bonus_hp += 2
                q.hp = min(q.max_hp, q.hp + healing)
            return "假将已牺牲，己方棋盘部队完成回复"
        if p.kind == "R" and p.equipment == "heavy" and number == 1:
            target = self.at(dst)
            path = line(p.pos, dst)
            if not target or target.side == p.side or path is None or any(self.at(q) for q in path):
                raise RuleError("重车冲击须选择直线可抵达的敌方棋子")
            dx = (dst[0] > p.x) - (dst[0] < p.x)
            dy = (dst[1] > p.y) - (dst[1] < p.y)
            adjacent, pushed = (dst[0] - dx, dst[1] - dy), (dst[0] + dx, dst[1] + dy)
            if adjacent != p.pos:
                self.relocate(p, adjacent, False)
            from engine import ALL
            blocked = pushed not in ALL or self.at(pushed) is not None
            if not blocked:
                self.relocate(target, pushed, False)
            self.combat(p, target, counter_factor=.5, force_kill=blocked)
            return "重车冲击完成" + ("，目标后方受阻，强制消灭" if blocked else "")
        return None
