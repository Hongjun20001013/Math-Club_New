from volleyball_coach.app import create_app
from volleyball_coach.quick import board_for
from volleyball_coach.seed import MENS_TEAM_ID


def _client(tmp_path):
    app = create_app(tmp_path / "coach.db")
    app.config["TESTING"] = True
    return app.test_client()


def _start(client, *, rotation="1", serving="them"):
    started = client.post(
        f"/teams/{MENS_TEAM_ID}/matches",
        data={
            "opponent": "测试",
            "mode": "light",
            "rotation": rotation,
            "serving": serving,
            "pair_id": "pair-d",
            "track_rotation": "on",
        },
    )
    return started.headers["Location"]


def _tap(client, url, tap, value, token, **extra):
    data = {"tap": tap, "value": value, "token": token, "scope": "set"}
    data.update(extra)
    return client.post(f"{url}/quick", data=data, follow_redirects=True)


def _score(html: str) -> tuple[str, str]:
    ours = html.split('class="score-us">', 1)[1].split("<", 1)[0]
    theirs = html.split('class="score-them">', 1)[1].split("<", 1)[0]
    return ours.strip(), theirs.strip()


def _rotation(html: str) -> str:
    return html.split('<span class="pill">R', 1)[1][:1]


def test_rates_match_the_written_formulas():
    rally_ids = [f"r{index}" for index in range(13)]
    rallies = [
        {"id": rally_id, "status": "scored", "set_index": 1, "completeness": "complete"}
        for rally_id in rally_ids
    ]
    actions = []
    for index, rally_id in enumerate(rally_ids):
        result = "kill" if index < 10 else ("error" if index == 10 else "in_play")
        actions.append(
            {
                "rally_id": rally_id,
                "ord": 1,
                "kind": "attack",
                "result": result,
                "player_id": "eric",
                "side": "us",
                "start": "",
                "line": "",
                "count_only": 0,
                "tag": "",
            }
        )
    board = board_for(rallies, actions, {"eric": "Eric"}, scope="match", set_index=1)
    row = board["attacks"][0]
    assert row["phrase"].startswith("13扣10中")
    assert row["errors"] == 1
    assert row["rate"] == "76.9%"
    assert row["eff"] == "69.2%"

    serves = []
    serve_rally = []
    sequence = ["ace", "ace", "out", "out", "out", "in_system", "in_system", "error", "unknown", "unknown"]
    for index, result in enumerate(sequence):
        rally_id = f"s{index}"
        serve_rally.append({"id": rally_id, "status": "scored", "set_index": 1, "completeness": "complete"})
        serves.append(
            {
                "rally_id": rally_id,
                "ord": 1,
                "kind": "serve",
                "result": result,
                "player_id": "leo",
                "side": "us",
                "start": "",
                "line": "",
                "count_only": 0,
                "tag": "",
            }
        )
    serve_board = board_for(serve_rally, serves, {"leo": "Leo"}, scope="set", set_index=1)
    serve = serve_board["serves"][0]
    assert serve["threat_ratio"] == "5/8"
    assert serve["in_ratio"] == "9/10"


def _cell(client, url, kind, value, token, player="", start=""):
    return client.post(
        f"{url}/quick",
        data={
            "tap": "cell",
            "kind": kind,
            "value": value,
            "player": player,
            "start": start,
            "token": token,
            "scope": "set",
        },
        follow_redirects=True,
    )


def test_receive_kill_is_two_cells_and_undo_keeps_the_pass(tmp_path):
    client = _client(tmp_path)
    url = _start(client, serving="them")
    page = client.get(url).get_data(as_text=True)
    assert "Leo" in page and "到位" in page and "扣死" in page

    _cell(client, url, "pass", "in_system", "c1-pass", player="leo")
    page = _cell(client, url, "attack", "kill", "c1-kill", player="andy-a").get_data(as_text=True)
    assert _score(page) == ("1", "0")
    assert _rotation(page) == "2"
    assert "1扣1中" in page
    assert "1 到位" in page
    assert "已得分" in page

    again = _cell(client, url, "attack", "kill", "c1-kill", player="andy-a")
    assert _score(again.get_data(as_text=True)) == ("1", "0")

    undone = client.post(
        f"{url}/quick",
        data={"tap": "undo_touch", "token": "c1-undo"},
        follow_redirects=True,
    ).get_data(as_text=True)
    assert _score(undone) == ("0", "0")
    assert _rotation(undone) == "1"
    assert "1扣1中" not in undone
    assert "Leo 一传到位" in undone


