from volleyball_coach.app import create_app
from volleyball_coach.seed import MENS_TEAM_ID


def _client(tmp_path):
    app = create_app(tmp_path / "coach.db")
    app.config["TESTING"] = True
    return app.test_client()


def _rotation(html: str) -> str:
    return html.split('<span class="pill">R', 1)[1][:1]


def _our_score(html: str) -> str:
    return html.split("<b>", 1)[1].split("</b>", 1)[0]


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
    assert 'name="no_back_row_attack"' in page
    assert 'name="no_back_row_attack" checked' not in page

    special = client.post(
        "/teams",
        data={"name": "U16", "preset": "local_special"},
        follow_redirects=True,
    )
    special_page = special.get_data(as_text=True)
    assert "U16" in special_page
    assert "Michael" not in special_page
    assert 'name="no_back_row_attack" checked' in special_page
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
        data={"opponent": "红队", "mode": "light", "rotation": "1", "serving": "them", "pair_id": "pair-d"},
    )
    assert started.status_code == 302
    match_url = started.headers["Location"]
    live = client.get(match_url)
    live_html = live.get_data(as_text=True)
    assert "对方发球" in live_html
    assert "对方轮次：未知" in live_html
    assert "Harvey" in live_html and "没有锁定" in live_html

    blocked = client.post(f"{match_url}/sub", data={"out": "leo", "in": "harvey"}, follow_redirects=True)
    blocked_html = blocked.get_data(as_text=True)
    assert "跨配对" in blocked_html
    assert _rotation(blocked_html) == "1"

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
        data={"opponent": "蓝队", "mode": "light", "rotation": "3", "serving": "us", "pair_id": "pair-d"},
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


def test_dictionary_and_drills_pages(tmp_path):
    client = _client(tmp_path)
    dictionary = client.get("/dictionary").get_data(as_text=True)
    assert "未知不记成 0" in dictionary
    assert "哪一轮接发最困难" in dictionary
    drills = client.get("/drills").get_data(as_text=True)
    assert "失败" not in drills
    assert "通过" in drills
