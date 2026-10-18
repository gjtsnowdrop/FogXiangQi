"""Exercise the desktop client and capture its own window for visual inspection."""
import sys
from pathlib import Path
from types import SimpleNamespace
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from game import App
from engine import ROOT, Game, SKILL_INFO


def main():
    from PIL import ImageGrab
    output = ROOT / "artifacts"
    output.mkdir(exist_ok=True)
    root = tk.Tk()
    errors = []
    root.report_callback_exception = lambda *args: errors.append(args)
    app = App(root)
    root.update()

    def capture(name):
        root.update()
        root.lift()
        root.update()
        ready = tk.BooleanVar(value=False)
        root.after(180, lambda: ready.set(True))
        root.wait_variable(ready)
        x, y = root.winfo_rootx(), root.winfo_rooty()
        ImageGrab.grab(bbox=(x, y, x + root.winfo_width(), y + root.winfo_height())).save(output / name)

    def click(pos):
        x, y = app.xy(pos)
        app.click(SimpleNamespace(x=x, y=y))
        root.update()

    capture("menu.png")
    app.start("local")
    root.update()
    capture("board.png")
    click((0, 6))
    click((0, 5))
    assert app.game.at((0, 5)).side == 0 and app.game.ap == 0
    app.end()
    root.update()
    assert app.game.pending_handoff
    capture("handoff.png")
    overlay = root.winfo_children()[-1]
    overlay.winfo_children()[-1].invoke()
    root.update()
    assert not app.game.pending_handoff and app.game.current == 1
    capture("black_view.png")

    app.start("debug")
    app.game.round = 4
    app.refresh()
    root.update()
    capture("debug.png")
    for size in ("940x720", "1280x800"):
        root.geometry(size)
        root.update()
        for widget in app.canvas.master.winfo_children():
            assert widget.winfo_y() + widget.winfo_height() <= app.canvas.master.winfo_height() + 2
        for item in app.canvas.find_all():
            if app.canvas.type(item) == "text":
                bounds = app.canvas.bbox(item)
                assert bounds[0] >= 0 and bounds[1] >= 0 and bounds[2] <= app.canvas.winfo_width() and bounds[3] <= app.canvas.winfo_height(), (size, bounds, app.canvas.winfo_width(), app.canvas.winfo_height(), app.cell, app.oy)
        capture(f"debug_{size}.png")
        app.sidebar_scroll.yview_moveto(1)
        root.update()
        last = app.sidebar_scroll.yview()[1]
        assert last >= .999, app.sidebar_scroll.yview()
        capture(f"debug_{size}_bottom.png")
        app.sidebar_scroll.yview_moveto(0)
    app.switch_view(0)
    root.update()
    capture("fog.png")
    app.action, app.edit_side, app.edit_kind = "edit", 0, "F"
    click((4, 8))
    assert app.game.at((4, 8)).kind == "F"
    app.game.save(output / "ui_test.txt")
    app.game = type(app.game).load(output / "ui_test.txt")
    app.build_board()
    root.update()
    assert app.game.at((4, 8)).kind == "F"

    root.geometry("940x720+300+40")
    root.update()
    app.editor()
    root.update()
    palette = app.palette
    assert palette.grab_current() is None
    assert palette.winfo_rootx() + palette.winfo_width() <= root.winfo_rootx()
    assert abs(palette.winfo_rooty() - app.canvas.winfo_rooty()) < 50
    previous_x = palette.winfo_rootx()
    root.geometry("940x720+330+55")
    root.update()
    assert abs(palette.winfo_rootx() - previous_x - 30) <= 2
    app.palette_buttons[(0, "R")].invoke()
    click((4, 8))
    assert app.game.at((4, 8)).kind == "R" and app.palette is palette
    app.palette_buttons[(1, "F")].invoke()
    click((4, 4))
    assert app.game.at((4, 4)).kind == "F" and app.palette is palette
    palette.event_generate("<Button-3>", x=20, y=20)
    root.update()
    assert app.palette is None and app.action == "move"

    def scenario():
        app.game = Game(mode="debug", round=7, turns=[7, 6], deployment=[10, 10])
        app.build_board()
        root.update()

    root.geometry("1120x800+25+20")
    root.update()
    scenario()
    app.deploy_menu()
    root.update()
    palette = app.palette
    assert app.palette_inset > 0
    assert app.ox - app.cell / 2 > app.palette_inset
    app.palette_buttons["R"].invoke()
    root.geometry("940x720+25+20")
    root.update()
    app.draw()
    for item in app.canvas.find_all():
        if app.canvas.type(item) == "text":
            bounds = app.canvas.bbox(item)
            assert bounds[0] >= app.palette_inset and bounds[2] <= app.canvas.winfo_width() and bounds[3] <= app.canvas.winfo_height(), bounds
    click((0, 9))
    assert app.palette is palette and app.game.ap == 2
    click((8, 9))
    assert app.palette is palette and app.game.deployment[0] == 0
    assert app.game.ap == 1
    assert "disabled" in app.palette_buttons["R"].state()
    root.geometry("1120x800+25+20")
    root.update()
    capture("persistent_deploy.png")
    root.event_generate("<Button-3>", x=20, y=20)
    root.update()
    assert app.palette is None

    scenario()
    app.game.ap = 0
    app.deploy_menu()
    root.update()
    assert "disabled" in app.palette_buttons["P"].state()
    app.waiver_checkbox.invoke()
    assert "disabled" not in app.palette_buttons["P"].state()
    assert "2部署点" in app.palette_buttons["P"].cget("text")
    app.palette_buttons["P"].invoke()
    click((0, 9))
    assert app.game.ap == 0 and app.game.deployment[0] == 8
    assert "3部署点" in app.palette_buttons["P"].cget("text")
    click((1, 9))
    assert app.game.deployment[0] == 5 and app.game.deployment_waivers[0] == 2
    assert "4部署点" in app.palette_buttons["P"].cget("text")
    capture("deployment_waiver.png")
    app.cancel_action()

    scenario()
    app.game.add(1, "R", (0, 6))
    app.deploy_menu()
    root.update()
    app.palette_buttons["N"].invoke()
    click((0, 8))
    assert app.game.deploy_locked[0] and app.palette is None
    assert "disabled" in app.deploy_button.state()

    scenario()
    pawn = app.game.add(0, "P", (3, 8))
    app.selected = pawn.uid
    app.skill_mode()
    root.update()
    palette = app.palette
    assert SKILL_INFO["P"][0] in [w.cget("text") for w in app.palette_body.winfo_children() if w.winfo_class() == "TLabel"]
    app.palette_buttons[0].invoke()
    click((3, 6))
    assert app.palette is palette
    click((4, 8))
    assert app.palette is None and app.game.by_id(pawn.uid).pos == (4, 8)

    scenario()
    cannon = app.game.add(0, "C", (3, 7))
    app.game.add(0, "P", (3, 5))
    app.game.add(1, "R", (3, 0))
    app.selected = cannon.uid
    app.skill_mode()
    root.update()
    assert len(app.palette_buttons) == 3
    app.palette_buttons[2].invoke()
    capture("persistent_skill.png")
    click((3, 0))
    assert app.palette is None and app.game.by_id(cannon.uid).pos == (3, 7)
    assert app.game.deployment[1] == 11

    scenario()
    cannon = app.game.add(0, "C", (3, 7))
    app.selected = cannon.uid
    app.skill_mode()
    root.update()
    palette = app.palette
    app.palette_buttons[0].invoke()
    root.update()
    assert app.palette is palette and len(app.palette_buttons) == 4
    app.palette_buttons["上"].invoke()
    root.update()
    assert app.palette is None and app.game.by_id(cannon.uid).recon == "上"

    scenario()
    advisor = app.game.add(0, "A", (3, 9))
    pawn = app.game.add(0, "P", (4, 7))
    app.selected = advisor.uid
    app.skill_mode()
    root.update()
    app.palette_buttons[2].invoke()
    click(pawn.pos)
    assert app.palette is None and app.game.by_id(pawn.uid).scout_bonus

    app.game.end_turn()
    app.game.end_turn()
    app.selected = advisor.uid
    app.skill_mode()
    root.update()
    app.palette_buttons[2].invoke()
    before = app.game.deployment[0]
    click(pawn.pos)
    assert app.game.by_id(pawn.uid).scout_bonus == 2 and app.game.deployment[0] == before - 1

    scenario()
    fake = app.game.add(0, "F", (4, 9), delay=1)
    app.game.add(1, "R", (4, 7))
    app.switch_view(0)
    assert app.canvas.find_withtag(f"cooldown_{fake.uid}")
    app.switch_view(1)
    assert fake.pos in app.game.vision(1)
    assert not app.canvas.find_withtag(f"cooldown_{fake.uid}")
    capture("fake_enemy_view.png")

    scenario()
    cannon = app.game.add(0, "C", (3, 7))
    app.game.add(0, "P", (3, 5))
    app.game.skill(cannon.uid, 2, dst=(3, 0))
    app.game.end_turn()
    app.game.end_turn()
    app.selected = cannon.uid
    app.skill_mode()
    root.update()
    assert "disabled" not in app.palette_buttons[0].state()
    assert "disabled" in app.palette_buttons[1].state() and "disabled" in app.palette_buttons[2].state()
    capture("bombardment_recovery.png")
    app.palette_buttons[0].invoke()
    app.palette_buttons["上"].invoke()
    assert app.game.by_id(cannon.uid).recon_until == app.game.turns[0] + 1

    scenario()
    app.game.round = 6
    cannon = app.game.add(0, "C", (3, 7))
    app.selected = cannon.uid
    app.skill_mode()
    root.update()
    assert "disabled" in app.palette_buttons[2].state()
    app.cancel_action()

    scenario()
    bishop = app.game.add(0, "B", (2, 9))
    friend = app.game.add(0, "K", (4, 7))
    app.selected = bishop.uid
    app.skill_mode()
    root.update()
    assert len(app.palette_buttons) == 3
    app.palette_buttons[2].invoke()
    click(friend.pos)
    assert app.game.by_id(friend.uid).pos == (2, 9)
    assert app.game.by_id(bishop.uid).pos == (4, 7)
    assert app.palette is None

    scenario()
    cannon = app.game.add(0, "C", (0, 8))
    app.game.add(0, "R", (4, 7))
    enemy = app.game.add(1, "P", (4, 6))
    friend = app.game.add(0, "P", (5, 6))
    app.game.skill(cannon.uid, 1, dst=(4, 5))
    app.switch_view(0)
    assert enemy.pos not in app.game.vision(0)
    assert friend.pos in app.game.vision(0)
    texts = [app.canvas.itemcget(item, "text") for item in app.canvas.find_all() if app.canvas.type(item) == "text"]
    assert "卒" not in texts and "兵" in texts
    capture("smoke_cover.png")
    for _ in range(4):
        app.game.end_turn()
    app.refresh()
    texts = [app.canvas.itemcget(item, "text") for item in app.canvas.find_all() if app.canvas.type(item) == "text"]
    assert "卒" in texts

    scenario()
    for x in range(7):
        app.game.add(0, "P", (x, 9))
    app.deploy_menu()
    root.update()
    assert "5部署点" in app.palette_buttons["P"].cget("text")
    app.waiver_checkbox.invoke()
    assert "6部署点" in app.palette_buttons["P"].cget("text")
    app.waiver_checkbox.invoke()
    app.palette_buttons["P"].invoke()
    click((8, 9))
    assert app.game.deployment[0] == 5
    assert "7部署点" in app.palette_buttons["P"].cget("text")
    assert "disabled" in app.palette_buttons["P"].state()
    assert "在场兵8个" in app.waiver_label.cget("text")
    capture("pawn_population_cost.png")
    app.cancel_action()
    app.editor()
    root.update()
    capture("persistent_editor.png")
    app.cancel_action()
    assert not errors, errors
    root.destroy()
    print("UI tests passed, including smoke hiding enemies from outside observers and restoring visibility on expiry.")


if __name__ == "__main__":
    main()
