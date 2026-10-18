"""Exercise the tactical desktop flows against the real Tk widgets."""
import copy
from pathlib import Path
import sys
import tkinter as tk
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import Game, ROOT
from game import App


def main():
    from PIL import ImageGrab
    root = tk.Tk()
    errors = []
    root.report_callback_exception = lambda *args: errors.append(args)
    root.attributes("-topmost", True)
    app = App(root)
    output = ROOT / "artifacts"
    output.mkdir(exist_ok=True)
    try:
        def update():
            root.update()

        def click(pos):
            x, y = app.xy(pos)
            app.click(SimpleNamespace(x=x, y=y))
            update()

        def capture(name):
            update()
            ready = tk.BooleanVar(value=False)
            root.after(180, lambda: ready.set(True))
            root.wait_variable(ready)
            x, y = root.winfo_rootx(), root.winfo_rooty()
            ImageGrab.grab(bbox=(x, y, x+root.winfo_width(), y+root.winfo_height())).save(output/name)

        def scenario():
            app.game = Game(mode="debug", ruleset="tactics", fog_enabled=False, round=7, turns=[7, 6], supplies=[20, 20], deployment=[20, 20])
            app.build_board()
            update()
            return app.game

        app.setup_game("debug")
        app.setup_rules.set("tactics")
        app.setup_fog.set(False)
        capture("tactics_setup.png")
        app.setup_begin.invoke()
        update()
        assert app.game.mode == "debug" and app.game.ruleset == "tactics" and not app.game.fog_enabled
        assert app.game.supplies == [10, 10]
        capture("tactics_board.png")

        g = scenario()
        p = g.add(0, "P", (4, 7))
        other = g.add(0, "P", (6, 7))
        app.selected = None
        app.military_menu()
        assert app.action == "management_select"
        click(p.pos)
        app.military_menu()
        update()
        palette = app.palette
        app.palette_buttons["upgrade"].invoke()
        app.palette_buttons["upgrade"].invoke()
        assert "disabled" in app.palette_buttons["upgrade"].state()
        assert app.palette is palette and p.level == 2
        click(other.pos)
        assert "disabled" in app.palette_buttons["upgrade"].state()
        click(p.pos)
        app.palette_buttons["heavy"].invoke()
        assert p.max_hp == 16 and p.equipment == "heavy"
        assert app.canvas.find_withtag(f"equipment_{p.uid}")
        hp_item = app.canvas.find_withtag(f"hp_{p.uid}")[0]
        assert app.canvas.itemcget(hp_item, "text") == "16"
        x, y = app.xy(p.pos)
        hx, hy = app.canvas.coords(hp_item)
        assert hx < x and hy > y
        descriptions = "\n".join(w.cget("text") for w in app.palette_body.winfo_children() if w.winfo_class() == "TLabel")
        assert "特殊效果" in descriptions and "血量上限" in descriptions and "本方本回合普通升级 2/2" in descriptions
        p.hp, g.supplies[0] = 1, 1
        app.military_menu()
        app.palette_buttons["full"].invoke()
        assert p.hp == 5 and g.supplies[0] == 0
        capture("tactics_management.png")
        for size in ("940x720", "1280x800"):
            root.geometry(size)
            update()
            for item in app.canvas.find_all():
                if app.canvas.type(item) == "text":
                    box = app.canvas.bbox(item)
                    assert box[0] >= 0 and box[2] <= app.canvas.winfo_width() and box[3] <= app.canvas.winfo_height(), (size, box)
            capture(f"tactics_{size}.png")
        app.cancel_action()

        g = scenario()
        p = g.add(0, "R", (4, 7))
        target = g.add(1, "N", (4, 3))
        app.selected = p.uid
        app.refresh()
        assert app.canvas.find_withtag("move_range") and app.canvas.find_withtag("attack_range")
        before = copy.deepcopy(g)
        x, y = app.xy(target.pos)
        for _ in range(4):
            app.hover_attack(SimpleNamespace(x=x, y=y))
        assert "预计伤害" in app.preview.get() and g == before
        capture("tactics_damage_preview.png")
        click(target.pos)
        assert g.by_id(target.uid) is None and g.ap == 0

        g = scenario()
        p = g.add(0, "C", (0, 7))
        g.equip(p.uid, "light")
        app.selected = p.uid
        app.skill_mode()
        update()
        assert len(app.palette_buttons) == 4
        app.palette_buttons[3].invoke()
        click((3, 7))
        assert app.first == (3, 7)
        click((3, 4))
        assert g.by_id(p.uid).pos == (3, 4) and g.ap == 1 and app.palette is None

        g = scenario()
        p = g.add(0, "N", (1, 9))
        g.equip(p.uid, "light")
        target = g.add(1, "R", (3, 8))
        target.hp = target.max_hp = 40
        app.selected = p.uid
        app.refresh()
        click(target.pos)
        assert p.followup and app.action == "followup" and "点选" in app.status.get()
        click((2, 9))
        assert p.pos == (2, 9) and not p.followup
        assert app.action == "move"

        g = scenario()
        p = g.add(0, "N", (1, 9))
        g.equip(p.uid, "light")
        target = g.add(1, "R", (3, 8))
        target.hp = target.max_hp = 40
        click(p.pos)
        click(target.pos)
        assert app.action == "followup"
        capture("tactics_horse_followup.png")
        click(p.pos)
        assert not p.followup and p.pos == (1, 9) and app.action == "move"

        g = scenario()
        p = g.add(0, "N", (1, 9))
        g.equip(p.uid, "light")
        target = g.add(1, "R", (3, 8))
        target.hp = target.max_hp = 40
        app.selected = p.uid
        app.skill_mode()
        app.palette_buttons[1].invoke()
        click(target.pos)
        assert app.action == "followup" and g.by_id(p.uid).followup
        click((2, 9))
        assert g.by_id(p.uid).pos == (2, 9) and not g.by_id(p.uid).followup

        g = scenario()
        fake = g.add(0, "F", (4, 8))
        friend = g.add(0, "P", (4, 7))
        friend.hp = 1
        app.selected = fake.uid
        app.skill_mode()
        update()
        app.palette_buttons[0].invoke()
        assert g.by_id(fake.uid) is None and g.by_id(friend.uid).hp == 9

        app.setup_game("local", "normal")
        app.setup_fog.set(False)
        app.setup_begin.invoke()
        update()
        assert app.game.ruleset == "normal" and not app.game.fog_enabled
        assert all(p.max_hp == 1 for p in app.game.pieces)
        assert not errors, errors
        print("Tactical UI passed: setup, fog choice, persistent management, equipment, upgrades, partial healing, damage preview, maneuver, horse followup, sacrifice and two sizes.")
    finally:
        root.destroy()


if __name__ == "__main__":
    main()
