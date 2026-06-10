import unittest
from pathlib import Path


class DocumentationTests(unittest.TestCase):
    def test_full_user_guide_exists_and_covers_classroom_flow(self):
        guide = Path("docs/完整使用说明.md")

        self.assertTrue(guide.exists())
        content = guide.read_text(encoding="utf-8")
        for keyword in [
            "匿名提醒",
            "老师端管理界面",
            "新班级清空",
            "自动备份",
            "截图上传",
            "老师回复",
            "频率限制",
            "弹窗提醒",
            "禁止多开",
            "防火墙",
        ]:
            self.assertIn(keyword, content)

    def test_readme_links_to_full_user_guide(self):
        readme = Path("README.md").read_text(encoding="utf-8")

        self.assertIn("完整使用说明", readme)
        self.assertIn("docs/完整使用说明.md", readme)


if __name__ == "__main__":
    unittest.main()