def test_serve_error_is_one_tap(tmp_path):
    client = _client(tmp_path)
    url = _start(client, serving="us")
    page = client.get(url).get_data(as_text=True)
    assert "发球失误" in page
    assert "Michael" in page
    done = _tap(client, url, "serve", "error", "ace-1").get_data(as_text=True)
    assert _score(done) == ("0", "1")
    assert "失误 1" in done
    assert "ACE 0" in done


def test_two_swings_and_unknown_pass(tmp_path):
    client = _client(tmp_path)
    url = _start(client, serving="them")
    _tap(client, url, "pass_player", "eric", "c2-p")
    _tap(client, url, "pass_quality", "unknown", "c2-q")
    _tap(client, url, "attack_player", "andy-a", "c2-a")
    _tap(client, url, "attack_result", "in_play", "c2-live")
    page = _tap(client, url, "attack_result", "error", "c2-err").get_data(as_text=True)
    assert _score(page) == ("0", "1")
    assert "2扣0中1失误" in page
    assert "未知 1" in page
    assert "1扣" not in page.split("Andy A", 1)[1].split("</details>", 1)[0]


def test_same_rally_keeps_touch_order(tmp_path):
    client = _client(tmp_path)
    url = _start(client, serving="them")
    steps = [
        ("pass_player", "vitas", "c3-1"),
        ("pass_quality", "in_system", "c3-2"),
        ("choose", "opp", "c3-3"),
        ("opp_start", "4", "c3-4"),
        ("opp_result", "in_play", "c3-5"),
        ("choose", "defense", "c3-6"),
        ("defense_player", "vitas", "c3-7"),
        ("defense_result", "dig", "c3-8"),
        ("choose", "attack", "c3-9"),
        ("attack_player", "leo", "c3-10"),
        ("attack_result", "in_play", "c3-11"),
        ("choose", "defense", "c3-12"),
        ("defense_player", "leo", "c3-13"),
        ("defense_result", "dig", "c3-14"),
        ("choose", "block", "c3-15"),
        ("block_player", "harvey", "c3-16"),
        ("block_result", "rebound", "c3-17"),
        ("attack_player", "michael", "c3-18"),
        ("attack_tag", "dump", "c3-19"),
        ("attack_result", "in_play", "c3-20"),
        ("score", "them", "c3-21"),
    ]
    page = ""
    for tap, value, token in steps:
        page = _tap(client, url, tap, value, token).get_data(as_text=True)
    assert _score(page) == ("0", "1")
    story = page.split("最近一球", 1)[1].split("</p>", 1)[0]
    assert story.index("Vitas 一传到位") < story.index("对方四号位没打死")
    assert story.index("Vitas 起球") < story.index("Leo 没打死")
    assert story.index("Leo 起球") < story.index("Harvey 拦回")
    assert story.index("Harvey 拦回") < story.index("Michael 探头")
    assert "起球 1" in page
    assert "拦回 1" in page


def test_serve_disrupts_then_block_touch_then_attack_point(tmp_path):
    client = _client(tmp_path)
    url = _start(client, serving="us")
    _tap(client, url, "serve_player", "harvey", "c4-who")
    _tap(client, url, "serve", "out", "c4-serve")
    _tap(client, url, "choose", "block", "c4-switch")
    _tap(client, url, "block_player", "michael", "c4-block")
    _tap(client, url, "block_result", "rebound", "c4-touch")
    _tap(client, url, "attack_player", "andy-a", "c4-hit")
    page = _tap(client, url, "attack_result", "kill", "c4-kill").get_data(as_text=True)
    assert _score(page) == ("1", "0")
    assert "Harvey" in page and "威胁 1/1" in page
    assert "ACE 0" in page
    assert "拦回 1" in page
    assert "得分 0" in page
    assert "1扣1中" in page


def test_opponent_angle_is_listed_without_a_jersey(tmp_path):
    client = _client(tmp_path)
    url = _start(client, rotation="2", serving="us")
    page = client.get(url).get_data(as_text=True)
    assert "Leo" in page and "发球" in page
    _tap(client, url, "serve", "in_system", "c5-serve")
    _tap(client, url, "opp_start", "4", "c5-start")
    _tap(client, url, "opp_line", "sharp", "c5-line")
    page = _tap(client, url, "opp_result", "kill", "c5-kill").get_data(as_text=True)
    assert _score(page) == ("0", "1")
    block = page.split('id="opp-4"', 1)[1].split("</details>", 1)[0]
    assert "四号位" in block
    assert "1扣1中" in block
    assert "小斜线 1" in block
    assert "未记号码" in page or "不猜人" in page
    assert f'href="#rally-' in block


