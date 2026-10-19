"""Courtside pages. The rules engine still runs if this process has no network."""

from __future__ import annotations

from pathlib import Path

from flask import Flask, abort, flash, g, jsonify, redirect, render_template, request, send_file, url_for

from volleyball_coach.dictionary import (
    METRICS,
    OPTIONAL_RALLY_FIELDS,
    REQUIRED_RALLY_FIELDS,
    SAMPLE_RULES,
    SKILL_METRICS,
    TERMS,
)
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
from volleyball_coach.model import (
    ATTACK_RESULT,
    BLOCK_TOUCH,
    DEFENSE_QUALITY,
    PASS_QUALITY,
    SEVERE_ERROR,
    SEVERE_KIND,
    Pair,
    Player,
    RotationScheme,
    Rules,
    ServePlan,
    TeamPlan,
)
from volleyball_coach.report import build_report, execution_of, skill_summary
from volleyball_coach.seed import MENS_TEAM_ID
from volleyball_coach.store import Store, ability_label, locked_pairs_of, new_id, now, plan_for_match

FONT_PATH = Path(__file__).resolve().parents[1] / "fonts" / "NotoSansSC-Regular.otf"
COURT_ORDER = (4, 3, 2, 5, 6, 1)
ROLES = (
    ("outside", "outside"),
    ("opposite", "oppo"),
    ("middle", "middle"),
    ("setter", "setter"),
    ("libero", "libero"),
    ("defender", "defender"),
    ("flex", "flex"),
    ("other", "other"),
)

COURT_SLOTS = (
    (4, "左前"),
    (3, "中前"),
    (2, "右前"),
    (5, "左后"),
    (6, "中后"),
    (1, "右后"),
)

STAT_FIELDS = (
    ("pass_quality", "一传", PASS_QUALITY),
    ("block_touch", "拦网", BLOCK_TOUCH),
    ("defense_quality", "防守", DEFENSE_QUALITY),
    ("attack_result", "扣球", ATTACK_RESULT),
    ("severe_error", "严重失误", SEVERE_ERROR),
)


