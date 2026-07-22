from pathlib import Path
import time

from app import storage


PRIVATE_TEMPLATE_TITLE = "FOF尽调报告_书签模板_2026修订版"
LICENSED_TEMPLATE_TITLE = "FOF尽调报告_持牌金融机构_书签模板"
PLACEHOLDER_DIR = Path(__file__).parent / "fixtures" / "placeholders"


def create_report_records(client, content: dict, template_type: str, title: str):
    manager_response = client.post(
        "/api/managers",
        json={"name": content["cover_manager_name"]},
    )
    assert manager_response.status_code == 201
    manager = manager_response.json()

    product_response = client.post(
        "/api/products",
        json={
            "manager_id": manager["id"],
            "name": content["cover_product_name"],
        },
    )
    assert product_response.status_code == 201
    product = product_response.json()

    report_response = client.post(
        "/api/reports",
        json={
            "title": title,
            "manager_id": manager["id"],
            "product_id": product["id"],
            "template_type": template_type,
            "content": content,
        },
    )
    assert report_response.status_code == 201
    return manager, product, report_response.json()


def test_private_report_crud_generation_and_state_flow(
    client,
    private_fund_data,
    tmp_path: Path,
    monkeypatch,
) -> None:
    generated_dir = tmp_path / "generated_reports"
    uploaded_dir = tmp_path / "uploaded_images"
    monkeypatch.setattr(storage, "GENERATED_DIR", generated_dir)
    monkeypatch.setattr(storage, "UPLOAD_DIR", uploaded_dir)

    manager, product, report = create_report_records(
        client,
        private_fund_data,
        "private_fund",
        PRIVATE_TEMPLATE_TITLE,
    )

    assert client.get(f"/api/managers/{manager['id']}").status_code == 200
    assert client.get(f"/api/products/{product['id']}").status_code == 200
    assert client.get(f"/api/reports/{report['id']}").json()["status"] == "draft"

    validation = client.post(f"/api/reports/{report['id']}/validate")
    assert validation.status_code == 200
    assert validation.json()["valid"] is True

    for field, fixture_name in (
        ("image_org_structure", "org_structure_placeholder.png"),
        ("image_performance_comparison", "performance_placeholder.png"),
    ):
        image_bytes = (PLACEHOLDER_DIR / fixture_name).read_bytes()
        upload = client.post(
            f"/api/reports/{report['id']}/images/{field}",
            content=image_bytes,
            headers={"Content-Type": "image/png", "X-Filename": fixture_name},
        )
        assert upload.status_code == 201, upload.text
        uploaded = upload.json()
        assert uploaded["field"] == field
        assert uploaded["width_px"] == 2400
        assert client.get(uploaded["download_url"]).content == image_bytes

    updated_report = client.get(f"/api/reports/{report['id']}").json()
    assert updated_report["content"]["image_org_structure"]["original_filename"] == (
        "org_structure_placeholder.png"
    )

    generation = client.post(f"/api/reports/{report['id']}/generate")
    assert generation.status_code == 200, generation.text
    generated = generation.json()
    assert generated["validation"]["success"] is True
    assert (generated_dir / generated["filename"]).is_file()

    download = client.get(generated["download_url"])
    assert download.status_code == 200
    assert download.content.startswith(b"PK")

    submitted = client.post(f"/api/reports/{report['id']}/submit")
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "submitted"

    forbidden_edit = client.put(
        f"/api/reports/{report['id']}",
        json={"title": PRIVATE_TEMPLATE_TITLE},
    )
    assert forbidden_edit.status_code == 409

    archived = client.post(f"/api/reports/{report['id']}/archive")
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    assert client.delete(f"/api/reports/{report['id']}").status_code == 409
    assert client.delete(f"/api/products/{product['id']}").status_code == 409
    assert client.delete(f"/api/managers/{manager['id']}").status_code == 409


def test_licensed_template_generation(
    client,
    licensed_institution_data,
    tmp_path: Path,
    monkeypatch,
) -> None:
    generated_dir = tmp_path / "generated_reports"
    monkeypatch.setattr(storage, "GENERATED_DIR", generated_dir)
    _, _, report = create_report_records(
        client,
        licensed_institution_data,
        "licensed_institution",
        LICENSED_TEMPLATE_TITLE,
    )

    generation = client.post(f"/api/reports/{report['id']}/generate")
    assert generation.status_code == 200, generation.text
    assert generation.json()["validation"]["success"] is True


def test_generation_job_queue_returns_immediately_and_produces_download(
    client,
    private_fund_data,
    tmp_path: Path,
    monkeypatch,
) -> None:
    generated_dir = tmp_path / "queued_generated_reports"
    monkeypatch.setattr(storage, "GENERATED_DIR", generated_dir)
    _, _, report = create_report_records(
        client,
        private_fund_data,
        "private_fund",
        "异步生成任务测试",
    )

    queued = client.post(f"/api/reports/{report['id']}/generation-jobs")
    assert queued.status_code == 202, queued.text
    job = queued.json()
    assert job["template_type"] == "private_fund"
    assert job["status"] in {"queued", "running", "completed"}

    deadline = time.monotonic() + 15
    while job["status"] in {"queued", "running"} and time.monotonic() < deadline:
        time.sleep(0.05)
        progress = client.get(
            f"/api/reports/{report['id']}/generation-jobs/{job['id']}"
        )
        assert progress.status_code == 200
        job = progress.json()

    assert job["status"] == "completed", job
    assert job["validation"]["success"] is True
    assert (generated_dir / job["filename"]).is_file()
    download = client.get(job["download_url"])
    assert download.status_code == 200
    assert download.content.startswith(b"PK")


def test_invalid_report_cannot_be_submitted(client, private_fund_data) -> None:
    incomplete = dict(private_fund_data)
    incomplete.pop("cover_strategy_futures_quant_trend")
    _, _, report = create_report_records(
        client,
        incomplete,
        "private_fund",
        PRIVATE_TEMPLATE_TITLE,
    )

    validation = client.post(f"/api/reports/{report['id']}/validate")
    assert validation.status_code == 200
    assert validation.json()["valid"] is False
    assert client.post(f"/api/reports/{report['id']}/submit").status_code == 422


def test_image_upload_rejects_non_image_field(client, private_fund_data) -> None:
    _, _, report = create_report_records(
        client,
        private_fund_data,
        "private_fund",
        PRIVATE_TEMPLATE_TITLE,
    )
    response = client.post(
        f"/api/reports/{report['id']}/images/cover_manager_name",
        content=b"not-an-image",
        headers={"Content-Type": "image/png"},
    )
    assert response.status_code == 422
