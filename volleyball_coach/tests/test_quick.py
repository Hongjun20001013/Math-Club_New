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
        data={"opponent": "测试", "mode": "light", "rotation": rotation, "serving": serving, "pair_id": "pair-d"},
    )
    return started.headers["Location"]


def _tap(client, url, tap, value, token, **extra):
    data = {"tap": tap, "value": value, "token": token, "scope": "set"}
    data.update(extra)
    return client.post(f"{url}/quick", data=data, follow_redirects=True)


def _score(html: str) -> tuple[str, str]:
    ours = html.split("<b>", 1)[1].split("</b>", 1)[0]
    theirs = html.split("<b>", 2)[2].split("</b>", 1)[0]
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


def test_receive_kill_is_four_taps_and_undo_restores(tmp_path):
    client = _client(tmp_path)
    url = _start(client, serving="them")
    page = client.get(url).get_data(as_text=True)
    assert "Leo" in page
    assert "到位" not in page.split('class="pad"', 1)[1].split('class="stats"', 1)[0]

    page = _tap(client, url, "pass_player", "leo", "c1-pass").get_data(as_text=True)
    assert "到位" in page
    page = _tap(client, url, "pass_quality", "in_system", "c1-quality").get_data(as_text=True)
    assert "Andy A" in page
    assert "扣球得分" not in page.split('class="pad"', 1)[1].split("最近一球", 1)[0]
    page = _tap(client, url, "attack_player", "andy-a", "c1-hitter").get_data(as_text=True)
    assert "扣球得分" in page
    page = _tap(client, url, "attack_result", "kill", "c1-kill").get_data(as_text=True)
    assert _score(page) == ("1", "0")
    assert _rotation(page) == "2"
    assert "1扣1中" in page
    assert "Leo" in page and "1 到位" in page
    assert "已得分" in page

    again = _tap(client, url, "attack_result", "kill", "c1-kill")
    assert _score(again.get_data(as_text=True)) == ("1", "0")

    undone = client.post(f"{url}/undo", follow_redirects=True).get_data(as_text=True)
    assert _score(undone) == ("0", "0")
    assert _rotation(undone) == "1"
    assert "1扣1中" not in undone


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
