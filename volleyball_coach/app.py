"""Courtside pages. The rules engine still runs if this process has no network."""

from __future__ import annotations

import json
from pathlib import Path

from flask import Flask, abort, flash, g, jsonify, redirect, render_template, request, send_file, url_for

from volleyball_coach.actions import (
    ATTACK_RESULT as ACTION_ATTACK,
    BLOCK_RESULT,
    DEPTHS,
    LINES,
    PASS_QUALITY as ACTION_PASS,
    PASS_STANDARD,
    PHASES,
    SCOPES,
    SET_QUALITY,
    SKILL_RESULTS,
    SKILLS,
    STARTS,
    attack_summary,
    block_summary,
    coverage,
    line_groups,
    pass_summary,
    team_block_kills,
)
from volleyball_coach.dictionary import (
    METRICS,
    OPTIONAL_RALLY_FIELDS,
    REQUIRED_RALLY_FIELDS,
    SAMPLE_RULES,
    SKILL_METRICS,
    TERMS,
)
from volleyball_coach.drills import acceptance_drills
from volleyball_coach.lineup import (
    apply_system,
    build_card,
    build_suggestion,
    legal_sub_options,
    origins_for_rotation,
    system_note,
    validate_pairs,
)
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
    role_chip,
)
from volleyball_coach.report import build_report, execution_of, skill_summary
from volleyball_coach.seed import MENS_TEAM_ID
from volleyball_coach.store import Store, ability_label, locked_pairs_of, new_id, now, plan_for_match
from volleyball_coach.tactics import (
    NOTE_KINDS,
    PHASES as TACTIC_PHASES,
    default_marks,
    display_num,
    execution_counts,
    execution_sentence,
    identity_drift,
    load_backup,
    load_snapshot,
    position_kind,
    prep_rows,
    present_marks,
    preview_marks,
    rotation_status,
    snapshot_payload,
)

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
        nav_match = None
        nav_plan = None
        nav_state = None
        view_args = request.view_args or {}
        match_id = view_args.get("match_id")
        team_id = view_args.get("team_id")
        nav_team_id = team_id
        prep_screen = request.endpoint in {"tactics", "tactics_sheet", "new_match", "board", "quicksheet"}
        try:
            if not match_id and team_id:
                matches = store().list_matches(team_id)
                live_match = next((item for item in matches if item["status"] == "live"), None)
                match_id = (live_match or (matches[0] if matches else None))
                match_id = match_id["id"] if match_id else None
            if match_id:
                found = store().get_match(match_id)
                if found is not None:
                    plan = plan_for_match(store(), found)
                    state, _points = replay(plan, store().events_for(match_id), locked_pairs_of(found), found["mode"])
                    if state is not None:
                        nav_match = found
                        nav_plan = plan
                        nav_state = state
            if nav_match is not None and not nav_team_id:
                nav_team_id = nav_match["team_id"]
            if not nav_team_id:
                preferred = store().conn.execute("SELECT id FROM teams WHERE id = ?", (MENS_TEAM_ID,)).fetchone()
                if preferred is None:
                    preferred = store().conn.execute("SELECT id FROM teams ORDER BY created_at LIMIT 1").fetchone()
                nav_team_id = preferred["id"] if preferred else None
        except Exception:
            nav_match = None
        return {
            "severe_kinds": SEVERE_KIND,
            "court_slots": COURT_SLOTS,
            "nav_match": nav_match,
            "nav_plan": nav_plan,
            "nav_state": nav_state,
            "nav_team_id": nav_team_id,
            "prep_screen": prep_screen,
        }

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
        teams = store().list_teams()
        ids = [row["id"] for row in teams]
        library = MENS_TEAM_ID if MENS_TEAM_ID in ids else (ids[0] if ids else None)
        return render_template(
            "home.html",
            teams=teams,
            mens_id=MENS_TEAM_ID,
            live_match=store().latest_live_match(),
            library_team=library,
        )

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
                system=existing.system if existing else "",
                setters=list(existing.setters) if existing else [],
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

    def tactic_or_404(team_id: str, tactic_id: str) -> dict:
        found = store().tactic(tactic_id)
        if found is None or found["team_id"] != team_id:
            abort(404)
        return found

    def confirmed_pairs(plan: TeamPlan) -> set[frozenset[str]]:
        return {pair.key() for pair in plan.pairs if pair.status == "confirmed"}

    def tactic_page_url(team_id: str, tactic_id: str, rotation: int = 1, phase: str = "receive"):
        return url_for("tactics", team_id=team_id, tactic=tactic_id, rotation=rotation, phase=phase)

    @app.get("/teams/<team_id>/tactics")
    def tactics(team_id: str):
        plan = team_or_404(team_id)
        library = store().tactics_for_team(team_id)
        chosen = store().tactic((request.args.get("tactic") or "").strip())
        if chosen and chosen["team_id"] != team_id:
            chosen = None
        if chosen:
            scheme = plan.scheme_by_id(chosen["scheme_id"]) or plan.default_scheme()
        else:
            scheme = plan.scheme_by_id(request.args.get("scheme")) or plan.default_scheme()
            for item in reversed(library):
                if scheme and item["scheme_id"] == scheme.id and item["status"] == "draft":
                    chosen = item
                    break
            if chosen is None and scheme:
                chosen = next((item for item in reversed(library) if item["scheme_id"] == scheme.id), None)
        rotation = request.args.get("rotation", "1")
        phase = request.args.get("phase") or "receive"
        try:
            rotation = int(rotation)
        except ValueError:
            rotation = 1
        if rotation not in range(1, 7):
            rotation = 1
        if phase not in TACTIC_PHASES:
            phase = "receive"
        view = apply_system(plan, scheme)
        locked = confirmed_pairs(plan)
        cards = {number: build_card(view, number, {}, locked) for number in range(1, 7)}
        marks = store().tactic_marks(chosen["id"]) if chosen else []
        notes = store().tactic_notes(chosen["id"]) if chosen else []
        statuses = [
            (number, rotation_status(cards[number], [mark for mark in marks if int(mark["rotation"]) == number and mark["phase"] == "receive"]))
            for number in range(1, 7)
        ]
        card = cards[rotation]
        if chosen:
            phase_marks = [mark for mark in marks if int(mark["rotation"]) == rotation and mark["phase"] == phase]
        else:
            phase_marks = preview_marks(card, rotation, phase)
        note_map = {
            note["kind"]: note["body"]
            for note in notes
            if int(note["rotation"]) == rotation
        }
        same_scheme = [item for item in library if scheme and item["scheme_id"] == scheme.id]
        return render_template(
            "tactics.html",
            plan=plan,
            view=view,
            scheme=scheme,
            tactics=same_scheme,
            tactic=chosen,
            rotation=rotation,
            phase=phase,
            phases=TACTIC_PHASES,
            note_kinds=NOTE_KINDS,
            statuses=statuses,
            marks=present_marks(view, card, phase_marks),
            card=card,
            notes=note_map,
            position_kind=position_kind(plan),
            drift=identity_drift(cards, marks),
            published=bool(chosen and chosen["status"] == "published"),
            on_court=court_options(scheme),
            system_note=system_note(scheme),
        )

    @app.get("/teams/<team_id>/tactics/<tactic_id>/sheet")
    def tactics_sheet(team_id: str, tactic_id: str):
        plan = team_or_404(team_id)
        tactic = tactic_or_404(team_id, tactic_id)
        scheme = plan.scheme_by_id(tactic["scheme_id"])
        view = apply_system(plan, scheme)
        locked = confirmed_pairs(plan)
        phase = request.args.get("phase") or "receive"
        if phase not in TACTIC_PHASES:
            phase = "receive"
        marks = store().tactic_marks(tactic_id)
        cards = []
        for number in range(1, 7):
            card = build_card(view, number, {}, locked)
            phase_marks = [mark for mark in marks if int(mark["rotation"]) == number and mark["phase"] == phase]
            cards.append(
                {
                    "card": card,
                    "marks": present_marks(view, card, phase_marks),
                    "status": rotation_status(card, [mark for mark in marks if int(mark["rotation"]) == number and mark["phase"] == "receive"]),
                }
            )
        return render_template(
            "tactics_sheet.html",
            plan=plan,
            tactic=tactic,
            scheme=scheme,
            phase=phase,
            phases=TACTIC_PHASES,
            cards=cards,
            position_kind=position_kind(plan),
        )

    @app.post("/teams/<team_id>/schemes/<scheme_id>/copy")
    def copy_scheme(team_id: str, scheme_id: str):
        team_or_404(team_id)
        try:
            copied = store().copy_scheme(team_id, scheme_id, request.form.get("name") or "")
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("tactics", team_id=team_id))
        flash("已复制阵容。默认阵容没有改。", "ok")
        return redirect(url_for("tactics", team_id=team_id, scheme=copied))

    @app.post("/teams/<team_id>/schemes/<scheme_id>/system")
    def save_scheme_system(team_id: str, scheme_id: str):
        plan = team_or_404(team_id)
        scheme = plan.scheme_by_id(scheme_id)
        back = request.referrer or url_for("tactics", team_id=team_id, scheme=scheme_id)
        if scheme is None or len(scheme.order) != 6:
            flash("先选一套完整的六人阵容。", "error")
            return redirect(back)
        try:
            label, setters = setters_from_system_form(scheme, request.form)
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(back)
        scheme.system = label_code(label)
        scheme.setters = setters
        store().save_scheme(plan.team_id, scheme)
        flash(f"体系已改成{label}。名单上原来的二传能力还留着。", "ok")
        tactic_id = (request.form.get("tactic") or "").strip()
        if tactic_id:
            phase = request.form.get("phase") or "receive"
            try:
                rotation = int(request.form.get("rotation") or "1")
            except ValueError:
                rotation = 1
            return redirect(tactic_page_url(team_id, tactic_id, rotation if rotation in range(1, 7) else 1, phase if phase in TACTIC_PHASES else "receive"))
        return redirect(url_for("tactics", team_id=team_id, scheme=scheme.id))

    @app.post("/teams/<team_id>/tactics")
    def create_tactic(team_id: str):
        plan = team_or_404(team_id)
        scheme = plan.scheme_by_id(request.form.get("scheme_id"))
        name = (request.form.get("name") or "").strip()
        if scheme is None or len(scheme.order) != 6:
            flash("先选一套完整的六人阵容，再生成战术。", "error")
            return redirect(url_for("tactics", team_id=team_id))
        if not name:
            flash("战术要有名字。", "error")
            return redirect(url_for("tactics", team_id=team_id, scheme=scheme.id))
        view = apply_system(plan, scheme)
        tactic_id = store().create_tactic(team_id, scheme.id, name, default_marks(view, confirmed_pairs(plan)))
        flash(f"已生成「{name}」的六轮示意站位。拖动只改坐标。", "ok")
        return redirect(tactic_page_url(team_id, tactic_id))

    @app.post("/teams/<team_id>/tactics/<tactic_id>/duplicate")
    def duplicate_tactic(team_id: str, tactic_id: str):
        tactic_or_404(team_id, tactic_id)
        try:
            copied = store().duplicate_tactic(tactic_id, request.form.get("name") or "")
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("tactics", team_id=team_id))
        flash("已另存成草稿。已发布的那一版没动。", "ok")
        return redirect(tactic_page_url(team_id, copied))

    @app.post("/teams/<team_id>/tactics/<tactic_id>/publish")
    def publish_tactic(team_id: str, tactic_id: str):
        tactic_or_404(team_id, tactic_id)
        try:
            store().publish_tactic(tactic_id)
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("tactics", team_id=team_id))
        flash("这一版已发布。再改会另存成草稿，不会覆盖这一版。", "ok")
        return redirect(tactic_page_url(team_id, tactic_id))

    @app.post("/teams/<team_id>/tactics/<tactic_id>/marks")
    def save_tactic_mark(team_id: str, tactic_id: str):
        tactic_or_404(team_id, tactic_id)
        wants_json = "application/json" in (request.headers.get("Accept") or "")

        def fail(message: str):
            if wants_json:
                return jsonify({"ok": False, "error": message}), 409
            flash(message, "error")
            return redirect(request.referrer or url_for("tactics", team_id=team_id))

        try:
            rotation = int(request.form.get("rotation", "0"))
            slot = int(request.form.get("slot", "0"))
            phase = request.form.get("phase") or ""
            x = float(request.form.get("x", ""))
            y = float(request.form.get("y", ""))
        except ValueError:
            return fail("坐标和轮次要是数字。")
        if phase not in TACTIC_PHASES or rotation not in range(1, 7) or slot not in range(1, 7):
            return fail("轮次、阶段或号位不对。")
        try:
            saved_x, saved_y = store().update_tactic_mark(
                tactic_id,
                rotation,
                phase,
                slot,
                request.form.get("player_id") or "",
                x,
                y,
            )
        except ValueError as exc:
            return fail(str(exc))
        if wants_json:
            return jsonify({"ok": True, "x": display_num(saved_x), "y": display_num(saved_y)})
        flash("示意坐标已保存。轮转身份没变。", "ok")
        return redirect(tactic_page_url(team_id, tactic_id, rotation, phase))

    @app.post("/teams/<team_id>/tactics/<tactic_id>/notes")
    def save_tactic_notes(team_id: str, tactic_id: str):
        tactic_or_404(team_id, tactic_id)
        try:
            rotation = int(request.form.get("rotation", "0"))
        except ValueError:
            rotation = 0
        if rotation not in range(1, 7):
            flash("轮次要是 1 到 6。", "error")
            return redirect(url_for("tactics", team_id=team_id))
        try:
            store().save_tactic_notes(
                tactic_id,
                rotation,
                {kind: request.form.get(kind) or "" for kind in NOTE_KINDS},
            )
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(tactic_page_url(team_id, tactic_id, rotation))
        flash(f"R{rotation} 的职责说明已保存在这套战术里。", "ok")
        phase = request.form.get("phase") or "receive"
        return redirect(tactic_page_url(team_id, tactic_id, rotation, phase if phase in TACTIC_PHASES else "receive"))

    @app.post("/teams/<team_id>/tactics/<tactic_id>/sync")
    def sync_tactic(team_id: str, tactic_id: str):
        plan = team_or_404(team_id)
        tactic = tactic_or_404(team_id, tactic_id)
        scheme = plan.scheme_by_id(tactic["scheme_id"])
        if scheme is None or len(scheme.order) != 6:
            flash("这套战术的阵容不完整，不能更正人员。", "error")
            return redirect(url_for("tactics", team_id=team_id))
        view = apply_system(plan, scheme)
        locked = confirmed_pairs(plan)
        occupants = {}
        for number in range(1, 7):
            card = build_card(view, number, {}, locked)
            occupants[number] = {slot: view_slot.occupant_id for slot, view_slot in card.slots.items()}
        try:
            store().sync_tactic_players(tactic_id, occupants)
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(tactic_page_url(team_id, tactic_id))
        flash("人员已按当前阵容更正。坐标还在原来的示意位置。", "ok")
        return redirect(tactic_page_url(team_id, tactic_id))

    @app.get("/teams/<team_id>/matches/new")
    def new_match(team_id: str):
        plan = team_or_404(team_id)
        scheme = plan.scheme_by_id(request.args.get("scheme")) or plan.default_scheme()
        library = store().tactics_for_team(team_id)
        published = [
            item
            for item in library
            if item["status"] == "published" and scheme and item["scheme_id"] == scheme.id
        ]
        asked = (request.args.get("tactic") or "").strip()
        tactic = next((item for item in published if item["id"] == asked), None)
        backup = plan.scheme_by_id(request.args.get("backup"))
        if backup is None or scheme is None or backup.id == scheme.id or len(backup.order) != 6:
            backup = None
        try:
            rotation = int(request.args.get("rotation") or "1")
        except ValueError:
            rotation = 1
        if rotation not in range(1, 7):
            rotation = 1
        view = apply_system(plan, scheme) if scheme else plan
        locked = confirmed_pairs(plan)
        cards = {number: build_card(view, number, {}, locked) for number in range(1, 7)}
        marks = store().tactic_marks(tactic["id"]) if tactic else []
        rows = prep_rows(view, cards, marks, locked)
        current = rows[rotation - 1]
        if tactic:
            phase_marks = [
                mark for mark in marks if int(mark["rotation"]) == rotation and mark["phase"] == "receive"
            ]
        else:
            phase_marks = preview_marks(cards[rotation], rotation, "receive")
        order = list(scheme.order) if scheme and len(scheme.order) == 6 else view.base_order()
        six = []
        for slot, player_id in enumerate(order, start=1):
            player = plan.players.get(player_id)
            six.append(
                {
                    "slot": slot,
                    "name": plan.name_of(player_id),
                    "role": role_chip(player.role) if player else "",
                }
            )
        on_court = set(order)
        bench = sorted(
            (player for player in plan.players.values() if player.id not in on_court),
            key=lambda player: player.name,
        )
        unlocked = [
            window
            for window in plan.sub_windows
            if frozenset((window.player_out, window.player_in)) not in locked
        ]
        return render_template(
            "match_new.html",
            plan=plan,
            scheme=scheme,
            view=view,
            tactic=tactic,
            backup=backup,
            published_tactics=published,
            rotation=rotation,
            rows=rows,
            current=current,
            marks=present_marks(view, cards[rotation], phase_marks),
            playable=len(view.base_order()) == 6,
            six=six,
            bench=bench,
            unlocked=unlocked,
            position_kind=position_kind(plan),
            system_note=system_note(scheme),
            court_slots=COURT_SLOTS,
        )

    @app.post("/teams/<team_id>/matches")
    def start_match(team_id: str):
        plan = team_or_404(team_id)

        def back():
            return redirect(
                url_for(
                    "new_match",
                    team_id=plan.team_id,
                    scheme=request.form.get("scheme_id") or None,
                    tactic=request.form.get("tactic_id") or None,
                    backup=request.form.get("backup_scheme_id") or None,
                    rotation=request.form.get("rotation") or None,
                )
            )

        chosen_scheme = plan.scheme_by_id(request.form.get("scheme_id")) or plan.default_scheme()
        working = apply_system(plan, chosen_scheme) if chosen_scheme else plan
        if len(working.base_order()) != 6:
            flash("先把六个首发槽位排满，或选一套完整方案，再开场。", "error")
            return back()
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
            return back()
        raw_backup = (request.form.get("backup_scheme_id") or "").strip()
        backup_scheme = None
        backup_json = ""
        if raw_backup:
            backup_scheme = plan.scheme_by_id(raw_backup)
            if backup_scheme is None or len(backup_scheme.order) != 6:
                flash("找不到这套备用阵容。", "error")
                return back()
            if chosen_scheme and backup_scheme.id == chosen_scheme.id:
                flash("备用阵容要换一套，不能和开场是同一套。", "error")
                return back()
            backup_view = apply_system(plan, backup_scheme)
            backup_json = json.dumps(
                {
                    "scheme_id": backup_scheme.id,
                    "name": backup_scheme.name,
                    "system": backup_scheme.system_label(),
                    "order": list(backup_scheme.order),
                    "plan": backup_view.to_json(),
                },
                ensure_ascii=False,
            )
        tactic_id = (request.form.get("tactic_id") or "").strip()
        tactic_json = ""
        tactic = None
        if tactic_id:
            tactic = store().tactic(tactic_id)
            if tactic is None or tactic["team_id"] != plan.team_id:
                flash("找不到这套战术。", "error")
                return back()
            if tactic["status"] != "published":
                flash("只有发布后的战术版本能带进比赛。", "error")
                return back()
            if chosen_scheme is None or tactic["scheme_id"] != chosen_scheme.id:
                flash("这套战术属于另一套阵容。开场要选对应的阵容。", "error")
                return back()
            tactic_json = json.dumps(
                snapshot_payload(
                    tactic,
                    store().tactic_marks(tactic_id),
                    store().tactic_notes(tactic_id),
                    working,
                    chosen_scheme.name,
                ),
                ensure_ascii=False,
            )
        match_id = store().create_match(
            working,
            request.form.get("opponent", ""),
            mode,
            {frozenset(pair) for pair in selected},
            rotation,
            serving,
            tactic_id=tactic_id,
            tactic_json=tactic_json,
            backup_scheme_id=backup_scheme.id if backup_scheme else "",
            backup_json=backup_json,
        )
        scheme_name = chosen_scheme.name if chosen_scheme else "当前首发槽"
        spare = f"备用「{backup_scheme.name}」。" if backup_scheme else ""
        if tactic:
            flash(f"开场使用方案「{scheme_name}」，战术「{tactic['name']}」。{spare}之后改战术库，不会改这场已经抄下来的版本。", "ok")
        else:
            flash(f"开场使用方案「{scheme_name}」。{spare}换人要再确认一次，轮次不会自动把人换上场。", "ok")
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
        actions = store().actions_for(match_id)
        open_rally = store().open_rally(match_id)
        open_actions = [item for item in actions if open_rally and item["rally_id"] == open_rally["id"]]
        opponents = store().opponents_for(match_id)
        depth = match["record_depth"] if "record_depth" in match.keys() else "light"
        scope = match["sample_scope"] if "sample_scope" in match.keys() else "sample"
        raw_tactic = match["tactic_json"] if "tactic_json" in match.keys() else ""
        raw_backup = match["backup_json"] if "backup_json" in match.keys() else ""
        plan_snapshot = load_snapshot(raw_tactic or "")
        backup_call = load_backup(raw_backup or "")
        plan_phase = "attack" if state.serving == "us" else "receive"
        plan_marks = []
        plan_note = ""
        lineup_differs = False
        execution_text = ""
        if plan_snapshot:
            opening = build_card(plan, state.rotation, {}, state.locked_pairs)
            phase_marks = [
                mark
                for mark in plan_snapshot["marks"]
                if int(mark["rotation"]) == state.rotation and mark["phase"] == plan_phase
            ]
            plan_marks = present_marks(plan, opening, phase_marks)
            note_kind = "serve_target" if state.serving == "us" else "block_task"
            for note in plan_snapshot.get("notes") or []:
                if int(note["rotation"]) == state.rotation and note["kind"] == note_kind and note.get("body"):
                    plan_note = note["body"]
            opening_ids = {item.occupant_id for item in opening.slots.values()} if opening.slots else set()
            lineup_differs = opening_ids != set(state.occupants.values())
            execution_text = execution_sentence(execution_counts(rallies), plan_snapshot.get("name") or "战术")
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
            bookmarks=bookmarks[-8:],
            skills=skill_summary(rallies),
            stat_fields=STAT_FIELDS,
            actions=actions,
            open_rally=open_rally,
            open_actions=open_actions,
            opponents=opponents,
            record_depth=depth,
            sample_scope=scope,
            coverage=coverage(rallies, actions, len(_points)),
            action_token=new_id("tok"),
            on_court=set(state.occupants.values()),
            player_table=player_rows(plan, actions, {item["id"]: item["participants"] for item in actions}),
            skills_vocab=SKILLS,
            skill_results=SKILL_RESULTS,
            starts=STARTS,
            lines=LINES,
            phases=PHASES,
            set_qualities=SET_QUALITY,
            depths=DEPTHS,
            scopes=SCOPES,
            plan_snapshot=plan_snapshot,
            backup_call=backup_call,
            plan_marks=plan_marks,
            plan_phase=plan_phase,
            plan_phase_label=TACTIC_PHASES[plan_phase],
            plan_note=plan_note,
            lineup_differs=lineup_differs,
            execution_text=execution_text,
        )

    @app.post("/matches/<match_id>/point")
    def post_point(match_id: str):
        match, plan, state, _points, _events = match_bundle(match_id)
        if match["status"] != "live":
            flash("本场已结束。比分如果记错了，用校正，不要继续往下加。", "error")
            return redirect(url_for("live", match_id=match_id))
        winner = request.form.get("winner", "")
        open_rally = store().open_rally(match_id)
        if open_rally and open_rally.get("scored"):
            flash("这一回合的比分已经记过，没有再次加分。", "error")
            return redirect(url_for("live", match_id=match_id))
        try:
            updated = apply_point(plan, state, winner)
        except MatchError as exc:
            flash(str(exc), "error")
            return redirect(url_for("live", match_id=match_id))
        store().append_event(
            match_id,
            "point",
            {"winner": winner, "rally_id": open_rally["id"] if open_rally else None},
        )
        if open_rally:
            execution = request.form.get("plan_execution") or ""
            store().close_rally(
                match_id,
                open_rally["id"],
                winner,
                updated.score_us,
                updated.score_them,
                1,
                execution,
            )
            flash("回合结束，比分已记下。", "ok")
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
        actions = store().actions_for(match_id)
        last_action = actions[-1] if actions else None
        last_event = events[-1] if events else None
        if last_action and (last_event is None or last_action["created_at"] > last_event["created_at"]):
            store().delete_action(match_id, last_action["id"])
            flash("已撤销上一个动作。比分和轮次没动。", "ok")
            return redirect(url_for("live", match_id=match_id))
        target = last_reversible_seq(events)
        if target is None:
            flash("没有可以撤销的操作。开场记录会保留。", "error")
            return redirect(url_for("live", match_id=match_id))
        undone = next(event for event in events if event["seq"] == target)
        store().append_event(match_id, "undo", {"target_seq": target})
        rally_id = undone["payload"].get("rally_id") if undone["type"] == "point" else None
        if rally_id:
            store().reopen_rally(match_id, int(rally_id))
            flash("已撤销这一分。回合里的动作还在，比分退回。", "ok")
        else:
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
        rallies = store().rallies_for(match_id)
        report = build_report(
            rallies=rallies,
            events=events,
            points=points,
            history_gap=state.history_gap,
            opponent=match["opponent"],
        )
        snap = load_snapshot(match["tactic_json"] if "tactic_json" in match.keys() else "")
        execution = None
        if snap:
            execution = {"sentence": execution_sentence(execution_counts(rallies), snap.get("name") or "战术")}
        return render_template("report.html", match=match, report=report, state=state, execution=execution)

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

    def _save_action(match_id: str, plan, state):
        opponents = store().opponents_for(match_id)
        try:
            fields, participants = action_from_form(request.form, plan, opponents)
        except ValueError as exc:
            flash(str(exc), "error")
            return None
        manual = request.form.get("confirm_lineup") == "on"
        requested = (request.form.get("rally_id") or "").strip()
        if requested:
            try:
                rally_id = int(requested)
            except ValueError:
                flash("回合编号无效。", "error")
                return None
            rally = store().rally(match_id, rally_id)
            if rally is None:
                flash("找不到这个回合。没有用当前阵容新建。", "error")
                return None
        else:
            rally = store().open_rally(match_id)
            if rally is None:
                match = store().get_match(match_id)
                scope = match["sample_scope"] if match and "sample_scope" in match.keys() else "sample"
                rally_id = store().insert_open_rally(
                    match_id,
                    {
                        "set_number": state.set_index,
                        "rotation": state.rotation,
                        "serving_side": state.serving,
                        "lineup": snapshot_lineup(plan, state),
                        "sample_scope": scope,
                        "score_us_before": state.score_us,
                        "score_them_before": state.score_them,
                    },
                )
                rally = store().rally(match_id, rally_id)
        lineup, source = lineup_for_action(rally, plan, state, manual)
        fields["rally_id"] = rally["id"]
        fields["lineup"] = lineup
        fields["lineup_source"] = source
        action_id, created = store().add_action(match_id, fields, participants)
        if created:
            flash("动作已保存。比分还没动。", "ok")
        else:
            flash("这一动作已经保存过，没有重复记。", "ok")
        return action_id

    @app.post("/matches/<match_id>/recording")
    def post_recording(match_id: str):
        match_bundle(match_id)
        depth = request.form.get("record_depth") or ""
        scope = request.form.get("sample_scope") or ""
        if depth not in DEPTHS or scope not in SCOPES:
            flash("记录方式没有保存。", "error")
            return redirect(url_for("live", match_id=match_id))
        store().set_recording(match_id, depth, scope)
        flash("记录方式已保存。之后的新回合用这个范围。", "ok")
        return redirect(url_for("live", match_id=match_id))

    @app.post("/matches/<match_id>/opponents")
    def post_opponent(match_id: str):
        match_bundle(match_id)
        jersey = (request.form.get("jersey") or "").strip()
        if not jersey:
            flash("先填写对方号码。", "error")
            return redirect(request.referrer or url_for("opponents_page", match_id=match_id))
        store().ensure_opponent(match_id, jersey, request.form.get("name") or "")
        flash(f"对方 {jersey} 号已建档。", "ok")
        return redirect(request.referrer or url_for("opponents_page", match_id=match_id))

    @app.post("/matches/<match_id>/actions")
    def post_action(match_id: str):
        _match, plan, state, _points, _events = match_bundle(match_id)
        _save_action(match_id, plan, state)
        return redirect(request.referrer or url_for("live", match_id=match_id))

    @app.post("/matches/<match_id>/actions/<int:action_id>")
    def post_action_edit(match_id: str, action_id: int):
        _match, plan, _state, _points, _events = match_bundle(match_id)
        opponents = store().opponents_for(match_id)
        try:
            fields, participants = action_from_form(request.form, plan, opponents)
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(request.referrer or url_for("video_page", match_id=match_id))
        if not store().update_action(match_id, action_id, fields, participants):
            flash("没有找到这个动作。", "error")
        else:
            flash("动作已改。比分和轮次没动。", "ok")
        return redirect(request.referrer or url_for("video_page", match_id=match_id))

    @app.post("/matches/<match_id>/actions/<int:action_id>/delete")
    def post_action_delete(match_id: str, action_id: int):
        match_bundle(match_id)
        if store().delete_action(match_id, action_id) is None:
            flash("没有找到这个动作。", "error")
        else:
            flash("动作已删除。比分和轮次没动。", "ok")
        return redirect(request.referrer or url_for("live", match_id=match_id))

    @app.get("/matches/<match_id>/players")
    def players_page(match_id: str):
        match, plan, state, _points, _events = match_bundle(match_id)
        actions = store().actions_for(match_id)
        set_filter = request.args.get("set") or ""
        rotation_filter = request.args.get("rotation") or ""
        phase_filter = request.args.get("phase") or ""
        player_filter = request.args.get("player") or ""
        skill_filter = request.args.get("skill") or ""
        result_filter = request.args.get("result") or ""
        selected = []
        for action in actions:
            if set_filter and str(action.get("set_number")) != set_filter:
                continue
            if rotation_filter and str(action.get("rotation") or "") != rotation_filter:
                continue
            if phase_filter and action.get("phase") != phase_filter:
                continue
            selected.append(action)
        table_actions = selected
        if player_filter:
            table_actions = [
                action
                for action in selected
                if action.get("player_id") == player_filter or player_filter in action.get("participants", [])
            ]
        membership = {item["id"]: item["participants"] for item in table_actions}
        rows = player_rows(plan, table_actions, membership)
        sort = request.args.get("sort") or "name"
        reverse = request.args.get("dir") == "desc"

        def sort_key(row):
            if sort == "pass":
                return row["passing"]["attempts"]
            if sort == "attack":
                return row["attack"]["attempts"]
            if sort == "block":
                return row["block"]["events"]
            return row["name"]

        rows.sort(key=sort_key, reverse=reverse)
        visible = selected
        if player_filter:
            visible = [
                action
                for action in selected
                if action.get("player_id") == player_filter or player_filter in action.get("participants", [])
            ]
        if skill_filter:
            visible = [action for action in visible if action.get("skill") == skill_filter]
        if result_filter:
            visible = [
                action
                for action in visible
                if action.get("result") == result_filter or action.get("quality") == result_filter
            ]
        return render_template(
            "players.html",
            match=match,
            plan=plan,
            state=state,
            rows=rows,
            actions=visible,
            show_actions=bool(skill_filter or result_filter or player_filter),
            team_block_kills=team_block_kills(table_actions),
            standards=PASS_STANDARD,
            skills_vocab=SKILLS,
            attack_labels=ACTION_ATTACK,
            block_labels=BLOCK_RESULT,
            phases=PHASES,
            scopes=SCOPES,
            filters={
                "set": set_filter,
                "rotation": rotation_filter,
                "phase": phase_filter,
                "player": player_filter,
                "skill": skill_filter,
                "result": result_filter,
                "sort": sort,
            },
            coverage=coverage(store().rallies_for(match_id), actions, 0),
        )

    @app.get("/matches/<match_id>/opponents")
    def opponents_page(match_id: str):
        match, plan, state, _points, _events = match_bundle(match_id)
        opponents = store().opponents_for(match_id)
        actions = [item for item in store().actions_for(match_id) if item.get("team_side") == "them" and item.get("skill") == "attack"]
        player_id = request.args.get("player") or (opponents[0]["id"] if opponents else "")
        start = request.args.get("start") or ""
        line = request.args.get("line") or ""
        phase = request.args.get("phase") or ""
        quality = request.args.get("set_quality") or ""
        chosen = [item for item in actions if not player_id or item.get("player_id") == player_id]
        if start:
            chosen = [item for item in chosen if item.get("start_zone") == start]
        if line:
            chosen = [item for item in chosen if item.get("attack_line") == line]
        if phase:
            chosen = [item for item in chosen if item.get("phase") == phase]
        if quality:
            chosen = [item for item in chosen if item.get("set_quality") == quality]
        names = {item["id"]: (item["name"] or f"{item['jersey']}号") for item in opponents}
        return render_template(
            "opponents.html",
            match=match,
            plan=plan,
            state=state,
            opponents=opponents,
            names=names,
            arrows=line_groups(chosen),
            actions=chosen,
            attack=attack_summary(chosen),
            starts=STARTS,
            lines=LINES,
            phases=PHASES,
            set_qualities=SET_QUALITY,
            attack_labels=ACTION_ATTACK,
            filters={"player": player_id, "start": start, "line": line, "phase": phase, "set_quality": quality},
        )

    @app.get("/matches/<match_id>/video")
    def video_page(match_id: str):
        match, plan, state, _points, events = match_bundle(match_id)
        rallies = store().rallies_for(match_id)
        actions = store().actions_for(match_id)
        opponents = store().opponents_for(match_id)
        return render_template(
            "video.html",
            match=match,
            plan=plan,
            state=state,
            rallies=rallies,
            actions=actions,
            opponents=opponents,
            bookmarks=[event for event in events if event["type"] == "bookmark"],
            on_court=set(state.occupants.values()),
            action_token=new_id("tok"),
            skills_vocab=SKILLS,
            skill_results=SKILL_RESULTS,
            starts=STARTS,
            lines=LINES,
            phases=PHASES,
            set_qualities=SET_QUALITY,
            names={item["id"]: (item["name"] or f"{item['jersey']}号") for item in opponents},
        )

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
        return chosen, apply_system(plan, chosen)
    return chosen, plan


