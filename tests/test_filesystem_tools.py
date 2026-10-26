from app.tools.filesystem import FilesystemTools


def test_filesystem_tools_write_read_list_and_search(tmp_path):
    tools = FilesystemTools(tmp_path)

    written = tools.write_file("notes/digest.md", "Agent news\nSecond line")
    read = tools.read_file("notes/digest.md")
    listed = tools.list_dir("notes")
    matches = tools.search_content("Agent", ".")

    assert written == {
        "ok": True,
        "data": {"path": "notes/digest.md", "bytes_written": 22},
        "error": None,
    }
    assert read["data"]["content"] == "Agent news\nSecond line"
    assert listed["data"]["entries"] == [
        {"name": "digest.md", "type": "file", "size": 22}
    ]
    assert matches["data"]["matches"] == [
        {"path": "notes/digest.md", "line": 1, "text": "Agent news"}
    ]


def test_filesystem_tools_reject_paths_outside_workspace(tmp_path):
    tools = FilesystemTools(tmp_path)

    result = tools.read_file("../secret.txt")

    assert result["ok"] is False
    assert result["error"] == "path escapes workspace"


def test_bash_allows_safe_echo_and_rejects_unapproved_commands(tmp_path):
    tools = FilesystemTools(tmp_path)

    allowed = tools.bash("echo hello agent")
    rejected = tools.bash("rm -rf .")

    assert allowed["ok"] is True
    assert allowed["data"]["stdout"] == "hello agent\n"
    assert rejected == {
        "ok": False,
        "data": None,
        "error": "command is not allowed",
    }

