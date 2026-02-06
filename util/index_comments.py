"""Comment storage keyed by page+field to avoid duplicates in the index CSV."""


class Comment:
    """A single QC comment for a (page, field)."""

    def __init__(self, page: int, field: str, comment: str):
        self.page = page
        self.field = field
        self.comment = comment
        self.identity = f"P{self.page}: {self.field}"

    def __str__(self) -> str:
        return f"P{self.page}: {self.field}: {self.comment}"


class Comments:
    """Dictionary of comments keyed by identity 'P{page}: {field}' to prevent duplicates."""

    def __init__(self, comments: dict[str, "Comment"] | None = None):
        self.comments = comments.copy() if comments else {}

    def add_comment(self, comment: Comment) -> None:
        self.comments[comment.identity] = comment

    def remove_comment(self, identity: str) -> None:
        self.comments.pop(identity, None)

    def get_comment(self, identity: str) -> Comment | None:
        return self.comments.get(identity)

    def get_for_page(self, page: int) -> dict[str, str]:
        """Return field name -> comment text for the given page (for UI display)."""
        result: dict[str, str] = {}
        for c in self.comments.values():
            if c.page == page and c.comment:
                result[c.field] = c.comment
        return result

    def to_csv_string(self) -> str:
        """Serialize to the Comments column format: 'P1: Field: comment | P2: ...'."""
        parts = [
            f"P{c.page}: {c.field}: {c.comment}"
            for c in sorted(self.comments.values(), key=lambda x: (x.page, x.field))
            if c.comment.strip()
        ]
        return " | ".join(parts)

    @classmethod
    def from_string(cls, cell: str) -> "Comments":
        """
        Parse the Comments column string. Duplicate (page, field) entries are merged
        (last occurrence wins), so the result is always deduplicated.
        """
        comments = cls()
        if not (cell or "").strip():
            return comments
        for part in cell.split("|"):
            token = part.strip()
            if not token or ":" not in token:
                continue
            prefix, rest = token.split(":", 1)
            prefix = prefix.strip()
            if not prefix.startswith("P") or not prefix[1:].isdigit():
                continue
            page_num = int(prefix[1:])
            rest = rest.strip()
            if not rest:
                continue
            if ":" in rest:
                field_name, comment = rest.split(":", 1)
                field_name = field_name.strip()
                comment = comment.strip()
            else:
                field_name = rest
                comment = ""
            if field_name:
                comments.add_comment(Comment(page_num, field_name, comment))
        return comments

    def __str__(self) -> str:
        return "|".join(str(c) for c in self.comments.values())
