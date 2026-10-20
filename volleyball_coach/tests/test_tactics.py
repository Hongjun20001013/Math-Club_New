import json
import sqlite3

from volleyball_coach.seed import MENS_TEAM_ID
from volleyball_coach.tests.test_app import _client, _our_score


def _arg(location: str, key: str) -> str:
    return location.split(f"{key}=")[1].split("&")[0]


def _pin(html: str, slot: str) -> str:
    return html.split(f'data-slot="{slot}"', 1)[1].split(">", 1)[0]


def test_lineups_stay_separate_and_drag_keeps_identity(tmp_path):
    client = _client(tmp_path)
    page = client.get(f"/teams/{MENS_TEAM_ID}/tactics")
    html = page.get_data(as_text=True)
    assert page.status_code == 200
    assert "没有正式自由人" in html
    assert "不会被改名为 libero" in html
    assert 'data-player="d"' not in html
    assert 'data-player="harvey"' not in html
    assert "Tang" not in html
    assert "示意站位" in html
    assert "已配置" in html and "待补充" in html and "存在冲突" in html
    assert "准备好了" not in html
    assert 'name="ready"' not in html

    copied = client.post(
        f"/teams/{MENS_TEAM_ID}/schemes/scheme-mens-62/copy",
        data={"name": "加强接发"},
        follow_redirects=False,
    )
    assert copied.status_code == 302
    copy_id = _arg(copied.headers["Location"], "scheme")
    client.post(
        f"/teams/{MENS_TEAM_ID}/schemes",
        data={
            "scheme_id": copy_id,
            "name": "加强接发",
            "slot_1": "michael",
            "slot_2": "vitas",
            "slot_3": "andy-a",
            "slot_4": "eric",
            "slot_5": "leo",
            "slot_6": "andy-b",
        },
        follow_redirects=True,
    )
    board = client.get(f"/teams/{MENS_TEAM_ID}/board").get_data(as_text=True)
    default_r2 = board.split('id="r2"')[1].split('id="r3"')[0]
    assert 'data-front="Vitas,Andy A,Eric"' in default_r2
    other = client.get(f"/teams/{MENS_TEAM_ID}/board?scheme={copy_id}").get_data(as_text=True)
    other_r2 = other.split('id="r2"')[1].split('id="r3"')[0]
    assert 'data-front="Leo,Andy A,Eric"' in other_r2

    made = client.post(
        f"/teams/{MENS_TEAM_ID}/tactics",
        data={"scheme_id": "scheme-mens-62", "name": "三人接发"},
        follow_redirects=False,
    )
    first_id = _arg(made.headers["Location"], "tactic")
    second = client.post(
        f"/teams/{MENS_TEAM_ID}/tactics",
        data={"scheme_id": "scheme-mens-62", "name": "保护主攻"},
        follow_redirects=False,
    )
    second_id = _arg(second.headers["Location"], "tactic")
    client.post(
        f"/teams/{MENS_TEAM_ID}/tactics/{first_id}/marks",
        data={"rotation": "1", "phase": "receive", "slot": "4", "player_id": "eric", "x": "11", "y": "22"},
        follow_redirects=True,
    )
    client.post(
        f"/teams/{MENS_TEAM_ID}/tactics/{first_id}/marks",
        data={"rotation": "1", "phase": "receive", "slot": "4", "player_id": "leo", "x": "3", "y": "4"},
        follow_redirects=True,
    )
    client.post(
        f"/teams/{MENS_TEAM_ID}/tactics/{first_id}/notes",
        data={"rotation": "1", "phase": "receive", "serve_target": "追四号位", "block_task": "", "cover_note": ""},
        follow_redirects=True,
    )
    first = client.get(f"/teams/{MENS_TEAM_ID}/tactics?tactic={first_id}&rotation=1&phase=receive").get_data(as_text=True)
    pin = _pin(first, "4")
    assert 'data-player="eric"' in pin
    assert 'data-x="11"' in pin and 'data-y="22"' in pin
    assert 'data-x="3"' not in pin
    assert 'data-status="已配置"' in first
    assert "追四号位" in first
    other_tactic = client.get(
        f"/teams/{MENS_TEAM_ID}/tactics?tactic={second_id}&rotation=1&phase=receive"
    ).get_data(as_text=True)
    other_pin = _pin(other_tactic, "4")
    assert 'data-x="11"' not in other_pin
    assert "追四号位" not in other_tactic

    trial = client.post(
        f"/teams/{MENS_TEAM_ID}/schemes/scheme-mens-62/copy",
        data={"name": "人员试验"},
        follow_redirects=False,
    )
    trial_id = _arg(trial.headers["Location"], "scheme")
    drifted = client.post(
        f"/teams/{MENS_TEAM_ID}/tactics",
        data={"scheme_id": trial_id, "name": "先摆位再换人"},
        follow_redirects=False,
    )
    drifted_id = _arg(drifted.headers["Location"], "tactic")
    client.post(
        f"/teams/{MENS_TEAM_ID}/tactics/{drifted_id}/marks",
        data={"rotation": "1", "phase": "receive", "slot": "4", "player_id": "eric", "x": "11", "y": "22"},
    )
    client.post(
        f"/teams/{MENS_TEAM_ID}/schemes",
        data={
            "scheme_id": trial_id,
            "name": "人员试验",
            "slot_1": "michael",
            "slot_2": "leo",
            "slot_3": "andy-a",
            "slot_4": "vitas",
            "slot_5": "eric",
            "slot_6": "andy-b",
        },
        follow_redirects=True,
    )
    conflict = client.get(f"/teams/{MENS_TEAM_ID}/tactics?tactic={drifted_id}&rotation=1&phase=receive").get_data(as_text=True)
    conflict_pin = _pin(conflict, "4")
    assert 'data-player="eric"' in conflict_pin
    assert 'data-status="存在冲突"' in conflict
    client.post(f"/teams/{MENS_TEAM_ID}/tactics/{drifted_id}/sync", follow_redirects=True)
    synced = client.get(f"/teams/{MENS_TEAM_ID}/tactics?tactic={drifted_id}&rotation=1&phase=receive").get_data(as_text=True)
    synced_pin = _pin(synced, "4")
    assert 'data-player="vitas"' in synced_pin
    assert 'data-x="11"' in synced_pin
    still = client.get(f"/teams/{MENS_TEAM_ID}/board").get_data(as_text=True)
    assert 'data-front="Vitas,Andy A,Eric"' in still.split('id="r2"')[1].split('id="r3"')[0]


