from volleyball_coach.app import create_app
from volleyball_coach.seed import MENS_TEAM_ID


def _client(tmp_path):
    app = create_app(tmp_path / "coach.db")
    app.config["TESTING"] = True
    return app.test_client()


def _rotation(html: str) -> str:
    return html.split('<span class="pill">R', 1)[1][:1]


def _our_score(html: str) -> str:
    return html.split('class="score-us">', 1)[1].split("<", 1)[0]


def test_other_team_does_not_inherit_mens_roster_or_rules(tmp_path):
    client = _client(tmp_path)
    home = client.get("/")
    assert "男排" in home.get_data(as_text=True)
    assert "不会把男排" in home.get_data(as_text=True)

    created = client.post(
        "/teams",
        data={"name": "女排", "preset": "blank", "notes": "自己的规则"},
        follow_redirects=True,
    )
    page = created.get_data(as_text=True)
    assert "女排" in page
    assert "Michael" not in page
    assert "禁止后排进攻" not in page
    assert "后排可以进攻" in page

    special = client.post(
        "/teams",
        data={"name": "U16", "preset": "local_special"},
        follow_redirects=True,
    )
    special_page = special.get_data(as_text=True)
    assert "U16" in special_page
    assert "Michael" not in special_page
    assert "禁止后排进攻" not in special_page
    assert "没有复制男排球员" in special_page


def test_live_rotation_illegal_sub_undo_and_report(tmp_path):
    client = _client(tmp_path)
    board = client.get(f"/teams/{MENS_TEAM_ID}/board")
    board_html = board.get_data(as_text=True)
    assert 'id="r2"' in board_html
    r2 = board_html.split('id="r2"')[1].split('id="r3"')[0]
    assert 'data-front="Vitas,Andy A,Eric"' in r2
    assert "Leo" not in r2.split("前排：")[1].split("</p>")[0]
    assert "已经转到后排" in board_html

    started = client.post(
        f"/teams/{MENS_TEAM_ID}/matches",
        data={"opponent": "红队", "mode": "light", "rotation": "1", "serving": "them", "pair_id": "pair-d", "track_rotation": "on"},
    )
    assert started.status_code == 302
    match_url = started.headers["Location"]
    live = client.get(match_url)
    live_html = live.get_data(as_text=True)
    assert "对方发球" in live_html
    assert "对方轮次：未知" in live_html
    assert "Harvey" in live_html and "没有锁定" in live_html

    swapped = client.post(f"{match_url}/sub", data={"out": "leo", "in": "harvey"}, follow_redirects=True)
    swapped_html = swapped.get_data(as_text=True)
    assert "已确认 Harvey 上场" in swapped_html
    assert "跨配对" not in swapped_html
    assert _rotation(swapped_html) == "1"

    moved = client.post(f"{match_url}/point", data={"winner": "us"}, follow_redirects=True)
    moved_html = moved.get_data(as_text=True)
    assert _rotation(moved_html) == "2"
    assert _our_score(moved_html) == "1"

    client.post(f"{match_url}/undo", follow_redirects=True)
    restored = client.get(match_url).get_data(as_text=True)
    assert _rotation(restored) == "1"
    assert _our_score(restored) == "0"

    third = client.post(
        f"/teams/{MENS_TEAM_ID}/matches",
        data={"opponent": "蓝队", "mode": "light", "rotation": "3", "serving": "us", "pair_id": "pair-d", "track_rotation": "on"},
    )
    third_url = third.headers["Location"]
    subbed = client.post(f"{third_url}/sub", data={"out": "andy-a", "in": "d"}, follow_redirects=True)
    assert "已确认 D 上场" in subbed.get_data(as_text=True)
    assert "Andy A" in subbed.get_data(as_text=True)

    review = client.get(f"{third_url}/review")
    assert "替补：D" in review.get_data(as_text=True)
    client.post(
        f"{third_url}/rallies",
        data={
            "set_number": "1",
            "rotation": "3",
            "serving_side": "them",
            "winner": "unknown",
            "sample_scope": "sample",
            "pass_quality": "unknown",
            "server_label": "",
            "target_type": "",
            "target_label": "",
            "actual_receiver": "",
            "actual_zone": "",
            "video_timestamp": "",
            "note": "",
            "attach_lineup": "on",
        },
    )
    report = client.get(f"{third_url}/report")
    report_html = report.get_data(as_text=True)
    assert "不能单独归因" in report_html
    assert "上场后胜率更高" not in report_html
    assert "胜率更高" not in report_html
    payload = client.get(f"{third_url}/report.json").get_json()
    rally = payload["rallies"][0]
    assert rally["pass_quality"] == "unknown"
    assert rally["winner"] == "unknown"
    assert payload["opponent_rotation"] is None
    assert "D" in rally["bench"]

    reopened_html = _client(tmp_path).get(third_url).get_data(as_text=True)
    assert "已确认 D 上场" not in reopened_html
    assert _rotation(reopened_html) == "3"
    assert "<strong>D</strong>" in reopened_html