def court_options(scheme: RotationScheme | None) -> list[tuple[int, list[str]]]:
    if scheme is None or len(scheme.order) != 6:
        return []
    options = []
    for number in range(1, 7):
        origins = origins_for_rotation(list(scheme.order), number)
        options.append((number, list(origins.values())))
    return options


def label_code(label: str) -> str:
    return {"6-2": "62", "5-1": "51", "自定义": "custom"}[label]


def setters_from_system_form(scheme: RotationScheme, form) -> tuple[str, list[str]]:
    system = form.get("system") or ""
    if system not in ("62", "51", "custom"):
        raise ValueError("体系要选 6-2、5-1，或自定义。")
    six = set(scheme.order)
    names = {"62": "6-2", "51": "5-1", "custom": "自定义"}
    if system == "51":
        setter = form.get("setter") or ""
        if setter not in six:
            raise ValueError("5-1 的二传必须在这六个人里。")
        return names[system], [setter]
    if system == "62":
        first = form.get("setter_a") or ""
        second = form.get("setter_b") or ""
        if first not in six or second not in six or first == second:
            raise ValueError("6-2 要选两名不同的、都在这六个人里的二传。")
        return names[system], [first, second]
    setters = []
    for number in range(1, 7):
        origins = origins_for_rotation(list(scheme.order), number)
        chosen = form.get(f"setter_{number}") or ""
        if chosen not in origins.values():
            raise ValueError(f"R{number} 的组织者必须是这一轮在场的人。")
        setters.append(chosen)
    return names[system], setters


