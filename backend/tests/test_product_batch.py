def test_batch_create_products_uses_shared_fields_and_is_atomic(client) -> None:
    manager = client.post("/api/managers", json={"name": "批量产品管理人"}).json()
    payload = {
        "manager_id": manager["id"],
        "product_type": "私募证券投资基金",
        "strategy_keys": ["cover_strategy_futures_quant_trend"],
        "products": [
            {"name": "CTA产品一", "established_date": "2021-04-01"},
            {"name": "CTA产品二", "established_date": "2021-08-10"},
            {"name": "CTA产品三", "established_date": None},
        ],
    }
    response = client.post("/api/products/batch", json=payload)
    assert response.status_code == 201, response.text
    products = response.json()
    assert [item["name"] for item in products] == ["CTA产品一", "CTA产品二", "CTA产品三"]
    assert all(item["product_type"] == "私募证券投资基金" for item in products)
    assert all(item["strategy_keys"] == ["cover_strategy_futures_quant_trend"] for item in products)

    duplicate_payload = {**payload, "products": [
        {"name": "CTA产品一", "established_date": None},
        {"name": "不会被部分创建", "established_date": None},
    ]}
    duplicate = client.post("/api/products/batch", json=duplicate_payload)
    assert duplicate.status_code == 409
    listed = client.get(f"/api/products?manager_id={manager['id']}").json()
    assert "不会被部分创建" not in {item["name"] for item in listed}


def test_batch_rejects_duplicate_names_inside_request(client) -> None:
    manager = client.post("/api/managers", json={"name": "重复校验管理人"}).json()
    response = client.post("/api/products/batch", json={
        "manager_id": manager["id"],
        "product_type": None,
        "strategy_keys": ["cover_strategy_stock_quant"],
        "products": [
            {"name": "同名产品", "established_date": None},
            {"name": "同名产品", "established_date": None},
        ],
    })
    assert response.status_code == 422
    assert client.get(f"/api/products?manager_id={manager['id']}").json() == []


def test_other_product_strategy_flows_to_report_cover_text(client) -> None:
    manager = client.post("/api/managers", json={"name": "其他策略管理人"}).json()
    product = client.post("/api/products", json={
        "manager_id": manager["id"],
        "name": "其他策略产品",
        "strategy_keys": ["cover_strategy_other"],
    })
    assert product.status_code == 201, product.text

    report = client.post("/api/reports", json={
        "title": "其他策略报告",
        "manager_id": manager["id"],
        "product_id": product.json()["id"],
        "template_type": "private_fund",
        "content": {
            "cover_investigator": "测试人员",
            "cover_report_date": "2026.8.4",
        },
    })
    assert report.status_code == 201, report.text
    assert report.json()["content"]["cover_strategy_other_text"] == "其他"
    assert report.json()["auto_strategy_keys"] == []

    validation = client.post(f"/api/reports/{report.json()['id']}/validate")
    assert validation.status_code == 200
    assert validation.json()["valid"] is True
