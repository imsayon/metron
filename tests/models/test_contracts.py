import unittest
from datetime import datetime, timezone

from metron.models.contracts import (
    ContractValidationError,
    FeatureContract,
    ModelVersion,
    Provenance,
    validate_figure_reference,
)


class ContractTests(unittest.TestCase):
    def contract(self):
        return FeatureContract(
            names=("ir1", "cape"),
            means={"ir1": 240, "cape": 100},
            stds={"ir1": 5, "cape": 50},
            domain_version=1,
            channel_version=1,
        )

    def test_feature_names_are_checked_by_name(self):
        contract = self.contract()
        contract.check_names({"ir1": 1, "cape": 2})
        with self.assertRaises(ContractValidationError):
            contract.check_names({"ir1": 1, "wrong": 2})

    def test_non_frozen_metric_reference_is_rejected(self):
        with self.assertRaises(ContractValidationError):
            validate_figure_reference("F-M0-CSI-lead-pilot_e-2026pre", frozen=False)
        self.assertEqual(
            validate_figure_reference("F-M0-CSI-lead-pilot_e-2026pre", frozen=True),
            "F-M0-CSI-lead-pilot_e-2026pre",
        )

    def test_model_version_requires_matching_versions(self):
        model = ModelVersion(
            model_version="m0-test",
            module="M0",
            git_sha="abc123",
            data_manifest_hash="manifest",
            feature_contract=self.contract(),
        )
        self.assertIs(model.validate(), model)
        with self.assertRaises(ContractValidationError):
            ModelVersion(
                model_version="m0-test",
                module="M0",
                git_sha="abc123",
                data_manifest_hash="manifest",
                feature_contract=self.contract(),
                frozen_figure_ids=("F-M0-CSI-lead-pilot_e-2026pre",),
                research_only=True,
            ).validate()

    def test_synthetic_provenance_cannot_publish_skill(self):
        with self.assertRaises(ContractValidationError):
            Provenance(
                model_version="m0",
                data_manifest_hash="fixture",
                issue_time=datetime.now(timezone.utc),
                rung="R0",
                synthetic=True,
                skill_ref="F-M0-CSI-lead-pilot_e-2026pre",
                frozen=True,
            ).validate()
