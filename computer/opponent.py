"""Observable-state heuristic opponent; runnable as python -m computer.opponent save.txt."""
from __future__ import annotations

import copy
import json
import sys

from engine import ALL, Game, RuleError, MOVE_AP, home, palace, line, neighbors


def choose_action(game):
    side = game.current
    view = copy.deepcopy(game)
    visible = game.vision(side)
    view.pieces = view.known(side)
    for p in view.pieces:
        if p.side != side and p.kind == "F":
            p.kind = "K"
    choices = []
    threats = view.threats(1 - side)
    for p in view.pieces:
        if p.side != side:
            continue
        if view.ap >= MOVE_AP and view.turns[side] >= p.ready_at:
            for dst in sorted(ALL):
                if not view.legal_base(p, dst):
                    continue
                victim = view.at(dst)
                forward = (p.y - dst[1]) * (1 if side == 0 else -1)
                score = (view.cost(victim.kind) * 12 if victim else 0) + forward * .3
                if victim and view.ruleset == "tactics":
                    preview = view.damage_preview(p.uid, dst)
                    damage = (preview["damage_min"] + preview["damage_max"]) / 2
                    score = damage * 1.5 - preview["counter_max"] * .8 + forward * .3
                    if preview["damage_min"] >= victim.hp:
                        score += view.cost(victim.kind) * 10
                score += (4 - abs(dst[0] - 4)) * .12
                if dst in threats:
                    score -= view.cost(p.kind) * 3
                if dst not in visible:
                    score += .4
                if p.pos in threats:
                    score += view.cost(p.kind) * 2
                choices.append((score, {"type": "move", "uid": p.uid, "dst": dst}))
        if p.kind == "C" and view.skill_ready(p, 2):
            for target in view.pieces:
                path = line(p.pos, target.pos)
                if target.side == side or target.kind in "KF" or path is None:
                    continue
                if sum(view.at(q) is not None for q in path) == 1:
                    choices.append((view.cost(target.kind) * 11,
                                    {"type": "skill", "uid": p.uid, "number": 2, "dst": target.pos}))
        if p.skill_turn != view.turns[side] and view.ap >= 1:
            if p.kind == "A" and view.skill_ready(p, 0):
                choices.append((1.1, {"type": "skill", "uid": p.uid, "number": 0}))
            if p.kind == "B" and not p.hidden and view.skill_ready(p, 0):
                choices.append((.7, {"type": "skill", "uid": p.uid, "number": 0}))
            if p.kind == "C" and p.y not in (4, 5) and view.skill_ready(p, 0):
                choices.append((.5, {"type": "skill", "uid": p.uid, "number": 0, "direction": "上" if side == 0 else "下"}))
        if view.ruleset == "tactics":
            if p.followup:
                for dst in sorted(neighbors(p.pos)):
                    if not view.at(dst):
                        choices.append((1, {"type": "followup", "uid": p.uid, "dst": dst}))
            if p.hp < p.max_hp / 2 and view.supplies[side] > 0:
                choices.append((2, {"type": "heal", "uid": p.uid}))
            used = view.upgrades_used[side]
            if p.kind not in "KF" and used < 2 and home(side, p.pos) and view.supplies[side] > 0:
                choices.append((.3, {"type": "upgrade", "uid": p.uid}))
    waive = view.ap == 0
    deployment_cost, _, _ = view.deployment_quote("P", waive)
    if view.deployment[side] >= deployment_cost and not view.deploy_locked[side]:
        for dst in sorted(ALL):
            if not home(side, dst) or view.at(dst) or dst in threats or dst not in visible:
                continue
            choices.append((.8 if palace(dst) or view.terrain(dst) == "炮台" else .2,
                            {"type": "deploy", "kind": "P", "dst": dst, "waive_ap": waive}))
    if not choices:
        return {"type": "end"}
    return max(choices, key=lambda entry: entry[0])[1]


def apply_action(game, action):
    action = dict(action)
    kind = action.pop("type")
    if kind == "move":
        return game.move(action["uid"], tuple(action["dst"]))
    if kind == "skill":
        uid, number = action.pop("uid"), action.pop("number")
        return game.skill(uid, number, **action)
    if kind == "deploy":
        return game.deploy(action["kind"], tuple(action["dst"]), waive_ap=action.get("waive_ap", False))
    if kind == "heal":
        return game.replenish(action["uid"], "full")
    if kind == "upgrade":
        return game.upgrade(action["uid"])
    if kind == "followup":
        return game.followup_move(action["uid"], tuple(action["dst"]))
    game.end_turn()
    return "电脑结束回合"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m computer.opponent save/game.txt")
    print(json.dumps(choose_action(Game.load(sys.argv[1])), ensure_ascii=False))