def create_app(db_path: str | Path | None = None) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["DB_PATH"] = str(db_path or Path(__file__).resolve().parent / "data" / "coach.db")
    app.secret_key = "volleyball-coach-local"
    app.jinja_env.filters["ability"] = ability_label

    @app.context_processor
    def inject_labels():
        return {"severe_kinds": SEVERE_KIND, "court_slots": COURT_SLOTS}

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
        return render_template("home.html", teams=store().list_teams(), mens_id=MENS_TEAM_ID)

    @app.post("/teams")
    def create_team():
        name = request.form.get("name", "").strip()
        if not name:
            flash("先写队名。", "error")
            return redirect(url_for("home"))
        rules = Rules()
        if request.form.get("preset") == "local_special":
            rules = Rules(
                no_back_row_attack=True,
                no_libero=True,
                fixed_pair_subs=True,
                unlimited_subs=True,
                pair_lock_scope="match",
                overlap_confirmed=False,
            )
        plan = TeamPlan(
            team_id=new_id("team"),
            name=name,
            rules=rules,
            notes=(request.form.get("notes") or "").strip(),
        )
        store().insert_plan(plan)
        if request.form.get("preset") == "local_special":
            flash("已套用那一组规则开关。名单是空的，没有复制男排球员。", "ok")
        else:
            flash("球队已单独建好。规则是空白的，名单也没有从男排复制。", "ok")
        return redirect(url_for("team_page", team_id=plan.team_id))

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

    @app.get("/teams/<team_id>/board")
    def board(team_id: str):
        plan = team_or_404(team_id)
        active, view = preview_plan(plan, request.args.get("scheme"))
        locked = {pair.key() for pair in view.pairs if pair.status == "confirmed"}
        cards = [build_card(view, rotation, {}, locked) for rotation in range(1, 7)]
        return render_template(
            "board.html",
            plan=plan,
            view=view,
            active_scheme=active,
            cards=cards,
            court_order=COURT_ORDER,
            court_slots=COURT_SLOTS,
            locked=locked,
        )

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
        _active, view = preview_plan(plan, request.args.get("scheme"))
        locked = {pair.key() for pair in view.pairs if pair.status == "confirmed"}
        cards = [build_card(view, rotation, {}, locked) for rotation in range(1, 7)]
        return render_template("quicksheet.html", plan=view, cards=cards, court_order=COURT_ORDER)

    @app.post("/teams/<team_id>/schemes")
    def save_scheme(team_id: str):
        plan = team_or_404(team_id)
        try:
            order = scheme_order_from_form(request.form, plan)
            name = (request.form.get("name") or "").strip()
            if not name:
                raise ValueError("方案要有名字。")
            raw_id = (request.form.get("scheme_id") or "").strip()
            existing = plan.scheme_by_id(raw_id) if raw_id else None
            if raw_id and existing is None:
                raise ValueError("找不到这套方案。")
            want_default = request.form.get("is_default") == "on"
            if existing and existing.is_default:
                want_default = True
            if not plan.schemes:
                want_default = True
            scheme = RotationScheme(
                id=raw_id or new_id("scheme"),
                name=name,
                order=order,
                is_default=want_default,
                notes=(request.form.get("notes") or "").strip(),
            )
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("board", team_id=plan.team_id))
        store().save_scheme(plan.team_id, scheme)
        if want_default and not (existing and existing.is_default):
            flash(f"已保存方案「{name}」，并设成开场默认。", "ok")
        elif existing and existing.is_default:
            flash(f"默认方案「{name}」已更新。六人顺序跟着这套走。", "ok")
        else:
            flash(f"已另存方案「{name}」。开场默认没有改。", "ok")
        return redirect(url_for("board", team_id=plan.team_id, scheme=scheme.id))

    @app.post("/teams/<team_id>/schemes/<scheme_id>/delete")
    def delete_scheme(team_id: str, scheme_id: str):
        team_or_404(team_id)
        if store().delete_scheme(team_id, scheme_id):
            flash("这套方案已删除。默认方案还在。", "ok")
        else:
            flash("默认方案要留着。先把另一套设成默认，再删这一套。", "error")
        return redirect(url_for("board", team_id=team_id))

    @app.get("/teams/<team_id>/matches/new")
    def new_match(team_id: str):
        plan = team_or_404(team_id)
        return render_template("match_new.html", plan=plan, court_slots=COURT_SLOTS)

    @app.post("/teams/<team_id>/matches")
    def start_match(team_id: str):
        plan = team_or_404(team_id)
        chosen_scheme = plan.scheme_by_id(request.form.get("scheme_id")) or plan.default_scheme()
        working = plan.with_order(chosen_scheme.order) if chosen_scheme else plan
        if len(working.base_order()) != 6:
            flash("先把六个首发槽位排满，或选一套完整方案，再开场。", "error")
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
            working,
            request.form.get("opponent", ""),
            mode,
            {frozenset(pair) for pair in selected},
            rotation,
            serving,
        )
        scheme_name = chosen_scheme.name if chosen_scheme else "当前首发槽"
        flash(f"开场使用方案「{scheme_name}」。换人要再确认一次，轮次不会自动把人换上场。", "ok")
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
            skills=skill_summary(rallies),
            stat_fields=STAT_FIELDS,
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
        store().append_event(match_id, "point", {"winner": winner})
        return redirect(url_for("live", match_id=match_id))

    @app.post("/matches/<match_id>/mark")
    def post_mark(match_id: str):
        """Stat line for the rally on screen now. Scoring is optional and uses that same rally."""
        match, plan, state, _points, _events = match_bundle(match_id)
        rotation = state.rotation
        serving = state.serving
        set_index = state.set_index
        lineup = [
            {"slot": slot, "player_id": state.occupants.get(slot), "name": plan.name_of(state.occupants.get(slot))}
            for slot in range(1, 7)
        ]
        bench = [plan.name_of(player_id) for player_id in state.occupants.values() if player_id not in set(plan.base_order())]
        try:
            fields = rally_from_form(request.form, set_index)
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("live", match_id=match_id))
        fields["rotation"] = rotation
        fields["serving_side"] = serving
        fields["set_number"] = set_index
        fields["lineup"] = lineup
        fields["bench_ids"] = bench
        also_score = request.form.get("also_score") == "on"
        if also_score:
            if match["status"] != "live":
                flash("本场已结束，统计可以补，比分不再往下加。", "error")
                return redirect(url_for("live", match_id=match_id))
            if fields["winner"] not in ("us", "them"):
                flash("胜方未知时不能同时改比分。先把技术统计留下。", "error")
                return redirect(url_for("live", match_id=match_id))
            try:
                apply_point(plan, state, fields["winner"])
            except MatchError as exc:
                flash(str(exc), "error")
                return redirect(url_for("live", match_id=match_id))
            store().append_event(match_id, "point", {"winner": fields["winner"]})
        store().add_rally(match_id, fields)
        if also_score:
            flash(f"R{rotation} 这一分已记下，比分和轮次按胜方走了一步。", "ok")
        else:
            flash(f"R{rotation} 这一分的技术统计已记下。比分和轮次没动。", "ok")
        return redirect(url_for("live", match_id=match_id))

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
        store().append_event(match_id, "undo", {"target_seq": target})
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
        store().append_event(
            match_id,
            "set_start",
            {"rotation": rotation, "serving": serving, "set_index": state.set_index + 1, "mode": state.mode, "overrides": {}},
        )
        flash(f"第 {state.set_index + 1} 局从 R{rotation} 开始。上一局的记录还在。", "ok")
        return redirect(url_for("live", match_id=match_id))

    @app.post("/matches/<match_id>/finish")
    def finish_match(match_id: str):
        match_bundle(match_id)
        store().set_match_status(match_id, "done")
        flash("本场已结束。赛后用三个问题补记录，不要只看比分。", "ok")
        return redirect(url_for("review", match_id=match_id))

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
            stat_fields=STAT_FIELDS,
            skills=skill_summary(store().rallies_for(match_id)),
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
                    "block_touch": rally.get("block_touch"),
                    "defense_quality": rally.get("defense_quality"),
                    "attack_result": rally.get("attack_result"),
                    "severe_error": rally.get("severe_error"),
                    "severe_kind": rally.get("severe_kind") or None,
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
            skill_metrics=SKILL_METRICS,
            samples=SAMPLE_RULES,
            required_fields=REQUIRED_RALLY_FIELDS,
            optional_fields=OPTIONAL_RALLY_FIELDS,
        )

    @app.get("/drills")
    def drills():
        results = acceptance_drills()
        return render_template("drills.html", results=results, passed=sum(item["passed"] for item in results))

    return app


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
    quality = optional_code(form, "pass_quality", PASS_QUALITY, "一传质量不在标注标准里。")
    block_touch = optional_code(form, "block_touch", BLOCK_TOUCH, "拦网不在标注标准里。")
    defense_quality = optional_code(form, "defense_quality", DEFENSE_QUALITY, "防守不在标注标准里。")
    attack_result = optional_code(form, "attack_result", ATTACK_RESULT, "扣球结果不在标注标准里。")
    severe_error = optional_code(form, "severe_error", SEVERE_ERROR, "严重失误不在标注标准里。")
    severe_kind = (form.get("severe_kind") or "").strip()
    if severe_error != "yes":
        severe_kind = ""
    elif severe_kind and severe_kind not in SEVERE_KIND:
        raise ValueError("严重失误的种类不在标注标准里。")
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
        "block_touch": block_touch,
        "defense_quality": defense_quality,
        "attack_result": attack_result,
        "severe_error": severe_error,
        "severe_kind": severe_kind,
        "server_label": (form.get("server_label") or "").strip(),
        "target_type": target_type,
        "target_label": (form.get("target_label") or "").strip(),
        "actual_receiver": (form.get("actual_receiver") or "").strip(),
        "actual_zone": (form.get("actual_zone") or "").strip(),
        "video_timestamp": (form.get("video_timestamp") or "").strip(),
        "sample_scope": scope,
        "note": (form.get("note") or "").strip(),
    }


def optional_code(form, name: str, allowed: dict, message: str):
    value = form.get(name) or ""
    if value == "":
        return None
    if value not in allowed:
        raise ValueError(message)
    return value


def scheme_order_from_form(form, plan: TeamPlan) -> list[str]:
    order = []
    for slot in range(1, 7):
        player_id = form.get(f"slot_{slot}", "")
        if player_id not in plan.players:
            raise ValueError(f"{slot} 号位要选名单里的人。")
        order.append(player_id)
    if len(set(order)) != 6:
        raise ValueError("六个号位必须是六个不同的人。")
    return order


def preview_plan(plan: TeamPlan, scheme_id: str | None) -> tuple[RotationScheme | None, TeamPlan]:
    chosen = plan.scheme_by_id(scheme_id) or plan.default_scheme()
    if chosen and len(chosen.order) == 6:
        return chosen, plan.with_order(chosen.order)
    return chosen, plan


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
