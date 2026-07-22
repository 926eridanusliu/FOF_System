from __future__ import annotations

import shutil
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from docx.image.image import Image as DocxImage
from lxml import etree


class DocxPackage:
    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    NS = {"w": W, "r": R}

    def __init__(self, template_path: str | Path):
        self.template_path = Path(template_path)
        self._temp = TemporaryDirectory()
        self.root = Path(self._temp.name)
        with zipfile.ZipFile(self.template_path) as archive:
            archive.extractall(self.root)
        self.parts: dict[Path, etree._ElementTree] = {}
        for part in self._xml_parts():
            parser = etree.XMLParser(remove_blank_text=False)
            self.parts[part] = etree.parse(str(part), parser)

    @classmethod
    def qn(cls, name: str) -> str:
        return f"{{{cls.W}}}{name}"

    @property
    def document_tree(self) -> etree._ElementTree:
        return self.parts[self.root / "word/document.xml"]

    @property
    def body(self):
        return self.document_tree.find(".//w:body", self.NS)

    def bookmark_index(self) -> dict[str, tuple[etree._Element, etree._Element, Path]]:
        result = {}
        for path, tree in self.parts.items():
            ends = {
                el.get(self.qn("id")): el
                for el in tree.xpath("//w:bookmarkEnd", namespaces=self.NS)
            }
            for start in tree.xpath("//w:bookmarkStart", namespaces=self.NS):
                name = start.get(self.qn("name"))
                end = ends.get(start.get(self.qn("id")))
                if name and end is not None:
                    result[name] = (start, end, path)
        return result

    def paragraph_count(self) -> int:
        return len(self.document_tree.xpath("//w:body//w:p", namespaces=self.NS))

    def save(self, output_path: str | Path) -> Path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        for path, tree in self.parts.items():
            path.write_bytes(
                etree.tostring(
                    tree,
                    xml_declaration=True,
                    encoding="UTF-8",
                    standalone="yes",
                )
            )
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for file in self.root.rglob("*"):
                if file.is_file():
                    archive.write(file, file.relative_to(self.root))
        return output

    def close(self) -> None:
        self._temp.cleanup()

    def add_image(self, image_path: Path, *, width_inches: float = 6.0):
        relationships_path = self.root / "word/_rels/document.xml.rels"
        relationships = etree.parse(str(relationships_path))
        relationship_root = relationships.getroot()
        ids = []
        for relationship in relationship_root:
            rid = relationship.get("Id", "")
            if rid.startswith("rId") and rid[3:].isdigit():
                ids.append(int(rid[3:]))
        relationship_id = f"rId{max(ids, default=0) + 1}"
        media = self.root / "word/media"
        media.mkdir(exist_ok=True)
        extension = image_path.suffix.lower().lstrip(".")
        if extension == "jpeg":
            extension = "jpg"
        index = 1
        while (media / f"bookmark_image_{index}.{extension}").exists():
            index += 1
        target = media / f"bookmark_image_{index}.{extension}"
        shutil.copy2(image_path, target)
        relationship = etree.SubElement(
            relationship_root,
            "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship",
        )
        relationship.set("Id", relationship_id)
        relationship.set(
            "Type",
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image",
        )
        relationship.set("Target", f"media/{target.name}")
        relationships_path.write_bytes(
            etree.tostring(
                relationships,
                xml_declaration=True,
                encoding="UTF-8",
                standalone="yes",
            )
        )
        self._ensure_image_content_type(extension)
        image = DocxImage.from_file(str(image_path))
        pixel_width, pixel_height = image.px_width, image.px_height
        cx = int(width_inches * 914400)
        cy = int(cx * pixel_height / pixel_width)
        return relationship_id, cx, cy

    def next_drawing_id(self) -> int:
        values = [
            int(value)
            for value in self.document_tree.xpath(
                "//wp:docPr/@id",
                namespaces={
                    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
                },
            )
            if str(value).isdigit()
        ]
        return max(values, default=0) + 1

    def _ensure_image_content_type(self, extension: str) -> None:
        content_types_path = self.root / "[Content_Types].xml"
        tree = etree.parse(str(content_types_path))
        root = tree.getroot()
        if any(
            child.get("Extension", "").lower() == extension
            for child in root
            if etree.QName(child).localname == "Default"
        ):
            return
        content_type = "image/png" if extension == "png" else "image/jpeg"
        default = etree.SubElement(
            root,
            "{http://schemas.openxmlformats.org/package/2006/content-types}Default",
        )
        default.set("Extension", extension)
        default.set("ContentType", content_type)
        content_types_path.write_bytes(
            etree.tostring(tree, xml_declaration=True, encoding="UTF-8", standalone="yes")
        )

    def _xml_parts(self):
        word = self.root / "word"
        yield word / "document.xml"
        yield from word.glob("header*.xml")
        yield from word.glob("footer*.xml")
