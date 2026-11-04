"""Courtside pages. The rules engine still runs if this process has no network."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from flask import Flask, abort, flash, g, jsonify, redirect, render_template, request, send_file, url_for

from volleyball_coach.dictionary import METRICS, OPTIONAL_RALLY_FIELDS, REQUIRED_RALLY_FIELDS, SAMPLE_RULES, TERMS
from volleyball_coach.drills import acceptance_drills
from volleyball_coach.lineup import build_card, build_suggestion, legal_sub_options, validate_pairs
from volleyball_coach.match import (
    MatchError,
    apply_correction,
    apply_manual_rotation,
    apply_mode,
    apply_point,
    apply_sub,
    last_reversible_seq,
    replay,
)
from volleyball_coach.model import PASS_QUALITY, Pair, Player, Rules, ServePlan, TeamPlan
from volleyball_coach.quick import (
    PASS_RESULTS,
    RECEPTION_EDITABLE,
    QuickError,
    action_winner,
    apply_tap,
    board_for,
    describe,
    draft_rally,
    pad_for,
    pause_lines,
    reception_editable,
    build_digest,
    record_cell,
    sheet_after,
)
from volleyball_coach.report import build_report, execution_of
from volleyball_coach.summary_pdf import render_summary_pdf
from volleyball_coach.seed import MENS_TEAM_ID
from volleyball_coach.store import Store, ability_label, locked_pairs_of, new_id, now, plan_for_match

FONT_PATH = Path(__file__).resolve().parents[1] / "fonts" / "NotoSansSC-Regular.otf"
COURT_ORDER = (4, 3, 2, 5, 6, 1)
ROLES = (
    ("outside", "主攻"),
    ("middle", "副攻"),
    ("setter", "二传"),
    ("opposite", "接应"),
    ("libero", "自由人"),
    ("other", "待定"),
    ("defender", "防守"),
    ("flex", "主攻或接应"),
)
ROLE_LABEL = dict(ROLES)


def create_app(db_path: str | Path | None = None) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["DB_PATH"] = str(db_path or Path(__file__).resolve().parent / "data" / "coach.db")
    app.secret_key = "volleyball-coach-local"
    app.jinja_env.filters["ability"] = ability_label

    @app.context_processor
    def inject_token():
        return {"new_token": new_id}

    @app.teardown_appcontext
    def close_store(_exc):
        store = g.pop("store", None)
        if store is not None:
            store.close()

    def store() -> Store:
        if "store" not in g:
            g.store = Store(app.config["DB_PATH"])
        return g.store

    def team_or_404(team_id: str) -> TeamPlan:
        plan = store().load_plan(team_id)
        if plan is None:
            abort(404)
        return plan

    def match_bundle(match_id: str):
        match = store().get_match(match_id)
        if match is None:
            abort(404)
        plan = plan_for_match(store(), match)
        locked = locked_pairs_of(match)
        events = store().events_for(match_id)
        try:
            state, points = replay(plan, events, locked, match["mode"])
        except MatchError as exc:
            abort(409, description=str(exc))
        if state is None:
            abort(409, description="这场比赛还没有开局记录。")
        return match, plan, state, points, events

    @app.get("/assets/noto-sans-sc.otf")
    def font_file():
        if not FONT_PATH.exists():
            abort(404)
        return send_file(FONT_PATH, mimetype="font/otf")

    @app.get("/")
    def home():
        remembered = store()
        cards = []
        for row in remembered.list_live_matches():
            match = remembered.get_match(row["id"])
            if match is None:
                continue
            plan = plan_for_match(remembered, match)
            state, _points = replay(plan, remembered.events_for(match["id"]), locked_pairs_of(match), match["mode"])
            cards.append(
                {
                    "id": match["id"],
                    "team_name": row["team_name"],
                    "opponent": match["opponent"],
                    "set_index": state.set_index if state else 1,
                    "score_us": state.score_us if state else 0,
                    "score_them": state.score_them if state else 0,
                }
            )
        plans = []
        for team in remembered.list_teams():
            loaded = remembered.load_plan(team["id"])
            if loaded:
                plans.append(loaded)
        return render_template(
            "home.html",
            teams=remembered.list_teams(),
            plans=plans,
            mens_id=MENS_TEAM_ID,
            live_matches=cards,
            roles=ROLES,
        )

    @app.post("/teams")
    def create_team():
        name = request.form.get("name", "").strip()
        if not name:
            flash("先写队名。", "error")
            return redirect(url_for("home"))
        rules = Rules()
        plan = TeamPlan(
            team_id=new_id("team"),
            name=name,
            rules=rules,
            notes=(request.form.get("notes") or "").strip(),
        )
        store().insert_plan(plan)
        raw_names = (request.form.get("names") or "").replace("，", " ").replace(",", " ")
        for name in [piece.strip() for piece in raw_names.split() if piece.strip()]:
            store().save_player(plan.team_id, Player(id=new_id("p"), name=name, role="other"))
        if request.form.get("preset") == "local_special":
            flash("名单是空的，没有复制男排球员。", "ok")
        else:
            flash("球队已单独建好。名单没有从男排复制。", "ok")
        if request.form.get("start") == "1":
            ready = store().load_plan(plan.team_id)
            if ready and ready.players:
                match_id = store().create_match(ready, "", "light", set(), 1, "them", require_lineup=False)
                return redirect(url_for("live", match_id=match_id))
        return redirect(url_for("team_page", team_id=plan.team_id))

    @app.post("/teams/<team_id>/roster")
    def save_roster(team_id: str):
        plan = team_or_404(team_id)
        title = (request.form.get("team_name") or "").strip()
        if title and title != plan.name:
            store().rename_team(plan.team_id, title)
            plan.name = title
        allowed = {code for code, _label in ROLES}
        ids = request.form.getlist("player_id")
        names = request.form.getlist("player_name")
        roles = request.form.getlist("player_role")
        for player_id, raw_name, role in zip(ids, names, roles):
            player = plan.players.get(player_id)
            name = raw_name.strip()
            if player is None or not name:
                continue
            player.name = name
            player.role = role if role in allowed else "other"
            store().save_player(plan.team_id, player)
        for raw_name, role in zip(request.form.getlist("new_name"), request.form.getlist("new_role")):
            name = raw_name.strip()
            if not name:
                continue
            store().save_player(
                plan.team_id,
                Player(id=new_id("p"), name=name, role=role if role in allowed else "other"),
            )
        if request.form.get("start") == "1":
            ready = store().load_plan(plan.team_id)
            if ready is None or not ready.players:
                flash("先写至少一个名字，再开始记。", "error")
                return redirect(url_for("home"))
            match_id = store().create_match(ready, "", "light", set(), 1, "them", require_lineup=False)
            return redirect(url_for("live", match_id=match_id))
        flash("名字和位置已记下。开始记球时沿用这份名单。", "ok")
        return redirect(url_for("home"))

    @app.get("/teams/<team_id>")
    def team_page(team_id: str):
        plan = team_or_404(team_id)
        return render_template(
            "team.html",
            plan=plan,
            abilities=store().abilities_for(team_id),
            matches=store().list_matches(team_id),
            roles=ROLES,
            ability_labels=ability_label,
        )

    @app.post("/teams/<team_id>/rules")
    def save_rules(team_id: str):
        plan = team_or_404(team_id)
        try:
            rules = rules_from_form(request.form)
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("team_page", team_id=plan.team_id))
        store().save_rules(plan.team_id, rules)
        store().save_team_meta(
            plan.team_id,
            (request.form.get("notes") or "").strip(),
            {
                "in_system": (request.form.get("call_in") or "全开").strip(),
                "half": (request.form.get("call_half") or "两翼").strip(),
                "out": (request.form.get("call_out") or "高球").strip(),
            },
        )
        flash("规则已保存。已经开始的比赛仍用开场时的规则。", "ok")
        return redirect(url_for("team_page", team_id=plan.team_id))

    @app.post("/teams/<team_id>/players")
    def add_player(team_id: str):
        plan = team_or_404(team_id)
        try:
            player = player_from_form(new_id("p"), request.form)
            ensure_slot_free(plan, player)
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("team_page", team_id=plan.team_id))
        store().save_player(plan.team_id, player)
        flash(f"{player.name} 已加入名单。", "ok")
        return redirect(url_for("team_page", team_id=plan.team_id))

    @app.post("/teams/<team_id>/players/<player_id>")
    def edit_player(team_id: str, player_id: str):
        plan = team_or_404(team_id)
        if player_id not in plan.players:
            abort(404)
        try:
            player = player_from_form(player_id, request.form)
            ensure_slot_free(plan, player)
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("team_page", team_id=plan.team_id))
        store().save_player(plan.team_id, player)
        flash(f"{player.name} 已更新。", "ok")
        return redirect(url_for("team_page", team_id=plan.team_id))

    @app.post("/teams/<team_id>/abilities")
    def add_ability(team_id: str):
        plan = team_or_404(team_id)
        player_id = request.form.get("player_id", "")
        skill = (request.form.get("skill") or "").strip()
        label = request.form.get("label") or "unknown"
        if player_id not in plan.players or not skill:
            flash("能力记录要选球员，并写明项目。", "error")
            return redirect(url_for("team_page", team_id=plan.team_id))
        try:
            store().save_ability(player_id, skill, label)
        except ValueError as exc:
            flash(str(exc), "error")
        else:
            flash("能力记录已保存。没有样本的项目保持尚未验证。", "ok")
        return redirect(url_for("team_page", team_id=plan.team_id))

    @app.post("/teams/<team_id>/pairs")
    def add_pair(team_id: str):
        plan = team_or_404(team_id)
        try:
            pair = pair_from_form(new_id("pair"), request.form, plan)
            proposed = [(item.a, item.b) for item in plan.pairs] + [(pair.a, pair.b)]
            error = validate_pairs(proposed)
            if error:
                raise ValueError(error)
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("team_page", team_id=plan.team_id))
        store().save_pair(plan.team_id, pair)
        flash("配对已保存。一个人不能再对应第二个替换对象。", "ok")
        return redirect(url_for("team_page", team_id=plan.team_id))

    @app.post("/teams/<team_id>/pairs/<pair_id>")
    def edit_pair(team_id: str, pair_id: str):
        plan = team_or_404(team_id)
        if not any(item.id == pair_id for item in plan.pairs):
            abort(404)
        try:
            pair = pair_from_form(pair_id, request.form, plan)
            proposed = [(pair.a, pair.b) if item.id == pair_id else (item.a, item.b) for item in plan.pairs]
            error = validate_pairs(proposed)
            if error:
                raise ValueError(error)
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("team_page", team_id=plan.team_id))
        store().save_pair(plan.team_id, pair)
        flash("配对已更新。已经开场的比赛仍用开场时锁定的那一对。", "ok")
        return redirect(url_for("team_page", team_id=plan.team_id))

    @app.post("/teams/<team_id>/pairs/<pair_id>/delete")
    def delete_pair(team_id: str, pair_id: str):
        team_or_404(team_id)
        store().delete_pair(team_id, pair_id)
        flash("配对已删除。", "ok")
        return redirect(url_for("team_page", team_id=team_id))

    @app.post("/teams/<team_id>/delete")
    def delete_team(team_id: str):
        plan = team_or_404(team_id)
        if request.form.get("confirm") != "1":
            flash("没有确认，这队还在。", "error")
            return redirect(url_for("home"))
        store().delete_team(plan.team_id)
        flash(f"「{plan.name}」和这队的比赛已经删除。", "ok")
        return redirect(url_for("home"))

    @app.post("/teams/<team_id>/roster/remove")
    def remove_roster_player(team_id: str):
        return _remove_player(team_id, (request.form.get("player_id") or "").strip())

    @app.post("/teams/<team_id>/players/<player_id>/delete")
    def delete_player(team_id: str, player_id: str):
        return _remove_player(team_id, player_id)

    def _remove_player(team_id: str, player_id: str):
        plan = team_or_404(team_id)
        player = plan.players.get(player_id)
        if player is None:
            abort(404)
        back = request.form.get("next") or "home"
        match_id = (request.form.get("match_id") or "").strip()
        if request.form.get("confirm") != "1":
            flash("没有确认，球员还在名单里。", "error")
        elif store().delete_player(plan.team_id, player_id):
            flash(f"{player.name} 已从名单去掉。已经记过的比赛仍留着当时的名字。", "ok")
        if back == "team":
            return redirect(url_for("team_page", team_id=plan.team_id))
        if back == "live" and match_id:
            return redirect(url_for("live", match_id=match_id, sheet="more"))
        return redirect(url_for("home"))

    @app.post("/teams/<team_id>/abilities/<int:ability_id>/delete")
    def delete_ability(team_id: str, ability_id: int):
        team_or_404(team_id)
        if request.form.get("confirm") != "1":
            flash("没有确认，这条观察还在。", "error")
        elif not store().delete_ability(team_id, ability_id):
            abort(404)
        else:
            flash("这条观察已删除。", "ok")
        return redirect(url_for("team_page", team_id=team_id))

    @app.get("/teams/<team_id>/board")
    def board(team_id: str):
        plan = team_or_404(team_id)
        locked = {pair.key() for pair in plan.pairs if pair.status == "confirmed"}
        cards = [build_card(plan, rotation, {}, locked) for rotation in range(1, 7)]
        return render_template("board.html", plan=plan, cards=cards, court_order=COURT_ORDER, locked=locked)

    @app.post("/teams/<team_id>/serve")
    def save_serve(team_id: str):
        plan = team_or_404(team_id)
        try:
            serve = serve_from_form(request.form)
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(request.referrer or url_for("board", team_id=plan.team_id))
        store().save_serve(plan.team_id, serve)
        flash(f"R{serve.rotation} 的发球目标已保存。没有证据时就保持暂无对手证据。", "ok")
        return redirect(request.referrer or url_for("board", team_id=plan.team_id))

    @app.get("/teams/<team_id>/quicksheet")
    def quicksheet(team_id: str):
        plan = team_or_404(team_id)
        locked = {pair.key() for pair in plan.pairs if pair.status == "confirmed"}
        cards = [build_card(plan, rotation, {}, locked) for rotation in range(1, 7)]
        return render_template("quicksheet.html", plan=plan, cards=cards)

    @app.post("/teams/<team_id>/starters")
    def save_starters(team_id: str):
        plan = team_or_404(team_id)
        assigned: dict[str, int] = {}
        for slot in range(1, 7):
            player_id = (request.form.get(f"slot_{slot}") or "").strip()
            if not player_id:
                continue
            if player_id not in plan.players:
                flash("首发要从这支队的名单里选。", "error")
                return _starters_redirect(plan.team_id)
            if player_id in assigned:
                flash("同一个人不能占两个槽。", "error")
                return _starters_redirect(plan.team_id)
            assigned[player_id] = slot
        for player in plan.players.values():
            player.base_slot = assigned.get(player.id)
            store().save_player(plan.team_id, player)
        if len(assigned) == 6:
            flash("六个首发槽已记下。", "ok")
        else:
            flash("已保存。没排满也能开始记。要跟踪轮次时再补齐六个槽。", "ok")
        return _starters_redirect(plan.team_id)

    @app.get("/teams/<team_id>/matches/new")
    def new_match(team_id: str):
        plan = team_or_404(team_id)
        return render_template("match_new.html", plan=plan)

    @app.post("/teams/<team_id>/matches")
    def start_match(team_id: str):
        plan = team_or_404(team_id)
        track = request.form.get("track_rotation") == "on"
        if track and len(plan.base_order()) != 6:
            flash("要跟踪轮次，先把六个首发槽选满。不勾选就能直接记。", "error")
            return redirect(url_for("new_match", team_id=plan.team_id))
        try:
            rotation = int(request.form.get("rotation", "1"))
            serving = request.form.get("serving", "")
            mode = request.form.get("mode", "plan")
            if rotation not in range(1, 7) or serving not in ("us", "them") or mode not in ("plan", "light"):
                raise ValueError("开场要选轮次、发球方，以及预案或轻记录。")
            chosen = set(request.form.getlist("pair_id"))
            selected = [(pair.a, pair.b) for pair in plan.pairs if pair.id in chosen]
            error = validate_pairs(selected)
            if error:
                raise ValueError(error)
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("new_match", team_id=plan.team_id))
        match_id = store().create_match(
            plan,
            request.form.get("opponent", ""),
            mode,
            {frozenset(pair) for pair in selected},
            rotation,
            serving,
            require_lineup=track,
        )
        flash("开场阵容已记下。换人要再确认一次，轮次不会自动把人换上场。", "ok")
        return redirect(url_for("live", match_id=match_id))

    @app.post("/teams/<team_id>/matches/quick")
    def quick_start(team_id: str):
        plan = team_or_404(team_id)
        if not plan.players:
            flash("先写至少一个名字，再开始记。", "error")
            return redirect(url_for("team_page", team_id=plan.team_id))
        match_id = store().create_match(
            plan,
            request.form.get("opponent", ""),
            "light",
            set(),
            1,
            "them",
            require_lineup=False,
        )
        return redirect(url_for("live", match_id=match_id))

    @app.get("/matches/<match_id>")
    def live(match_id: str):
        match, plan, state, _points, events = match_bundle(match_id)
        card = build_card(plan, state.rotation, state.overrides, state.locked_pairs)
        rallies = store().rallies_for(match_id)
        sample = confirmed_serve_samples(rallies, state.rotation, card.serve.target_label)
        suggestion = build_suggestion(plan, state, sample)
        subs = []
        for out_id, in_id in legal_sub_options(plan, state):
            warning = ""
            try:
                nxt = apply_sub(plan, state, out_id, in_id)
                warning = nxt.conflicts[0] if nxt.conflicts else ""
            except MatchError as exc:
                warning = str(exc)
            subs.append(
                {
                    "out": out_id,
                    "in": in_id,
                    "label": f"{plan.name_of(in_id)} 换 {plan.name_of(out_id)}",
                    "warning": warning,
                }
            )
        unlocked = [pair for pair in plan.pairs if pair.key() not in state.locked_pairs]
        bookmarks = [event for event in events if event["type"] == "bookmark"]
        scope = request.args.get("scope") or "set"
        if scope not in ("set", "last10", "match"):
            scope = "set"
        names = {player_id: player.name for player_id, player in plan.players.items()}
        open_rally = store().open_quick_rally(match_id)
        open_actions = store().actions_for_rally(open_rally["id"]) if open_rally else []
        quick_rallies = store().quick_rallies(match_id)
        quick_actions = store().quick_actions(match_id)
        last = store().last_scored_rally(match_id)
        last_actions = store().actions_for_rally(last["id"]) if last else []
        tracking = True
        serving_confirmed = True
        for event in events:
            if event["type"] == "set_start":
                tracking = bool(event["payload"].get("require_lineup", True))
                serving_confirmed = bool(event["payload"].get("serving_confirmed", True))
        sheet = request.args.get("sheet") or ""
        if sheet not in ("pass", "attack", "serve", "opp", "more"):
            sheet = "serve" if state.serving == "us" and serving_confirmed else "pass"
        view = request.args.get("view") or ""
        players = sorted(plan.players.values(), key=lambda player: (not player.receive_primary, player.name))
        court_ids: list[str] = []
        for event in events:
            if event["type"] == "set_start":
                court_ids = [player_id for player_id in (event["payload"].get("court") or []) if player_id in plan.players]
        desk = _desk_rows(players, set(court_ids))
        server_id = ""
        if tracking and state.serving == "us":
            server_id = state.occupants.get(1) or ""
        elif state.serving == "us":
            for rally in reversed(quick_rallies):
                if rally["status"] not in ("scored", "open") or rally.get("serving") != "us":
                    continue
                serves = [
                    action
                    for action in quick_actions
                    if action["rally_id"] == rally["id"] and action["kind"] == "serve" and action.get("player_id")
                ]
                if serves:
                    server_id = serves[-1]["player_id"]
                if rally["status"] == "scored":
                    break
        if not serving_confirmed and not tracking:
            serve_label = "发球未记"
        elif state.serving == "us":
            serve_label = "我方发球"
        else:
            serve_label = "对方发球"
        return render_template(
            "live.html",
            match=match,
            plan=plan,
            state=state,
            card=card,
            suggestion=suggestion,
            subs=subs,
            unlocked=unlocked,
            court_order=COURT_ORDER,
            bookmarks=bookmarks[-3:],
            scope=scope,
            pad=pad_for(plan, state, open_rally, open_actions),
            open_rally=open_rally,
            board=board_for(quick_rallies, quick_actions, names, scope=scope, set_index=state.set_index),
            rally_text={
                rally["id"]: describe(
                    [action for action in quick_actions if action["rally_id"] == rally["id"]],
                    names,
                )
                for rally in quick_rallies
                if rally["status"] == "scored"
            },
            last_rally=last,
            last_story=describe(last_actions, names) if last else "",
            last_edit=reception_editable(last_actions),
            tracking=tracking,
            serving_confirmed=serving_confirmed,
            serve_label=serve_label,
            sheet=sheet,
            view=view,
            players=players,
            desk=desk,
            role_labels=ROLE_LABEL,
            court_ids=court_ids,
            court_names="、".join(plan.name_of(player_id) for player_id in court_ids),
            touch_counts=_touch_counts(open_actions),
            server_id=server_id,
            server_name=names.get(server_id, ""),
            lines=pause_lines(board_for(quick_rallies, quick_actions, names, scope=scope, set_index=state.set_index)),
        )

    @app.post("/matches/<match_id>/point")
    def post_point(match_id: str):
        match, plan, state, _points, _events = match_bundle(match_id)
        if match["status"] != "live":
            flash("本场已结束。比分如果记错了，用校正，不要继续往下加。", "error")
            return redirect(url_for("live", match_id=match_id))
        winner = request.form.get("winner", "")
        try:
            apply_point(plan, state, winner)
        except MatchError as exc:
            flash(str(exc), "error")
            return redirect(url_for("live", match_id=match_id))
        remembered = store()
        rally = remembered.open_quick_rally(match_id) or draft_rally(match_id, state)
        existing = remembered.actions_for_rally(rally["id"]) if rally.get("id") else []
        rally = dict(rally)
        rally["status"] = "scored"
        rally["winner"] = winner
        rally["phase"] = "done"
        rally["completeness"] = "complete" if existing else "score_only"
        remembered.persist_tap(match_id, new_id("t"), rally, [], winner=winner)
        return redirect(url_for("live", match_id=match_id))

    @app.post("/matches/<match_id>/quick")
    def post_quick(match_id: str):
        match, plan, state, _points, events = match_bundle(match_id)
        scope = request.form.get("scope") or "set"
        if scope not in ("set", "last10", "match"):
            scope = "set"
        target = url_for("live", match_id=match_id, scope=scope)
        if match["status"] != "live":
            flash("本场已结束。比分如果记错了，用校正，不要继续往下加。", "error")
            return redirect(target)
        tap = request.form.get("tap") or ""
        value = (request.form.get("value") or "").strip()
        token = (request.form.get("token") or "").strip() or new_id("t")
        remembered = store()

        def respond(sheet: str, message: str, category: str = "ok"):
            if request.headers.get("X-Requested-With") == "fetch":
                _match, fresh_plan, fresh_state, _points, _events = match_bundle(match_id)
                fresh_names = {player_id: player.name for player_id, player in fresh_plan.players.items()}
                last_touch = remembered.latest_action(match_id)
                story = ""
                if last_touch:
                    story = describe(remembered.actions_for_rally(last_touch["rally_id"]), fresh_names)
                open_rally = remembered.open_quick_rally(match_id)
                open_actions = remembered.actions_for_rally(open_rally["id"]) if open_rally else []
                return jsonify(
                    {
                        "ok": category != "error",
                        "score_us": fresh_state.score_us if fresh_state else 0,
                        "score_them": fresh_state.score_them if fresh_state else 0,
                        "serving": fresh_state.serving if fresh_state else "",
                        "sheet": sheet,
                        "last": story,
                        "message": message,
                        "synced": True,
                        "open": bool(open_rally),
                        "counts": _touch_counts(open_actions),
                    }
                )
            if message:
                flash(message, category)
            return redirect(url_for("live", match_id=match_id, scope=scope, sheet=sheet))

        if tap == "undo_touch":
            try:
                remembered.conn.execute(
                    "INSERT INTO op_tokens (token, match_id, created_at) VALUES (?, ?, ?)",
                    (token, match_id, now()),
                )
            except Exception:
                remembered.conn.rollback()
                return respond("pass", "")
            action = remembered.latest_action(match_id)
            if action is None:
                remembered.conn.commit()
                return respond("pass", "没有可以撤销的记录。", "error")
            rally = remembered.rally_by_id(action["rally_id"])
            earlier = [item for item in remembered.actions_for_rally(action["rally_id"]) if item["id"] != action["id"]]
            remembered.void_action(action["id"])
            if (
                rally
                and rally["status"] == "scored"
                and rally.get("point_seq")
                and action_winner(action)
                and not any(action_winner(item) for item in earlier)
            ):
                remembered.append_event(match_id, "undo", {"target_seq": rally["point_seq"]}, commit=False)
                remembered.reopen_rally(rally["id"])
            remembered.conn.commit()
            return respond("pass", "已撤销这一笔。上一笔还在。")
        if tap == "mark_line":
            from volleyball_coach.quick import OPP_LINES

            if value not in OPP_LINES:
                return respond("opp", "线路不在可选范围内。", "error")
            remembered.mark_line(match_id, value)
            return respond("opp", "线路已补在这一球上，比分没动。")
        if tap == "cell":
            kind = (request.form.get("kind") or "").strip()
            player_id = (request.form.get("player") or "").strip()
            start = (request.form.get("start") or "").strip()
            line = (request.form.get("line") or "").strip()
            tag = (request.form.get("tag") or "").strip()
            confirmed = True
            for event in events:
                if event["type"] == "set_start":
                    confirmed = bool(event["payload"].get("serving_confirmed", True))
            implied = "them" if kind == "pass" else "us" if kind == "serve" else None
            if implied and not confirmed and state.score_us == 0 and state.score_them == 0:
                state.serving = implied
                remembered.update_latest_set_start(match_id, serving=implied, serving_confirmed=True)
                remembered.conn.commit()
            rally = remembered.open_quick_rally(match_id) or draft_rally(match_id, state)
            try:
                updated, new_actions, winner = record_cell(
                    rally,
                    kind=kind,
                    result=value,
                    player_id=player_id,
                    start=start,
                    line=line,
                    tag=tag,
                )
            except QuickError as exc:
                return respond(request.form.get("sheet") or "pass", str(exc), "error")
            if winner:
                try:
                    apply_point(plan, state, winner)
                except MatchError as exc:
                    return respond("pass", str(exc), "error")
            saved = remembered.persist_tap(match_id, token, updated, new_actions, winner=winner)
            sheet = sheet_after(kind, value, state.serving)
            if not saved:
                return respond(sheet, "")
            return respond(sheet, "已得分 · 撤销" if winner else "已记")
        if tap == "edit_quality":
            if value not in PASS_RESULTS:
                flash("接发质量只能改成到位、半到位、不到位、直接失分或没看清。", "error")
                return redirect(target)
            action_id = request.form.get("action_id") or ""
            last = remembered.last_scored_rally(match_id)
            actions = remembered.actions_for_rally(last["id"]) if last else []
            action = next((item for item in actions if item["id"] == action_id), None)
            if action is None or reception_editable(actions) is None or reception_editable(actions)["id"] != action_id:
                if action and action["kind"] == "serve" and action["result"] not in RECEPTION_EDITABLE:
                    flash("发球得分或发球失误改了就会改比分。要改这一球，先撤销再重记。", "error")
                else:
                    flash("上一球没有可以改的接发质量。", "error")
                return redirect(target)
            if action["kind"] == "serve" and value not in RECEPTION_EDITABLE:
                flash("发球得分或发球失误改了就会改比分。要改这一球，先撤销再重记。", "error")
                return redirect(target)
            if remembered.edit_reception(match_id, token, action_id, value):
                flash("接发质量已改。比分和轮次没动。", "ok")
            return redirect(target)
        if tap == "repair":
            last = remembered.last_scored_rally(match_id)
            if last is None:
                flash("还没有上一球可以补。", "error")
                return redirect(target)
            player_id = (request.form.get("player") or "").strip()
            if value not in ("kill", "error", "blocked", "in_play", "count") or not player_id:
                flash("补记要选攻手和这一下的结果。", "error")
                return redirect(target)
            implied = {"kill": "us", "error": "them", "blocked": "them"}.get(value)
            saved = remembered.attach_action(
                match_id,
                token,
                last["id"],
                {
                    "side": "us",
                    "player_id": player_id,
                    "kind": "attack",
                    "result": value,
                    "count_only": 1 if value == "count" else 0,
                    "tag": "",
                },
            )
            if not saved:
                return redirect(target)
            if implied and implied != last["winner"]:
                flash("这一下已经补在上一球。比分没有加。结果和当时的得分方不一致，数字旁边能看到。", "ok")
            else:
                flash("已补在上一球，比分没有再加。", "ok")
            return redirect(target)
        rally = remembered.open_quick_rally(match_id) or draft_rally(match_id, state)
        prior = remembered.actions_for_rally(rally["id"]) if rally.get("id") else []
        try:
            updated, new_actions, winner = apply_tap(rally, tap, value)
        except QuickError as exc:
            flash(str(exc), "error")
            return redirect(target)
        if tap == "score" and not prior and not new_actions:
            updated["completeness"] = "score_only"
        elif tap == "flag_score":
            updated["completeness"] = "pending"
        if winner:
            try:
                apply_point(plan, state, winner)
            except MatchError as exc:
                flash(str(exc), "error")
                return redirect(target)
        saved = remembered.persist_tap(match_id, token, updated, new_actions, winner=winner)
        if saved and winner:
            flash("已得分 · 撤销", "ok")
        return redirect(target)

    @app.post("/matches/<match_id>/players")
    def add_match_player(match_id: str):
        _match, plan, _state, _points, _events = match_bundle(match_id)
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("先写名字。", "error")
            return redirect(url_for("live", match_id=match_id))
        store().save_player(plan.team_id, Player(id=new_id("p"), name=name, role="other"))
        flash(f"{name} 已加入名单，这场就能记。", "ok")
        return redirect(url_for("live", match_id=match_id, sheet="more"))

    @app.post("/matches/<match_id>/sub")
    def post_sub(match_id: str):
        match, plan, state, _points, _events = match_bundle(match_id)
        if match["status"] != "live":
            flash("本场已结束，不再记新的换人。", "error")
            return redirect(url_for("live", match_id=match_id))
        out_id = request.form.get("out", "")
        in_id = request.form.get("in", "")
        try:
            apply_sub(plan, state, out_id, in_id)
        except MatchError as exc:
            flash(str(exc), "error")
            return redirect(url_for("live", match_id=match_id))
        store().append_event(
            match_id,
            "sub",
            {
                "out": out_id,
                "in": in_id,
                "out_name": plan.name_of(out_id),
                "in_name": plan.name_of(in_id),
                "rotation": state.rotation,
                "set_index": state.set_index,
            },
        )
        flash(f"已确认 {plan.name_of(in_id)} 上场，{plan.name_of(out_id)} 下场。", "ok")
        return redirect(url_for("live", match_id=match_id))

    @app.post("/matches/<match_id>/undo")
    def post_undo(match_id: str):
        _match, _plan, _state, _points, events = match_bundle(match_id)
        target = last_reversible_seq(events)
        if target is None:
            flash("没有可以撤销的操作。开场记录会保留。", "error")
            return redirect(url_for("live", match_id=match_id))
        undone = next(event for event in events if event["seq"] == target)
        store().append_event(match_id, "undo", {"target_seq": target})
        if undone["type"] == "point":
            store().void_rally_for_point(match_id, target)
        flash("已撤销上一步。", "ok")
        return redirect(url_for("live", match_id=match_id))

    @app.post("/matches/<match_id>/rotation")
    def post_rotation(match_id: str):
        match, plan, state, _points, _events = match_bundle(match_id)
        if match["status"] != "live":
            flash("本场已结束。", "error")
            return redirect(url_for("live", match_id=match_id))
        try:
            rotation = int(request.form.get("rotation", ""))
            apply_manual_rotation(plan, state, rotation)
        except (MatchError, ValueError):
            flash("轮次要选 R1 到 R6。", "error")
            return redirect(url_for("live", match_id=match_id))
        store().append_event(match_id, "manual_rotation", {"rotation": rotation})
        flash("轮次已改。比分链停在这里，不会用漏掉的分去猜过程。", "ok")
        return redirect(url_for("live", match_id=match_id))

    @app.post("/matches/<match_id>/mode")
    def post_mode(match_id: str):
        match, plan, state, _points, _events = match_bundle(match_id)
        mode = request.form.get("mode", "")
        try:
            apply_mode(state, mode)
        except MatchError as exc:
            flash(str(exc), "error")
            return redirect(url_for("live", match_id=match_id))
        store().append_event(match_id, "mode", {"mode": mode})
        store().set_match_mode(match_id, mode)
        flash("已换成预案模式。" if mode == "plan" else "已换成轻记录。每分点一下得分方即可。", "ok")
        return redirect(url_for("live", match_id=match_id))

    @app.get("/matches/<match_id>/correct")
    def correct_form(match_id: str):
        match, plan, state, _points, _events = match_bundle(match_id)
        return render_template("correct.html", match=match, plan=plan, state=state)

    @app.post("/matches/<match_id>/correct")
    def post_correct(match_id: str):
        _match, plan, state, _points, _events = match_bundle(match_id)
        try:
            rotation = int(request.form.get("rotation", ""))
            serving = request.form.get("serving", "")
            score_us = int(request.form.get("score_us", ""))
            score_them = int(request.form.get("score_them", ""))
            occupants = {}
            for slot in range(1, 7):
                player_id = request.form.get(f"slot_{slot}", "")
                if player_id not in plan.players:
                    raise ValueError("六个槽位都要选这支球队里的人。")
                occupants[slot] = player_id
            apply_correction(
                plan,
                state,
                rotation=rotation,
                serving=serving,
                occupants_by_slot=occupants,
                score_us=score_us,
                score_them=score_them,
            )
        except (MatchError, ValueError) as exc:
            flash(str(exc), "error")
            return redirect(url_for("correct_form", match_id=match_id))
        store().append_event(
            match_id,
            "correct",
            {
                "rotation": rotation,
                "serving": serving,
                "score_us": score_us,
                "score_them": score_them,
                "occupants": {str(slot): player_id for slot, player_id in occupants.items()},
            },
        )
        flash("已按你确认的发球队员、轮次和六人建立新状态。中间漏掉的分没有被猜出来。", "ok")
        return redirect(url_for("live", match_id=match_id))

    @app.post("/matches/<match_id>/bookmark")
    def post_bookmark(match_id: str):
        tag = request.form.get("tag", "")
        if tag not in ("接发", "进攻", "拦防"):
            flash("书签只能标接发、进攻或拦防。", "error")
            return redirect(url_for("live", match_id=match_id))
        store().append_event(match_id, "bookmark", {"tag": tag, "note": (request.form.get("note") or "").strip()})
        flash(f"已记下{tag}书签。", "ok")
        return redirect(url_for("live", match_id=match_id))

    @app.post("/matches/<match_id>/court")
    def save_court(match_id: str):
        _match, plan, _state, _points, _events = match_bundle(match_id)
        if request.form.get("clear") == "1":
            store().set_set_court(match_id, [])
            flash("这一局改回全队名单。", "ok")
        else:
            chosen = [player_id for player_id in request.form.getlist("player_id") if player_id in plan.players]
            store().set_set_court(match_id, chosen)
            if chosen:
                flash("这一局上场的人已记下。下一局可以再换。", "ok")
            else:
                flash("这一局没有勾人，格子里仍是全队。", "ok")
        sheet = request.form.get("sheet") or "attack"
        if sheet not in ("pass", "attack", "serve", "opp", "more"):
            sheet = "attack"
        return redirect(url_for("live", match_id=match_id, sheet=sheet))

    @app.post("/matches/<match_id>/next-set")
    def next_set(match_id: str):
        match, plan, state, _points, _events = match_bundle(match_id)
        try:
            rotation = int(request.form.get("rotation", ""))
            serving = request.form.get("serving", "")
            if rotation not in range(1, 7) or serving not in ("us", "them"):
                raise ValueError("新的一局要选轮次和发球方。")
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("live", match_id=match_id))
        locked = locked_pairs_of(match)
        if plan.rules.pair_lock_scope == "set":
            chosen = set(request.form.getlist("pair_id"))
            selected = [(pair.a, pair.b) for pair in plan.pairs if pair.id in chosen]
            error = validate_pairs(selected)
            if error:
                flash(error, "error")
                return redirect(url_for("live", match_id=match_id))
            locked = {frozenset(pair) for pair in selected}
            store().replace_locked_pairs(match_id, locked)
        require_lineup = True
        previous_court: list[str] = []
        for event in _events:
            if event["type"] == "set_start":
                require_lineup = bool(event["payload"].get("require_lineup", True))
                previous_court = [player_id for player_id in (event["payload"].get("court") or []) if player_id in plan.players]
        store().append_event(
            match_id,
            "set_start",
            {
                "rotation": rotation,
                "serving": serving,
                "set_index": state.set_index + 1,
                "mode": state.mode,
                "overrides": {},
                "require_lineup": require_lineup,
                "serving_confirmed": True,
                "court": list(previous_court),
            },
        )
        flash(f"第 {state.set_index + 1} 局。上一局上场的人先留着，换了谁再改勾选。", "ok")
        return redirect(url_for("live", match_id=match_id, court=1))

    @app.post("/matches/<match_id>/finish")
    def finish_match(match_id: str):
        match_bundle(match_id)
        store().set_match_status(match_id, "done")
        flash("本场已结束。下面是汇总，可以下载 PDF。", "ok")
        return redirect(url_for("summary_page", match_id=match_id))

    @app.post("/matches/<match_id>/delete")
    def delete_match(match_id: str):
        match = store().get_match(match_id)
        if match is None:
            abort(404)
        team_id = match["team_id"]
        if request.form.get("confirm") != "1":
            flash("没有确认，这场还在。", "error")
            return redirect(url_for("live", match_id=match_id))
        store().delete_match(match_id)
        flash("这场记录已删除。", "ok")
        if request.form.get("next") == "home":
            return redirect(url_for("home"))
        return redirect(url_for("team_page", team_id=team_id))

    @app.get("/matches/<match_id>/review")
    def review(match_id: str):
        match, plan, state, _points, events = match_bundle(match_id)
        card = build_card(plan, state.rotation, state.overrides, state.locked_pairs)
        lineup = [
            {"slot": slot, "player_id": state.occupants.get(slot), "name": plan.name_of(state.occupants.get(slot))}
            for slot in range(1, 7)
        ]
        bench = sorted(player_id for player_id in state.occupants.values() if player_id not in set(plan.base_order()))
        return render_template(
            "review.html",
            match=match,
            plan=plan,
            state=state,
            card=card,
            rallies=store().rallies_for(match_id),
            bookmarks=[event for event in events if event["type"] == "bookmark"],
            lineup=lineup,
            bench_ids=bench,
            bench_names=[plan.name_of(player_id) for player_id in bench],
            qualities=PASS_QUALITY,
            required_fields=REQUIRED_RALLY_FIELDS,
            optional_fields=OPTIONAL_RALLY_FIELDS,
        )

    @app.post("/matches/<match_id>/rallies")
    def add_rally(match_id: str):
        match, plan, state, _points, _events = match_bundle(match_id)
        try:
            fields = rally_from_form(request.form, state.set_index)
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("review", match_id=match_id))
        if request.form.get("attach_lineup") == "on":
            fields["lineup"] = [
                {"slot": slot, "player_id": state.occupants.get(slot), "name": plan.name_of(state.occupants.get(slot))}
                for slot in range(1, 7)
            ]
            fields["bench_ids"] = [plan.name_of(player_id) for player_id in state.occupants.values() if player_id not in set(plan.base_order())]
        else:
            fields["lineup"] = []
            fields["bench_ids"] = []
        fields["opponent"] = match["opponent"]
        store().add_rally(match_id, fields)
        flash("回合已保存。未知仍然是未知。", "ok")
        return redirect(url_for("review", match_id=match_id))

    @app.post("/matches/<match_id>/rallies/<int:rally_id>/delete")
    def remove_rally(match_id: str, rally_id: int):
        match_bundle(match_id)
        store().delete_rally(match_id, rally_id)
        flash("这条回合记录已删除。", "ok")
        return redirect(url_for("review", match_id=match_id))

    def _match_digest(match_id: str):
        match, plan, _state, _points, _events = match_bundle(match_id)
        names = {player_id: player.name for player_id, player in plan.players.items()}
        rallies = store().quick_rallies(match_id)
        actions = store().quick_actions(match_id)
        return match, plan, build_digest(rallies, actions, names)

    @app.get("/matches/<match_id>/summary")
    def summary_page(match_id: str):
        match, plan, digest = _match_digest(match_id)
        return render_template("summary.html", match=match, plan=plan, digest=digest)

    @app.get("/matches/<match_id>/summary.pdf")
    def summary_pdf(match_id: str):
        match, plan, digest = _match_digest(match_id)
        payload = render_summary_pdf(digest, team=plan.name, opponent=match["opponent"])
        filename = f"{plan.name}-数据汇总.pdf"
        return send_file(
            BytesIO(payload),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename,
        )

    @app.get("/matches/<match_id>/report")
    def report_page(match_id: str):
        match, _plan, state, points, events = match_bundle(match_id)
        report = build_report(
            rallies=store().rallies_for(match_id),
            events=events,
            points=points,
            history_gap=state.history_gap,
            opponent=match["opponent"],
        )
        return render_template("report.html", match=match, report=report, state=state)

    @app.get("/matches/<match_id>/report.json")
    def report_json(match_id: str):
        match, _plan, state, points, events = match_bundle(match_id)
        rallies = store().rallies_for(match_id)
        report = build_report(
            rallies=rallies,
            events=events,
            points=points,
            history_gap=state.history_gap,
            opponent=match["opponent"],
        )
        payload = {
            "match_id": match_id,
            "team_id": match["team_id"],
            "opponent": match["opponent"] or None,
            "exported_at": now(),
            "opponent_rotation": None,
            "report": report,
            "rallies": [
                {
                    "id": rally["id"],
                    "set_number": rally["set_number"],
                    "rotation": rally["rotation"],
                    "serving_side": rally["serving_side"],
                    "winner": rally["winner"],
                    "pass_quality": rally["pass_quality"],
                    "server_label": rally["server_label"] or None,
                    "target_type": rally["target_type"] or None,
                    "target_label": rally["target_label"] or None,
                    "actual_receiver": rally["actual_receiver"] or None,
                    "actual_zone": rally["actual_zone"] or None,
                    "lineup": rally["lineup"],
                    "bench": rally["bench_ids"],
                    "video_timestamp": rally["video_timestamp"] or None,
                    "sample_scope": rally["sample_scope"],
                    "note": rally["note"] or None,
                    "execution": execution_of(rally),
                }
                for rally in rallies
            ],
        }
        return jsonify(payload)

    @app.get("/dictionary")
    def dictionary():
        return render_template(
            "dictionary.html",
            terms=TERMS,
            metrics=METRICS,
            samples=SAMPLE_RULES,
            required_fields=REQUIRED_RALLY_FIELDS,
            optional_fields=OPTIONAL_RALLY_FIELDS,
        )

    @app.get("/drills")
    def drills():
        results = acceptance_drills()
        return render_template("drills.html", results=results, passed=sum(item["passed"] for item in results))

    return app


def _touch_counts(actions: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for action in actions:
        if action.get("voided"):
            continue
        kind = action.get("kind") or ""
        if kind not in ("attack", "pass", "serve", "block", "defense"):
            continue
        key = f"{kind}:{action.get('player_id') or ''}"
        counts[key] = counts.get(key, 0) + 1
    return counts


def _desk_rows(players: list[Player], court_ids: set[str] | None = None) -> dict[str, list[Player]]:
    """On-court names come first. Position only suggests an order, not a slot number."""

    def pass_key(player: Player) -> tuple:
        band = 0 if player.receive_primary else 1
        role = {"outside": 0, "libero": 1, "opposite": 2, "middle": 3, "setter": 4}.get(player.role, 5)
        return (band, role, player.name)

    def attack_key(player: Player) -> tuple:
        role = {"outside": 0, "flex": 0, "opposite": 1, "middle": 2, "setter": 3, "defender": 5, "libero": 6}.get(player.role, 4)
        return (role, player.name)

    on_court = [player for player in players if player.id in court_ids] if court_ids else list(players)
    bench = [player for player in players if court_ids and player.id not in court_ids]
    passing = sorted(on_court, key=pass_key)
    hitting = sorted(on_court, key=attack_key)
    if court_ids:
        attack_main = [player for player in hitting if player.role != "libero"] or hitting
        attack_rest = [player for player in hitting if player.role == "libero"]
        pass_main = passing
        pass_rest: list[Player] = []
        serve_main = [player for player in on_court if player.role != "libero"] or list(on_court)
        serve_rest = [player for player in on_court if player.role == "libero"]
    else:
        attack_main = hitting[:4]
        attack_rest = hitting[4:]
        pass_main = passing[:3]
        pass_rest = passing[3:]
        serve_main = sorted((player for player in players if player.role != "libero"), key=lambda player: player.name)
        serve_rest = [player for player in players if player.role == "libero"]
    return {
        "pass_main": pass_main,
        "pass_rest": pass_rest,
        "attack_main": attack_main,
        "attack_rest": attack_rest,
        "serve_main": serve_main,
        "serve_rest": serve_rest,
        "bench": bench,
    }


def _starters_redirect(team_id: str):
    if request.form.get("next") == "team":
        return redirect(url_for("team_page", team_id=team_id))
    return redirect(url_for("new_match", team_id=team_id))


def rules_from_form(form) -> Rules:
    unlimited = form.get("unlimited_subs") == "on"
    raw_max = (form.get("max_subs") or "").strip()
    max_subs = None
    if not unlimited and raw_max:
        try:
            max_subs = int(raw_max)
        except ValueError as exc:
            raise ValueError("换人上限要填整数，或留空表示先不拦截。") from exc
        if max_subs < 0:
            raise ValueError("换人上限不能是负数。")
    scope = form.get("pair_lock_scope") or "match"
    if scope not in ("match", "set"):
        raise ValueError("配对锁定范围只能是整场或每一局。")
    return Rules(
        no_back_row_attack=form.get("no_back_row_attack") == "on",
        no_libero=form.get("no_libero") == "on",
        fixed_pair_subs=form.get("fixed_pair_subs") == "on",
        unlimited_subs=unlimited,
        max_subs=max_subs,
        pair_lock_scope=scope,
        overlap_confirmed=form.get("overlap_confirmed") == "on",
        timeouts_known=form.get("timeouts_known") == "on",
    )


def player_from_form(player_id: str, form) -> Player:
    name = (form.get("name") or "").strip()
    if not name:
        raise ValueError("球员要有名字。")
    role = form.get("role") or "other"
    if role not in {code for code, _label in ROLES}:
        raise ValueError("角色不在可选范围内。")
    raw_slot = (form.get("base_slot") or "").strip()
    base_slot = None
    if raw_slot:
        try:
            base_slot = int(raw_slot)
        except ValueError as exc:
            raise ValueError("首发槽位要填 1 到 6。") from exc
        if base_slot not in range(1, 7):
            raise ValueError("首发槽位要填 1 到 6。")
    sets_when = form.get("sets_when") or "never"
    if sets_when not in ("never", "back_row", "always"):
        raise ValueError("组织职责只能是不组织、后排时组织，或一直组织。")
    raw_rank = (form.get("backup_rank") or "").strip()
    try:
        backup_rank = int(raw_rank) if raw_rank else 9
    except ValueError as exc:
        raise ValueError("补位顺序要填数字。") from exc
    return Player(
        id=player_id,
        name=name,
        role=role,
        base_slot=base_slot,
        receive_primary=form.get("receive_primary") == "on",
        sets_when=sets_when,
        can_backup_set=form.get("can_backup_set") == "on",
        backup_rank=backup_rank,
        setting_verified=form.get("setting_verified") == "on",
        jersey=(form.get("jersey") or "").strip(),
        private_note=(form.get("private_note") or "").strip(),
    )


def ensure_slot_free(plan: TeamPlan, player: Player) -> None:
    if player.base_slot is None:
        return
    for other in plan.players.values():
        if other.id != player.id and other.base_slot == player.base_slot:
            raise ValueError(f"槽位 {player.base_slot} 已经是 {other.name}。")


def pair_from_form(pair_id: str, form, plan: TeamPlan) -> Pair:
    left = form.get("player_a", "")
    right = form.get("player_b", "")
    status = form.get("status") or "candidate"
    if left not in plan.players or right not in plan.players:
        raise ValueError("配对双方都要在名单里。")
    if left == right:
        raise ValueError("配对的两个人必须不同。")
    if status not in ("confirmed", "candidate"):
        raise ValueError("配对状态只能是已确认或候选。")
    return Pair(pair_id, left, right, status, (form.get("notes") or "").strip())


def serve_from_form(form) -> ServePlan:
    try:
        rotation = int(form.get("rotation", ""))
    except ValueError as exc:
        raise ValueError("要选哪一轮的发球目标。") from exc
    if rotation not in range(1, 7):
        raise ValueError("轮次必须是 1 到 6。")
    target_type = form.get("target_type") or "unset"
    if target_type not in ("unset", "person", "zone"):
        raise ValueError("目标只能是人、区域，或先不设。")
    label = (form.get("target_label") or "").strip()
    if target_type != "unset" and not label:
        raise ValueError("选了人或区域，就要写上目标。没有证据就改回不设。")
    if target_type == "unset":
        label = ""
    return ServePlan(
        rotation=rotation,
        target_type=target_type,
        target_label=label,
        backup_label=(form.get("backup_label") or "").strip(),
        block_note=(form.get("block_note") or "").strip(),
        evidence=(form.get("evidence") or "暂无对手证据").strip() or "暂无对手证据",
    )


def rally_from_form(form, default_set: int) -> dict:
    serving = form.get("serving_side", "")
    winner = form.get("winner", "")
    scope = form.get("sample_scope", "")
    if serving not in ("us", "them", "unknown"):
        raise ValueError("发球方要选我方、对方，或未知。")
    if winner not in ("us", "them", "unknown"):
        raise ValueError("胜方要选我方、对方，或未知。")
    if scope not in ("complete", "sample", "key_clip"):
        raise ValueError("要标明这是完整比赛、抽样，还是关键片段。")
    rotation_raw = form.get("rotation", "")
    rotation = None
    if rotation_raw != "unknown":
        try:
            rotation = int(rotation_raw)
        except ValueError as exc:
            raise ValueError("轮次要选 R1 到 R6，或未知。") from exc
        if rotation not in range(1, 7):
            raise ValueError("轮次要选 R1 到 R6，或未知。")
    quality = form.get("pass_quality") or ""
    if quality == "":
        quality = None
    elif quality not in PASS_QUALITY:
        raise ValueError("一传质量不在标注标准里。")
    try:
        set_number = int(form.get("set_number") or default_set)
    except ValueError as exc:
        raise ValueError("局数要填数字。") from exc
    target_type = form.get("target_type") or ""
    if target_type not in ("", "person", "zone"):
        raise ValueError("发球目标只能是人、区域，或先不填。")
    return {
        "set_number": set_number,
        "rotation": rotation,
        "serving_side": serving,
        "winner": winner,
        "pass_quality": quality,
        "server_label": (form.get("server_label") or "").strip(),
        "target_type": target_type,
        "target_label": (form.get("target_label") or "").strip(),
        "actual_receiver": (form.get("actual_receiver") or "").strip(),
        "actual_zone": (form.get("actual_zone") or "").strip(),
        "video_timestamp": (form.get("video_timestamp") or "").strip(),
        "sample_scope": scope,
        "note": (form.get("note") or "").strip(),
    }


def confirmed_serve_samples(rallies: list[dict], rotation: int, target_label: str) -> int:
    if not target_label:
        return 0
    total = 0
    for rally in rallies:
        if rally.get("rotation") != rotation or rally.get("serving_side") != "us":
            continue
        if (rally.get("target_label") or "").strip() != target_label:
            continue
        if execution_of(rally) in ("hit", "miss"):
            total += 1
    return total


def main() -> None:
    create_app().run(host="127.0.0.1", port=5055, debug=False)


if __name__ == "__main__":
    main()