def test_published_version_is_what_the_match_keeps(tmp_path):
    client = _client(tmp_path)
    made = client.post(
        f"/teams/{MENS_TEAM_ID}/tactics",
        data={"scheme_id": "scheme-mens-62", "name": "三人接发"},
        follow_redirects=False,
    )
    tactic_id = _arg(made.headers["Location"], "tactic")
    client.post(
        f"/teams/{MENS_TEAM_ID}/tactics/{tactic_id}/marks",
        data={"rotation": "1", "phase": "receive", "slot": "4", "player_id": "eric", "x": "11", "y": "22"},
    )
    client.post(f"/teams/{MENS_TEAM_ID}/tactics/{tactic_id}/publish", follow_redirects=True)
    refused = client.post(
        f"/teams/{MENS_TEAM_ID}/tactics/{tactic_id}/marks",
        data={"rotation": "1", "phase": "receive", "slot": "4", "player_id": "eric", "x": "19", "y": "19"},
        headers={"Accept": "application/json"},
    )
    assert refused.status_code == 409
    frozen = client.get(f"/teams/{MENS_TEAM_ID}/tactics?tactic={tactic_id}&rotation=1&phase=receive").get_data(as_text=True)
    assert 'data-x="11"' in _pin(frozen, "4")
    assert "已发布" in frozen

    started = client.post(
        f"/teams/{MENS_TEAM_ID}/matches",
        data={
            "opponent": "红队",
            "mode": "light",
            "rotation": "1",
            "serving": "them",
            "pair_id": "pair-d",
            "scheme_id": "scheme-mens-62",
            "tactic_id": tactic_id,
        },
    )
    assert started.status_code == 302
    match_url = started.headers["Location"]
    conn = sqlite3.connect(tmp_path / "coach.db")
    raw = conn.execute("SELECT tactic_json FROM matches").fetchone()[0]
    blob = json.loads(raw)
    assert any(
        int(mark["rotation"]) == 1 and mark["phase"] == "receive" and int(mark["slot"]) == 4 and abs(float(mark["x"]) - 11) < 0.01
        for mark in blob["marks"]
    )
    live = client.get(match_url).get_data(as_text=True)
    assert 'data-snapshot="1"' in live
    assert 'data-x="11"' in _pin(live, "4")
    assert _our_score(live) == "0"

    copied = client.post(
        f"/teams/{MENS_TEAM_ID}/tactics/{tactic_id}/duplicate",
        follow_redirects=False,
    )
    draft_id = _arg(copied.headers["Location"], "tactic")
    client.post(
        f"/teams/{MENS_TEAM_ID}/tactics/{draft_id}/marks",
        data={"rotation": "1", "phase": "receive", "slot": "4", "player_id": "eric", "x": "44", "y": "44"},
    )
    again = client.get(match_url).get_data(as_text=True)
    assert 'data-x="11"' in _pin(again, "4")
    assert 'data-x="44"' not in again
    raw_again = conn.execute("SELECT tactic_json FROM matches").fetchone()[0]
    assert abs(float(json.loads(raw_again)["marks"][0]["x"]) - 44) > 1 or "44" not in raw_again
    assert any(abs(float(mark["x"]) - 11) < 0.01 for mark in json.loads(raw_again)["marks"])

    client.post(
        f"{match_url}/actions",
        data={"team_side": "us", "skill": "attack", "result": "continue", "client_token": "rally", "player_id": "leo"},
    )
    client.post(f"{match_url}/point", data={"winner": "us", "plan_execution": "hit"}, follow_redirects=True)
    finished = client.get(match_url).get_data(as_text=True)
    assert "执行到 1" in finished
    assert "示意点" in finished
    assert "胜率更高" not in finished
    assert _our_score(finished) == "1"
    report = client.get(f"{match_url}/report").get_data(as_text=True)
    assert "当时选用的预案" in report
    assert "不能单独归因" in report
    assert "胜率更高" not in report


