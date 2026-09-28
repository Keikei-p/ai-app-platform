import unittest

from src.core.specialist_agents import SpecialistAgentRegistry
from src.core.specialist_squad import SpecialistSquadSelector


class SpecialistSquadSelectorTests(unittest.TestCase):
    def setUp(self):
        self.selector = SpecialistSquadSelector()
        self.registry = SpecialistAgentRegistry()

    def test_registry_has_fifteen_specialist_roles(self):
        names = {row.name for row in self.registry.list()}
        self.assertEqual(len(names), 15)
        self.assertTrue({
            "database", "web", "mobile", "performance",
            "accessibility", "devops",
        }.issubset(names))

    def test_mobile_app_goal_recruits_mobile_and_accessibility(self):
        result = self.selector.select(
            "iPhoneとAndroidのスマホアプリを作ってUIも見やすくしたい",
            project_detail={"targets": ["android", "ios"], "app_type": "mobile"},
        )
        self.assertIn("mobile", result.roles)
        self.assertIn("accessibility", result.roles)
        self.assertIn("coding", result.roles)
        self.assertLessEqual(len(result.worker_roles), 6)

    def test_database_goal_recruits_database_specialist(self):
        result = self.selector.select(
            "Firestoreのデータ保存と集計、移行設計を見直したい",
            project_detail={"targets": ["web"]},
        )
        self.assertIn("database", result.roles)
        self.assertIn("database", result.worker_roles)

    def test_web_goal_recruits_web_performance_and_accessibility(self):
        result = self.selector.select(
            "Webサイトをレスポンシブにして速度も改善したい",
            project_detail={"targets": ["web"], "app_type": "web"},
        )
        self.assertIn("web", result.roles)
        self.assertIn("performance", result.roles)
        self.assertIn("accessibility", result.roles)

    def test_release_and_build_do_not_enter_parallel_worker_pool(self):
        result = self.selector.select(
            "本番リリースしてApp Store向けにビルドしたい",
            project_detail={"targets": ["ios"]},
        )
        self.assertIn("release", result.roles)
        self.assertIn("build", result.roles)
        self.assertNotIn("release", result.worker_roles)
        self.assertNotIn("build", result.worker_roles)

    def test_every_selected_role_exists(self):
        result = self.selector.select("WebとDBを使うスマホアプリを作る")
        names = {row.name for row in self.registry.list()}
        self.assertTrue(set(result.roles).issubset(names))
        self.assertTrue(set(result.worker_roles).issubset(names))


if __name__ == "__main__":
    unittest.main()
