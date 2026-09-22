from allin1.help_topics import HELP_TOPICS, search_help_topics


def test_help_center_has_unique_keys_and_core_workflows():
    keys = [topic.key for topic in HELP_TOPICS]
    assert len(keys) == len(set(keys))
    assert {"getting-started", "packages", "asset-viewer", "rpf-explorer", "recovery"} <= set(keys)


def test_help_center_starts_with_the_first_run_workflow():
    assert [topic.key for topic in HELP_TOPICS[:3]] == [
        "getting-started", "editions", "install-repair",
    ]
    priorities = [topic.onboarding_priority for topic in HELP_TOPICS]
    assert priorities == sorted(priorities)


def test_help_search_matches_keywords_and_ranks_title_matches():
    matches = search_help_topics("RPF")
    assert matches
    assert matches[0].key == "rpf-explorer"
    assert all("rpf" in " ".join((
        topic.title, topic.summary, topic.body, *topic.keywords,
    )).casefold() for topic in matches)


def test_help_search_requires_every_word_and_empty_query_returns_all():
    assert search_help_topics("") == HELP_TOPICS
    assert search_help_topics("controller input")[0].key == "input"
    assert search_help_topics("definitely-not-a-topic") == ()


def test_troubleshooting_help_documents_unified_navigation_shortcuts():
    topic = next(topic for topic in HELP_TOPICS if topic.key == "troubleshooting")

    assert "Ctrl+B" in topic.body
    assert "Ctrl+Tab" in topic.body
    assert "Ctrl+Shift+Tab" in topic.body