def test_lineup_system_can_be_five_one_or_custom(tmp_path):
    client = _client(tmp_path)
    board = client.get(f"/teams/{MENS_TEAM_ID}/board").get_data(as_text=True)
    assert "二传 Eric" in board.split('id="r4"')[1].split('id="r5"')[0]
    assert 'data-front="Vitas,Andy A,Eric"' in board.split('id="r2"')[1].split('id="r3"')[0]

    copied = client.post(
        f"/teams/{MENS_TEAM_ID}/schemes/scheme-mens-62/copy",
        data={"name": "五一试验"},
        follow_redirects=False,
    )
    copy_id = _arg(copied.headers["Location"], "scheme")
    made = client.post(
        f"/teams/{MENS_TEAM_ID}/tactics",
        data={"scheme_id": copy_id, "name": "五一站位"},
        follow_redirects=False,
    )
    tactic_id = _arg(made.headers["Location"], "tactic")
    client.post(
        f"/teams/{MENS_TEAM_ID}/tactics/{tactic_id}/marks",
        data={"rotation": "1", "phase": "receive", "slot": "4", "player_id": "eric", "x": "11", "y": "22"},
    )

    switched = client.post(
        f"/teams/{MENS_TEAM_ID}/schemes/{copy_id}/system",
        data={"system": "51", "setter": "michael", "tactic": tactic_id, "rotation": "4", "phase": "receive"},
        follow_redirects=True,
    )
    assert "体系已改成5-1。名单上原来的二传能力还留着。" in switched.get_data(as_text=True)
    preview = client.get(f"/teams/{MENS_TEAM_ID}/board?scheme={copy_id}").get_data(as_text=True)
    assert "二传 Michael" in preview.split('id="r4"')[1].split('id="r5"')[0]
    assert 'data-front="Vitas,Andy A,Eric"' in preview.split('id="r2"')[1].split('id="r3"')[0]
    default = client.get(f"/teams/{MENS_TEAM_ID}/board").get_data(as_text=True)
    assert "二传 Eric" in default.split('id="r4"')[1].split('id="r5"')[0]
    assert 'data-front="Vitas,Andy A,Eric"' in default.split('id="r2"')[1].split('id="r3"')[0]
    kept = client.get(f"/teams/{MENS_TEAM_ID}/tactics?tactic={tactic_id}&rotation=1&phase=receive").get_data(as_text=True)
    pin = _pin(kept, "4")
    assert 'data-player="eric"' in pin
    assert 'data-x="11"' in pin and 'data-y="22"' in pin

    custom = {
        "system": "custom",
        "tactic": tactic_id,
        "rotation": "1",
        "phase": "receive",
    }
    for number in range(1, 7):
        custom[f"setter_{number}"] = "leo"
    client.post(f"/teams/{MENS_TEAM_ID}/schemes/{copy_id}/system", data=custom, follow_redirects=True)
    custom_page = client.get(f"/teams/{MENS_TEAM_ID}/tactics?tactic={tactic_id}&rotation=1&phase=receive").get_data(as_text=True)
    assert "主二传" in custom_page and "<strong>Leo</strong>" in custom_page
    custom_pin = _pin(custom_page, "4")
    assert 'data-player="eric"' in custom_pin
    assert 'data-x="11"' in custom_pin and 'data-y="22"' in custom_pin

    refused = client.post(
        f"/teams/{MENS_TEAM_ID}/schemes/{copy_id}/system",
        data={"system": "51", "setter": "harvey", "tactic": tactic_id},
        follow_redirects=True,
    )
    refused_html = refused.get_data(as_text=True)
    assert "5-1 的二传必须在这六个人里。" in refused_html
    assert "<strong>Leo</strong>" in refused_html
    assert "准备好了" not in refused_html
    assert "胜率更高" not in refused_html
    conn = sqlite3.connect(tmp_path / "coach.db")
    assert conn.execute("SELECT sets_when FROM players WHERE id = 'eric'").fetchone()[0] == "back_row"
    assert conn.execute("SELECT sets_when FROM players WHERE id = 'michael'").fetchone()[0] == "back_row"


