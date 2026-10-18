"""Fog warfare rules. Coordinates: a-i, ranks 1-10 (red starts at rank 1)."""
from __future__ import annotations

import copy
import json
import random
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from tactics import TacticsRules

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "XQPy-0.1"))
from XQlightPy.position import Position, COORD_XY, MOVE

CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
KINDS = "PRNCBAKF"
NAMES = {"P": "兵", "R": "车", "N": "马", "C": "炮", "B": "象", "A": "士", "K": "将", "F": "假将"}
SKILLS = {
    "P": ("战术调整", "战术后撤"), "C": ("侦察", "烟雾弹", "轰击"),
    "R": ("出车", "冲击"), "N": ("快速部署", "慌不择路"),
    "B": ("伏兵", "替死", "护驾"), "A": ("后勤部队", "伪装", "派遣随军侦察"),
    "K": ("战地部署", "飞将过河"), "F": ("战地部署", "飞将过河")
}
MAX_AP = 3
MOVE_AP = 3
BOMBARDMENT_START_ROUND = 7
SKILL_INFO = {
    "P": ("在己方棋盘左右移动一格，不能吃子。", "后退最多两格，遇到阻碍提前停止，不能吃子。"),
    "C": ("选择上下左右一个方向，视野改为整条直线，持续4个己方回合（含本回合）。移动或攻击取消；从第二回合起敌方在已有视野内能看到侦察线。河界不可扩大视野。",
          "选择2×2区域的左上角，烟雾外无法看见区域内部；区域内棋子只提供自身格视野。持续2回合，进入烟雾也会受影响，离开恢复视野。",
          "开局前6轮不能使用，第7轮解锁。隔一个炮架沿直线原地攻击，击杀非兵棋子返还敌方1部署点，兵不返还；对真将和假将无效。空炮使棋子冷却2回合，期间仅能使用持续1回合的侦察。"),
    "R": ("沿直线越过恰好一个友方棋子，到达空位，不能吃子。", "抵达直线目标旁，将其向前推一格。后方受阻则目标不动，不能吃子。"),
    "N": ("连续选择两个不吃子的马步，完成后才更新视野；途中受阻会停下并冷却2回合。", "本次马步不受蹩马腿限制，可以吃子；之后冷却2回合。"),
    "B": ("伏兵期间不会出现在敌方视野中，其所在格变为迷雾；移动或攻击解除。", "消耗升变棋种的部署点，可立即进行一次不吃子的合法移动；敌方获得1积分及1部署点。",
          "与象攻击范围内的一枚棋子交换位置，仍受象眼和河界限制。友方棋子只交换；敌方棋子交换后视为吃掉象，敌方获得象的积分与部署点。"),
    "A": ("获得1部署点，每3轮额外增加1点收益。", "每方每局一次，消耗10部署点在己方空位部署假将，只有己方知道身份。",
          "选择位于己方棋盘的友方棋子，永久增加1视野，可叠加。首次无额外部署费，第2、3、4次额外花费1、2、3部署点。过河继续有效；新增视野被敌军遮挡，河界仍强制视野1。"),
    "K": ("消耗2部署点，在全部空闲友方炮台和瞭望塔部署兵；炮台下回合可用，瞭望塔冷却2回合。", "向敌方底线直线移动；遇敌方将可吃子，遇其他棋子停在其前方。九宫格外不能普通移动。")
}
SKILL_INFO["F"] = SKILL_INFO["K"]


def skill_cost(kind, number):
    return 2 if kind == "R" or (kind == "N" and number == 0) or (kind in "KF" and number == 0) else 1


ALL = {(x, y) for x in range(9) for y in range(10)}
DIRECTIONS = {"上": (0, -1), "下": (0, 1), "左": (-1, 0), "右": (1, 0)}
TYPES = {"K": 0, "F": 0, "A": 1, "B": 2, "N": 3, "R": 4, "C": 5, "P": 6}


def coord(pos):
    return f"{chr(97 + pos[0])}{10 - pos[1]}"


def parse_coord(value):
    value = value.strip().lower()
    pos = (ord(value[0]) - 97, 10 - int(value[1:]))
    if pos not in ALL:
        raise ValueError("坐标范围为 a1 至 i10")
    return pos


def home(side, pos):
    return pos[1] >= 5 if side == 0 else pos[1] <= 4


def palace(pos):
    return 3 <= pos[0] <= 5 and (pos[1] <= 2 or pos[1] >= 7)


def neighbors(pos):
    return {(pos[0] + dx, pos[1] + dy) for dx, dy in DIRECTIONS.values()} & ALL


def line(src, dst):
    if src == dst or (src[0] != dst[0] and src[1] != dst[1]):
        return None
    dx = (dst[0] > src[0]) - (dst[0] < src[0])
    dy = (dst[1] > src[1]) - (dst[1] < src[1])
    result, p = [], (src[0] + dx, src[1] + dy)
    while p != dst:
        result.append(p)
        p = (p[0] + dx, p[1] + dy)
    return result