def snapshot_lineup(plan: TeamPlan, state) -> list[dict]:
    return [
        {"slot": slot, "player_id": state.occupants.get(slot), "name": plan.name_of(state.occupants.get(slot))}
        for slot in range(1, 7)
    ]


def action_from_form(form, plan: TeamPlan, opponents: list[dict]) -> tuple[dict, list[str]]:
    skill = form.get("skill") or ""
    if skill not in SKILL_RESULTS:
        raise ValueError("先选技术动作。")
    result = form.get("result") or ""
    if result not in SKILL_RESULTS[skill]:
        raise ValueError("先选这个动作的结果。")
    side = form.get("team_side") or "us"
    if side not in ("us", "them"):
        raise ValueError("先选我方或对方。")
    token = (form.get("client_token") or "").strip()
    if not token:
        raise ValueError("缺少动作标记，请再保存一次。")

    def optional(name: str, allowed: dict) -> str:
        value = (form.get(name) or "").strip()
        if value and value not in allowed:
            raise ValueError("有一个选项不在可选范围内。")
        return value

    player_id = ""
    participants: list[str] = []
    if skill == "block":
        if side != "us":
            raise ValueError("拦网记在我方参与的人身上。")
        participants = [player for player in form.getlist("block_player") if player in plan.players]
        player_id = participants[0] if len(participants) == 1 else ""
    elif side == "us":
        player_id = form.get("player_id") or ""
        if player_id and player_id not in plan.players:
            raise ValueError("球员不在这支球队里。")
        if player_id:
            participants = [player_id]
    else:
        player_id = form.get("opponent_id") or ""
        known = {item["id"] for item in opponents}
        if player_id and player_id not in known:
            raise ValueError("对方号码还没建档。")
    quality = result if skill == "pass" else optional("quality", ACTION_PASS)
    return {
        "client_token": token,
        "team_side": side,
        "player_id": player_id,
        "skill": skill,
        "result": result,
        "quality": quality,
        "start_zone": optional("start_zone", STARTS),
        "attack_line": optional("attack_line", LINES),
        "end_zone": (form.get("end_zone") or "").strip(),
        "phase": optional("phase", PHASES),
        "set_quality": optional("set_quality", SET_QUALITY),
        "video_timestamp": (form.get("video_timestamp") or "").strip(),
        "view_flip": form.get("view_flip") == "on",
        "confirm_status": "unknown" if result == "unknown" or not (player_id or participants) else "confirmed",
    }, participants