def _prep(html: str, number: int) -> str:
    return html.split(f'data-prep="{number}"', 1)[1].split("</li>", 1)[0]


def test_prep_page_checks_duties_before_the_match_starts(tmp_path):
    client = _client(tmp_path)
    bare = client.get(f"/teams/{MENS_TEAM_ID}/matches/new").get_data(as_text=True)
    assert "准备比赛" in bare
    assert "状态分为已配置、待补充、存在冲突。" in bare
    assert "准备好了" not in bare
    assert 'name="ready"' not in bare
    assert "示意站位" in bare
    assert "没有正式自由人" in bare
    assert "不会被改名为 libero" in bare
    assert "没有锁定" in bare
    assert 'data-player="d"' not in bare
    assert 'data-player="harvey"' not in bare
    assert "/sheet" not in bare
    opening = _prep(bare, 1)
    assert "待补充" in opening
    assert "二传 Michael" in opening
    assert "发球 Michael" in opening
    assert "补位 Eric" in opening
    fourth = _prep(bare, 4)
    assert "二传 Eric" in fourth
    assert "发球 Eric" in fourth
    assert "补位 Michael" in fourth
    assert "发球 Leo" in _prep(bare, 2)

    made = client.post(
        f"/teams/{MENS_TEAM_ID}/tactics",
        data={"scheme_id": "scheme-mens-62", "name": "开场卡"},
        follow_redirects=False,
    )
    tactic_id = _arg(made.headers["Location"], "tactic")
    client.post(
        f"/teams/{MENS_TEAM_ID}/tactics",
        data={"scheme_id": "scheme-mens-62", "name": "草稿不进开场"},
        follow_redirects=True,
    )
    client.post(f"/teams/{MENS_TEAM_ID}/tactics/{tactic_id}/publish", follow_redirects=True)
    copied = client.post(
        f"/teams/{MENS_TEAM_ID}/schemes/scheme-mens-62/copy",
        data={"name": "前排试验"},
        follow_redirects=False,
    )
    copy_id = _arg(copied.headers["Location"], "scheme")
    client.post(
        f"/teams/{MENS_TEAM_ID}/schemes",
        data={
            "scheme_id": copy_id,
            "name": "前排试验",
            "slot_1": "michael",
            "slot_2": "leo",
            "slot_3": "vitas",
            "slot_4": "eric",
            "slot_5": "andy-a",
            "slot_6": "andy-b",
        },
        follow_redirects=True,
    )
    other = client.post(
        f"/teams/{MENS_TEAM_ID}/tactics",
        data={"scheme_id": copy_id, "name": "前排冲突"},
        follow_redirects=False,
    )
    other_id = _arg(other.headers["Location"], "tactic")
    client.post(f"/teams/{MENS_TEAM_ID}/tactics/{other_id}/publish", follow_redirects=True)

    ready = client.get(
        f"/teams/{MENS_TEAM_ID}/matches/new?scheme=scheme-mens-62&tactic={tactic_id}&rotation=3"
    ).get_data(as_text=True)
    assert 'data-status="已配置"' in _prep(ready, 1)
    assert 'data-status="已配置"' in _prep(ready, 3)
    assert "D 换 Andy A" in ready
    assert "防守替补不占前排" not in ready
    assert "草稿不进开场" not in ready
    assert "前排冲突" not in ready
    assert f"/tactics/{tactic_id}/sheet" in ready
    assert "准备好了" not in ready
    assert 'data-player="d"' not in ready

    conflict = client.get(
        f"/teams/{MENS_TEAM_ID}/matches/new?scheme={copy_id}&tactic={other_id}&rotation=3"
    ).get_data(as_text=True)
    assert 'data-status="已配置"' in _prep(conflict, 1)
    assert 'data-status="存在冲突"' in _prep(conflict, 3)
    assert "防守替补不占前排" in conflict
    assert "开场卡" not in conflict
    assert 'data-player="d"' not in conflict
    assert 'data-player="harvey"' not in conflict


