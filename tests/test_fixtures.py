def test_live_fixture_has_expected_shape(status_1_01):
    assert status_1_01["model"] == "SX-DC-8-12-120"
    outlets = status_1_01["devices"][0]["outlets"]
    assert len(outlets) == 7
    assert any(o.get("isHidden") for o in outlets)


def test_documented_fixture_has_expected_shape(status_0_5):
    assert status_0_5["model"] == "SX-DC-8-1224"
    measurements = status_0_5["devices"][0]["deviceMeasurements"]
    assert measurements["inputState"] == ["No Ground"]


def test_mac_is_scrubbed(status_1_01, who_are_you):
    blob = f"{status_1_01}{who_are_you}"
    assert "A6:67" not in blob
    assert "ACA667" not in blob
