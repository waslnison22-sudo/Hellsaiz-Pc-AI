from hellsaiz_pc_ai.update_client import _version_parts


def test_versions_compare_numerically():
    assert _version_parts("v0.10.0") > _version_parts("0.9.9")
    assert _version_parts("0.2.0") > _version_parts("0.2.0-beta")