def test_backup_lineup_is_snapshotted_and_old_matches_stay(tmp_path):
    client = _client(tmp_path)
    made = client.post(
        f"/teams/{MENS_TEAM_ID}/tactics",
        data={"scheme_id": "scheme-mens-62", "name": "开场卡"},
        follow_redirects=False,
    )
    tactic_id = _arg(made.headers["Location"], "tactic")
    client.post(
        f"/teams/{MENS_TEAM_ID}/tactics/{tactic_id}/marks",
        data={"rotation": "1", "phase": "receive", "slot": "4", "player_id": "eric", "x": "11", "y": "22"},
    )
    client.post(f"/teams/{MENS_TEAM_ID}/tactics/{tactic_id}/publish", follow_redirects=True)
    copied = client.post(
        f"/teams/{MENS_TEAM_ID}/schemes/scheme-mens-62/copy",
        data={"name": "备用阵容"},
        follow_redirects=False,
    )
    copy_id = _arg(copied.headers["Location"], "scheme")
    client.post(
        f"/teams/{MENS_TEAM_ID}/schemes",
        data={
            "scheme_id": copy_id,
            "name": "备用阵容",
            "slot_1": "michael",
            "slot_2": "leo",
            "slot_3": "vitas",
            "slot_4": "eric",
            "slot_5": "andy-a",
            "slot_6": "andy-b",
        },
        follow_redirects=True,
    )
    other = client.post(
        f"/teams/{MENS_TEAM_ID}/tactics",
        data={"scheme_id": copy_id, "name": "另一套战术"},
        follow_redirects=False,
    )
    other_id = _arg(other.headers["Location"], "tactic")
    client.post(f"/teams/{MENS_TEAM_ID}/tactics/{other_id}/publish", follow_redirects=True)

    same = client.post(
        f"/teams/{MENS_TEAM_ID}/matches",
        data={
            "opponent": "红队",
            "mode": "light",
            "rotation": "1",
            "serving": "us",
            "scheme_id": "scheme-mens-62",
            "tactic_id": tactic_id,
            "backup_scheme_id": "scheme-mens-62",
        },
    )
    assert same.status_code == 302
    assert "/matches/new" in same.headers["Location"]

    first = client.post(
        f"/teams/{MENS_TEAM_ID}/matches",
        data={
            "opponent": "红队",
            "mode": "light",
            "rotation": "1",
            "serving": "them",
            "pair_id": "pair-d",
            "scheme_id": "scheme-mens-62",
            "tactic_id": tactic_id,
        },
    )
    assert first.status_code == 302
    first_url = first.headers["Location"]
    mismatched = client.post(
        f"/teams/{MENS_TEAM_ID}/matches",
        data={
            "opponent": "红队",
            "mode": "light",
            "rotation": "1",
            "serving": "them",
            "scheme_id": "scheme-mens-62",
            "tactic_id": other_id,
            "backup_scheme_id": copy_id,
        },
    )
    assert mismatched.status_code == 302
    assert "/matches/new" in mismatched.headers["Location"]

    second = client.post(
        f"/teams/{MENS_TEAM_ID}/matches",
        data={
            "opponent": "蓝队",
            "mode": "light",
            "rotation": "3",
            "serving": "us",
            "pair_id": "pair-d",
            "scheme_id": "scheme-mens-62",
            "tactic_id": tactic_id,
            "backup_scheme_id": copy_id,
        },
    )
    assert second.status_code == 302
    second_url = second.headers["Location"]
    conn = sqlite3.connect(tmp_path / "coach.db")
    rows = {
        row[0]: row
        for row in conn.execute("SELECT id, tactic_json, backup_json, plan_json FROM matches")
    }
    assert len(rows) == 2
    first_id = first_url.rstrip("/").split("/")[-1]
    second_id = second_url.rstrip("/").split("/")[-1]
    assert rows[first_id][2] == ""
    first_marks = json.loads(rows[first_id][1])["marks"]
    assert any(abs(float(mark["x"]) - 11) < 0.01 for mark in first_marks)
    backup = json.loads(rows[second_id][2])
    assert backup["name"] == "备用阵容"
    assert backup["order"][4] == "andy-a"
    opening = {player["id"]: player["base_slot"] for player in json.loads(rows[second_id][3])["players"]}
    assert opening["andy-a"] == 3
    live = client.get(second_url).get_data(as_text=True)
    assert "备用阵容" in live
    assert _our_score(live) == "0"
    assert "胜率更高" not in live

    client.post(
        f"/teams/{MENS_TEAM_ID}/schemes",
        data={
            "scheme_id": copy_id,
            "name": "备用已改",
            "slot_1": "eric",
            "slot_2": "leo",
            "slot_3": "vitas",
            "slot_4": "michael",
            "slot_5": "andy-a",
            "slot_6": "andy-b",
        },
        follow_redirects=True,
    )
    kept = {
        row[0]: row
        for row in conn.execute("SELECT id, tactic_json, backup_json FROM matches")
    }
    assert kept[first_id][2] == ""
    assert any(abs(float(mark["x"]) - 11) < 0.01 for mark in json.loads(kept[first_id][1])["marks"])
    assert json.loads(kept[second_id][2])["name"] == "备用阵容"
    assert json.loads(kept[second_id][2])["order"][0] == "michael"
    again = client.get(second_url).get_data(as_text=True)
    assert "备用阵容" in again
    assert "备用已改" not in again
    assert _our_score(again) == "0"
