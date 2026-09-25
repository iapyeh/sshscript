#!/usr/bin/env python3
"""Validate the maintained SSHScript v3a documentation source."""

from __future__ import annotations

import argparse
import ast
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import posixpath
import re
import sys
from urllib.parse import unquote, urljoin, urlsplit


ROOT = Path(__file__).resolve().parents[1]
DOC_ROOT = ROOT / "v3a"
CURRENT_VERSION = "3.1.4"
PLACEHOLDER_MARKER = "> **Documentation status: Placeholder**"
LAST_UPDATED_RE = re.compile(
    r"(?:^|\n)Last Updated: "
    r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\n?\Z"
)
LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
STALE_RELEASE_PATTERNS = [
    (re.compile(r"\bv3\.1\s+beta\b", re.IGNORECASE), "v3.1 beta status"),
    (re.compile(r"\b(?:is|remains)\s+beta\b", re.IGNORECASE), "beta status"),
    (
        re.compile(r"not\s+(?:currently\s+|yet\s+)?published\s+on\s+PyPI", re.IGNORECASE),
        "unpublished-on-PyPI claim",
    ),
    (
        re.compile(r"(?:public\s+)?v3\.1\s+artifact\s+pending", re.IGNORECASE),
        "pending v3.1 artifact claim",
    ),
    (
        re.compile(r"(?:test\s+)?matrix\s+(?:is|remains)\s+pending", re.IGNORECASE),
        "pending test-matrix claim",
    ),
    (
        re.compile(r"\bdevelopment implementation\b", re.IGNORECASE),
        "development-only implementation claim",
    ),
    (
        re.compile(r"PyPI.{0,80}\b2\.0\.2\b", re.IGNORECASE | re.DOTALL),
        "stale PyPI 2.0.2 claim",
    ),
]


@dataclass(frozen=True)
class Page:
    path: Path
    metadata: dict[str, object]
    body: str
    text: str
    url: str

    @property
    def relative_path(self) -> str:
        return self.path.relative_to(ROOT).as_posix()

    @property
    def visible(self) -> bool:
        return self.metadata.get("nav_exclude") is not True

    @property
    def placeholder(self) -> bool:
        return PLACEHOLDER_MARKER in self.body


def parse_scalar(value: str) -> object:
    value = value.strip()
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"null", "~"}:
        return None
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        try:
            return ast.literal_eval(value)
        except (SyntaxError, ValueError):
            return value[1:-1]
    return value


