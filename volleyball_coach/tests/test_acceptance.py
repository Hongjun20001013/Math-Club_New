from volleyball_coach.drills import acceptance_drills


def test_acceptance_drills_pass():
    results = acceptance_drills()
    failed = [item for item in results if not item["passed"]]
    assert not failed, "\n".join(f"{item['name']}: {item['detail']}" for item in failed)
    assert len(results) >= 20
