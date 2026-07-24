from pathlib import Path

from app import storage
from tests.test_scorecard import _calculation_payload, _nav_csv


PLACEHOLDER_DIR = Path(__file__).parent / "fixtures" / "placeholders"


def create_report(client, content: dict) -> dict:
    manager = client.post(
        "/api/managers",
        json={"name": content["cover_manager_name"]},
    ).json()
    product = client.post(
        "/api/products",
        json={"manager_id": manager["id"], "name": content["cover_product_name"]},
    ).json()
    response = client.post(
        "/api/reports",
        json={
            "title": "版本管理测试报告",
            "manager_id": manager["id"],
            "product_id": product["id"],
            "template_type": "private_fund",
            "content": content,
            "conclusion": "初次尽调结论",
            "risk_items": ["初始风险"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_submit_creates_immutable_versions_compare_and_restore(
    client,
    private_fund_data,
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(storage, "VERSION_STORAGE_DIR", tmp_path / "versions")
    monkeypatch.setattr(storage, "NAV_UPLOAD_DIR", tmp_path / "nav")
    report = create_report(client, private_fund_data)
    report_id = report["id"]

    uploaded = client.post(
        f"/api/reports/{report_id}/scorecard/nav",
        content=_nav_csv(),
        headers={"Content-Type": "text/csv", "X-Filename": "nav.csv"},
    )
    assert uploaded.status_code == 201, uploaded.text
    calculated = client.post(
        f"/api/reports/{report_id}/scorecard/calculate",
        json=_calculation_payload(),
    )
    assert calculated.status_code == 200, calculated.text
    original_total_score = calculated.json()["total_score"]

    first_submit = client.post(f"/api/reports/{report_id}/submit")
    assert first_submit.status_code == 200, first_submit.text

    versions = client.get(f"/api/reports/{report_id}/versions")
    assert versions.status_code == 200
    assert len(versions.json()) == 1
    first = versions.json()[0]
    assert first["version_number"] == 1
    assert len(first["snapshot_hash"]) == 64

    detail = client.get(f"/api/reports/{report_id}/versions/1")
    assert detail.status_code == 200
    assert detail.json()["report_snapshot"]["conclusion"] == "初次尽调结论"
    assert client.put(f"/api/reports/{report_id}/versions/1", json={}).status_code == 405
    assert client.delete(f"/api/reports/{report_id}/versions/1").status_code == 405

    restored = client.post(f"/api/reports/{report_id}/versions/1/restore")
    assert restored.status_code == 200, restored.text
    assert restored.json()["status"] == "draft"
    assert restored.json()["submitted_at"] is None
    restored_scorecard = client.get(f"/api/reports/{report_id}/scorecard")
    assert restored_scorecard.status_code == 200
    assert restored_scorecard.json()["total_score"] == original_total_score
    assert len(list((tmp_path / "nav" / f"report-{report_id}").glob("*.csv"))) == 2

    changed_content = dict(restored.json()["content"])
    changed_content["cover_investigator"] = "第二次调查人"
    edited = client.put(
        f"/api/reports/{report_id}",
        json={
            "title": "版本管理测试报告（第二版）",
            "content": changed_content,
            "conclusion": "第二次尽调结论",
            "risk_items": ["初始风险", "新增风险"],
        },
    )
    assert edited.status_code == 200, edited.text
    second_submit = client.post(f"/api/reports/{report_id}/submit")
    assert second_submit.status_code == 200, second_submit.text

    versions = client.get(f"/api/reports/{report_id}/versions").json()
    assert [item["version_number"] for item in versions] == [2, 1]
    comparison = client.get(
        f"/api/reports/{report_id}/versions/compare",
        params={"from_version": 1, "to_version": 2},
    )
    assert comparison.status_code == 200, comparison.text
    changes = {item["field_path"]: item for item in comparison.json()["changes"]}
    assert changes["title"]["before"] == "版本管理测试报告"
    assert changes["title"]["after"] == "版本管理测试报告（第二版）"
    assert changes["content.cover_investigator"]["after"] == "第二次调查人"
    assert changes["conclusion"]["after"] == "第二次尽调结论"
    assert changes["risk_items"]["change_type"] == "changed"

    rolled_back = client.post(f"/api/reports/{report_id}/versions/1/restore")
    assert rolled_back.status_code == 200, rolled_back.text
    assert rolled_back.json()["status"] == "draft"
    assert rolled_back.json()["title"] == "版本管理测试报告"
    assert rolled_back.json()["content"]["cover_investigator"] == (
        private_fund_data["cover_investigator"]
    )
    assert rolled_back.json()["risk_items"] == ["初始风险"]
    assert client.delete(f"/api/reports/{report_id}").status_code == 409
    assert len(client.get(f"/api/reports/{report_id}/versions").json()) == 2


def test_version_restore_uses_immutable_image_copy(
    client,
    private_fund_data,
    tmp_path: Path,
    monkeypatch,
) -> None:
    upload_dir = tmp_path / "uploads"
    version_dir = tmp_path / "versions"
    monkeypatch.setattr(storage, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(storage, "VERSION_STORAGE_DIR", version_dir)
    report = create_report(client, private_fund_data)
    report_id = report["id"]

    for field, fixture_name in (
        ("image_org_structure", "org_structure_placeholder.png"),
        ("image_performance_comparison", "performance_placeholder.png"),
    ):
        response = client.post(
            f"/api/reports/{report_id}/images/{field}",
            content=(PLACEHOLDER_DIR / fixture_name).read_bytes(),
            headers={"Content-Type": "image/png", "X-Filename": fixture_name},
        )
        assert response.status_code == 201, response.text

    submitted = client.post(f"/api/reports/{report_id}/submit")
    assert submitted.status_code == 200, submitted.text
    version_detail = client.get(f"/api/reports/{report_id}/versions/1").json()
    images = version_detail["file_manifest"]["images"]
    assert set(images) == {
        "image_org_structure",
        "image_performance_comparison",
    }
    for metadata in images.values():
        immutable_file = version_dir / metadata["path"]
        assert immutable_file.is_file()
        assert len(metadata["sha256"]) == 64

    restored = client.post(f"/api/reports/{report_id}/versions/1/restore")
    assert restored.status_code == 200, restored.text
    for field in images:
        restored_path = Path(restored.json()["content"][field]["path"])
        assert restored_path.is_file()
        assert restored_path.is_relative_to(upload_dir)

    validation = client.post(f"/api/reports/{report_id}/validate")
    assert validation.status_code == 200
    assert validation.json()["valid"] is True
