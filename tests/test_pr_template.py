"""Pull-request template contracts (behavior assertions, not full-text).

The template must pin issue linkage to an approved issue, exactly the
supported type labels, the workspace gate command, a rollback section,
and the size-exception rule — without claiming checks (shellcheck,
skills testing) this repository does not run.
"""

import os
import re
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_PATH = os.path.join(REPO_ROOT, ".github", "PULL_REQUEST_TEMPLATE.md")

SUPPORTED_TYPE_LABELS = {"type:bug", "type:chore"}


def read_text(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


class PullRequestTemplateTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(
            os.path.isfile(TEMPLATE_PATH),
            ".github/PULL_REQUEST_TEMPLATE.md must exist",
        )
        self.text = read_text(TEMPLATE_PATH)

    def test_issue_linkage_keywords_present(self):
        for keyword in ("Closes #N", "Fixes", "Resolves"):
            self.assertIn(keyword, self.text, keyword)

    def test_linked_issue_must_be_approved(self):
        self.assertIn("status:approved", self.text)

    def test_exactly_supported_type_labels(self):
        found = set(re.findall(r"type:[a-z-]+", self.text))
        self.assertEqual(found, SUPPORTED_TYPE_LABELS, found)

    def test_workspace_gate_command_present(self):
        self.assertIn("python3 tools/test.py", self.text)

    def test_rollback_section_present(self):
        self.assertRegex(self.text, r"(?m)^## Rollback\s*$")

    def test_size_exception_rule_present(self):
        self.assertIn("size:exception", self.text)
        self.assertIn("400", self.text)

    def test_no_unsupported_check_claims(self):
        lowered = self.text.lower()
        self.assertNotIn("shellcheck", lowered)
        self.assertNotIn("skills test", lowered)


if __name__ == "__main__":
    unittest.main()
