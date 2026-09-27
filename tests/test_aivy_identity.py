import unittest

from src.core.aivy_identity import AIVY


class AivyIdentityTests(unittest.TestCase):
    def test_aivy_identity_is_stable(self):
        self.assertEqual(AIVY.name, "Aivy")
        self.assertEqual(AIVY.pronunciation, "アイヴィー")
        self.assertEqual(AIVY.tagline, "育つほど、つくれる。")
        self.assertEqual(AIVY.product_name, "AI App Platform")

    def test_growth_principles_preserve_evidence_and_human_agency(self):
        joined = " ".join(AIVY.principles).lower()
        self.assertIn("evidence", joined)
        self.assertIn("verified", joined)
        self.assertIn("human", joined)
        self.assertIn("secrets", joined)

    def test_system_preamble_names_aivy_and_role(self):
        prompt = AIVY.system_preamble()
        self.assertIn("Aivy", prompt)
        self.assertIn("AI App Development Partner", prompt)
        self.assertIn("育つほど、つくれる。", prompt)


if __name__ == "__main__":
    unittest.main()