def lineup_for_action(rally: dict, plan: TeamPlan, state, manual: bool) -> tuple[list, str]:
    if manual:
        return snapshot_lineup(plan, state), "manual"
    if rally.get("lineup"):
        source = "live" if rally.get("status") == "open" else "historical"
        return rally["lineup"], source
    return [], "unknown"


def player_rows(plan: TeamPlan, actions: list[dict], membership: dict[int, list[str]]) -> list[dict]:
    by_player: dict[str, list[dict]] = {player_id: [] for player_id in plan.players}
    unknown: list[dict] = []
    for action in actions:
        if action.get("team_side") != "us":
            continue
        owners = membership.get(action["id"]) or ([action["player_id"]] if action.get("player_id") else [])
        if action.get("skill") == "block":
            owners = membership.get(action["id"], [])
        if not owners:
            unknown.append(action)
            continue
        for player_id in owners:
            if player_id in by_player:
                by_player[player_id].append(action)
            else:
                unknown.append(action)
    rows = []
    for player_id, player in plan.players.items():
        own = by_player[player_id]
        passes = [item for item in own if item["skill"] == "pass"]
        attacks = [item for item in own if item["skill"] == "attack"]
        rows.append(
            {
                "id": player_id,
                "name": player.name,
                "jersey": player.jersey,
                "passing": pass_summary(passes),
                "attack": attack_summary(attacks),
                "block": block_summary(actions, membership, player_id),
            }
        )
    lonely_blocks = [item for item in actions if item.get("skill") == "block" and not membership.get(item["id"])]
    block_counts = {code: sum(1 for item in lonely_blocks if item.get("result") == code) for code in BLOCK_RESULT}
    rows.append(
        {
            "id": "",
            "name": "球员未知",
            "jersey": "",
            "passing": pass_summary([item for item in unknown if item["skill"] == "pass"]),
            "attack": attack_summary([item for item in unknown if item["skill"] == "attack"]),
            "block": {
                "events": len(lonely_blocks),
                "counts": block_counts,
                "kills": block_counts["kill"],
                "unknown": block_counts["unknown"],
            },
        }
    )
    return rows


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
