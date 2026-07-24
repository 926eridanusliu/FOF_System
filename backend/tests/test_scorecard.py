from datetime import date
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from docx import Document

from app import storage
from app.services.scorecard import parse_nav_upload
from tests.test_api_workflow import create_report_records


def _minimal_nav_xlsx() -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
              <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
              <Default Extension="xml" ContentType="application/xml"/>
              <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
              <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
            </Types>""",
        )
        archive.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
            </Relationships>""",
        )
        archive.writestr(
            "xl/workbook.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
              xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
              <sheets><sheet name="净值" sheetId="1" r:id="rId1"/></sheets>
            </workbook>""",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
            </Relationships>""",
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>
                <row r="1">
                  <c r="A1" t="inlineStr"><is><t>日期</t></is></c>
                  <c r="B1" t="inlineStr"><is><t>累计净值</t></is></c>
                </row>
                <row r="2">
                  <c r="A2" t="inlineStr"><is><t>2025-01-01</t></is></c>
                  <c r="B2"><v>1.0</v></c>
                </row>
                <row r="3">
                  <c r="A3" t="inlineStr"><is><t>2025-02-01</t></is></c>
                  <c r="B3"><v>1.02</v></c>
                </row>
              </sheetData>
            </worksheet>""",
        )
    return output.getvalue()


def _nav_csv() -> bytes:
    values = [
        1.0000, 1.0200, 1.0404, 1.0612, 1.0506, 1.0716, 1.0930,
        1.1149, 1.1038, 1.1258, 1.1483, 1.1713, 1.1947, 1.2186,
        1.2429, 1.2678, 1.2931, 1.3189, 1.3453, 1.3722,
    ]
    rows = ["日期,累计净值"]
    year, month = 2024, 1
    for value in values:
        rows.append(f"{date(year, month, 1).isoformat()},{value:.4f}")
        month += 1
        if month == 13:
            year += 1
            month = 1
    return ("\n".join(rows) + "\n").encode()


def _calculation_payload() -> dict:
    return {
        "date_column": "日期",
        "nav_column": "累计净值",
        "benchmark_column": None,
        "benchmark_mode": "absolute",
        "risk_free_rate_percent": 0,
        "qualitative": {
            "strategy_scale_group": "cta_t0",
            "managed_scale_100m": 150,
            "active_product_count": 115,
            "company_headcount": 65,
            "manager_same_strategy_years": 5,
            "manager_industry_years": 10,
            "manager_philosophy_level": "complete",
            "manager_profile_stable": True,
            "research_headcount": 48,
            "research_background_match": True,
            "core_research_experience_years": 5,
            "research_live_track_record": True,
            "core_departures_1y": 0,
            "core_departures_3y": 0,
            "incentive_level": "long_term",
            "current_strategy_scale_100m": 55,
            "theoretical_capacity_100m": 90,
            "differentiation_level": "significant",
            "risk_system_level": "complete",
            "risk_team_headcount": 3,
            "risk_team_experience_years": 11,
            "manager_coinvest_percent": 0,
            "manager_coinvest_lock_years": 0,
            "core_personal_coinvest": False,
            "regulatory_events_3y": 0,
            "negative_or_litigation_events_3y": 0,
        },
    }


def test_xlsx_parser_reads_inline_strings_and_numbers() -> None:
    table = parse_nav_upload(_minimal_nav_xlsx(), ".xlsx")
    assert table.sheet_name == "净值"
    assert table.detected_columns == {
        "date": "日期",
        "nav": "累计净值",
        "benchmark": None,
    }
    assert table.rows[1]["累计净值"] == 1.02


def test_scorecard_api_calculates_and_appends_report(
    client,
    private_fund_data,
    tmp_path: Path,
    monkeypatch,
) -> None:
    generated_dir = tmp_path / "generated"
    nav_dir = tmp_path / "nav"
    monkeypatch.setattr(storage, "GENERATED_DIR", generated_dir)
    monkeypatch.setattr(storage, "NAV_UPLOAD_DIR", nav_dir)
    _, _, report = create_report_records(
        client,
        private_fund_data,
        "private_fund",
        "评分卡端到端测试",
    )

    uploaded = client.post(
        f"/api/reports/{report['id']}/scorecard/nav",
        content=_nav_csv(),
        headers={"Content-Type": "text/csv", "X-Filename": "nav.csv"},
    )
    assert uploaded.status_code == 201, uploaded.text
    assert uploaded.json()["detected_columns"]["date"] == "日期"
    assert uploaded.json()["detected_columns"]["nav"] == "累计净值"

    calculated = client.post(
        f"/api/reports/{report['id']}/scorecard/calculate",
        json=_calculation_payload(),
    )
    assert calculated.status_code == 200, calculated.text
    result = calculated.json()
    assert result["quantitative_score"] <= 62
    assert result["qualitative_score"] == 33
    assert result["total_score"] == (
        result["quantitative_score"] + result["qualitative_score"]
    )
    assert len(result["score_rows"]) == 14
    assert result["metrics"]["observations"] == 20

    generation = client.post(f"/api/reports/{report['id']}/generate")
    assert generation.status_code == 200, generation.text
    output_path = generated_dir / generation.json()["filename"]
    document = Document(output_path)
    assert any(
        paragraph.text == "附录：私募产品准入评分表"
        for paragraph in document.paragraphs
    )
    assert any(
        "近1年收益率/相对收益（取高）" in cell.text
        for table in document.tables
        for row in table.rows
        for cell in row.cells
    )


def test_licensed_template_also_receives_scorecard_appendix(
    client,
    licensed_institution_data,
    tmp_path: Path,
    monkeypatch,
) -> None:
    generated_dir = tmp_path / "licensed-generated"
    nav_dir = tmp_path / "licensed-nav"
    monkeypatch.setattr(storage, "GENERATED_DIR", generated_dir)
    monkeypatch.setattr(storage, "NAV_UPLOAD_DIR", nav_dir)
    _, _, report = create_report_records(
        client,
        licensed_institution_data,
        "licensed_institution",
        "持牌机构评分卡测试",
    )
    uploaded = client.post(
        f"/api/reports/{report['id']}/scorecard/nav",
        content=_nav_csv(),
        headers={"Content-Type": "text/csv; charset=utf-8", "X-Filename": "nav.csv"},
    )
    assert uploaded.status_code == 201, uploaded.text
    calculated = client.post(
        f"/api/reports/{report['id']}/scorecard/calculate",
        json=_calculation_payload(),
    )
    assert calculated.status_code == 200, calculated.text
    generation = client.post(f"/api/reports/{report['id']}/generate")
    assert generation.status_code == 200, generation.text
    document = Document(generated_dir / generation.json()["filename"])
    assert any(
        paragraph.text == "附录：私募产品准入评分表"
        for paragraph in document.paragraphs
    )