def parse_front_matter(path: Path, text: str) -> tuple[dict[str, object], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("missing opening YAML front-matter boundary")
    try:
        end = next(index for index, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration as exc:
        raise ValueError("missing closing YAML front-matter boundary") from exc

    metadata: dict[str, object] = {}
    for line_number, line in enumerate(lines[1:end], 2):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[:1].isspace() or ":" not in line:
            raise ValueError(
                f"unsupported front-matter syntax on line {line_number}: {line!r}"
            )
        key, value = line.split(":", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"empty front-matter key on line {line_number}")
        if key in metadata:
            raise ValueError(f"duplicate front-matter key {key!r}")
        metadata[key] = parse_scalar(value)
    return metadata, "\n".join(lines[end + 1 :]) + ("\n" if text.endswith("\n") else "")


def normalize_url(value: str) -> str:
    value = unquote(value)
    if not value.startswith("/"):
        value = "/" + value
    had_trailing_slash = value.endswith("/")
    value = posixpath.normpath(value)
    if value == ".":
        value = "/"
    if had_trailing_slash and value != "/":
        value += "/"
    return value


def page_url(path: Path, metadata: dict[str, object]) -> str:
    permalink = metadata.get("permalink")
    if isinstance(permalink, str) and permalink:
        return normalize_url(permalink)
    relative = path.relative_to(ROOT).as_posix()
    if path.name == "index.md":
        output = "/" + str(Path(relative).parent).replace("\\", "/") + "/"
    else:
        output = "/" + relative[:-3] + "/"
    return normalize_url(output)


def load_pages(errors: list[str]) -> list[Page]:
    pages: list[Page] = []
    paths = sorted(DOC_ROOT.rglob("*.md")) + [ROOT / "README.md"]
    for path in paths:
        text = path.read_text(encoding="utf-8")
        try:
            metadata, body = parse_front_matter(path, text)
        except ValueError as exc:
            errors.append(f"{path.relative_to(ROOT)}: {exc}")
            continue
        if path.name.endswith(".zh-tw.md") or metadata.get("published") is False:
            continue
        pages.append(Page(path, metadata, body, text, page_url(path, metadata)))
    return pages


def check_page_shape(page: Page, errors: list[str], check_mtime: bool) -> None:
    label = page.relative_path
    title = page.metadata.get("title")
    if not isinstance(title, str) or not title.strip():
        errors.append(f"{label}: missing nonempty title")
    match = H1_RE.search(page.body)
    if not match:
        errors.append(f"{label}: missing H1")
    elif title != match.group(1):
        errors.append(
            f"{label}: front-matter title {title!r} does not match H1 {match.group(1)!r}"
        )

    updated = LAST_UPDATED_RE.search(page.text)
    if not updated:
        errors.append(f"{label}: missing trailing Last Updated timestamp")
    else:
        try:
            datetime.strptime(updated.group(1), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            errors.append(f"{label}: invalid Last Updated timestamp {updated.group(1)!r}")
        if check_mtime:
            actual = datetime.fromtimestamp(page.path.stat().st_mtime).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            if updated.group(1) != actual:
                errors.append(
                    f"{label}: Last Updated {updated.group(1)} does not match mtime {actual}"
                )

    if page.placeholder:
        for key in ("nav_exclude", "search_exclude"):
            if page.metadata.get(key) is not True:
                errors.append(f"{label}: placeholder must set {key}: true")
    else:
        for pattern, description in STALE_RELEASE_PATTERNS:
            if pattern.search(page.body):
                errors.append(f"{label}: contains {description}")


def check_navigation(pages: list[Page], errors: list[str]) -> None:
    by_title: dict[str, list[Page]] = defaultdict(list)
    for page in pages:
        title = page.metadata.get("title")
        if isinstance(title, str):
            by_title[title].append(page)

    for title, matches in sorted(by_title.items()):
        if len(matches) > 1:
            locations = ", ".join(page.relative_path for page in matches)
            errors.append(f"duplicate public title {title!r}: {locations}")

    for page in pages:
        label = page.relative_path
        parent_title = page.metadata.get("parent")
        grand_title = page.metadata.get("grand_parent")
        parent: Page | None = None
        if parent_title is not None:
            matches = by_title.get(str(parent_title), [])
            if len(matches) != 1:
                errors.append(f"{label}: parent {parent_title!r} does not resolve uniquely")
            else:
                parent = matches[0]
                if page.visible and not parent.visible:
                    errors.append(f"{label}: visible page has hidden parent {parent_title!r}")
                if page.visible and parent.metadata.get("has_children") is not True:
                    errors.append(
                        f"{label}: visible page parent {parent_title!r} must set has_children: true"
                    )

        if grand_title is not None:
            if len(by_title.get(str(grand_title), [])) != 1:
                errors.append(
                    f"{label}: grand_parent {grand_title!r} does not resolve uniquely"
                )
            if parent is not None and parent.metadata.get("parent") != grand_title:
                errors.append(
                    f"{label}: grand_parent {grand_title!r} does not match "
                    f"parent page's parent {parent.metadata.get('parent')!r}"
                )
        elif parent is not None and parent.metadata.get("parent") is not None:
            errors.append(f"{label}: third-level page is missing grand_parent")

    visible = [page for page in pages if page.visible]
    roots = [page for page in visible if page.metadata.get("parent") is None]
    if len(roots) != 1 or roots[0].metadata.get("title") != "SSHScript v3.1 Documentation":
        details = ", ".join(
            f"{page.metadata.get('title')!r} ({page.relative_path})" for page in roots
        )
        errors.append(
            "visible navigation must have only the SSHScript v3.1 Documentation "
            f"root; found: {details or 'none'}"
        )

    siblings: dict[tuple[object, object], dict[int, Page]] = defaultdict(dict)
    for page in visible:
        order = page.metadata.get("nav_order")
        if not isinstance(order, int):
            errors.append(f"{page.relative_path}: visible page needs integer nav_order")
            continue
        group = (page.metadata.get("grand_parent"), page.metadata.get("parent"))
        prior = siblings[group].get(order)
        if prior is not None:
            errors.append(
                f"{page.relative_path}: nav_order {order} collides with "
                f"{prior.relative_path} among siblings"
            )
        else:
            siblings[group][order] = page

    visible_children: dict[str, int] = defaultdict(int)
    for page in visible:
        parent = page.metadata.get("parent")
        if isinstance(parent, str):
            visible_children[parent] += 1
    for page in visible:
        title = page.metadata.get("title")
        if page.metadata.get("has_children") is True and visible_children[str(title)] == 0:
            errors.append(f"{page.relative_path}: has_children is true but no child is visible")


def url_aliases(url: str) -> set[str]:
    url = normalize_url(url)
    aliases = {url}
    if url != "/":
        aliases.add(url.rstrip("/"))
        aliases.add(url.rstrip("/") + "/")
    return aliases


def check_links(pages: list[Page], errors: list[str]) -> int:
    known_urls: dict[str, Page] = {}
    for page in pages:
        for alias in url_aliases(page.url):
            prior = known_urls.get(alias)
            if prior is not None and prior != page:
                errors.append(
                    f"{page.relative_path}: output URL {alias!r} collides with "
                    f"{prior.relative_path}"
                )
            known_urls[alias] = page

    checked = 0
    for page in pages:
        for match in LINK_RE.finditer(page.body):
            raw = match.group(1).strip()
            if raw.startswith("<") and raw.endswith(">"):
                raw = raw[1:-1]
            if re.match(r"^(?:https?:|mailto:|tel:)", raw, re.IGNORECASE):
                continue
            if raw.startswith("#"):
                continue
            target = re.sub(r"\{\{\s*site\.baseurl\s*\}\}", "", raw)
            if "{{" in target or "{%" in target:
                errors.append(f"{page.relative_path}: unsupported Liquid link target {raw!r}")
                continue
            parsed = urlsplit(target)
            target_path = parsed.path
            if not target_path:
                continue
            if target_path == "/sshscript":
                target_path = "/"
            elif target_path.startswith("/sshscript/"):
                target_path = target_path[len("/sshscript") :]
            if target_path.startswith("/"):
                resolved = normalize_url(target_path)
            else:
                resolved = normalize_url(urljoin(page.url, target_path))
            checked += 1
            if not any(alias in known_urls for alias in url_aliases(resolved)):
                errors.append(
                    f"{page.relative_path}: internal link {raw!r} resolves to "
                    f"missing page {resolved!r}"
                )
    return checked


def check_repository_metadata(errors: list[str]) -> None:
    for relative in ("_config.yml", "index.html", "404.html", "README.md"):
        if not (ROOT / relative).is_file():
            errors.append(f"repository root is missing {relative}")
    info_path = ROOT / "info.json"
    try:
        version = json.loads(info_path.read_text(encoding="utf-8")).get("version")
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        errors.append(f"info.json is missing or invalid: {exc}")
    else:
        if version != CURRENT_VERSION:
            errors.append(
                f"info.json version is {version!r}; expected {CURRENT_VERSION!r}"
            )

    config = (ROOT / "_config.yml").read_text(encoding="utf-8")
    if not re.search(
        r"^remote_theme:\s+\S+@[0-9a-f]{40}(?:\s+#.*)?$",
        config,
        re.MULTILINE,
    ):
        errors.append("_config.yml must pin remote_theme to an immutable commit")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-mtime",
        action="store_true",
        help="also require filesystem mtime to equal each trailing Last Updated value",
    )
    args = parser.parse_args()

    errors: list[str] = []
    pages = load_pages(errors)
    for page in pages:
        check_page_shape(page, errors, args.check_mtime)
    check_navigation(pages, errors)
    links = check_links(pages, errors)
    check_repository_metadata(errors)

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"Documentation validation failed with {len(errors)} error(s).", file=sys.stderr)
        return 1

    placeholders = sum(page.placeholder for page in pages)
    visible = sum(page.visible for page in pages)
    v3a_pages = sum(DOC_ROOT in page.path.parents for page in pages)
    print(
        f"Validated {v3a_pages} public English v3a pages plus the branch README "
        f"({visible} visible navigation nodes, {placeholders} placeholders) "
        f"and {links} internal links."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
