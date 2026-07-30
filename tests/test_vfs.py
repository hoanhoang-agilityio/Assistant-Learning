from pathlib import Path

import pytest

from core.orchestration.graph.run import create_initial_state
from core.vfs import VFS, init_run_workspace, run_workspace_name
from core.vfs.bootstrap import RUN_SUBDIRS


@pytest.fixture
def workspace_root(tmp_path: Path) -> Path:
    return tmp_path / "workspace"


@pytest.fixture
def run_vfs(workspace_root: Path) -> VFS:
    run_path = init_run_workspace("test-run-001", workspace_root=workspace_root)
    return VFS.for_run(run_path)


def test_write_and_read(run_vfs: VFS) -> None:
    run_vfs.write("plan/profile.json", '{"goal": "fat_loss"}')
    assert run_vfs.read("plan/profile.json") == '{"goal": "fat_loss"}'


def test_exists(run_vfs: VFS) -> None:
    assert run_vfs.exists("plan/") is True
    assert run_vfs.exists("plan/todos.json") is False
    run_vfs.write("plan/todos.json", "[]")
    assert run_vfs.exists("plan/todos.json") is True


def test_append(run_vfs: VFS) -> None:
    run_vfs.write("logs/events.jsonl", '{"event": "start"}\n')
    run_vfs.append("logs/events.jsonl", '{"event": "planning"}\n')
    content = run_vfs.read("logs/events.jsonl")
    assert content == '{"event": "start"}\n{"event": "planning"}\n'


def test_nested_paths_created_on_write(run_vfs: VFS) -> None:
    run_vfs.write("research/findings/part-1.md", "evidence")
    assert run_vfs.read("research/findings/part-1.md") == "evidence"


def test_path_traversal_rejected(run_vfs: VFS) -> None:
    with pytest.raises(ValueError, match="escapes workspace root"):
        run_vfs.read("../outside.txt")


def test_init_run_workspace_creates_folder_tree(workspace_root: Path) -> None:
    run_path = init_run_workspace("abc-123", workspace_root=workspace_root)
    assert run_path == workspace_root / run_workspace_name("abc-123")
    assert run_path.is_dir()
    for subdir in RUN_SUBDIRS:
        assert (run_path / subdir).is_dir()


def test_create_initial_state_sets_workspace_path(workspace_root: Path) -> None:
    state = create_initial_state(
        run_id="run-42",
        thread_id="thread-42",
        query="Build a hypertrophy plan",
        workspace_root=workspace_root,
    )
    expected_path = workspace_root / run_workspace_name("run-42")
    assert state["workspace_path"] == str(expected_path.resolve())
    assert state["run_id"] == "run-42"
    assert state["thread_id"] == "thread-42"
    assert state["query"] == "Build a hypertrophy plan"
    assert state["current_node"] == "supervisor"
    assert Path(state["workspace_path"]).is_dir()
