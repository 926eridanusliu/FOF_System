from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from docx import Document
from lxml import etree

OUTPUTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(OUTPUTS))

from docx_engine import DocxGenerator, StyleSpec
from validator import Validator
from validator.mapper import InputDataMapper


class ValidatorTestCase(unittest.TestCase):
    data_path = Path(os.getenv("FOF_VALIDATOR_TEST_DATA", ""))
    private_template = OUTPUTS / "app" / "templates" / "private_fund_template.docx"
    licensed_template = (
        OUTPUTS / "app" / "templates" / "licensed_institution_template.docx"
    )

    @classmethod
    def setUpClass(cls):
        if not os.getenv("FOF_VALIDATOR_TEST_DATA") or not cls.data_path.is_file():
            raise unittest.SkipTest(
                "Set FOF_VALIDATOR_TEST_DATA to an approved full regression JSON file"
            )
        cls.data = json.loads(cls.data_path.read_text(encoding="utf-8"))

    def test_licensed_exact_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            payload = InputDataMapper().map(self.data, "licensed")
            generated = Path(td) / "licensed.docx"
            DocxGenerator(
                cls.licensed_template,
                OUTPUTS / "app" / "templates" / "licensed_institution_manifest.json",
            ).generate(payload, generated)
            report = Validator(self.licensed_template).validate(generated, self.data)
            self.assertEqual(report.missing, 0)
            self.assertEqual(report.mismatched, 0)
            self.assertEqual(report.extra, 0)
            self.assertEqual(report.table_issue_count, 0)

    def test_private_round_trip_mapped_fields(self):
        with tempfile.TemporaryDirectory() as td:
            payload = InputDataMapper().map(self.data, "private")
            generated = Path(td) / "private.docx"
            DocxGenerator(
                self.private_template,
                OUTPUTS / "app" / "templates" / "private_fund_manifest.json",
            ).generate(payload, generated)
            report = Validator(self.private_template).validate(generated, self.data)
            self.assertEqual(report.missing, 0)
            self.assertEqual(report.mismatched, 0)
            self.assertEqual(report.extra, 0)
            self.assertEqual(report.table_issue_count, 0)

    def test_detects_value_mismatch_and_extra(self):
        with tempfile.TemporaryDirectory() as td:
            payload = InputDataMapper().map(self.data, "licensed")
            payload["cover_manager_name"] = "错误管理人"
            payload["attachment_extra_1"] = "不应出现的附件"
            generated = Path(td) / "bad_values.docx"
            DocxGenerator(
                self.licensed_template,
                OUTPUTS / "app" / "templates" / "licensed_institution_manifest.json",
            ).generate(payload, generated)
            report = Validator(self.licensed_template).validate(generated, self.data)
            self.assertGreaterEqual(report.mismatched, 1)
            self.assertGreaterEqual(report.extra, 1)

    def test_detects_format_issue(self):
        with tempfile.TemporaryDirectory() as td:
            payload = InputDataMapper().map(self.data, "licensed")
            generated = Path(td) / "bad_format.docx"
            DocxGenerator(
                self.licensed_template,
                OUTPUTS / "app" / "templates" / "licensed_institution_manifest.json",
                styles={
                    "qa": StyleSpec(
                        font_east_asia="Arial",
                        size_pt=18,
                        color="FF0000",
                    )
                },
            ).generate(payload, generated)
            report = Validator(self.licensed_template).validate(generated, self.data)
            self.assertGreater(report.format_issue_count, 0)

    def test_detects_missing_value(self):
        with tempfile.TemporaryDirectory() as td:
            payload = InputDataMapper().map(self.data, "licensed")
            payload["cover_manager_name"] = ""
            generated = Path(td) / "missing.docx"
            DocxGenerator(
                self.licensed_template,
                OUTPUTS / "app" / "templates" / "licensed_institution_manifest.json",
            ).generate(payload, generated)
            report = Validator(self.licensed_template).validate(generated, self.data)
            self.assertGreaterEqual(report.missing, 1)

    def test_detects_table_alignment_change(self):
        with tempfile.TemporaryDirectory() as td:
            payload = InputDataMapper().map(self.data, "licensed")
            generated = Path(td) / "table_bad.docx"
            DocxGenerator(
                self.licensed_template,
                OUTPUTS / "app" / "templates" / "licensed_institution_manifest.json",
            ).generate(payload, generated)
            unpacked = Path(td) / "unpacked"
            with zipfile.ZipFile(generated) as archive:
                archive.extractall(unpacked)
            xml_path = unpacked / "word/document.xml"
            tree = etree.parse(str(xml_path))
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            width = tree.xpath("//w:body/w:tbl[1]/w:tblGrid/w:gridCol[1]", namespaces=ns)[0]
            key = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}w"
            width.set(key, str(int(width.get(key)) + 200))
            xml_path.write_bytes(etree.tostring(
                tree, xml_declaration=True, encoding="UTF-8", standalone="yes"
            ))
            with zipfile.ZipFile(generated, "w", zipfile.ZIP_DEFLATED) as archive:
                for file in unpacked.rglob("*"):
                    if file.is_file():
                        archive.write(file, file.relative_to(unpacked))
            report = Validator(self.licensed_template).validate(generated, self.data)
            self.assertGreater(report.table_issue_count, 0)


if __name__ == "__main__":
    unittest.main()
