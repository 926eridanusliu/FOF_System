from __future__ import annotations

from .base_filler import BaseFiller


class QASectionFiller(BaseFiller):
    category = "qa"

    def fill(self, field: str, value: object):
        return self.fill_result(field, value).as_tuple()

    def fill_result(self, field: str, value: object, *, meta: dict | None = None):
        located = self.bookmark(field)
        if located is None:
            return self.result(False, field, value, field, message="未找到问答书签")
        string = "" if value is None else str(value)
        abnormal, message = self.styles.validate_value(string, self.category)
        start, end, _ = located
        holder = start.getparent()
        if holder.tag != self.package.qn("p") or end.getparent() is not holder:
            return self.result(False, field, value, field, message="问答书签不在单一段落内")
        lines = string.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if not lines:
            lines = [""]
        visible = "".join(holder.xpath(".//w:t/text()", namespaces=self.package.NS)).strip()
        parent = holder.getparent()
        inserted = 0
        if visible:
            # Bookmark is on the question: insert answer paragraph(s) after it.
            insertion_mode = (meta or {}).get("insertion_mode", "append_after_question")
            anchor = (
                self._following_block_end(holder)
                if insertion_mode == "append_after_following_block"
                else holder
            )
            for line in lines:
                paragraph = self.styles.clone_paragraph(holder)
                self._mark_generated(paragraph)
                self.styles.format_answer_paragraph(paragraph)
                self._append_text_runs(
                    paragraph,
                    line,
                    source_paragraph=holder,
                )
                parent.insert(parent.index(anchor) + 1, paragraph)
                anchor = paragraph
                inserted += 1
            location = (
                f"bookmark:{field}; after_following_block"
                if insertion_mode == "append_after_following_block"
                else f"bookmark:{field}; after_question"
            )
        else:
            # Existing blank answer paragraph is the first slot.
            self.styles.format_answer_paragraph(holder)
            while start.getnext() is not end:
                holder.remove(start.getnext())
            self._insert_text_runs_before(
                holder,
                end,
                lines[0],
                source_paragraph=holder,
            )
            anchor = holder
            for line in lines[1:]:
                paragraph = self.styles.clone_paragraph(holder)
                self._mark_generated(paragraph)
                self.styles.format_answer_paragraph(paragraph)
                self._append_text_runs(
                    paragraph,
                    line,
                    source_paragraph=holder,
                )
                parent.insert(parent.index(anchor) + 1, paragraph)
                anchor = paragraph
                inserted += 1
            location = f"bookmark:{field}; blank_answer_paragraph"
        return self.result(
            True,
            field,
            value,
            location,
            abnormal=abnormal,
            message=message,
            delta=inserted,
        )

    def _mark_generated(self, paragraph) -> None:
        # A valid Word revision-session attribute gives the validator a stable
        # way to distinguish inserted answer paragraphs from untagged fixed
        # template labels that may also lack w14:paraId.
        paragraph.set(self.package.qn("rsidR"), "C0D3C0D3")

    def _append_text_runs(self, paragraph, text: str, *, source_paragraph):
        # Word accepts very large w:t nodes, but some renderers silently omit a
        # single node containing several thousand characters.  Splitting the
        # node into style-identical runs keeps the logical paragraph and its
        # extracted value unchanged while making long answers reliably visible.
        chunks = [
            text[index:index + 500]
            for index in range(0, len(text), 500)
        ] or [""]
        for chunk in chunks:
            paragraph.append(
                self.styles.make_run(
                    chunk,
                    source_paragraph=source_paragraph,
                    category=self.category,
                )
            )

    def _insert_text_runs_before(
        self,
        paragraph,
        anchor,
        text: str,
        *,
        source_paragraph,
    ):
        chunks = [
            text[index:index + 500]
            for index in range(0, len(text), 500)
        ] or [""]
        position = paragraph.index(anchor)
        for chunk in chunks:
            paragraph.insert(
                position,
                self.styles.make_run(
                    chunk,
                    source_paragraph=source_paragraph,
                    category=self.category,
                ),
            )
            position += 1

    def _following_block_end(self, question):
        """Return the last non-empty paragraph in the block following a question."""
        anchor = question
        found_content = False
        sibling = question.getnext()
        while sibling is not None and sibling.tag == self.package.qn("p"):
            text = "".join(
                sibling.xpath(".//w:t/text()", namespaces=self.package.NS)
            ).strip()
            if not text:
                if found_content:
                    break
                sibling = sibling.getnext()
                continue
            found_content = True
            anchor = sibling
            sibling = sibling.getnext()
        return anchor

    def clear_result(self, field: str, message: str = "策略不适用，已跳过并清空占位"):
        located = self.bookmark(field)
        if located is None:
            return self.result(False, field, "", field, message="未找到问答书签")
        start, end, _ = located
        holder = start.getparent()
        if end.getparent() is not holder:
            return self.result(False, field, "", field, message="问答书签跨容器")
        while start.getnext() is not end:
            holder.remove(start.getnext())
        return self.result(
            True,
            field,
            "",
            f"bookmark:{field}; skipped",
            message=message,
        )
