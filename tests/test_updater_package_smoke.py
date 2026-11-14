from hellsaiz_pc_ai.updater import run_package_self_test


def test_updater_package_self_test_signs_and_verifies():
    assert run_package_self_test() == 0
