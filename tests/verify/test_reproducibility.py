from metron.verify import data_manifest_hash, figure_id, verification_run_id


def test_hashes_and_run_ids_are_order_independent() -> None:
    left = data_manifest_hash(["b", "a"], channel_version=1, domain_version=1, definition_version=1)
    right = data_manifest_hash(
        ["a", "b"], channel_version=1, domain_version=1, definition_version=1
    )
    assert left == right

    kwargs = {
        "data_manifest_hash": left,
        "channel_version": 1,
        "definition_version": 1,
        "git_sha": "abc123",
        "spec": {"leads": [30, 60]},
        "seed": 7,
        "model_versions": ["M2", "M0"],
    }
    reordered = {**kwargs, "model_versions": ["M0", "M2"]}
    assert verification_run_id(**kwargs) == verification_run_id(**reordered)


def test_figure_id_matches_contract() -> None:
    assert figure_id("M2", "CSI", "lead", "pilot_e", "2026pre") == "F-M2-CSI-lead-pilot_e-2026pre"
    assert figure_id("CMP-IMD", "CSI", "district", "pilot_e", "2026pre") == (
        "F-CMP-IMD-CSI-district-pilot_e-2026pre"
    )
