from datetime import datetime, timezone

import numpy as np
import pytest
from metron.features.builder import build_feature_bundle
from metron.features.contracts import FeatureContract, FeatureContractError
from metron.grids.config import load_domain
from metron.qc.satellite import qc_satellite


def contract() -> FeatureContract:
    return FeatureContract(
        names=("sat/ir1", "nwp/cape"),
        means=(220.0, 500.0),
        stds=(10.0, 100.0),
        mins=(150.0, 0.0),
        maxs=(400.0, 20_000.0),
        domain_version=1,
        channel_version=1,
    )


def test_contract_is_name_based_and_reorders_live_mapping():
    feature_contract = contract()
    normalized = feature_contract.normalize(
        {
            "nwp/cape": np.full((2, 2), 500.0),
            "sat/ir1": np.full((2, 2), 220.0),
        },
        masks={"nwp/cape": np.ones((2, 2)), "sat/ir1": np.ones((2, 2))},
        domain_version=1,
        channel_version=1,
    )
    assert normalized.shape == (2, 2, 2)
    assert np.all(normalized == 0.0)

    with pytest.raises(FeatureContractError, match="feature names mismatch"):
        feature_contract.validate(("sat/ir1", "nwp/cape", "radar/zmax"))


def test_missing_channel_becomes_zero_with_mask_and_rung_abstains():
    domain = load_domain("pilot_e")
    sat = qc_satellite(
        "ir1",
        np.full(domain.shape, 220.0, dtype=np.float32),
        obs_time=datetime(2026, 9, 21, 10, tzinfo=timezone.utc),
        arrival_time=datetime(2026, 9, 21, 10, 2, tzinfo=timezone.utc),
        issue_time=datetime(2026, 9, 21, 10, 5, tzinfo=timezone.utc),
        calibrated=True,
    )
    bundle = build_feature_bundle(
        {"sat/ir1": sat},
        contract(),
        shape=domain.shape,
        domain_version=1,
        channel_version=1,
    )
    assert bundle.rung_hint == "R4"
    assert bundle.missing == ("nwp/cape",)
    assert np.isfinite(bundle.model_tensor()).all()
    assert not bundle.valid_mask[1].any()
