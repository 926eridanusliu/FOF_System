from __future__ import annotations

from pathlib import Path

from lxml import etree

from .base_filler import BaseFiller


class ImageFiller(BaseFiller):
    """Insert an inline image at an image bookmark without text searching."""

    category = "image"

    def fill(self, field: str, value: object):
        return self.fill_result(field, value).as_tuple()

    def fill_result(self, field: str, value: object):
        located = self.bookmark(field)
        if located is None:
            return self.result(False, field, value, field, message="未找到图片书签")
        if not value:
            return self.result(True, field, "", f"bookmark:{field}", message="未提供图片")
        options = value if isinstance(value, dict) else {"path": value}
        image_path = Path(str(options.get("path", ""))).expanduser()
        if not image_path.is_file():
            return self.result(
                False, field, value, f"bookmark:{field}", message=f"图片不存在：{image_path}"
            )
        try:
            relationship_id, width, height = self.package.add_image(
                image_path,
                width_inches=float(options.get("width_inches", 6.0)),
            )
            start, end, _ = located
            holder = start.getparent()
            while start.getnext() is not end:
                holder.remove(start.getnext())
            holder.insert(
                holder.index(end),
                self._drawing_run(relationship_id, width, height, image_path.name),
            )
        except Exception as exc:
            return self.result(
                False, field, value, f"bookmark:{field}", message=f"图片插入失败：{exc}"
            )
        return self.result(
            True,
            field,
            f"[图片] {image_path.name}",
            f"bookmark:{field}; inline_image",
        )

    def _drawing_run(self, relationship_id: str, cx: int, cy: int, name: str):
        ns = {
            "w": self.package.W,
            "r": self.package.R,
            "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
            "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
            "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
        }
        xml = f"""
        <w:r xmlns:w="{ns['w']}" xmlns:r="{ns['r']}"
             xmlns:wp="{ns['wp']}" xmlns:a="{ns['a']}" xmlns:pic="{ns['pic']}">
          <w:drawing>
            <wp:inline distT="0" distB="0" distL="0" distR="0">
              <wp:extent cx="{cx}" cy="{cy}"/>
              <wp:effectExtent l="0" t="0" r="0" b="0"/>
              <wp:docPr id="{self.package.next_drawing_id()}" name="{self._escape(name)}"/>
              <wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr>
              <a:graphic>
                <a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
                  <pic:pic>
                    <pic:nvPicPr>
                      <pic:cNvPr id="0" name="{self._escape(name)}"/>
                      <pic:cNvPicPr/>
                    </pic:nvPicPr>
                    <pic:blipFill>
                      <a:blip r:embed="{relationship_id}"/>
                      <a:stretch><a:fillRect/></a:stretch>
                    </pic:blipFill>
                    <pic:spPr>
                      <a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>
                      <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
                    </pic:spPr>
                  </pic:pic>
                </a:graphicData>
              </a:graphic>
            </wp:inline>
          </w:drawing>
        </w:r>
        """
        return etree.fromstring(xml.encode("utf-8"))

    @staticmethod
    def _escape(value: str) -> str:
        return (
            value.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;")
        )
