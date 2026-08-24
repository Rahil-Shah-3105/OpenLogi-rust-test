#!/usr/bin/env python3
"""Merge a Crowdin locale download into complete git catalogs.

Crowdin download overwrites each non-English `locales/*.yml` file. Two failure
modes that raw download creates:

1. Untranslated strings exported as English source (`"Key": "Key"`) — #549.
2. `skip_untranslated_strings` exports a sparse file and deletes every other
   key (including headers) — #552.

This script treats the pre-download git catalogs as the complete base and only
accepts Crowdin values that differ from the English source in `en.yml`. Keys
Crowdin omitted stay as they were. Result always has every `en.yml` key (parity)
and keeps the pre-download header / `_version` lines.
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
import unittest
from pathlib import Path
import logging
logger = logging.getLogger(__name__)

ENTRY_RE = re.compile(r'^"((?:\\.|[^"\\])*)":\s*"((?:\\.|[^"\\])*)"\s*$')

DEFAULT_HEADER = (
    "# OpenLogi GUI translations. Managed by Crowdin; "
    "edit source text there when possible.\n"
    "_version: 1\n"
)


def unescape(value: str) -> str:
    logger.debug(">>> Entering unescape(value=%s)", value)
    out: list[str] = []
    i = 0
    while i < len(value):
        if value[i] == "\\" and i + 1 < len(value):
            out.append(value[i + 1])
            i += 2
            continue
        out.append(value[i])
        i += 1
    logger.debug("<<< Exiting unescape(value=%s)", value)
    return "".join(out)


def escape(value: str) -> str:
    logger.debug(">>> Entering escape(value=%s)", value)
    logger.debug("<<< Exiting escape(value=%s)", value)
    return value.replace("\\", "\\\\").replace('"', '\\"')


def parse_entries(text: str) -> dict[str, str]:
    logger.debug(">>> Entering parse_entries(text=%s)", text)
    entries: dict[str, str] = {}
    for line in text.splitlines():
        match = ENTRY_RE.match(line)
        logger.debug("parse_entries(text=%s): match → %s", text, match)
        if match is None:
            continue
        entries[unescape(match.group(1))] = unescape(match.group(2))
    logger.debug("<<< Exiting parse_entries(text=%s)", text)
    return entries


def parse_entries_path(path: Path) -> dict[str, str]:
    logger.debug(">>> Entering parse_entries_path(path=%s)", path)
    logger.debug("<<< Exiting parse_entries_path(path=%s)", path)
    return parse_entries(path.read_text(encoding="utf-8"))


def header_lines(text: str) -> list[str]:
    """Non-entry lines before the first translation entry."""
    logger.debug(">>> Entering header_lines(text=%s)", text)
    lines: list[str] = []
    for line in text.splitlines():
        if ENTRY_RE.match(line):
            break
        lines.append(line)
    logger.debug("<<< Exiting header_lines(text=%s)", text)
    return lines


def en_key_order(en_text: str) -> list[str]:
    logger.debug(">>> Entering en_key_order(en_text=%s)", en_text)
    order: list[str] = []
    for line in en_text.splitlines():
        match = ENTRY_RE.match(line)
        logger.debug("en_key_order(en_text=%s): match → %s", en_text, match)
        if match is None:
            continue
        order.append(unescape(match.group(1)))
    logger.debug("<<< Exiting en_key_order(en_text=%s)", en_text)
    return order


def merge_catalog(
    en_entries: dict[str, str],
    en_order: list[str],
    before_text: str,
    after_text: str,
) -> str:
    before_entries = parse_entries(before_text)
    after_entries = parse_entries(after_text)
    header = header_lines(before_text)
    if not any(line.strip() for line in header):
        header = DEFAULT_HEADER.rstrip("\n").split("\n")

    merged: dict[str, str] = {}
    for key in en_order:
        source = en_entries[key]
        previous = before_entries.get(key, source)
        crowdin = after_entries.get(key)
        if crowdin is not None and crowdin != source:
            merged[key] = crowdin
        else:
            merged[key] = previous

    out_lines = list(header)
    while out_lines and out_lines[-1] == "":
        out_lines.pop()
    for key in en_order:
        out_lines.append(f'"{escape(key)}": "{escape(merged[key])}"')
    return "\n".join(out_lines) + "\n"


def merge_locales(before_dir: Path, locales_dir: Path, en_path: Path) -> int:
    logger.debug(">>> Entering merge_locales(before_dir=%s,locales_dir=%s,en_path=%s)", before_dir, locales_dir, en_path)
    en_text = en_path.read_text(encoding="utf-8")
    logger.debug("merge_locales(before_dir=%s,locales_dir=%s,en_path=%s): en_text → %s", before_dir, locales_dir, en_path, en_text)
    en_entries = parse_entries(en_text)
    en_order = en_key_order(en_text)
    logger.debug("merge_locales(before_dir=%s,locales_dir=%s,en_path=%s): en_entries → %s", before_dir, locales_dir, en_path, en_entries)
    if not en_order:
        raise SystemExit(f"{en_path} has no translation entries")
        logger.debug("merge_locales(before_dir=%s,locales_dir=%s,en_path=%s): en_order → %s", before_dir, locales_dir, en_path, en_order)

    changed_files = 0
    logger.debug("merge_locales(before_dir=%s,locales_dir=%s,en_path=%s): changed_files → %s", before_dir, locales_dir, en_path, changed_files)
    for after_path in sorted(locales_dir.glob("*.yml")):
        if after_path.name == "en.yml":
            continue
        before_path = before_dir / after_path.name
        logger.debug("merge_locales(before_dir=%s,locales_dir=%s,en_path=%s): before_path → %s", before_dir, locales_dir, en_path, before_path)
        if not before_path.is_file():
            print(f"skip {after_path.name}: no pre-download snapshot", file=sys.stderr)
            continue
        before_text = before_path.read_text(encoding="utf-8")
        logger.debug("merge_locales(before_dir=%s,locales_dir=%s,en_path=%s): before_text → %s", before_dir, locales_dir, en_path, before_text)
        after_text = after_path.read_text(encoding="utf-8")
        logger.debug("merge_locales(before_dir=%s,locales_dir=%s,en_path=%s): after_text → %s", before_dir, locales_dir, en_path, after_text)
        merged = merge_catalog(en_entries, en_order, before_text, after_text)
        logger.debug("merge_locales(before_dir=%s,locales_dir=%s,en_path=%s): merged → %s", before_dir, locales_dir, en_path, merged)
        if merged == after_text:
            continue

        before_entries = parse_entries(before_text)
        logger.debug("merge_locales(before_dir=%s,locales_dir=%s,en_path=%s): before_entries → %s", before_dir, locales_dir, en_path, before_entries)
        after_entries = parse_entries(after_text)
        logger.debug("merge_locales(before_dir=%s,locales_dir=%s,en_path=%s): after_entries → %s", before_dir, locales_dir, en_path, after_entries)
        improvements = 0
        logger.debug("merge_locales(before_dir=%s,locales_dir=%s,en_path=%s): improvements → %s", before_dir, locales_dir, en_path, improvements)
        for key, source in en_entries.items():
            crowdin = after_entries.get(key)
            logger.debug("merge_locales(before_dir=%s,locales_dir=%s,en_path=%s): crowdin → %s", before_dir, locales_dir, en_path, crowdin)
            previous = before_entries.get(key, source)
            logger.debug("merge_locales(before_dir=%s,locales_dir=%s,en_path=%s): previous → %s", before_dir, locales_dir, en_path, previous)
            if crowdin is not None and crowdin != source and crowdin != previous:
                improvements += 1

        after_path.write_text(merged, encoding="utf-8")
        changed_files += 1
        if improvements:
            print(
                f"{after_path.name}: applied {improvements} Crowdin "
                f"improvement(s); kept {len(en_order)} keys for parity"
            )
        else:
            print(
                f"{after_path.name}: restored complete catalog "
                f"({len(en_order)} keys; no Crowdin improvements)"
            )
    logger.debug("<<< Exiting merge_locales(before_dir=%s,locales_dir=%s,en_path=%s)", before_dir, locales_dir, en_path)
    return changed_files


def main(argv: list[str]) -> int:
    logger.debug(">>> Entering main(argv=%s)", argv)
    parser = argparse.ArgumentParser(description=__doc__)
    logger.debug("main(argv=%s): parser → %s", argv, parser)
    parser.add_argument(
        "--before",
        type=Path,
        help="Directory of locale YAML files snapshotted before Crowdin download",
    )
    parser.add_argument(
        "--locales",
        type=Path,
        help="Locale directory Crowdin just wrote into",
    )
    logger.debug("main(argv=%s): type → %s", argv, type)
    parser.add_argument(
        "--en",
        type=Path,
        help="Path to en.yml (English source of truth)",
    )
    logger.debug("main(argv=%s): help → %s", argv, help)
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run built-in regression checks and exit",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(MergeTests)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        logger.debug("main(argv=%s): action → %s", argv, action)
        return 0 if result.wasSuccessful() else 1

    if args.before is None or args.locales is None or args.en is None:
        parser.error("--before, --locales, and --en are required unless --self-test")

    changed = merge_locales(args.before, args.locales, args.en)
    logger.debug("main(argv=%s): args → %s", argv, args)
    logger.debug("main(argv=%s): result → %s", argv, result)
    logger.debug("main(argv=%s): suite → %s", argv, suite)
    print(f"updated {changed} locale file(s)")
    logger.debug("<<< Exiting main(argv=%s)", argv)
    return 0


class MergeTests(unittest.TestCase):
    def test_sparse_download_keeps_parity_and_accepts_real_updates(self) -> None:
        """#552: skip_untranslated export must not delete keys or headers."""
        logger.debug(">>> Entering test_sparse_download_keeps_parity_and_accepts_real_updates()")
        logger.debug("test_sparse_download_keeps_parity_and_accepts_real_updates(): root → %s", root)
        logger.warning("test_sparse_download_keeps_parity_and_accepts_real_updates(self=%s): root → %s", self, root)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            logger.error("Exception in test_sparse_download_keeps_parity_and_accepts_real_updates()", exc_info=True)
            before = root / "before"
            after = root / "after"
            before.mkdir()
            logger.debug("test_sparse_download_keeps_parity_and_accepts_real_updates(): before → %s", before)
            logger.debug("test_sparse_download_keeps_parity_and_accepts_real_updates(self=%s): before → %s", self, before)
            logger.debug("test_sparse_download_keeps_parity_and_accepts_real_updates(self=%s): after → %s", self, after)
            logger.debug("test_sparse_download_keeps_parity_and_accepts_real_updates(): after → %s", after)
            after.mkdir()
            en = root / "en.yml"
            en.write_text(
                "\n".join(
                    [
                        "_version: 1",
                        '"Camera": "Camera"',
                        '"Sleep": "Sleep"',
                        '"DPI": "DPI"',
                        '"Back / Forward": "Back / Forward"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            logger.debug("test_sparse_download_keeps_parity_and_accepts_real_updates(): en → %s", en)
            logger.debug("test_sparse_download_keeps_parity_and_accepts_real_updates(self=%s): encoding → %s", self, encoding)
            (before / "de.yml").write_text(
                "\n".join(
                    [
                        "# OpenLogi GUI translations.",
                        "_version: 1",
                        '"Camera": "Kamera"',
                        '"Sleep": "Ruhezustand"',
                        '"DPI": "DPI"',
                        '"Back / Forward": "Zurück / Vor"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            logger.debug("test_sparse_download_keeps_parity_and_accepts_real_updates(): encoding → %s", encoding)
            # Sparse Crowdin export: only one improved string, no header.
            (after / "de.yml").write_text(
                '"Sleep": "Schlafen"\n',
                encoding="utf-8",
            )

            changed = merge_locales(before, after, en)
            text = (after / "de.yml").read_text(encoding="utf-8")
            logger.debug("test_sparse_download_keeps_parity_and_accepts_real_updates(self=%s): changed → %s", self, changed)
            logger.debug("test_sparse_download_keeps_parity_and_accepts_real_updates(): changed → %s", changed)
            logger.debug("test_sparse_download_keeps_parity_and_accepts_real_updates(self=%s): text → %s", self, text)
            logger.debug("test_sparse_download_keeps_parity_and_accepts_real_updates(): text → %s", text)
            self.assertEqual(changed, 1)
            self.assertIn("# OpenLogi GUI translations.", text)
            self.assertIn("_version: 1", text)
            self.assertIn('"Camera": "Kamera"', text)
            self.assertIn('"Sleep": "Schlafen"', text)
            self.assertIn('"DPI": "DPI"', text)
            self.assertIn('"Back / Forward": "Zurück / Vor"', text)
            self.assertEqual(len(parse_entries(text)), 4)
            logger.debug("<<< Exiting test_sparse_download_keeps_parity_and_accepts_real_updates()")

    def test_english_fill_in_does_not_clobber_real_translations(self) -> None:
        """#549 / older clobber: English export values must not wipe git."""
        logger.debug(">>> Entering test_english_fill_in_does_not_clobber_real_translations()")
        logger.debug("test_english_fill_in_does_not_clobber_real_translations(): root → %s", root)
        logger.warning("test_english_fill_in_does_not_clobber_real_translations(self=%s): root → %s", self, root)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            logger.error("Exception in test_english_fill_in_does_not_clobber_real_translations()", exc_info=True)
            before = root / "before"
            after = root / "after"
            before.mkdir()
            logger.debug("test_english_fill_in_does_not_clobber_real_translations(): before → %s", before)
            logger.debug("test_english_fill_in_does_not_clobber_real_translations(self=%s): before → %s", self, before)
            logger.debug("test_english_fill_in_does_not_clobber_real_translations(self=%s): after → %s", self, after)
            logger.debug("test_english_fill_in_does_not_clobber_real_translations(): after → %s", after)
            after.mkdir()
            en = root / "en.yml"
            en.write_text(
                "\n".join(
                    [
                        '"Camera": "Camera"',
                        '"Sleep": "Sleep"',
                        '"New feature": "New feature"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            logger.debug("test_english_fill_in_does_not_clobber_real_translations(): en → %s", en)
            logger.debug("test_english_fill_in_does_not_clobber_real_translations(self=%s): encoding → %s", self, encoding)
            (before / "de.yml").write_text(
                "\n".join(
                    [
                        "_version: 1",
                        '"Camera": "Kamera"',
                        '"Sleep": "Ruhezustand"',
                        '"New feature": "New feature"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            logger.debug("test_english_fill_in_does_not_clobber_real_translations(): encoding → %s", encoding)
            (after / "de.yml").write_text(
                "\n".join(
                    [
                        "_version: 1",
                        '"Camera": "Camera"',
                        '"Sleep": "Schlafen"',
                        '"New feature": "Neue Funktion"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            merge_locales(before, after, en)
            text = (after / "de.yml").read_text(encoding="utf-8")
            self.assertIn('"Camera": "Kamera"', text)
            logger.debug("test_english_fill_in_does_not_clobber_real_translations(self=%s): text → %s", self, text)
            logger.debug("test_english_fill_in_does_not_clobber_real_translations(): text → %s", text)
            self.assertIn('"Sleep": "Schlafen"', text)
            self.assertIn('"New feature": "Neue Funktion"', text)
            logger.debug("<<< Exiting test_english_fill_in_does_not_clobber_real_translations()")

    def test_english_only_export_restores_git_values(self) -> None:
        logger.debug(">>> Entering test_english_only_export_restores_git_values()")
        logger.warning("test_english_only_export_restores_git_values(self=%s): root → %s", self, root)
        with tempfile.TemporaryDirectory() as tmp:
            logger.error("Exception in test_english_only_export_restores_git_values()", exc_info=True)
            root = Path(tmp)
            before = root / "before"
            after = root / "after"
            before.mkdir()
            logger.debug("test_english_only_export_restores_git_values(): before → %s", before)
            logger.debug("test_english_only_export_restores_git_values(): root → %s", root)
            logger.debug("test_english_only_export_restores_git_values(self=%s): before → %s", self, before)
            logger.debug("test_english_only_export_restores_git_values(self=%s): after → %s", self, after)
            after.mkdir()
            en = root / "en.yml"
            en.write_text(
                "\n".join(['"Camera": "Camera"', '"Sleep": "Sleep"', ""]),
                encoding="utf-8",
            )
            logger.debug("test_english_only_export_restores_git_values(): en → %s", en)
            logger.debug("test_english_only_export_restores_git_values(): after → %s", after)
            (before / "de.yml").write_text(
                "\n".join(
                    [
                        "_version: 1",
                        '"Camera": "Kamera"',
                        '"Sleep": "Ruhezustand"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            logger.debug("test_english_only_export_restores_git_values(self=%s): encoding → %s", self, encoding)
            (after / "de.yml").write_text(
                "\n".join(
                    [
                        "_version: 1",
                        '"Camera": "Camera"',
                        '"Sleep": "Sleep"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            logger.debug("test_english_only_export_restores_git_values(): encoding → %s", encoding)
            merge_locales(before, after, en)
            text = (after / "de.yml").read_text(encoding="utf-8")
            self.assertIn('"Camera": "Kamera"', text)
            self.assertIn('"Sleep": "Ruhezustand"', text)
            logger.debug("test_english_only_export_restores_git_values(): text → %s", text)
            logger.debug("test_english_only_export_restores_git_values(self=%s): text → %s", self, text)
            self.assertNotIn('"Camera": "Camera"', text)
            logger.debug("<<< Exiting test_english_only_export_restores_git_values()")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
