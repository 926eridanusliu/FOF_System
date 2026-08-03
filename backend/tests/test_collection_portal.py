from urllib.parse import urlparse


def _create_manager(client):
    response = client.post("/api/managers", json={"name": "测试管理人"})
    assert response.status_code == 201
    return response.json()


def _create_product(client, manager_id: int, name: str, strategies: list[str]):
    response = client.post(
        "/api/products",
        json={
            "manager_id": manager_id,
            "name": name,
            "strategy_keys": strategies,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_multi_product_report_uses_strategy_union(client) -> None:
    manager = _create_manager(client)
    quant = _create_product(
        client,
        manager["id"],
        "量化产品",
        ["cover_strategy_stock_quant", "cover_strategy_market_neutral"],
    )
    futures = _create_product(
        client,
        manager["id"],
        "期货产品",
        ["cover_strategy_futures_quant_trend"],
    )

    response = client.post(
        "/api/reports",
        json={
            "title": "多产品尽调",
            "manager_id": manager["id"],
            "product_id": quant["id"],
            "product_ids": [quant["id"], futures["id"]],
            "template_type": "private_fund",
            "content": {
                "cover_investigator": "测试员",
                "cover_report_date": "2026.07.28",
            },
        },
    )
    assert response.status_code == 201, response.text
    report = response.json()
    assert report["product_ids"] == [quant["id"], futures["id"]]
    assert set(report["auto_strategy_keys"]) == {
        "cover_strategy_stock_quant",
        "cover_strategy_market_neutral",
        "cover_strategy_futures_quant_trend",
    }
    assert report["content"]["cover_product_name"] == "量化产品、期货产品"
    assert report["content"]["cover_strategy_market_neutral"] is True


def test_json_import_preview_and_apply(client, private_fund_data) -> None:
    manager = _create_manager(client)
    product = _create_product(
        client, manager["id"], "测试产品", ["cover_strategy_stock_quant"]
    )
    report_response = client.post(
        "/api/reports",
        json={
            "title": "JSON 导入",
            "manager_id": manager["id"],
            "product_id": product["id"],
            "template_type": "private_fund",
            "content": private_fund_data,
        },
    )
    report_id = report_response.json()["id"]
    payload = {
        "content": {
            "qa_section1_q001_answer": "导入后的回答",
            "cover_manager_name": "不应覆盖的管理人",
            "not_in_template": "忽略",
        }
    }

    preview = client.post(
        f"/api/reports/{report_id}/import-json?apply=false", json=payload
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["applied"] is False
    assert preview.json()["recognized_count"] == 2
    assert "not_in_template" in preview.json()["ignored_fields"]

    applied = client.post(
        f"/api/reports/{report_id}/import-json?apply=true", json=payload
    )
    assert applied.status_code == 200
    report = client.get(f"/api/reports/{report_id}").json()
    assert report["content"]["qa_section1_q001_answer"] == "导入后的回答"
    assert report["content"]["cover_manager_name"] == manager["name"]


def test_invitation_is_scoped_expires_and_locks_after_submit(
    client, private_fund_data
) -> None:
    manager = _create_manager(client)
    product = _create_product(
        client, manager["id"], "外部填写产品", ["cover_strategy_market_neutral"]
    )
    report_response = client.post(
        "/api/reports",
        json={
            "title": "外部资料收集",
            "manager_id": manager["id"],
            "product_id": product["id"],
            "template_type": "private_fund",
            "content": private_fund_data,
        },
    )
    report_id = report_response.json()["id"]
    created = client.post(
        f"/api/reports/{report_id}/invitations",
        json={"expires_in_days": 7},
    )
    assert created.status_code == 201, created.text
    token = urlparse(created.json()["fill_url"]).path.rsplit("/", 1)[-1]

    public = client.get(f"/api/public/fill/{token}")
    assert public.status_code == 200
    data = public.json()
    data["content"]["qa_section1_q001_answer"] = "管理人填写内容"
    saved = client.put(
        f"/api/public/fill/{token}",
        json={
            "content": data["content"],
            "conclusion": "补充说明",
            "risk_items": ["风险披露"],
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["content"]["cover_strategy_market_neutral"] is True

    submitted = client.post(f"/api/public/fill/{token}/submit")
    assert submitted.status_code == 200
    assert submitted.json()["submitted_at"] is not None
    assert client.put(
        f"/api/public/fill/{token}",
        json={"content": data["content"], "risk_items": []},
    ).status_code == 409


def test_revoked_invitation_is_unavailable(client, private_fund_data) -> None:
    manager = _create_manager(client)
    product = _create_product(
        client, manager["id"], "撤销链接产品", ["cover_strategy_stock_quant"]
    )
    report = client.post(
        "/api/reports",
        json={
            "title": "撤销测试",
            "manager_id": manager["id"],
            "product_id": product["id"],
            "content": private_fund_data,
        },
    ).json()
    invitation = client.post(
        f"/api/reports/{report['id']}/invitations",
        json={"expires_in_days": 1},
    ).json()
    token = urlparse(invitation["fill_url"]).path.rsplit("/", 1)[-1]
    assert client.delete(
        f"/api/reports/{report['id']}/invitations/{invitation['id']}"
    ).status_code == 204
    assert client.get(f"/api/public/fill/{token}").status_code == 410


def test_report_delete_is_audited_and_reversible(client, private_fund_data) -> None:
    manager = _create_manager(client)
    product = _create_product(
        client, manager["id"], "待删除报告产品", ["cover_strategy_stock_quant"]
    )
    report = client.post(
        "/api/reports",
        json={
            "title": "重复的测试报告",
            "manager_id": manager["id"],
            "product_id": product["id"],
            "content": private_fund_data,
        },
    ).json()

    deleted = client.request(
        "DELETE",
        f"/api/reports/{report['id']}",
        json={"reason": "重复创建"},
    )
    assert deleted.status_code == 204
    assert client.get(f"/api/reports/{report['id']}").status_code == 404
    assert client.get("/api/reports").json() == []

    records = client.get("/api/deletions").json()
    assert records[0]["entity_type"] == "report"
    assert records[0]["reason"] == "重复创建"
    assert records[0]["snapshot"]["status"] == "draft"
    assert client.post(f"/api/deletions/{records[0]['id']}/restore").status_code == 200
    assert client.get(f"/api/reports/{report['id']}").status_code == 200


def test_manager_delete_hides_related_data_and_restore_recovers_it(
    client, private_fund_data
) -> None:
    manager = _create_manager(client)
    product = _create_product(
        client, manager["id"], "关联产品", ["cover_strategy_market_neutral"]
    )
    report = client.post(
        "/api/reports",
        json={
            "title": "关联报告",
            "manager_id": manager["id"],
            "product_id": product["id"],
            "content": private_fund_data,
        },
    ).json()

    deleted = client.request(
        "DELETE",
        f"/api/managers/{manager['id']}",
        json={"reason": "重复管理人档案"},
    )
    assert deleted.status_code == 204
    assert client.get(f"/api/managers/{manager['id']}").status_code == 404
    assert client.get(f"/api/products?manager_id={manager['id']}").json() == []
    assert client.get(f"/api/reports/{report['id']}").status_code == 404

    record = client.get("/api/deletions?entity_type=manager").json()[0]
    assert record["snapshot"]["product_count"] == 1
    assert record["snapshot"]["report_count"] == 1
    assert client.post(f"/api/deletions/{record['id']}/restore").status_code == 200
    assert client.get(f"/api/managers/{manager['id']}").status_code == 200
    assert client.get(f"/api/reports/{report['id']}").status_code == 200