def test_starting_slots_are_on_the_match_page(tmp_path):
    client = _client(tmp_path)
    created = client.post("/teams", data={"name": "小队", "preset": "blank"})
    team_url = created.headers["Location"]
    names = ["Leo", "Vitas", "Andy", "Junhao", "Michael", "Eric"]
    for name in names:
        added = client.post(f"{team_url}/players", data={"name": name, "role": "outside"}, follow_redirects=True)
        assert name in added.get_data(as_text=True)
    page = client.get(f"{team_url}/matches/new").get_data(as_text=True)
    assert "首发六个槽" in page
    assert "1 右后" in page
    assert "六个槽还没选满" not in page
    started_empty = client.post(
        f"{team_url}/matches",
        data={"opponent": "白队", "mode": "light", "rotation": "1", "serving": "them"},
    )
    assert started_empty.status_code == 302
    roster = client.get(team_url).get_data(as_text=True)
    ids = []
    for name in names:
        marker = f"保存 {name}"
        chunk = roster.split(marker, 1)[0]
        ids.append(chunk.split('action="/teams/')[-1].split("/players/", 1)[1].split('"', 1)[0])
    saved = client.post(
        f"{team_url}/starters",
        data={f"slot_{slot}": player_id for slot, player_id in enumerate(ids, start=1)},
        follow_redirects=True,
    )
    saved_html = saved.get_data(as_text=True)
    assert "六个首发槽已记下" in saved_html
    started = client.post(
        f"{team_url}/matches",
        data={"opponent": "红队", "mode": "light", "rotation": "1", "serving": "them"},
    )
    assert started.status_code == 302


def test_roster_position_is_set_before_recording(tmp_path):
    client = _client(tmp_path)
    home = client.get("/").get_data(as_text=True)
    assert "先定名字和位置" in home
    andy = home.split('aria-label="Andy A 的位置"', 1)[1].split("</select>", 1)[0]
    assert 'value="middle" selected' in andy
    assert "副攻" in andy
    started = client.post(
        f"/teams/{MENS_TEAM_ID}/roster",
        data={
            "player_id": "andy-a",
            "player_name": "Andy A",
            "player_role": "middle",
            "new_name": "Sky",
            "new_role": "setter",
            "start": "1",
        },
    )
    assert started.status_code == 302
    page = client.get(started.headers["Location"]).get_data(as_text=True)
    assert "Sky" in page and "二传" in page
    assert "Andy A" in page and "副攻" in page
    roster = client.get(f"/teams/{MENS_TEAM_ID}").get_data(as_text=True)
    assert "Andy A · 首发槽 3" in roster
    assert "几号位" in roster


def test_team_name_can_be_changed(tmp_path):
    client = _client(tmp_path)
    created = client.post("/teams", data={"name": "1"})
    assert created.status_code == 302
    team_url = created.headers["Location"]
    saved = client.post(f"{team_url}/roster", data={"team_name": "一队"}, follow_redirects=True)
    page = saved.get_data(as_text=True)
    assert 'name="team_name" value="一队"' in page