class RuleError(ValueError):
    pass


@dataclass
class Piece:
    uid: int
    side: int
    kind: str
    x: int
    y: int
    attack: int = 1
    hp: int = 1
    max_hp: int = 1
    ready_at: int = 0
    skill_turn: int = -1
    hidden: bool = False
    recon: str | None = None
    recon_until: int = 0
    recon_started: int = -1
    scout_bonus: int = 0
    cooldown_reason: str = ""
    logistics: int = 0
    defense: float = 0
    equipment: str = "normal"
    level: int = 0
    bonus_hp: int = 0
    upgrade_turn: int = -1
    upgrades_this_turn: int = 0
    equipped_turn: int = 0
    steps_this_turn: int = 0
    acted_this_turn: bool = False
    followup: bool = False
    aimed: bool = False

    @property
    def pos(self):
        return self.x, self.y


@dataclass
class Game(TacticsRules):
    pieces: list[Piece] = field(default_factory=list)
    current: int = 0
    round: int = 1
    turns: list[int] = field(default_factory=lambda: [1, 0])
    ap: int = MAX_AP
    scores: list[int] = field(default_factory=lambda: [0, 0])
    deployment: list[int] = field(default_factory=lambda: [0, 0])
    disguise_used: list[bool] = field(default_factory=lambda: [False, False])
    deploy_locked: list[bool] = field(default_factory=lambda: [False, False])
    deployment_waivers: list[int] = field(default_factory=lambda: [0, 0])
    smoke: list[dict] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)
    winner: int | None = None
    mode: str = "local"
    pending_handoff: bool = False
    next_uid: int = 1
    ruleset: str = "normal"
    fog_enabled: bool = True
    supplies: list[int] = field(default_factory=lambda: [10, 10])
    upgrades_used: list[int] = field(default_factory=lambda: [0, 0])
    rng_seed: int = field(default_factory=lambda: random.SystemRandom().randrange(2**53))
    rng_counter: int = 0

    @classmethod
    def new(cls, mode="local", ruleset="normal", fog_enabled=True):
        if ruleset not in ("normal", "tactics") or type(fog_enabled) is not bool:
            raise RuleError("请选择有效模式和迷雾设置")
        game = cls(mode=mode, ruleset=ruleset, fog_enabled=fog_enabled, deployment=[CONFIG["initial_deployment"]] * 2)
        for side, y, cy, py in ((0, 9, 7, 6), (1, 0, 2, 3)):
            for x, kind in enumerate("RNBAKABNR"):
                game.add(side, kind, (x, y))
            for x in (1, 7):
                game.add(side, "C", (x, cy))
            for x in (0, 2, 4, 6, 8):
                game.add(side, "P", (x, py))
        return game

    def add(self, side, kind, pos, delay=0):
        if kind not in KINDS or side not in (0, 1) or pos not in ALL or self.at(pos):
            raise RuleError("棋子或位置无效，目标位置必须为空")
        stats = CONFIG["piece_stats"][kind]
        p = Piece(self.next_uid, side, kind, *pos, stats["attack"], stats["hp"], stats["hp"], self.turns[side] + delay)
        self.next_uid += 1
        self.pieces.append(p)
        if self.ruleset == "tactics":
            self.apply_tactical_stats(p, full=True)
        return p

    def at(self, pos):
        return next((p for p in self.pieces if p.pos == pos), None)

    def by_id(self, uid):
        return next((p for p in self.pieces if p.uid == uid), None)

    def cost(self, kind):
        return CONFIG["piece_stats"][kind]["cost"]

    def log(self, action, **data):
        entry = dict(round=self.round, side=self.current, action=action, **data)
        self.history.append(json.loads(json.dumps(entry, ensure_ascii=False)))

    def require(self, p=None, ap=0, skill=False, skill_number=None):
        if self.winner is not None:
            raise RuleError("对局已经结束")
        if self.pending_handoff:
            raise RuleError("请先交接给下一位玩家")
        if ap > self.ap:
            raise RuleError("行动点不足")
        if p:
            if p not in self.pieces or p.side != self.current:
                raise RuleError("请选择己方棋子")
            if self.turns[p.side] < p.ready_at and not (skill and skill_number == 0 and self.bombardment_cooling(p)):
                raise RuleError("棋子处于冷却，不能移动或使用技能")
            if skill and p.skill_turn == self.turns[p.side]:
                raise RuleError("该棋子本回合已经使用技能")

    def bombardment_cooling(self, p):
        return p.kind == "C" and p.cooldown_reason == "bombardment" and self.turns[p.side] < p.ready_at

    def require_skill(self, p, number):
        if p is None or number not in range(len(self.tactical_skill_names(p))):
            raise RuleError("棋子或技能不存在")
        self.require(p, self.tactical_skill_cost(p, number), True, number)
        if p.kind == "C" and number == 2 and self.round < BOMBARDMENT_START_ROUND:
            raise RuleError("轰击开局冷却6轮，第7轮起可使用")

    def skill_ready(self, p, number):
        try:
            self.require_skill(p, number)
            return True
        except RuleError:
            return False

    def cool_down(self, p, reason="normal"):
        p.ready_at = self.turns[p.side] + 3
        p.cooldown_reason = reason

    def terrain(self, pos):
        x, y = pos
        if y in (2, 7) and x in (1, 7):
            return "炮台"
        if y in (3, 6) and x in (0, 2, 4, 6, 8):
            return "瞭望塔"
        return ""

    def smoke_cells(self, side=None):
        cells = set()
        for cloud in self.smoke:
            active = any(self.turns[s] < cloud["until"][s] for s in (0, 1)) if side is None else self.turns[side] < cloud["until"][side]
            if active:
                cells.update(tuple(pos) for pos in cloud["cells"])
        return cells

    def smoked(self, p):
        return p.pos in self.smoke_cells(p.side)

    def recon_active(self, p):
        return bool(p.recon and self.turns[p.side] < p.recon_until and p.y not in (4, 5))

    def recon_path(self, p):
        if not self.recon_active(p):
            return set()
        dx, dy = DIRECTIONS[p.recon]
        result, q = {p.pos}, p.pos
        while True:
            q = (q[0] + dx, q[1] + dy)
            if q not in ALL:
                return result
            result.add(q)

    def base_vision(self, p, extra=0):
        if self.smoked(p):
            return {p.pos}
        if p.y in (4, 5):
            return neighbors(p.pos) | {p.pos}
        if self.recon_active(p):
            return self.recon_path(p)
        bonus = max(0, 4 - self.round) + bool(self.terrain(p.pos)) + extra
        radius = (2 if p.kind == "C" or (p.kind == "P" and home(p.side, p.pos)) else 1) + bonus
        if self.ruleset == "tactics" and p.kind == "N" and p.equipment == "light":
            radius += 1
        visible = set()
        for q in ALL:
            dx, dy = abs(q[0] - p.x), abs(q[1] - p.y)
            if p.kind == "R":
                inside = ((dx == 0 or dy == 0) and max(dx, dy) <= 3 + bonus) or (dx == dy and dx <= 1 + bonus)
            else:
                inside = (dx + dy if CONFIG["vision_shape"] == "diamond" else max(dx, dy)) <= radius
            if inside:
                visible.add(q)
        return visible

    def scout_line_clear(self, p, dst):
        # Supercover grid traversal: both edge-touching cells block a diagonal ray.
        x, y = p.pos
        nx, ny = abs(dst[0] - x), abs(dst[1] - y)
        sx = (dst[0] > x) - (dst[0] < x)
        sy = (dst[1] > y) - (dst[1] < y)
        ix = iy = 0
        blockers = {q.pos for q in self.pieces if q.side != p.side}
        while ix < nx or iy < ny:
            cross_x, cross_y = (1 + 2 * ix) * ny, (1 + 2 * iy) * nx
            if cross_x == cross_y:
                touched = {(x + sx, y), (x, y + sy)}
                if (touched - {dst}) & blockers:
                    return False
                x, y, ix, iy = x + sx, y + sy, ix + 1, iy + 1
            elif cross_x < cross_y:
                x, ix = x + sx, ix + 1
            else:
                y, iy = y + sy, iy + 1
            if (x, y) != dst and (x, y) in blockers:
                return False
        return True

    def piece_vision(self, p):
        visible = self.base_vision(p)
        extra = p.scout_bonus + (1 if self.ruleset == "tactics" and p.kind == "N" and p.equipment == "light" else 0)
        if extra and not self.smoked(p) and p.y not in (4, 5) and not self.recon_active(p):
            visible |= {q for q in self.base_vision(p, extra) - visible if self.scout_line_clear(p, q)}
        if p.kind == "A" and palace(p.pos) and not self.smoked(p):
            visible |= {q for q in ALL if palace(q) and home(p.side, q)}
        return (visible - self.smoke_cells(p.side)) | {p.pos}

    def vision(self, side):
        visible = set()
        for p in self.pieces:
            if p.side == side:
                visible |= self.piece_vision(p)
        if not self.fog_enabled:
            visible = ALL - self.smoke_cells(side)
        for p in self.pieces:
            if self.fog_enabled and p.side != side and p.kind == "A":
                visible -= neighbors(p.pos)
            if p.side != side and p.hidden:
                visible.discard(p.pos)
        return visible | {p.pos for p in self.pieces if p.side == side}

    def recon_marks(self, side):
        visible = ALL if side is None else self.vision(side)
        marks = []
        for p in self.pieces:
            if not self.recon_active(p) or self.smoked(p):
                continue
            if side not in (None, p.side) and self.turns[p.side] <= p.recon_started:
                continue
            cells = (self.recon_path(p) - {p.pos}) & visible
            if cells:
                marks.append((p.side, p.recon, cells))
        return marks

    def known(self, side):
        vision = self.vision(side)
        return [p for p in self.pieces if p.side == side or p.pos in vision]

    def position(self, pieces=None, side=None):
        pos = Position()
        pos.clearBoard()
        pos.sdPlayer = self.current if side is None else side
        for p in self.pieces if pieces is None else pieces:
            pos.addPiece(COORD_XY(p.x + 3, p.y + 3), TYPES[p.kind] + (8 if p.side == 0 else 16))
        return pos

    def legal_base(self, p, dst, pieces=None, ignore_leg=False):
        if dst not in ALL or dst == p.pos:
            return False
        collection = self.pieces if pieces is None else pieces
        target = next((q for q in collection if q.pos == dst), None)
        if target and target.side == p.side:
            return False
        if self.ruleset == "tactics":
            tactical = self.tactical_geometry(p, dst, collection)
            if tactical is not None:
                return tactical
        if p.kind in "KAF" and not palace(p.pos):
            return False
        if p.kind in "KF":
            return palace(dst) and home(0 if p.y >= 7 else 1, dst) and abs(dst[0] - p.x) + abs(dst[1] - p.y) == 1
        if p.kind == "N" and ignore_leg:
            return sorted((abs(dst[0] - p.x), abs(dst[1] - p.y))) == [1, 2]
        pos = self.position(collection, p.side)
        return bool(pos.legalMove(MOVE(COORD_XY(p.x + 3, p.y + 3), COORD_XY(dst[0] + 3, dst[1] + 3))))

    def selection_targets(self, uid, followup=False):
        p = self.by_id(uid)
        if not p or p.side != self.current:
            return set(), set()
        known = self.known(p.side)
        occupied = {q.pos: q for q in known}
        if followup:
            return (neighbors(p.pos) - occupied.keys() if p.followup else set()), set()
        moves, attacks = set(), set()
        for dst in ALL - {p.pos}:
            target = occupied.get(dst)
            path = line(p.pos, dst)
            cannon_shot = (p.kind == "C" and path is not None
                           and sum(pos in occupied for pos in path) == 1
                           and (not target or target.side != p.side)
                           and (self.ruleset != "tactics" or max(abs(dst[0]-p.x), abs(dst[1]-p.y)) <= (3 if p.equipment == "heavy" else 5)))
            if cannon_shot:
                attacks.add(dst)
            elif self.legal_base(p, dst, known):
                (attacks if target else moves).add(dst)
        return moves, attacks

    def threats(self, side, pieces=None):
        collection = self.pieces if pieces is None else pieces
        result = set()
        for p in collection:
            if p.side != side:
                continue
            result |= neighbors(p.pos)
            for dst in ALL:
                # Evaluate capture geometry against an enemy dummy, including cannon screens.
                others = [q for q in collection if q.pos != dst]
                if dst == p.pos:
                    continue
                dummy = Piece(-1, 1 - side, "P", *dst)
                if self.legal_base(p, dst, others + [dummy]):
                    result.add(dst)
        return result

    def hit(self, attacker, target):
        if self.ruleset == "tactics":
            return self.combat(attacker, target)
        attacker.recon = None
        if not CONFIG["instant_kill"]:
            target.hp -= attacker.attack
            if target.hp > 0:
                return False
        self.capture(attacker, target)
        return True

    def capture(self, attacker, target):
        value = self.cost(target.kind)
        self.scores[attacker.side] += value
        self.award_deployment(attacker.side, value)
        self.pieces.remove(target)
        if target.kind == "K":
            self.winner = attacker.side

    def relocate(self, p, dst, capture=True):
        source = p.pos
        target = self.at(dst)
        if target:
            if not capture or target.side == p.side:
                raise RuleError("目标被占用，不能吃子")
            if self.ruleset == "tactics" and p.kind == "R":
                dx = (dst[0] > source[0]) - (dst[0] < source[0])
                dy = (dst[1] > source[1]) - (dst[1] < source[1])
                adjacent = (dst[0] - dx, dst[1] - dy)
                if adjacent != source:
                    self.relocate(p, adjacent, False)
            killed = self.hit(p, target)
            if p not in self.pieces:
                return
            if not killed:
                return
        if self.ruleset == "tactics":
            p.steps_this_turn += max(abs(dst[0] - p.x), abs(dst[1] - p.y))
            p.acted_this_turn = True
        p.x, p.y = dst
        self.movement_effects(p)

    def movement_effects(self, p):
        p.hidden = False
        p.recon = None
        p.aimed = False

    def move(self, uid, dst):
        p = self.by_id(uid)
        if p is None:
            raise RuleError("棋子不存在")
        self.require(p, MOVE_AP)
        src = p.pos
        if dst not in ALL or dst == src:
            raise RuleError("目标坐标无效")
        path = line(src, dst)
        if self.ruleset == "tactics" and p.kind == "C" and max(abs(dst[0] - p.x), abs(dst[1] - p.y)) > (3 if p.equipment == "heavy" else 5):
            raise RuleError("目标超过炮的移动力")
        if p.kind == "C" and path is not None:
            screens = [q for q in path if self.at(q)]
            if len(screens) == 1:
                target = self.at(dst)
                if target and target.side == p.side:
                    raise RuleError("炮不能攻击友方")
                self.ap -= MOVE_AP
                p.hidden = False
                p.recon = None
                if target:
                    self.relocate(p, dst)
                else:
                    self.cool_down(p)
                self.log("炮击", source=coord(src), target=coord(dst), hit=bool(target))
                return "炮击命中" if target else "炮击落空，冷却两个己方回合"
        if not self.legal_base(p, dst, self.known(p.side)):
            raise RuleError("不符合象棋走法或路径被阻挡")
        if not self.legal_base(p, dst):
            if p.kind in "RC" and path is not None:
                blockers = [q for q in path if self.at(q)]
                if blockers:
                    q = blockers[0]
                    dx = (dst[0] > src[0]) - (dst[0] < src[0])
                    dy = (dst[1] > src[1]) - (dst[1] < src[1])
                    dst = (q[0] - dx, q[1] - dy)
                    if dst != src:
                        self.relocate(p, dst, False)
                else:
                    dst = src
            else:
                dst = src
            self.ap -= MOVE_AP
            self.log("移动受阻", source=coord(src), target=coord(dst))
            return "遭遇迷雾中的阻碍，已停止移动"
        self.relocate(p, dst)
        self.ap -= MOVE_AP
        self.log("移动", source=coord(src), target=coord(dst))
        return "移动完成"

    def pawn_deployment_surcharge(self):
        count = sum(p.side == self.current and p.kind == "P" for p in self.pieces)
        return max(0, count + 1 - 6) * 2

    def deployment_quote(self, kind, waive_ap=False):
        if kind not in ("P", "R", "N", "C", "B", "A"):
            raise RuleError("只能部署普通棋子")
        surcharge = self.deployment_waivers[self.current] + 1 if waive_ap else 0
        population_fee = self.pawn_deployment_surcharge() if kind == "P" else 0
        return self.cost(kind) + population_fee + surcharge, 0 if waive_ap else 1, surcharge

    def deploy(self, kind, dst, waive_ap=False):
        cost, ap_cost, surcharge = self.deployment_quote(kind, waive_ap)
        population_fee = self.pawn_deployment_surcharge() if kind == "P" else 0
        self.require(ap=ap_cost)
        self.require_deploy()
        if kind not in "PRNCBA" or dst not in ALL or not home(self.current, dst):
            raise RuleError("只能在己方棋盘部署普通棋子")
        if self.deployment[self.current] < cost:
            raise RuleError("部署点不足")
        known = self.known(self.current)
        if any(p.pos == dst for p in known):
            raise RuleError("目标位置被占用")
        if self.ruleset == "tactics" and (self.at(dst) or self.deployment_forbidden(self.current, dst)):
            raise RuleError("无法部署：目标被占用或处于入侵敌军的攻击范围，不扣除费用")
        if self.ruleset != "tactics" and dst in self.threats(1 - self.current, known):
            raise RuleError("目标处于已知敌方邻接或攻击范围")
        self.deployment[self.current] -= cost
        self.ap -= ap_cost
        if waive_ap:
            self.deployment_waivers[self.current] += 1
        if self.ruleset != "tactics" and (self.at(dst) or (dst in self.vision(1 - self.current) and dst in self.threats(1 - self.current))):
            self.scores[1 - self.current] += self.cost(kind)
            self.deploy_locked[self.current] = True
            self.log("部署失败", kind=kind, target=coord(dst), cost=cost, surcharge=surcharge, population_fee=population_fee, ap=ap_cost)
            return "遭遇隐藏敌军：部署失败，部署点已扣除，敌方获得积分"
        delay = 1 if dst[1] in (0, 9) or palace(dst) or self.terrain(dst) == "炮台" else 3
        self.add(self.current, kind, dst, delay)
        self.log("部署", kind=kind, target=coord(dst), cost=cost, surcharge=surcharge, population_fee=population_fee, ap=ap_cost)
        return "部署成功"

    def require_deploy(self):
        if self.deploy_locked[self.current]:
            raise RuleError("本回合部署失败过，不能再部署部队")

    def transform(self, p, kind, surcharge=0):
        if kind not in ("R", "N", "C", "B", "A"):
            raise RuleError("请选择车、马、炮、象或士")
        cost = self.cost(kind) + surcharge
        if self.deployment[p.side] < cost:
            raise RuleError("部署点不足")
        self.deployment[p.side] -= cost
        p.kind = kind
        stats = CONFIG["piece_stats"][kind]
        p.attack, p.hp, p.max_hp = stats["attack"], stats["hp"], stats["hp"]
        p.hidden, p.recon = False, None
        if self.ruleset == "tactics":
            p.equipment, p.level, p.aimed = "normal", 0, False
            self.apply_tactical_stats(p, full=True)
        return cost

    def promote(self, uid, kind):
        p = self.by_id(uid)
        if p is None or p.kind != "P":
            raise RuleError("只能升变兵")
        self.require(p, 2)
        cost = self.transform(p, kind, 0 if home(p.side, p.pos) else 2)
        self.ap -= 2
        self.log("兵升变", target=coord(p.pos), kind=kind, cost=cost)
        return "兵升变完成"

    def skill(self, uid, number, **options):
        # Validate multi-step skills on a copy so failed choices never spend resources.
        trial = copy.deepcopy(self)
        result = trial._skill(uid, number, **options)
        self.__dict__.update(trial.__dict__)
        return result

    def _skill(self, uid, number, **o):
        p = self.by_id(uid)
        if p is None or number not in range(len(self.tactical_skill_names(p))):
            raise RuleError("棋子或技能不存在")
        kind, src = p.kind, p.pos
        skill_name = self.tactical_skill_names(p)[number]
        cost = self.tactical_skill_cost(p, number)
        self.require_skill(p, number)
        dst = tuple(o.get("dst", src))
        if dst not in ALL:
            raise RuleError("目标位置越界")
        message = "技能使用完成"
        special = self.special_tactical_skill(p, number, o)
        if special is not None:
            self.ap -= cost
            p.skill_turn = self.turns[p.side]
            self.log("技能", name=skill_name, source=coord(src), target=coord(p.pos), options=o)
            return special
        if kind == "P":
            if number == 0:
                if not home(p.side, src) or abs(dst[0] - p.x) != 1 or dst[1] != p.y or self.at(dst):
                    raise RuleError("战术调整只能在己方棋盘左右移动一格，不能吃子")
                self.relocate(p, dst, False)
            else:
                dy = 1 if p.side == 0 else -1
                for _ in range(2):
                    q = (p.x, p.y + dy)
                    if q not in ALL or self.at(q):
                        break
                    self.relocate(p, q, False)
        elif kind == "C":
            if number == 0:
                direction = o.get("direction")
                if direction not in DIRECTIONS or p.y in (4, 5):
                    raise RuleError("请选择侦察方向；河界上的棋子无法扩大视野")
                duration = 1 if self.bombardment_cooling(p) else 4
                p.recon, p.recon_until, p.recon_started = direction, self.turns[p.side] + duration, self.turns[p.side]
                if self.ruleset == "tactics":
                    p.aimed = True
            elif number == 1:
                if dst[0] >= 8 or dst[1] >= 9:
                    raise RuleError("请选择2×2区域的左上角，区域必须完整位于棋盘内")
                cells = [[dst[0] + dx, dst[1] + dy] for dx in range(2) for dy in range(2)]
                until = [self.turns[s] + (2 if s == self.current else 3) for s in (0, 1)]
                self.smoke.append(dict(cells=cells, until=until))
            else:
                path = line(src, dst)
                if path is None or sum(self.at(q) is not None for q in path) != 1:
                    raise RuleError("轰击需要直线路径上恰好一个炮架")
                target = self.at(dst)
                if target and (target.side == p.side or (self.ruleset != "tactics" and target.kind in "KF")):
                    raise RuleError("轰击不能攻击友方，对真将和假将无效")
                p.recon, p.hidden = None, False
                if target:
                    refund = target.kind != "P"
                    killed = self.combat(p, target, bombard=True) if self.ruleset == "tactics" else self.hit(p, target)
                    if killed and refund:
                        self.award_deployment(1 - p.side, 1)
                    message = "轰击命中，炮保持原位"
                else:
                    p.aimed = False
                    self.cool_down(p, "bombardment")
                    message = "轰击落空，冷却两个己方回合"
        elif kind == "R":
            path = line(src, dst)
            if path is None:
                raise RuleError("车技能必须沿直线选择目标")
            if number == 0:
                blockers = [self.at(q) for q in path if self.at(q)]
                if self.at(dst) or len(blockers) != 1 or blockers[0].side != p.side:
                    raise RuleError("出车必须越过恰好一个友方棋子，目标必须为空")
                self.relocate(p, dst, False)
            else:
                target = self.at(dst)
                if target is None or any(self.at(q) for q in path):
                    raise RuleError("选择直线路径上可抵达的一个棋子")
                dx = (dst[0] > p.x) - (dst[0] < p.x)
                dy = (dst[1] > p.y) - (dst[1] < p.y)
                adjacent, pushed = (dst[0] - dx, dst[1] - dy), (dst[0] + dx, dst[1] + dy)
                if adjacent != src:
                    self.relocate(p, adjacent, False)
                if pushed in ALL and not self.at(pushed):
                    self.relocate(target, pushed, False)
                else:
                    message = "已抵达目标旁，目标后方受阻，未能推动"
        elif kind == "N":
            if number == 0:
                targets = [tuple(o.get("first", src)), dst]
                # Both moves execute atomically; no intermediate view is exposed to callers.
                for q in targets:
                    if q not in ALL or not self.legal_base(p, q) or self.at(q):
                        self.cool_down(p)
                        message = "快速部署受阻，已停下并进入两回合冷却"
                        break
                    self.relocate(p, q, False)
            else:
                if not self.legal_base(p, dst, ignore_leg=True):
                    raise RuleError("请选择合法的马步目标")
                self.relocate(p, dst)
                self.cool_down(p)
        elif kind == "B":
            if number == 0:
                p.hidden = True
            elif number == 1:
                target_kind = o.get("kind")
                self.transform(p, target_kind)
                if dst != src:
                    if self.at(dst) or not self.legal_base(p, dst):
                        raise RuleError("替死后的立即移动必须合法且不能吃子")
                    self.relocate(p, dst, False)
                self.scores[1 - p.side] += 1
                self.award_deployment(1 - p.side, 1)
            else:
                target = self.at(dst)
                if target is None:
                    raise RuleError("护驾目标必须是一枚棋子")
                geometry = [q for q in self.pieces if q is not target]
                geometry.append(Piece(-1, 1 - p.side, target.kind, *dst))
                if not self.legal_base(p, dst, geometry):
                    raise RuleError("目标不在象的攻击范围内，或象眼受阻")
                p.x, p.y = dst
                target.x, target.y = src
                self.movement_effects(p)
                self.movement_effects(target)
                if target.side != p.side:
                    self.capture(target, p)
                    message = "交换完成，象被敌方吃掉"
                else:
                    message = "护驾完成，已与友方棋子交换位置"
        elif kind == "A":
            if number == 0:
                p.logistics += 1
                bonus = 1 + (self.round - 1) // 3
                self.award_deployment(p.side, bonus)
                message = f"获得{bonus}点部署点"
            elif number == 1:
                self.require_deploy()
                if self.disguise_used[p.side] or self.deployment[p.side] < 10:
                    raise RuleError("伪装每方每局一次，需要10点部署点")
                known = self.known(p.side)
                if not home(p.side, dst) or any(q.pos == dst for q in known):
                    raise RuleError("假将必须部署在己方空位")
                if self.ruleset == "tactics" and (self.at(dst) or self.deployment_forbidden(p.side, dst)):
                    raise RuleError("无法部署假将：目标被占用或处于入侵敌军攻击范围")
                if self.ruleset != "tactics" and dst in self.threats(1 - p.side, known):
                    raise RuleError("假将不能部署在已知敌方攻击范围")
                self.deployment[p.side] -= 10
                self.disguise_used[p.side] = True
                if self.ruleset != "tactics" and (self.at(dst) or (dst in self.vision(1 - p.side) and dst in self.threats(1 - p.side))):
                    self.scores[1 - p.side] += 10
                    self.deploy_locked[p.side] = True
                    message = "假将部署遭遇隐藏敌军，敌方获得10积分"
                else:
                    self.add(p.side, "F", dst, 1 if palace(dst) or dst[1] in (0, 9) or self.terrain(dst) == "炮台" else 3)
            else:
                target = self.at(dst)
                if not target or target.side != p.side or not home(p.side, dst):
                    raise RuleError("随军侦察请选择己方棋盘内的友方棋子")
                surcharge = target.scout_bonus
                if self.deployment[p.side] < surcharge:
                    raise RuleError(f"叠加随军侦察需要额外{surcharge}点部署点")
                self.deployment[p.side] -= surcharge
                target.scout_bonus += 1
                message = f"已派遣随军侦察，目标额外视野+{target.scout_bonus}，花费{surcharge}部署点"
        elif kind in "KF":
            if number == 0:
                self.require_deploy()
                if self.deployment[p.side] < 2:
                    raise RuleError("战地部署需要2点部署点")
                cells = [q for q in ALL if home(p.side, q) and self.terrain(q) and not self.at(q)]
                if self.ruleset == "tactics":
                    cells = [q for q in cells if not self.deployment_forbidden(p.side, q)]
                if not cells:
                    raise RuleError("没有空闲的友方炮台或瞭望塔")
                self.deployment[p.side] -= 2
                for q in cells:
                    self.add(p.side, "P", q, 1 if self.terrain(q) == "炮台" else 3)
            else:
                dy = -1 if p.side == 0 else 1
                goal = 0 if p.side == 0 else 9
                q = src
                while q[1] != goal:
                    next_pos = (q[0], q[1] + dy)
                    target = self.at(next_pos)
                    if target:
                        if target.side != p.side and target.kind in "KF":
                            self.relocate(p, next_pos)
                        break
                    q = next_pos
                else:
                    pass
                if p.pos == src and q != src:
                    self.relocate(p, q, False)
        self.ap -= cost
        p.skill_turn = self.turns[p.side]
        self.log("技能", name=skill_name, source=coord(src), target=coord(p.pos), options=o)
        return message

    def end_turn(self):
        self.require()
        self.log("结束回合")
        self.current = 1 - self.current
        if self.current == 0:
            self.round += 1
        self.turns[self.current] += 1
        self.ap = MAX_AP
        self.deploy_locked[self.current] = False
        self.deployment_waivers[self.current] = 0
        r = self.round
        income = 2 if r >= 50 else 1 if r >= 30 or (r >= 4 and r % 2 == 0) else 0
        self.deployment[self.current] += income
        self.tactics_start_turn()
        self.pending_handoff = self.mode == "local"
        self.smoke = [s for s in self.smoke if any(self.turns[i] < s["until"][i] for i in (0, 1))]

    def rating(self, side):
        mine, other = self.scores[side], self.scores[1 - side]
        if self.winner == side:
            if mine > 3 * other:
                return "不可思议的胜利"
            if mine > 2 * other:
                return "压倒性完胜"
            if mine > other:
                return "不错的胜利"
            if mine * 2 < other:
                return "损失惨重的胜利"
            return "胶着的胜利"
        if mine > 3 * other:
            return "战术的失败，战略的成功"
        if mine > 2 * other:
            return "棋差一着"
        return "胶着的失败"

    def save(self, path):
        data = asdict(self)
        data["format"] = "fog-xiangqi"
        data["version"] = 5
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        version = data.pop("version", None)
        if data.pop("format", None) != "fog-xiangqi" or version not in (1, 2, 3, 4, 5):
            raise RuleError("不支持的存档格式")
        if version == 1:
            for p in data["pieces"]:
                if p.get("recon"):
                    p.setdefault("recon_started", p.get("recon_until", 0) - 1)
        for p in data["pieces"]:
            if type(p.get("scout_bonus", 0)) is bool:
                p["scout_bonus"] = int(p["scout_bonus"])
        data["pieces"] = [Piece(**p) for p in data["pieces"]]
        if "upgrades_used" not in data and version < 5:
            data["upgrades_used"] = [min(2, sum(p.upgrades_this_turn for p in data["pieces"]
                if p.side == side and p.upgrade_turn == data["turns"][side])) for side in (0, 1)]
        game = cls(**data)
        if len(game.upgrades_used) != 2 or any(type(v) is not int or not 0 <= v <= 2 for v in game.upgrades_used):
            raise RuleError("存档普通升级次数无效")
        if game.ruleset not in ("normal", "tactics") or type(game.fog_enabled) is not bool or len(game.supplies) != 2 or any(type(v) is not int or v < 0 for v in game.supplies):
            raise RuleError("存档模式或军需点无效")
        if type(game.rng_seed) is not int or type(game.rng_counter) is not int or game.rng_counter < 0:
            raise RuleError("存档随机序列无效")
        if any(p.equipment not in ("normal", "light", "heavy") or p.level < 0 or p.max_hp <= 0 or not 0 < p.hp <= p.max_hp for p in game.pieces):
            raise RuleError("存档装备或血量无效")
        if game.current not in (0, 1) or game.mode not in ("local", "ai", "debug") or game.round < 1 or not 0 <= game.ap <= MAX_AP:
            raise RuleError("存档回合数据无效")
        if len(game.turns) != 2 or len(game.scores) != 2 or len(game.deployment) != 2 or any(v < 0 for v in game.scores + game.deployment + game.turns):
            raise RuleError("存档玩家数据无效")
        if len(game.deploy_locked) != 2 or any(type(v) is not bool for v in game.deploy_locked):
            raise RuleError("存档部署状态无效")
        if len(game.deployment_waivers) != 2 or any(type(v) is not int or v < 0 for v in game.deployment_waivers):
            raise RuleError("存档部署减免次数无效")
        if len({p.pos for p in game.pieces}) != len(game.pieces) or len({p.uid for p in game.pieces}) != len(game.pieces):
            raise RuleError("存档含重复棋子")
        if any(p.pos not in ALL or p.side not in (0, 1) or p.kind not in KINDS for p in game.pieces):
            raise RuleError("存档棋子数据无效")
        if any(type(p.scout_bonus) is not int or p.scout_bonus < 0 or p.cooldown_reason not in ("", "normal", "bombardment") for p in game.pieces):
            raise RuleError("存档技能状态无效")
        if game.next_uid <= max((p.uid for p in game.pieces), default=0):
            raise RuleError("存档棋子编号无效")
        return game
