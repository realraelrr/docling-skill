from docling_skill.text_normalization import normalize_agent_markdown


def test_normalize_agent_markdown_rewrites_cjk_compatibility_characters():
    normalized, report = normalize_agent_markdown("## 南 ⽠ 书\n\n周志华⽼师讲解机器学习。")

    assert normalized == "## 南瓜书\n\n周志华老师讲解机器学习。"
    assert report == {
        "applied": True,
        "cjk_compatibility_replacement_count": 2,
        "cjk_space_merge_count": 2,
    }


def test_normalize_agent_markdown_keeps_code_english_and_placeholders_stable():
    markdown = (
        "中 文 之间 有 空 格\n\n"
        "English words keep spaces.\n\n"
        "[[image:picture-p2-1]]\n\n"
        "<!-- formula-not-decoded -->\n\n"
        "```python\n"
        "text = '南 ⽠ 书'\n"
        "```\n"
    )

    normalized, report = normalize_agent_markdown(markdown)

    assert "中文之间有空格" in normalized
    assert "English words keep spaces." in normalized
    assert "[[image:picture-p2-1]]" in normalized
    assert "<!-- formula-not-decoded -->" in normalized
    assert "text = '南 ⽠ 书'" in normalized
    assert report["applied"] is True
    assert report["cjk_space_merge_count"] == 5