def test_pass_error_does_not_ask_for_an_attack(tmp_path):
    client = _client(tmp_path)
    url = _start(client, serving="them")
    _tap(client, url, "pass_player", "leo", "err-p")
    page = _tap(client, url, "pass_quality", "error", "err-q").get_data(as_text=True)
    pad = page.split('class="pad"', 1)[1].split('class="stats"', 1)[0]
    assert "扣球得分" not in pad
    assert _score(page) == ("0", "1")
    assert "直接失分" in page


def test_editing_pass_quality_does_not_move_the_score(tmp_path):
    client = _client(tmp_path)
    url = _start(client, serving="them")
    _tap(client, url, "pass_player", "leo", "ed-p")
    page = _tap(client, url, "pass_quality", "in_system", "ed-q").get_data(as_text=True)
    _tap(client, url, "attack_player", "andy-a", "ed-a")
    page = _tap(client, url, "attack_result", "kill", "ed-k").get_data(as_text=True)
    action_id = page.split('name="action_id" value="', 1)[1].split('"', 1)[0]
    edited = client.post(
        f"{url}/quick",
        data={"tap": "edit_quality", "value": "half", "action_id": action_id, "token": "ed-edit", "scope": "set"},
        follow_redirects=True,
    ).get_data(as_text=True)
    assert _score(edited) == ("1", "0")
    assert _rotation(edited) == "2"
    assert "半到位 1" in edited


def test_score_only_is_not_an_attack_rate(tmp_path):
    client = _client(tmp_path)
    url = _start(client, serving="them")
    page = _tap(client, url, "flag_score", "us", "flag-1").get_data(as_text=True)
    assert _score(page) == ("1", "0")
    assert "未记录技术动作" in page
    assert "待补或只记了比分 1 球" in page
    assert "1扣" not in page


def test_quick_start_without_slots_records_cells(tmp_path):
    client = _client(tmp_path)
    created = client.post("/teams", data={"name": "小队", "names": "Eric Leo Vitas", "start": "1"})
    assert created.status_code == 302
    url = created.headers["Location"]
    page = client.get(url).get_data(as_text=True)
    assert "发球未记" in page
    assert "Eric" in page and "到位" in page
    assert '<span class="pill">R' not in page
    _cell(client, url, "pass", "in_system", "q-pass", player=_player_id(client, url, "Leo"))
    page = _cell(client, url, "attack", "kill", "q-kill", player=_player_id(client, url, "Eric")).get_data(as_text=True)
    assert _score(page) == ("1", "0")
    assert "1扣1中" in page
    assert "1 到位" in page


def test_count_only_and_two_digs_do_not_invent_errors(tmp_path):
    client = _client(tmp_path)
    url = _start(client, serving="them")
    _cell(client, url, "attack", "count", "n-count", player="vitas")
    page = _cell(client, url, "score", "them", "n-score").get_data(as_text=True)
    assert _score(page) == ("0", "1")
    vitas = page.split('id="atk-vitas"', 1)[1].split("</details>", 1)[0]
    assert "1扣0中" in vitas
    assert "只计次数 1" in vitas
    assert "1失误" not in vitas

    _cell(client, url, "defense", "dig_spike", "d1", player="leo")
    _cell(client, url, "defense", "dig_spike", "d2", player="leo")
    page = _cell(client, url, "score", "us", "d-score").get_data(as_text=True)
    stats = page.split('class="stats"', 1)[1]
    assert "本范围还没有接发" in stats
    assert "防起 2" in page or "防起 1" in page


def test_two_identical_attacks_are_both_kept(tmp_path):
    client = _client(tmp_path)
    url = _start(client, serving="them")
    _cell(client, url, "attack", "in_play", "same-1", player="andy-a")
    _cell(client, url, "score", "them", "same-1-end")
    _cell(client, url, "attack", "in_play", "same-2", player="andy-a")
    page = _cell(client, url, "score", "them", "same-2-end").get_data(as_text=True)
    assert "2扣0中" in page


def test_opponent_line_shows_on_the_pause_card(tmp_path):
    client = _client(tmp_path)
    url = _start(client, serving="them")
    _cell(client, url, "opp", "kill", "opp-1", start="4")
    page = client.post(
        f"{url}/quick",
        data={"tap": "mark_line", "value": "sharp", "token": "opp-line"},
        follow_redirects=True,
    ).get_data(as_text=True)
    block = page.split('id="opp-4"', 1)[1].split("</details>", 1)[0]
    assert "四号位" in block
    assert "小斜线 1" in block
    assert "仅失分片段" in block
    assert 'href="#rally-' in block


def test_score_only_cell_stays_out_of_the_attack_rate(tmp_path):
    client = _client(tmp_path)
    url = _start(client, serving="them")
    page = _cell(client, url, "score", "us", "only-1").get_data(as_text=True)
    assert _score(page) == ("1", "0")
    assert "未记录技术动作" in page
    assert "待补或只记了比分 1 球" in page
    assert "1扣" not in page


