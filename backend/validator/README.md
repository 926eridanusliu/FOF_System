# Validator

自动提取生成 DOCX 中全部书签字段，并与输入 JSON 逐字段比较。支持附件1-1
（私募基金）与附件1-2（持牌金融机构）。

## 使用方法

```python
from validator import Validator

validator = Validator(
    template_path="FOF尽调报告_持牌金融机构_书签模板.docx",
    profile="licensed",
)

report = validator.validate(
    "附件1-2_完整数据.docx",
    "完整数据.json",
)

print(report.success)
print(report.missing, report.mismatched, report.extra)

report.to_json("验证报告.json")
report.to_docx("验证报告.docx")
```

附件1-1可使用 `profile="private_2026"`；也可省略 `profile`，由 Validator
根据书签自动识别模板类型。

## 检查范围

- 字段值一致；
- 输入有值但文档为空；
- 输入为空但文档有多余内容；
- 输入字段有值但文档不存在对应书签；
- 同一字段字体/字号/颜色是否统一；
- 与空白模板上下文字体、字号、颜色是否一致；
- 表格行列、网格宽度、单元格宽度、合并属性和对齐方式是否变化。

如果输入数据已经是书签名扁平字典，验证器会直接使用；如果是
`yuanlan_data_corrected.json` 的嵌套结构，会自动识别 1-1/1-2 模板并映射。

## 命令行

```bash
PYTHONPATH=outputs python3 -m validator \
  生成结果.docx \
  yuanlan_data_corrected.json \
  --template 原始空白模板.docx \
  --json-report 验证报告.json \
  --docx-report 验证报告.docx
```

验证通过时退出码为 `0`；存在遗漏、不一致、多余填充或格式/表格异常时退出码为 `2`。