def test_each_set_keeps_its_own_court(tmp_path):
    client = _client(tmp_path)
    started = client.post(
        f"/teams/{MENS_TEAM_ID}/roster",
        data={"player_id": "leo", "player_name": "Leo", "player_role": "outside", "start": "1"},
    )
    url = started.headers["Location"]
    client.post(f"{url}/court", data={"player_id": ["leo", "andy-a"], "sheet": "attack"})
    page = client.get(f"{url}?sheet=attack").get_data(as_text=True)
    assert "这一局上场：Leo、Andy A" in page
    main, bench = page.split("没上场", 1)
    assert "Leo" in main and "Andy A" in main
    assert "Harvey" in bench
    nxt = client.post(f"{url}/next-set", data={"rotation": "1", "serving": "them"}, follow_redirects=True)
    body = nxt.get_data(as_text=True)
    assert "第 2 局" in body
    assert 'value="leo" checked' in body
    assert 'value="andy-a" checked' in body
    harvey = body.split('value="harvey"', 1)[1].split(">", 1)[0]
    assert "checked" not in harvey


def test_team_player_match_and_note_can_be_deleted(tmp_path):
    client = _client(tmp_path)
    created = client.post("/teams", data={"name": "临时队", "names": "Isa"})
    team_url = created.headers["Location"]
    client.post(f"{team_url}/delete")
    assert "临时队" in client.get("/").get_data(as_text=True)
    started = client.post(f"{team_url}/roster", data={"team_name": "临时队", "start": "1"})
    match_url = started.headers["Location"]
    removed = client.post(f"{team_url}/delete", data={"confirm": "1"}, follow_redirects=True)
    page = removed.get_data(as_text=True)
    assert 'name="team_name" value="临时队"' not in page
    assert "男排" in page
    assert client.get(team_url).status_code == 404
    assert client.get(match_url).status_code == 404

    client.post(f"/teams/{MENS_TEAM_ID}/roster", data={"new_name": "Sky", "new_role": "libero"})
    home = client.get("/").get_data(as_text=True)
    player_id = home.split('value="Sky"', 1)[0].split('name="player_id" value="')[-1].split('"', 1)[0]
    client.post(f"/teams/{MENS_TEAM_ID}/players/{player_id}/delete")
    assert "Sky" in client.get("/").get_data(as_text=True)
    client.post(f"/teams/{MENS_TEAM_ID}/players/{player_id}/delete", data={"confirm": "1"})
    after = client.get("/").get_data(as_text=True)
    assert 'value="Sky"' not in after
    assert "Leo" in after

    started = client.post(
        f"/teams/{MENS_TEAM_ID}/roster",
        data={"player_id": "leo", "player_name": "Leo", "player_role": "outside", "start": "1"},
    )
    match_url = started.headers["Location"]
    client.post(f"{match_url}/delete", data={"confirm": "1"})
    assert client.get(match_url).status_code == 404
    assert client.get(f"/teams/{MENS_TEAM_ID}").status_code == 200

    noted = client.post(
        f"/teams/{MENS_TEAM_ID}/abilities",
        data={"player_id": "leo", "skill": "今晚单独的观察", "label": "stable"},
        follow_redirects=True,
    ).get_data(as_text=True)
    assert "今晚单独的观察" in noted
    action = noted.split("今晚单独的观察", 1)[1].split('action="', 1)[1].split('"', 1)[0]
    client.post(action)
    assert "今晚单独的观察" in client.get(f"/teams/{MENS_TEAM_ID}").get_data(as_text=True)
    client.post(action, data={"confirm": "1"}, follow_redirects=True)
    assert "今晚单独的观察" not in client.get(f"/teams/{MENS_TEAM_ID}").get_data(as_text=True)


def test_dictionary_and_drills_pages(tmp_path):
    client = _client(tmp_path)
    dictionary = client.get("/dictionary").get_data(as_text=True)
    assert "未知不记成 0" in dictionary
    assert "哪一轮接发最困难" in dictionary
    drills = client.get("/drills").get_data(as_text=True)
    assert "失败" not in drills
    assert "通过" in drills