def test_eric_sets_add_up_and_set_two_edits_leave_set_one(tmp_path):
    client = _client(tmp_path)
    url = _start(client, serving="them")
    for index in range(4):
        _cell(client, url, "attack", "kill", f"s1-k{index}", player="eric")
    page = _cell(client, url, "attack", "error", "s1-e", player="eric").get_data(as_text=True)
    assert "5扣4中1失误" in page
    client.post(f"{url}/next-set", data={"rotation": "1", "serving": "them"})
    for index in range(6):
        _cell(client, url, "attack", "kill", f"s2-k{index}", player="eric")
    for index in range(2):
        _cell(client, url, "pass", "in_system", f"s2-p{index}", player="leo")
        _cell(client, url, "attack", "in_play", f"s2-i{index}", player="eric")
        _cell(client, url, "score", "them", f"s2-end{index}")
    page = client.get(f"{url}?scope=set").get_data(as_text=True)
    assert "8扣6中" in page
    assert "5扣4中1失误" not in page
    whole = client.get(f"{url}?scope=match").get_data(as_text=True)
    assert "13扣10中1失误" in whole
    assert "76.9%" in whole
    assert "69.2%" in whole
    action_id = page.split('name="action_id" value="', 1)[1].split('"', 1)[0]
    client.post(
        f"{url}/quick",
        data={"tap": "edit_quality", "value": "half", "action_id": action_id, "token": "s2-edit"},
        follow_redirects=True,
    )
    after = client.get(f"{url}?scope=match").get_data(as_text=True)
    assert "13扣10中1失误" in after
    assert "76.9%" in after
    assert "69.2%" in after
    current = client.get(f"{url}?scope=set").get_data(as_text=True)
    assert "8扣6中" in current
    assert "5扣4中1失误" not in current


def test_summary_pdf_uses_the_same_attack_rates(tmp_path):
    from volleyball_coach.quick import build_digest
    from volleyball_coach.summary_pdf import render_summary_pdf

    rally_ids = [f"r{index}" for index in range(13)]
    rallies = [
        {
            "id": rally_id,
            "status": "scored",
            "set_index": 1 if index < 5 else 2,
            "completeness": "complete",
            "winner": "us" if index != 10 else "them",
            "score_us_before": index,
            "score_them_before": 0,
            "point_seq": index + 1,
        }
        for index, rally_id in enumerate(rally_ids)
    ]
    actions = []
    for index, rally_id in enumerate(rally_ids):
        result = "kill" if index < 10 else ("error" if index == 10 else "in_play")
        actions.append(
            {
                "rally_id": rally_id,
                "ord": 1,
                "kind": "attack",
                "result": result,
                "player_id": "eric",
                "side": "us",
                "start": "",
                "line": "",
                "count_only": 0,
                "tag": "",
            }
        )
    digest = build_digest(rallies, actions, {"eric": "Eric"})
    assert digest["team"]["phrase"].startswith("13扣10中")
    assert digest["team"]["errors"] == 1
    assert digest["team"]["rate"] == "76.9%"
    assert digest["team"]["eff"] == "69.2%"
    assert digest["sets"][0]["team"]["phrase"].startswith("5扣")
    assert "上场后胜率更高" not in repr(digest)
    payload = render_summary_pdf(digest, team="男排", opponent="红队")
    assert payload.startswith(b"%PDF")
    import pymupdf

    text = "\n".join(page.get_text() for page in pymupdf.open(stream=payload, filetype="pdf"))
    assert "13扣10中" in text
    assert "76.9%" in text
    assert "69.2%" in text
    assert "上场后胜率更高" not in text

    client = _client(tmp_path)
    url = _start(client, serving="them")
    _cell(client, url, "pass", "in_system", "pdf-pass", player="leo")
    _cell(client, url, "attack", "kill", "pdf-kill", player="andy-a")
    page = client.get(f"{url}/summary").get_data(as_text=True)
    assert "下载数据汇总 PDF" in page
    assert "1扣1中" in page
    assert "1到位" in page
    downloaded = client.get(f"{url}/summary.pdf")
    assert downloaded.mimetype == "application/pdf"
    assert downloaded.data.startswith(b"%PDF")
    finished = client.post(f"{url}/finish", follow_redirects=True)
    assert "下载数据汇总 PDF" in finished.get_data(as_text=True)


def _player_id(client, url, name: str) -> str:
    page = client.get(url).get_data(as_text=True)
    marker = f'aria-label="{name} 到位"'
    chunk = page.split(marker, 1)[0]
    return chunk.rsplit('name="player" value="', 1)[1].split('"', 1)[0]
