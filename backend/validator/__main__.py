from __future__ import annotations

import argparse

from .validator import Validator


def main() -> None:
    parser = argparse.ArgumentParser(description="验证书签生成的 DOCX")
    parser.add_argument("generated_docx")
    parser.add_argument("input_data")
    parser.add_argument("--template", help="原始空白模板，用于格式和表格精确比较")
    parser.add_argument("--profile", choices=["auto", "private", "licensed"], default="auto")
    parser.add_argument("--json-report", default="validation_report.json")
    parser.add_argument("--docx-report", default="validation_report.docx")
    args = parser.parse_args()
    report = Validator(args.template, profile=args.profile).validate(
        args.generated_docx,
        args.input_data,
    )
    report.to_json(args.json_report)
    report.to_docx(args.docx_report)
    print(report.to_json())
    raise SystemExit(0 if report.success else 2)


if __name__ == "__main__":
    main()
