"""Tk desktop client for fog xiangqi. Run: python game.py."""
from __future__ import annotations

from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from engine import Game, RuleError, ROOT, CONFIG, NAMES, SKILLS, SKILL_INFO, MAX_AP, skill_cost, KINDS, ALL, coord, home, palace
from computer.opponent import choose_action, apply_action

BG, PANEL, INK, MUTED = "#f0f3f4", "#ffffff", "#1b292d", "#66777b"
RED, BLACK, GREEN = "#b63b46", "#263c44", "#187d70"
GLYPHS = ({"P": "兵", "C": "炮", "R": "车", "N": "马", "B": "相", "A": "仕", "K": "帅", "F": "帅"},
          {"P": "卒", "C": "砲", "R": "車", "N": "馬", "B": "象", "A": "士", "K": "将", "F": "将"})


class App:
    def __init__(self, root):
        self.root = root
        root.title(CONFIG["title"])
        root.geometry("1120x800")
        root.minsize(940, 720)
        root.configure(bg=BG)
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TButton", font=("Microsoft YaHei UI", 11), padding=8)
        style.configure("TLabel", background=BG, foreground=INK, font=("Microsoft YaHei UI", 11))
        style.configure("TFrame", background=BG)
        style.configure("TCombobox", padding=5)
        style.configure("TRadiobutton", font=("Microsoft YaHei UI", 11), background=BG)
        style.configure("TCheckbutton", font=("Microsoft YaHei UI", 10), background=BG)
        self.game = None
        self.selected = None
        self.action = "move"
        self.skill_number = None
        self.skill_options = {}
        self.first = None
        self.view = None
        self.ai_token = 0
        self.ai_steps = 0
        self.images = {}
        self.palette = None
        self.palette_inset = 0
        self.palette_buttons = {}
        self.root.bind("<Button-3>", self.cancel_action)
        self.root.bind("<Configure>", self.position_palette, add="+")
        self.load_images()
        self.menu()

    def load_images(self):
        for key, filename in CONFIG.get("textures", {}).items():
            try:
                path = (ROOT / "textures" / filename).resolve()
                path.relative_to((ROOT / "textures").resolve())
                img = tk.PhotoImage(file=str(path))
                factor = max(1, (max(img.width(), img.height()) + 47) // 48)
                self.images[key] = img.subsample(factor)
            except (tk.TclError, ValueError):
                pass

    def clear(self):
        self.ai_token += 1
        self.close_palette(False)
        for widget in self.root.winfo_children():
            widget.destroy()

    def menu(self):
        self.clear()
        self.game = None
        frame = ttk.Frame(self.root, padding=32)
        frame.pack(expand=True)
        tk.Label(frame, text="迷雾战棋", font=("Microsoft YaHei UI", 34, "bold"), bg=BG, fg=INK).pack(pady=(0, 10))
        tk.Label(frame, text="中国象棋", font=("Microsoft YaHei UI", 16), bg=BG, fg=GREEN).pack(pady=(0, 30))
        self.start_frame = ttk.Frame(frame)
        ttk.Button(frame, text="开始游戏", command=lambda: self.start_frame.pack(pady=8, before=self.load_button)).pack(fill="x", pady=6)
        ttk.Button(self.start_frame, text="本地双人", command=lambda: self.setup_game("local")).pack(side="left", padx=4)
        ttk.Button(self.start_frame, text="与电脑对战", command=lambda: self.setup_game("ai")).pack(side="left", padx=4)
        self.load_button = ttk.Button(frame, text="读取游戏", command=self.load)
        self.load_button.pack(fill="x", pady=6)
        ttk.Button(frame, text="战棋模式", command=lambda: self.setup_game("local", "tactics")).pack(fill="x", pady=6)
        ttk.Button(frame, text="调试模式及残局设计", command=lambda: self.setup_game("debug")).pack(fill="x", pady=6)
        ttk.Button(frame, text="退出", command=self.root.destroy).pack(fill="x", pady=6)

    def setup_game(self, mode, ruleset="normal"):
        self.clear()
        self.game = None
        frame = ttk.Frame(self.root, padding=32)
        frame.pack(expand=True)
        ttk.Label(frame, text="残局设计设置" if mode == "debug" else "对局设置", font=("Microsoft YaHei UI", 23, "bold")).pack(pady=18)
        self.setup_rules = tk.StringVar(value=ruleset)
        self.setup_fog = tk.BooleanVar(value=True)
        self.setup_opponent = tk.StringVar(value=mode)
        for text, value in (("普通模式", "normal"), ("战棋模式", "tactics")):
            ttk.Radiobutton(frame, text=text, value=value, variable=self.setup_rules).pack(anchor="w", pady=9)
        ttk.Checkbutton(frame, text="启用战争迷雾", variable=self.setup_fog).pack(anchor="w", pady=16)
        if mode != "debug":
            for text, value in (("本地双人", "local"), ("与电脑对战", "ai")):
                ttk.Radiobutton(frame, text=text, value=value, variable=self.setup_opponent).pack(anchor="w", pady=8)
        self.setup_begin = ttk.Button(frame, text="进入残局设计" if mode == "debug" else "开始对局", command=lambda: self.start(self.setup_opponent.get(), self.setup_rules.get(), self.setup_fog.get()))
        self.setup_begin.pack(fill="x", pady=(24, 8))
        ttk.Button(frame, text="返回", command=self.menu).pack(fill="x")

    def start(self, mode, ruleset="normal", fog_enabled=True):
        self.game = Game.new(mode, ruleset, fog_enabled)
        self.build_board()

    def build_board(self):
        self.clear()
        self.selected, self.action, self.view = None, "move", None
        self.first, self.skill_number, self.skill_options = None, None, {}
        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.columnconfigure(1, minsize=300)
        outer.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(outer, bg=PANEL, highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew", padx=(0, 20))
        self.canvas.bind("<Configure>", lambda event: self.draw())
        self.canvas.bind("<Button-1>", self.click)
        self.canvas.bind("<Motion>", self.hover_attack)
        self.canvas.bind("<Leave>", lambda event: self.preview.set(""))
        sidebar = ttk.Frame(outer)
        sidebar.grid(row=0, column=1, sticky="nsew")
        self.sidebar_scroll = tk.Canvas(sidebar, width=300, bg=BG, highlightthickness=0)
        self.sidebar_scroll.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(sidebar, orient="vertical", command=self.sidebar_scroll.yview)
        scrollbar.pack(side="right", fill="y")
        self.sidebar_scroll.configure(yscrollcommand=scrollbar.set)
        right = ttk.Frame(self.sidebar_scroll, width=300)
        window = self.sidebar_scroll.create_window((0, 0), window=right, anchor="nw")
        right.bind("<Configure>", lambda event: self.sidebar_scroll.configure(scrollregion=self.sidebar_scroll.bbox("all")))
        self.sidebar_scroll.bind("<Configure>", lambda event: self.sidebar_scroll.itemconfigure(window, width=event.width))
        self.root.bind("<MouseWheel>", self.scroll_sidebar)
        self.title = ttk.Label(right, font=("Microsoft YaHei UI", 18, "bold"))
        self.title.pack(anchor="w", pady=(4, 16))
        self.score = ttk.Label(right, justify="left")
        self.score.pack(anchor="w", pady=8)
        self.points = ttk.Label(right, foreground=GREEN, font=("Microsoft YaHei UI", 14, "bold"))
        self.points.pack(anchor="w", pady=8)
        ttk.Separator(right).pack(fill="x", pady=12)
        self.detail = ttk.Label(right, text="", wraplength=280, justify="left")
        self.detail.pack(anchor="w", pady=(0, 12))
        self.deploy_button = ttk.Button(right, text="部署部队", command=self.deploy_menu)
        self.deploy_button.pack(fill="x", pady=4)
        ttk.Button(right, text="使用技能", command=self.skill_mode).pack(fill="x", pady=4)
        ttk.Button(right, text="兵升变", command=self.promote).pack(fill="x", pady=4)
        if self.game.ruleset == "tactics":
            ttk.Button(right, text="军需管理", command=self.military_menu).pack(fill="x", pady=4)
        ttk.Button(right, text="结束回合", command=self.end).pack(fill="x", pady=4)
        ttk.Button(right, text="保存游戏", command=self.save).pack(fill="x", pady=4)
        ttk.Button(right, text="主菜单", command=self.return_menu).pack(fill="x", pady=4)
        if self.game.mode == "debug":
            self.debug_tools(right)
        self.status = tk.StringVar(value="")
        ttk.Label(outer, textvariable=self.status, wraplength=1000, foreground=MUTED).grid(row=1, column=0, columnspan=2, sticky="w", pady=(10, 0))
        self.preview = tk.StringVar(value="")
        tk.Label(outer, textvariable=self.preview, bg=BG, fg=GREEN, font=("Microsoft YaHei UI", 10), height=2, anchor="w", justify="left", wraplength=880).grid(row=2, column=0, columnspan=2, sticky="ew")
        self.refresh()
        if self.game.pending_handoff:
            self.handoff()
        elif self.game.mode == "ai" and self.game.current == 1 and self.game.winner is None:
            self.schedule_ai()

    def viewing_side(self):
        if self.game.mode == "debug":
            return self.view
        return 0 if self.game.mode == "ai" else self.game.current

    def scroll_sidebar(self, event):
        if self.game is None or not self.sidebar_scroll.winfo_exists():
            return
        x, y = self.sidebar_scroll.winfo_rootx(), self.sidebar_scroll.winfo_rooty()
        if x <= event.x_root <= x + self.sidebar_scroll.winfo_width() and y <= event.y_root <= y + self.sidebar_scroll.winfo_height():
            self.sidebar_scroll.yview_scroll(-int(event.delta / 120), "units")

    def geometry(self):
        w, h = max(100, self.canvas.winfo_width()), max(100, self.canvas.winfo_height())
        width = w - self.palette_inset
        self.cell = max(1, min((width - 112) / 8, (h - 100) / 9))
        self.ox, self.oy = self.palette_inset + (width - self.cell * 8) / 2 + 8, (h - self.cell * 9) / 2

    def xy(self, pos):
        return self.ox + pos[0] * self.cell, self.oy + pos[1] * self.cell

    def draw(self):
        if not self.game:
            return
        c = self.canvas
        c.delete("all")
        self.geometry()
        s = self.cell
        side = self.viewing_side()
        visible = ALL if side is None else self.game.vision(side)
        for pos in sorted(ALL):
            x, y = self.xy(pos)
            fill = "#eef5f1" if palace(pos) else "#f8faf9"
            if self.game.terrain(pos) == "炮台":
                fill = "#dcebe6"
            elif self.game.terrain(pos) == "瞭望塔":
                fill = "#e4eaf0"
            if pos not in visible:
                fill = "#53626a"
            c.create_rectangle(x - s / 2, y - s / 2, x + s / 2, y + s / 2, fill=fill, outline="")
        for y in range(10):
            x0, yy = self.xy((0, y))
            x1, _ = self.xy((8, y))
            c.create_line(x0, yy, x1, yy, fill="#839792")
            c.create_text(x0 - min(s * .68, 34), yy, text=str(10 - y), fill=MUTED, font=("Segoe UI", 11))
        for x in range(9):
            xx, top = self.xy((x, 0))
            _, bottom = self.xy((x, 9))
            if x in (0, 8):
                c.create_line(xx, top, xx, bottom, fill="#839792")
            else:
                c.create_line(xx, top, xx, self.xy((x, 4))[1], fill="#839792")
                c.create_line(xx, self.xy((x, 5))[1], xx, bottom, fill="#839792")
            c.create_text(xx, bottom + min(s * .66, 34), text=chr(97 + x), fill=MUTED, font=("Segoe UI", 11))
        for y0, y1 in ((0, 2), (7, 9)):
            c.create_line(*self.xy((3, y0)), *self.xy((5, y1)), fill="#839792")
            c.create_line(*self.xy((5, y0)), *self.xy((3, y1)), fill="#839792")
        c.create_text(self.ox + s * 2, self.oy + s * 4.5, text="楚 河", font=("Microsoft YaHei UI", 14), fill=MUTED)
        c.create_text(self.ox + s * 6, self.oy + s * 4.5, text="汉 界", font=("Microsoft YaHei UI", 14), fill=MUTED)
        for owner, direction, cells in self.game.recon_marks(side):
            color = RED if owner == 0 else GREEN
            for pos in cells:
                x, y = self.xy(pos)
                vertical = direction in ("上", "下")
                dx, dy = (0, s * .43) if vertical else (s * .43, 0)
                c.create_line(x - dx, y - dy, x + dx, y + dy, fill=color, width=3, dash=(4, 3))
        for pos in self.game.smoke_cells(side) & visible:
            x, y = self.xy(pos)
            c.create_rectangle(x - s * .4, y - s * .4, x + s * .4, y + s * .4, fill="#b4bcc3", stipple="gray50", outline="")
        range_targets = self.game.selection_targets(self.selected, self.action == "followup") if self.action in ("move", "followup") and side in (None, self.game.current) else (set(), set())
        for p in self.game.pieces:
            if side is not None and p.side != side and (p.pos not in visible or p.hidden):
                continue
            x, y = self.xy(p.pos)
            r = s * .35
            color = RED if p.side == 0 else BLACK
            selected = self.selected == p.uid
            c.create_oval(x - r - 2, y - r + 2, x + r + 2, y + r + 6, fill="#c9d3d0", outline="")
            c.create_oval(x - r, y - r, x + r, y + r, fill=PANEL, outline=GREEN if selected else color, width=4 if selected else 2)
            key = f"{'red' if p.side == 0 else 'black'}_{'K' if p.kind == 'F' and side not in (None, p.side) else p.kind}"
            image = self.images.get(key)
            if image:
                factor = max(1, int(max(image.width(), image.height()) / max(1, s * .6)) + 1)
                if factor > 1:
                    scaled_key = (key, factor)
                    if scaled_key not in self.images:
                        self.images[scaled_key] = image.subsample(factor)
                    image = self.images[scaled_key]
                c.create_image(x, y, image=image)
            else:
                c.create_text(x, y, text=GLYPHS[p.side][p.kind], fill=color, font=("Microsoft YaHei UI", max(8, int(s * (.27 if self.game.ruleset == "tactics" else .32))), "bold"))
            if self.game.ruleset == "tactics":
                hp_text = f"{p.hp:g}"
                font_size = max(6, min(int(s*.17), int(s*.62/max(1, len(hp_text)))))
                badge = c.create_text(x-r, y+r, text=hp_text, anchor="center", fill=PANEL,
                                      font=("Segoe UI", font_size, "bold"), tags=(f"hp_{p.uid}",))
                box = c.bbox(badge)
                background = c.create_rectangle(box[0]-2, box[1], box[2]+2, box[3], fill=GREEN if p.hp > p.max_hp/2 else RED, outline="")
                c.tag_lower(background, badge)
                if p.equipment != "normal":
                    c.create_text(x+r, y-r, text="轻" if p.equipment == "light" else "重", fill=GREEN, font=("Microsoft YaHei UI", max(6, int(s*.14)), "bold"), tags=(f"equipment_{p.uid}",))
            if p.kind == "F" and side in (None, p.side):
                c.create_text(x + r, y - r, text="伪", fill=GREEN, font=("Microsoft YaHei UI", 10, "bold"))
            if p.hidden and side in (None, p.side):
                c.create_text(x - r, y - r, text="隐", fill=GREEN, font=("Microsoft YaHei UI", 10))
            remaining = max(0, p.ready_at - self.game.turns[p.side])
            if remaining and (p.kind != "F" or side in (None, p.side)):
                bx, by, br = x + r * .8, y + r * .8, min(9, max(5, s * .16))
                c.create_oval(bx - br, by - br, bx + br, by + br, fill=GREEN, outline=PANEL)
                c.create_text(bx, by, text=str(remaining-1) if remaining > 1 else "待", fill=PANEL, font=("Microsoft YaHei UI", max(6, int(br))), tags=(f"cooldown_{p.uid}",))
        for targets, tag in zip(range_targets, ("move_range", "attack_range")):
            for pos in targets:
                x, y = self.xy(pos)
                occupied = any(q.pos == pos and (q.side == side or side is None or (pos in visible and not q.hidden)) for q in self.game.pieces)
                r = s * (.41 if occupied else .13)
                c.create_rectangle(x-r, y-r, x+r, y+r, outline=RED, width=2, tags=(tag,))
        if self.first:
            x, y = self.xy(self.first)
            c.create_oval(x - s * .42, y - s * .42, x + s * .42, y + s * .42, outline=GREEN, width=3, dash=(3, 3))
        if self.game.pending_handoff:
            c.create_rectangle(0, 0, c.winfo_width(), c.winfo_height(), fill="#273339", outline="")

    def refresh(self):
        g = self.game
        if not g:
            return
        label = "红方 · 玩家1" if g.current == 0 else "黑方 · 玩家2"
        self.title.configure(text=f"{'战棋' if g.ruleset == 'tactics' else '普通'} · 第 {g.round} 轮\n{label}")
        self.score.configure(text=f"红方积分  {g.scores[0]}\n黑方积分  {g.scores[1]}")
        viewer = self.viewing_side()
        if viewer is None:
            self.points.configure(text=f"行动点 {g.ap} / {MAX_AP}\n部署点 红{g.deployment[0]} · 黑{g.deployment[1]}")
        else:
            self.points.configure(text=f"行动点 {g.ap} / {MAX_AP}\n己方部署点 {g.deployment[viewer]}")
        if g.ruleset == "tactics":
            self.points.configure(text=self.points.cget("text") + (f"\n军需 红{g.supplies[0]} · 黑{g.supplies[1]}" if viewer is None else f"\n己方军需点 {g.supplies[viewer]}"))
        p = g.by_id(self.selected)
        text = ""
        if p and (viewer is None or viewer == p.side):
            text = f"{NAMES[p.kind]} · {coord(p.pos)}\n攻击 {p.attack}   血量 {p.hp}/{p.max_hp}"
            if g.ruleset == "tactics":
                text = f"{NAMES[p.kind]} · {coord(p.pos)} · 等级{p.level}\n血量 {p.hp:g}/{p.max_hp:g}\n攻击 {p.attack:g}（当前{g.effective_attack(p):.1f}）\n反击防御 {p.defense:g}"
                if p.followup:
                    text += "\n可进行轻马攻击后移动"
            if p.skill_turn == g.turns[p.side]:
                text += "\n本回合技能已使用"
            remaining = max(0, p.ready_at - g.turns[p.side])
            if remaining:
                text += f"\n冷却 {remaining-1} 个己方回合" if remaining > 1 else "\n下一己方回合可用"
            if p.scout_bonus:
                text += f"\n随军侦察 +{p.scout_bonus}"
            if g.bombardment_cooling(p):
                text += "\n仅能使用1回合侦察"
            if g.recon_active(p):
                text += f"\n侦察：{p.recon} · 剩余{p.recon_until-g.turns[p.side]}回合"
            if g.ruleset == "tactics" and p.aimed:
                text += "\n已瞄准"
        self.detail.configure(text=text)
        self.deploy_button.configure(text="本回合禁止部署" if g.deploy_locked[g.current] else "取消部署" if self.action == "deploy" else "部署部队",
                                     state="disabled" if g.deploy_locked[g.current] else "normal")
        self.draw()
        if g.winner is not None and getattr(self, "shown_winner", None) != id(g):
            self.shown_winner = id(g)
            self.root.after(10, lambda: messagebox.showinfo("对局结束", f"{'红方' if g.winner == 0 else '黑方'}胜利\n{g.rating(g.winner)}\n败方：{g.rating(1-g.winner)}", parent=self.root))

    def enabled(self):
        return self.game and not self.game.pending_handoff and (self.game.mode != "ai" or self.game.current == 0) and (self.game.winner is None or self.game.mode == "debug")

    def hover_attack(self, event):
        self.preview.set("")
        if not self.enabled() or not self.selected or self.action not in ("move", "skill_target"):
            return
        dst = (round((event.x-self.ox)/self.cell), round((event.y-self.oy)/self.cell))
        try:
            p = self.game.by_id(self.selected)
            bombard = self.action == "skill_target" and p.kind == "C" and self.skill_number == 2
            skill_number = self.skill_number if self.action == "skill_target" else None
            if skill_number is not None:
                if not ((p.kind == "C" and skill_number == 2) or (p.kind == "R" and p.equipment == "heavy" and skill_number == 1) or (p.kind == "N" and skill_number == 1)):
                    return
                self.game.require_skill(p, skill_number)
            else:
                self.game.require(p, 3)
            values = self.game.damage_preview(self.selected, dst, bombard=bombard, skill_number=skill_number)
            def span(a, b):
                return f"{a:g}" if a == b else f"{a:g}–{b:g}"
            self.preview.set(f"预计伤害 {span(values['damage_min'],values['damage_max'])} · 预计反击 {span(values['counter_min'],values['counter_max'])}" + (" · 已计入护驾分担" if values["shared"] else "") + "（仅按可见信息）")
        except (RuleError, AttributeError, TypeError):
            pass

    def military_menu(self, feedback=""):
        if not self.enabled():
            return
        p = self.game.by_id(self.selected)
        if self.action != "management":
            self.reset_action()
        self.action = "management"
        if not p or p.side != self.game.current:
            self.action = "management_select"
            self.show_palette("军需管理", [], lambda value: None, "选择己方棋子")
            return
        g = self.game
        used = g.upgrades_used[p.side]
        own_half = home(p.side, p.pos)
        rate = g.healing_rate(p)
        options = [("普通升级 · 1军需", "upgrade", own_half and p.kind not in "KF" and used < 2 and g.supplies[p.side] >= 1, g.management_description(p, "upgrade")),
                   ("轻装 · 2军需", "light", own_half and p.kind not in "KF" and p.equipment != "light" and g.supplies[p.side] >= 2, g.management_description(p, "light")),
                   ("重装 · 2军需", "heavy", own_half and p.kind not in "KF" and p.equipment != "heavy" and g.supplies[p.side] >= 2, g.management_description(p, "heavy")),
                   ("回复一半", "half", p.hp < p.max_hp and g.supplies[p.side] > 0, f"回复最大血量的50%；当前每军需回复{rate:g}血"),
                   ("回满血", "full", p.hp < p.max_hp and g.supplies[p.side] > 0, "军需不足时按实际消耗补员")]
        def apply(value):
            description = g.management_description(p, value) if value in ("upgrade", "light", "heavy") else ""
            if value == "upgrade":
                fn = lambda: g.upgrade(p.uid)
            elif value in ("light", "heavy"):
                fn = lambda: g.equip(p.uid, value)
            else:
                fn = lambda: g.replenish(p.uid, value)
            if self.execute(fn):
                self.military_menu(self.status.get() + "\n" + description)
        context = f"{NAMES[p.kind]} · 等级{p.level}\n本方本回合普通升级 {used}/2次；等级无上限。"
        if not own_half:
            context += "\n升级和换装须回到己方棋盘。"
        self.show_palette("军需管理", options, apply, (feedback + "\n\n" if feedback else "") + context)

    def begin_followup(self):
        p = self.game.by_id(self.selected)
        if self.enabled() and self.game.winner is None and p and p.followup:
            self.reset_action()
            self.action = "followup"
            self.status.set("轻装马攻击完成，可以继续移动：选择上下左右空位；点选马的原位放弃移动")

    def reset_action(self):
        self.close_palette()
        self.action, self.skill_number, self.first = "move", None, None
        self.skill_options = {}

    def cancel_action(self, event=None):
        if self.action == "followup" and self.game:
            p = self.game.by_id(self.selected)
            if p and p.followup:
                self.game.followup_move(p.uid, p.pos)
        self.reset_action()
        if self.game and hasattr(self, "status"):
            self.status.set("行动已取消")
            self.refresh()

    def close_palette(self, redraw=True):
        if self.palette is not None and self.palette.winfo_exists():
            self.palette.destroy()
        self.palette, self.palette_inset = None, 0
        self.root.minsize(940, 720)
        self.palette_buttons = {}
        if redraw and self.game and hasattr(self, "canvas") and self.canvas.winfo_exists():
            self.draw()

    def position_palette(self, event=None):
        if event is not None and event.widget is not self.root:
            return
        if self.palette is None or not self.palette.winfo_exists():
            return
        width = 256
        outside = self.root.winfo_rootx() >= width + 12
        self.root.minsize(940 if outside else min(1120, max(940, self.root.winfo_screenwidth()-50)), 720)
        x = self.root.winfo_rootx() - width - 12 if outside else self.canvas.winfo_rootx() + 4
        y = self.canvas.winfo_rooty() + 8
        height = max(240, min(620, self.canvas.winfo_height() - 16, self.root.winfo_screenheight() - y - 60))
        self.palette.geometry(f"{width}x{height}+{max(0,x)}+{max(25,y)}")
        inset = 0 if outside else width + 20
        if inset != self.palette_inset:
            self.palette_inset = inset
            self.draw()

    def show_palette(self, title, options, select, context=""):
        if self.palette is None or not self.palette.winfo_exists():
            self.palette = tk.Toplevel(self.root)
            self.palette.transient(self.root)
            self.palette.resizable(False, False)
            self.palette.configure(bg=BG)
            self.palette.protocol("WM_DELETE_WINDOW", self.cancel_action)
            self.palette.bind("<Button-3>", self.cancel_action)
            self.palette_title = ttk.Label(self.palette, font=("Microsoft YaHei UI", 13, "bold"), wraplength=230)
            self.palette_title.pack(fill="x", padx=12, pady=(12, 6))
            self.palette_options = ttk.Frame(self.palette)
            self.palette_options.pack(fill="x", padx=12, pady=(0, 6))
            scroll = tk.Canvas(self.palette, bg=BG, highlightthickness=0)
            self.palette_scroll = scroll
            scroll.pack(side="top", fill="both", expand=True, padx=10)
            bar = ttk.Scrollbar(scroll, orient="vertical", command=scroll.yview)
            bar.pack(side="right", fill="y")
            scroll.configure(yscrollcommand=bar.set)
            self.palette_body = ttk.Frame(scroll)
            window = scroll.create_window((0, 0), window=self.palette_body, anchor="nw")
            self.palette_body.bind("<Configure>", lambda event: scroll.configure(scrollregion=scroll.bbox("all")))
            scroll.bind("<Configure>", lambda event: scroll.itemconfigure(window, width=event.width - 18))
            self.palette.bind("<MouseWheel>", lambda event: scroll.yview_scroll(-int(event.delta/120), "units"))
            ttk.Button(self.palette, text="取消", command=self.cancel_action).pack(fill="x", padx=12, pady=10)
        self.palette.title(title)
        self.palette_scroll.yview_moveto(0)
        self.palette_title.configure(text=title)
        for widget in self.palette_options.winfo_children():
            widget.destroy()
        for widget in self.palette_body.winfo_children():
            widget.destroy()
        self.palette_buttons = {}
        if context:
            ttk.Label(self.palette_body, text=context, wraplength=218, foreground=MUTED).pack(fill="x", pady=(0, 10))
        for label, value, available, description in options:
            button = ttk.Button(self.palette_body, text=label, command=lambda v=value: select(v), state="normal" if available else "disabled")
            button.pack(fill="x", pady=(6, 2))
            self.palette_buttons[value] = button
            if description:
                ttk.Label(self.palette_body, text=description, wraplength=218, foreground=MUTED, font=("Microsoft YaHei UI", 10)).pack(fill="x", pady=(0, 8))
        self.position_palette()
        self.root.after_idle(self.position_palette)
        self.refresh()

    def execute(self, fn):
        try:
            result = fn()
            self.status.set(result or "完成")
            self.refresh()
            return True
        except (RuleError, ValueError, TypeError) as exc:
            self.status.set(str(exc))
            return False

    def click(self, event):
        if not self.enabled():
            return
        x = round((event.x - self.ox) / self.cell)
        y = round((event.y - self.oy) / self.cell)
        dst = (x, y)
        if dst not in ALL:
            return
        g = self.game
        p = g.at(dst)
        viewer = self.viewing_side()
        if p and viewer is not None and p.side != viewer and (p.hidden or dst not in g.vision(viewer)):
            p = None
        if self.action == "edit":
            self.edit_square(dst)
        elif self.action == "followup":
            if self.selected and self.execute(lambda: g.followup_move(self.selected, dst)):
                self.reset_action()
        elif self.action == "deploy":
            if self.deploy_kind is None:
                self.status.set("请选择部署棋种")
                return
            if self.execute(lambda: g.deploy(self.deploy_kind, dst, waive_ap=self.deploy_waiver.get())):
                if g.deploy_locked[g.current]:
                    self.reset_action()
                else:
                    self.update_deployment_options()
        elif self.action == "skill_target":
            selected = g.by_id(self.selected)
            if not selected:
                self.reset_action()
                return
            double = (selected.kind == "N" and self.skill_number == 0) or (selected.kind == "C" and self.skill_number == 3)
            if double and self.first is None:
                if not g.legal_base(selected, dst, g.known(selected.side)) or (p is not None):
                    self.status.set("请选择第一步合法的空位")
                    return
                self.first = dst
                self.status.set("选择第二步落点")
            else:
                options = dict(self.skill_options, dst=dst)
                if self.first:
                    options["first"] = self.first
                if self.execute(lambda: g.skill(self.selected, self.skill_number, **options)):
                    self.reset_action()
                    self.begin_followup()
        elif p and p.side == g.current:
            self.selected = p.uid
            if self.action == "skill_select":
                self.pick_skill()
            elif self.action in ("management_select", "management"):
                self.military_menu()
            elif self.action == "move":
                self.begin_followup()
        elif self.selected and self.action == "move":
            if self.execute(lambda: g.move(self.selected, dst)):
                self.begin_followup()
        self.refresh()

    def choice(self, title, options):
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.transient(self.root)
        dialog.resizable(False, False)
        x, y = self.root.winfo_rootx(), self.root.winfo_rooty()
        dialog.geometry(f"+{max(0,x-260) if x >= 260 else x+20}+{max(25,y+70)}")
        answer = []
        frame = ttk.Frame(dialog, padding=18)
        frame.pack(fill="both", expand=True)
        columns = 2 if len(options) > 10 else 1
        for index, (label, value, available) in enumerate(options):
            def select(v=value):
                answer.append(v)
                dialog.destroy()
            ttk.Button(frame, text=label, command=select, state="normal" if available else "disabled").grid(row=index // columns, column=index % columns, sticky="ew", padx=3, pady=3)
        ttk.Button(frame, text="取消", command=dialog.destroy).grid(row=(len(options)+columns-1)//columns, column=0, columnspan=columns, sticky="ew", pady=(12, 0))
        dialog.grab_set()
        self.root.wait_window(dialog)
        return answer[0] if answer else None

    def deploy_menu(self):
        if not self.enabled():
            return
        if self.action == "deploy":
            self.reset_action()
            self.status.set("部署已取消")
        else:
            if self.game.deploy_locked[self.game.current]:
                self.status.set("本回合部署失败过，不能再部署部队")
                return
            self.reset_action()
            self.action, self.deploy_kind = "deploy", None
            self.deploy_waiver = tk.BooleanVar(value=False)
            def select(kind):
                self.deploy_kind = kind
                self.status.set(f"选择{NAMES[kind]}的部署位置")
            self.show_palette("部署部队", [(NAMES[k], k, False, "") for k in "PRNCBA"], select)
            box = ttk.LabelFrame(self.palette_options, text="行动点减免", padding=6)
            box.pack(fill="x")
            self.waiver_checkbox = ttk.Checkbutton(box, text="额外部署点换免行动点", variable=self.deploy_waiver, command=self.update_deployment_options)
            self.waiver_checkbox.pack(anchor="w")
            self.waiver_label = ttk.Label(box, wraplength=218, font=("Microsoft YaHei UI", 10))
            self.waiver_label.pack(anchor="w", pady=(3, 0))
            self.update_deployment_options()
        self.refresh()

    def update_deployment_options(self):
        waive = self.deploy_waiver.get()
        text = f"本次减免额外 +{self.game.deployment_waivers[self.game.current]+1}部署点" if waive else "普通部署消耗1行动点"
        count = sum(p.side == self.game.current and p.kind == "P" for p in self.game.pieces)
        text += f"\n在场兵{count}个，兵附加费+{self.game.pawn_deployment_surcharge()}点"
        self.waiver_label.configure(text=text)
        for kind, button in self.palette_buttons.items():
            total, ap_cost, _ = self.game.deployment_quote(kind, waive)
            available = self.game.deployment[self.game.current] >= total and self.game.ap >= ap_cost and not self.game.deploy_locked[self.game.current]
            button.configure(text=f"{NAMES[kind]} · {total}部署点\n{ap_cost}行动点", state="normal" if available else "disabled")

    def skill_mode(self):
        if not self.enabled():
            return
        self.reset_action()
        self.action = "skill_select"
        p = self.game.by_id(self.selected)
        if p and p.side == self.game.current:
            self.pick_skill()
        else:
            self.status.set("选择使用技能的己方棋子")
            self.show_palette("使用技能", [], lambda value: None, "选择己方棋子")

    def pick_skill(self):
        p = self.game.by_id(self.selected)
        if not p:
            return
        choices = []
        for n, name in enumerate(self.game.tactical_skill_names(p)):
            cost = self.game.tactical_skill_cost(p, n)
            available = self.game.skill_ready(p, n)
            if p.kind == "A" and n == 1:
                available &= not self.game.disguise_used[p.side] and self.game.deployment[p.side] >= 10 and not self.game.deploy_locked[p.side]
            if p.kind in "KF" and n == 0:
                available &= self.game.deployment[p.side] >= 2 and not self.game.deploy_locked[p.side]
            description = self.game.tactical_skill_description(p, n)
            if p.kind == "C" and n == 0 and self.game.bombardment_cooling(p):
                description = "轰击落空恢复期间，仅可使用本回合有效的1回合侦察；无法移动、吃子或使用其他技能。"
            choices.append((f"{name} · {cost}行动点", n, available, description))
        self.show_palette(f"{NAMES[p.kind]} · 选择技能", choices, self.activate_skill)

    def perform_skill(self, number, **options):
        if self.execute(lambda: self.game.skill(self.selected, number, **options)):
            self.reset_action()
            self.refresh()

    def activate_skill(self, n):
        p = self.game.by_id(self.selected)
        if not p:
            return
        self.skill_number, self.skill_options = n, {}
        if (p.kind in "BA" and n == 0) or (p.kind == "P" and n == 1) or p.kind in "KF":
            self.perform_skill(n)
            return
        if p.kind == "C" and n == 0:
            if self.game.ruleset == "tactics":
                self.perform_skill(n, direction="上" if p.side == 0 else "下")
                return
            self.show_palette("侦察方向", [(d, d, True, "") for d in ("上", "下", "左", "右")],
                              lambda direction: self.perform_skill(n, direction=direction),
                              "本次侦察持续1个己方回合" if self.game.bombardment_cooling(p) else SKILL_INFO[p.kind][n])
            return
        if p.kind == "B" and n == 1:
            def select(kind):
                self.skill_options["kind"] = kind
                self.action = "skill_target"
                self.status.set("选择替死后的移动目标，或点击原位")
            self.show_palette("替死 · 选择棋种", [(f"{NAMES[k]} · {self.game.cost(k)}点", k,
                              self.game.deployment[p.side] >= self.game.cost(k), "") for k in "RNCBA"], select, SKILL_INFO[p.kind][n])
            return
        self.action = "skill_target"
        self.first = None
        self.status.set("选择技能目标" if not (p.kind == "C" and n == 1) else "选择烟雾区域左上角")
        self.refresh()

    def choose_transform(self, p, surcharge):
        return self.choice("选择升变棋子", [(f"{NAMES[k]} · {self.game.cost(k)+surcharge}点", k,
                                           self.game.deployment[p.side] >= self.game.cost(k)+surcharge) for k in "RNCBA"])

    def promote(self):
        if not self.enabled():
            return
        p = self.game.by_id(self.selected)
        if not p or p.side != self.game.current or p.kind != "P":
            self.status.set("请先选择己方兵")
            return
        self.reset_action()
        kind = self.choose_transform(p, 0 if home(p.side, p.pos) else 2)
        if kind:
            self.execute(lambda: self.game.promote(p.uid, kind))

    def end(self):
        if not self.enabled():
            return
        if self.execute(self.game.end_turn):
            self.selected = None
            self.reset_action()
            self.status.set("")
            self.refresh()
            if self.game.pending_handoff:
                self.handoff()
            elif self.game.mode == "ai":
                self.schedule_ai()

    def handoff(self):
        overlay = tk.Frame(self.root, bg="#273339")
        overlay.place(x=0, y=0, relwidth=1, relheight=1)
        tk.Label(overlay, text="回合交接", bg="#273339", fg="white", font=("Microsoft YaHei UI", 24, "bold")).pack(pady=(180, 30))
        player = self.game.current + 1
        def resume():
            self.game.pending_handoff = False
            overlay.destroy()
            self.status.set("")
            self.refresh()
        ttk.Button(overlay, text=f"玩家{player}继续游戏", command=resume).pack(ipadx=25, ipady=10)

    def schedule_ai(self):
        self.ai_steps = 0
        token = self.ai_token
        self.root.after(450, lambda: self.ai_tick(token))

    def ai_tick(self, token):
        if token != self.ai_token or not self.game or self.game.current != 1 or self.game.winner is not None:
            return
        self.ai_steps += 1
        action = choose_action(self.game) if self.ai_steps <= 12 else {"type": "end"}
        try:
            self.status.set(apply_action(self.game, action))
        except RuleError:
            self.game.end_turn()
            self.status.set("电脑结束回合")
        self.refresh()
        if self.game.current == 1 and self.game.winner is None:
            self.root.after(450, lambda: self.ai_tick(token))

    def save(self):
        if not self.game:
            return
        path = filedialog.asksaveasfilename(parent=self.root, initialdir=ROOT / "save", initialfile=datetime.now().strftime("game_%Y%m%d_%H%M%S.txt"), defaultextension=".txt", filetypes=[("游戏存档", "*.txt")])
        if path:
            try:
                self.game.save(path)
                self.status.set("游戏已保存")
            except OSError as exc:
                messagebox.showerror("保存失败", str(exc), parent=self.root)

    def load(self):
        path = filedialog.askopenfilename(parent=self.root, initialdir=ROOT / "save", filetypes=[("游戏存档", "*.txt")])
        if not path:
            return
        try:
            game = Game.load(path)
        except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
            messagebox.showerror("读取失败", str(exc), parent=self.root)
            return
        self.game = game
        self.build_board()

    def return_menu(self):
        if messagebox.askyesno("主菜单", "返回主菜单？未保存的进度将丢失。", parent=self.root):
            self.menu()

    def debug_tools(self, right):
        ttk.Separator(right).pack(fill="x", pady=10)
        row = ttk.Frame(right)
        row.pack(fill="x")
        for label, side in (("上帝", None), ("红方", 0), ("黑方", 1)):
            ttk.Button(row, text=label, command=lambda s=side: self.switch_view(s)).pack(side="left", expand=True, fill="x")
        row = ttk.Frame(right)
        row.pack(fill="x", pady=5)
        ttk.Button(row, text="编辑棋盘", command=self.editor).pack(side="left", expand=True, fill="x")
        ttk.Button(row, text="玩家数据", command=self.edit_resources).pack(side="left", expand=True, fill="x")
        row = ttk.Frame(right)
        row.pack(fill="x", pady=5)
        ttk.Button(row, text="清空", command=self.empty_board).pack(side="left", expand=True, fill="x")
        ttk.Button(row, text="测试残局", command=self.test_position).pack(side="left", expand=True, fill="x")

    def switch_view(self, side):
        self.view = side
        self.selected = None
        self.refresh()

    def editor(self):
        self.reset_action()
        self.action = "edit"
        self.edit_side, self.edit_kind = None, ""
        def select(choice):
            self.edit_side, self.edit_kind = choice
            self.status.set("选择编辑位置；可连续放置")
        self.show_palette("编辑棋盘", [(f"{'红方' if s == 0 else '黑方'} {NAMES[k]}", (s, k), True, "") for s in (0, 1) for k in KINDS]
                          + [("删除棋子", (-1, ""), True, "")], select)

    def edit_square(self, pos):
        if self.edit_side is None:
            self.status.set("请先选择棋子或删除工具")
            return
        target = self.game.at(pos)
        if target:
            self.game.pieces.remove(target)
        if self.edit_side != -1:
            self.game.add(self.edit_side, self.edit_kind, pos)
        self.game.winner = None
        self.selected = None
        self.refresh()

    def edit_resources(self):
        g = self.game
        dialog = tk.Toplevel(self.root)
        dialog.title("玩家与回合数据")
        dialog.transient(self.root)
        x, y = self.root.winfo_rootx(), self.root.winfo_rooty()
        dialog.geometry(f"+{max(0,x-260) if x >= 260 else x+20}+{max(25,y+70)}")
        frame = ttk.Frame(dialog, padding=16)
        frame.pack()
        specs = [("红方积分", g.scores[0]), ("黑方积分", g.scores[1]), ("红方部署点", g.deployment[0]),
                 ("黑方部署点", g.deployment[1]), ("轮数", g.round), ("当前玩家 1/2", g.current + 1), ("行动点 0–3", g.ap)]
        if g.ruleset == "tactics":
            specs += [("红方军需点", g.supplies[0]), ("黑方军需点", g.supplies[1])]
        variables = []
        for i, (label, value) in enumerate(specs):
            ttk.Label(frame, text=label).grid(row=i, column=0, sticky="w", pady=5)
            var = tk.StringVar(value=str(value))
            variables.append(var)
            ttk.Entry(frame, textvariable=var, width=12).grid(row=i, column=1)
        def apply():
            try:
                values = [int(v.get()) for v in variables]
                if any(v < 0 for v in values) or values[4] < 1 or values[5] not in (1, 2) or not 0 <= values[6] <= MAX_AP:
                    raise ValueError("数据超出范围")
                g.scores, g.deployment = values[:2], values[2:4]
                g.round, g.current, g.ap = values[4], values[5] - 1, values[6]
                if g.ruleset == "tactics":
                    g.supplies = values[7:9]
                g.turns = [g.round, g.round if g.current == 1 else g.round - 1]
                g.winner, g.pending_handoff = None, False
                g.deploy_locked = [False, False]
                g.deployment_waivers = [0, 0]
                g.upgrades_used = [0, 0]
                self.selected = None
                dialog.destroy()
                self.refresh()
            except ValueError as exc:
                messagebox.showerror("数据无效", str(exc), parent=dialog)
        ttk.Button(frame, text="应用", command=apply).grid(row=len(specs), column=0, columnspan=2, sticky="ew", pady=10)
        dialog.grab_set()

    def empty_board(self):
        if messagebox.askyesno("清空棋盘", "清空所有棋子？", parent=self.root):
            self.game.pieces.clear()
            self.game.winner = None
            self.selected = None
            self.refresh()

    def test_position(self):
        if any(sum(p.kind == "K" and p.side == s for p in self.game.pieces) != 1 for s in (0, 1)):
            self.status.set("测试残局需要双方各一个真将")
            return
        mode = self.choice("测试残局", [("本地双人", "local", True), ("与电脑对战", "ai", True)])
        if mode:
            self.game.mode = mode
            self.game.winner = None
            self.game.pending_handoff = False
            self.reset_action()
            self.build_board()


def main():
    (ROOT / "save").mkdir(exist_ok=True)
    (ROOT / "textures").mkdir(exist_ok=True)
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
