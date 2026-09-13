"""Issue-form and docs-link contracts (stdlib only, no YAML dependency).

The `Pre-submission checks` group must appear exactly once per form,
immediately after the introductory markdown and before the first
input/textarea/dropdown, so reporters see it before writing. Required
options, title prefixes, and labels are pinned to prevent silent drift.
"""

import os
import re
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUG_FORM_PATH = os.path.join(
    REPO_ROOT, ".github", "ISSUE_TEMPLATE", "bug-report.yml"
)
FEATURE_FORM_PATH = os.path.join(
    REPO_ROOT, ".github", "ISSUE_TEMPLATE", "feature-request.yml"
)
README_PATH = os.path.join(REPO_ROOT, "README.md")
CONTRIBUTING_PATH = os.path.join(REPO_ROOT, "CONTRIBUTING.md")

TYPE_RE = re.compile(r"^  - type: (\w+)\s*$", re.MULTILINE)
ID_RE = re.compile(r"^    id: (\S+)\s*$", re.MULTILINE)
LABEL_RE = re.compile(r"^      label: (.*)\s*$", re.MULTILINE)
OPTION_RE = re.compile(r"^        - label: (.*)\s*$", re.MULTILINE)
REQUIRED_RE = re.compile(r"^          required: (true|false)\s*$", re.MULTILINE)

EXPECTED = {
    BUG_FORM_PATH: {
        "title": '"[Bug]: "',
        "label": "bug",
        "options": [
            "I searched open and closed issues for an existing report.",
            "I removed credentials, tokens, authentication callbacks, and other secrets.",
        ],
    },
    FEATURE_FORM_PATH: {
        "title": '"[Feature]: "',
        "label": "enhancement",
        "options": [
            "I searched open and closed issues for an existing request.",
            "This request does not include credentials, tokens, authentication callbacks, or other secrets.",
        ],
    },
}


def read_text(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def form_field_types(text):
    """Return the ordered `type:` values of the form body entries."""
    return TYPE_RE.findall(text)


def checkboxes_blocks(text):
    """Return [(id, label, [(option, required), ...])] for checkboxes fields."""
    blocks = []
    current = None
    option = None
    for line in text.splitlines():
        type_match = TYPE_RE.match(line)
        if type_match:
            if current is not None:
                blocks.append(current)
            current = None
            if type_match.group(1) == "checkboxes":
                current = {"id": None, "label": None, "options": []}
            option = None
            continue
        if current is None:
            continue
        id_match = ID_RE.match(line)
        if id_match and current["id"] is None:
            current["id"] = id_match.group(1)
            continue
        label_match = LABEL_RE.match(line)
        if label_match and current["label"] is None:
            current["label"] = label_match.group(1)
            continue
        option_match = OPTION_RE.match(line)
        if option_match:
            option = option_match.group(1)
            continue
        required_match = REQUIRED_RE.match(line)
        if required_match and option is not None:
            current["options"].append((option, required_match.group(1)))
            option = None
    if current is not None:
        blocks.append(current)
    return [
        (block["id"], block["label"], block["options"]) for block in blocks
    ]


class IssueFormOrderTests(unittest.TestCase):
    def test_checks_group_is_first_field_after_intro(self):
        for path in (BUG_FORM_PATH, FEATURE_FORM_PATH):
            with self.subTest(form=path):
                types = form_field_types(read_text(path))
                self.assertGreaterEqual(len(types), 2, path)
                self.assertEqual(types[0], "markdown", path)
                self.assertEqual(types[1], "checkboxes", path)
                first_content = next(
                    index
                    for index, kind in enumerate(types)
                    if kind in ("input", "textarea", "dropdown")
                )
                checks_index = types.index("checkboxes")
                self.assertLess(checks_index, first_content, path)

    def test_exactly_one_checks_group(self):
        for path in (BUG_FORM_PATH, FEATURE_FORM_PATH):
            with self.subTest(form=path):
                blocks = checkboxes_blocks(read_text(path))
                self.assertEqual(len(blocks), 1, path)
                field_id, label, _ = blocks[0]
                self.assertEqual(field_id, "checks", path)
                self.assertEqual(label, "Pre-submission checks", path)

    def test_required_options_preserved(self):
        for path, expected in EXPECTED.items():
            with self.subTest(form=path):
                (_, _, options) = checkboxes_blocks(read_text(path))[0]
                self.assertEqual(
                    [text for text, _ in options], expected["options"], path
                )
                for _, required in options:
                    self.assertEqual(required, "true", path)

    def test_title_prefix_and_labels_preserved(self):
        for path, expected in EXPECTED.items():
            with self.subTest(form=path):
                text = read_text(path)
                self.assertIn('title: "%s"' % expected["title"].strip('"'), text)
                self.assertIn("  - %s" % expected["label"], text)


class DocsLinkTests(unittest.TestCase):
    def test_contributing_exists_and_readme_links_it(self):
        self.assertTrue(
            os.path.isfile(CONTRIBUTING_PATH), "CONTRIBUTING.md must exist"
        )
        readme = read_text(README_PATH)
        self.assertIn("CONTRIBUTING.md", readme)
        self.assertIn("## Contributing", readme)


if __name__ == "__main__":
    unittest.main()
