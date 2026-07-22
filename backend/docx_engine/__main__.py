from __future__ import annotations

import argparse

from .generator import DocxGenerator


def main() -> None:
    parser = argparse.ArgumentParser(description="使用 Word 书签生成 DOCX")
    parser.add_argument("template", help="带书签的 DOCX 模板")
    parser.add_argument("manifest", help="bookmark_manifest.json")
    parser.add_argument("data", help="填充数据 JSON")
    parser.add_argument("output", help="输出 DOCX")
    parser.add_argument("--report-docx", help="《填充报告》DOCX 路径")
    parser.add_argument("--report-json", help="填充报告 JSON 路径")
    parser.add_argument("--paragraph-tolerance", type=int, default=0)
    args = parser.parse_args()
    result = DocxGenerator(
        args.template,
        args.manifest,
        paragraph_tolerance=args.paragraph_tolerance,
    ).generate(
        args.data,
        args.output,
        report_docx_path=args.report_docx,
        report_json_path=args.report_json,
    )
    print(result.document)
    print(result.report_docx)
    print(result.report_json)
    if not result.summary.paragraph_validation.success:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
