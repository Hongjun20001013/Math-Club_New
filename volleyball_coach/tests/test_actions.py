from volleyball_coach.actions import arrow, attack_summary, pass_summary, team_block_kills
from volleyball_coach.app import create_app
from volleyball_coach.seed import MENS_TEAM_ID


def _client(tmp_path):
    app = create_app(tmp_path / "coach.db")
    app.config["TESTING"] = True
    return app.test_client()


def _start(client):
    started = client.post(
        f"/teams/{MENS_TEAM_ID}/matches",
        data={"opponent": "红队", "mode": "light", "rotation": "1", "serving": "them", "pair_id": "pair-d"},
    )
    return started.headers["Location"]


def _post_action(client, match_url, **data):
    payload = {"team_side": "us", "skill": "attack", "result": "continue", "client_token": data.pop("token")}
    payload.update(data)
    return client.post(f"{match_url}/actions", data=payload, follow_redirects=True)


def test_rates_keep_unknown_out_of_the_denominator():
    passing = pass_summary([{"quality": "in_system"}, {"quality": "unknown"}])
    assert passing["judged"] == 1
    assert passing["unknown"] == 1
    assert passing["in_rate"] == "100%"
    attack = attack_summary(
        [{"result": "kill"}, {"result": "error"}, {"result": "blocked"}, {"result": "unknown"}]
    )
    assert attack["attempts"] == 3
    assert attack["unknown"] == 1
    assert attack["efficiency_num"] == -1
    straight = arrow("left", "straight", flipped=False)
    flipped = arrow("left", "straight", flipped=True)
    assert straight["x1"] > 50
    assert flipped["x1"] < 50
    assert arrow("unknown", "straight") is None


def test_two_attacks_shared_block_undo_and_historical_lineup(tmp_path):
    client = _client(tmp_path)
    match_url = _start(client)

    _post_action(client, match_url, token="a1", player_id="leo", result="continue")
    _post_action(client, match_url, token="a1", player_id="leo", result="kill")
    _post_action(client, match_url, token="a2", player_id="vitas", result="kill")
    blocked = client.post(
        f"{match_url}/actions",
        data={
            "team_side": "us",
            "skill": "block",
            "result": "kill",
            "client_token": "b1",
            "block_player": ["leo", "vitas"],
        },
        follow_redirects=True,
    )
    players = client.get(f"{match_url}/players").get_data(as_text=True)
    leo = players.split('data-player="leo"')[1].split(">")[0]
    vitas = players.split('data-player="vitas"')[1].split(">")[0]
    assert 'data-attack="1"' in leo
    assert 'data-attack="1"' in vitas
    assert 'data-block="1"' in leo
    assert 'data-block="1"' in vitas
    assert 'data-block-team="1"' in players
    assert team_block_kills(
        [{"skill": "block", "result": "kill"}, {"skill": "block", "result": "kill"}]
    ) == 2

    client.post(
        f"{match_url}/actions",
        data={"team_side": "us", "skill": "pass", "result": "unknown", "client_token": "p1", "player_id": "leo"},
    )
    client.post(
        f"{match_url}/actions",
        data={"team_side": "us", "skill": "pass", "result": "in_system", "client_token": "p2", "player_id": "leo"},
    )
    passed = client.get(f"{match_url}/players").get_data(as_text=True)
    assert "未知 1" in passed
    assert "分母 1" in passed

    client.post(f"{match_url}/undo", follow_redirects=True)
    undone = client.get(f"{match_url}/players").get_data(as_text=True)
    leo_after = undone.split('data-player="leo"')[1].split(">")[0]
    assert 'data-pass="1"' in leo_after

    scored = client.post(f"{match_url}/point", data={"winner": "us"}, follow_redirects=True)
    scored_html = scored.get_data(as_text=True)
    assert '<span class="pill">R2</span>' in scored_html or ">R2<" in scored_html
    assert ">1<" in scored_html
    client.post(f"{match_url}/undo", follow_redirects=True)
    restored = client.get(match_url).get_data(as_text=True)
    assert ">0<" in restored
    still = client.get(f"{match_url}/players").get_data(as_text=True)
    assert 'data-attack="1"' in still.split('data-player="vitas"')[1].split(">")[0]

    edited = client.post(
        f"{match_url}/actions/1",
        data={
            "client_token": "edit",
            "team_side": "us",
            "skill": "attack",
            "result": "kill",
            "player_id": "leo",
        },
        follow_redirects=True,
    )
    assert edited.status_code == 200
    changed = client.get(f"{match_url}/players").get_data(as_text=True)
    assert "得分 1" in changed.split('data-player="leo"')[1].split("</tr>")[0]
    assert ">0<" in client.get(match_url).get_data(as_text=True)

    client.post(
        f"{match_url}/rallies",
        data={
            "set_number": "1",
            "rotation": "1",
            "serving_side": "them",
            "winner": "unknown",
            "sample_scope": "sample",
            "pass_quality": "unknown",
            "attach_lineup": "on",
        },
    )
    payload = client.get(f"{match_url}/report.json").get_json()
    old = next(rally for rally in payload["rallies"] if rally["lineup"] and rally["winner"] == "unknown")
    client.post(f"{match_url}/sub", data={"out": "andy-a", "in": "d"})
    client.post(
        f"{match_url}/actions",
        data={
            "team_side": "us",
            "skill": "attack",
            "result": "continue",
            "client_token": "hist",
            "player_id": "leo",
            "rally_id": old["id"],
        },
    )
    video = client.get(f"{match_url}/video").get_data(as_text=True)
    historical = video.split('data-lineup-source="historical"')[1]
    ids = historical.split('data-lineup-ids="')[1].split('"')[0]
    assert "andy-a" in ids.split(",")
    assert "d" not in ids.split(",")

    client.post(f"{match_url}/opponents", data={"jersey": "7", "name": "对角"})
    opponents = client.get(f"{match_url}/opponents").get_data(as_text=True)
    opp_id = opponents.split('option value="')[1].split('"')[0]
    client.post(
        f"{match_url}/actions",
        data={
            "team_side": "them",
            "skill": "attack",
            "result": "kill",
            "client_token": "o1",
            "opponent_id": opp_id,
            "start_zone": "left",
            "attack_line": "straight",
            "rally_id": old["id"],
        },
    )
    client.post(
        f"{match_url}/actions",
        data={
            "team_side": "them",
            "skill": "attack",
            "result": "error",
            "client_token": "o2",
            "opponent_id": opp_id,
            "start_zone": "left",
            "attack_line": "cross",
            "view_flip": "on",
            "rally_id": old["id"],
        },
    )
    scout = client.get(f"{match_url}/opponents?player={opp_id}&line=straight").get_data(as_text=True)
    assert scout.count("直线") >= 1
    assert "大斜线" not in scout.split("<ol")[1]
    flipped = client.get(f"{match_url}/opponents?player={opp_id}&line=cross").get_data(as_text=True)
    assert "换边" in flipped
