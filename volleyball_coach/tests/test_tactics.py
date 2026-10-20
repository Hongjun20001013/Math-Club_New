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
