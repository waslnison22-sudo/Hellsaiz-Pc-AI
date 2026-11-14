from pathlib import Path

from hellsaiz_pc_ai.app.single_instance import SingleInstanceLock


def test_only_one_process_can_hold_the_lock(tmp_path: Path):
    lock_path = tmp_path / "assistant.lock"
    first = SingleInstanceLock(lock_path)
    second = SingleInstanceLock(lock_path)

    assert first.acquire() is True
    assert second.acquire() is False

    first.release()
    assert second.acquire() is True
    second.release()


def test_release_is_idempotent(tmp_path: Path):
    lock = SingleInstanceLock(tmp_path / "assistant.lock")

    lock.release()
    assert lock.acquire() is True
    lock.release()
    lock.release()
    assert lock.acquire() is True
    lock.release()


def test_context_manager_releases_lock(tmp_path: Path):
    lock_path = tmp_path / "assistant.lock"
    with SingleInstanceLock(lock_path):
        assert SingleInstanceLock(lock_path).acquire() is False

    assert SingleInstanceLock(lock_path).acquire() is True
