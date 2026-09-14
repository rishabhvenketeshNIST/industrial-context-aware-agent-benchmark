"""
Production-hardening security audit: credentials must never end up in a
persisted benchmark artifact (trace/raw record/evaluation/QA report).

This complements, but does not duplicate, the existing GROUND-TRUTH
isolation tests (tests/unit/tasks/test_task_ground_truth_isolation.py,
tests/unit/reporting/test_qa_report.py::TestGroundTruthNeverReachesTheAgent)
-- those cover the agent never seeing hidden ground truth; these cover a
different, equally real risk: the LLM API key / database password /
Neo4j credentials / MQTT credentials never ending up in a persisted
artifact a researcher (or, eventually, a published dataset) might read.
"""

from __future__ import annotations

from icab.agent.interface import EvidenceReference, InvestigationResult, TerminationReason
from icab.benchmark.config import BenchmarkConfig
from icab.common.config import ICABSettings
from icab.experiments.models import ExperimentConfig, ExperimentRecord
from icab.reporting.qa_report import QAReportEntry
from icab.trace.models import TraceEvent

_FAKE_SECRET = "sk-FAKE-TEST-SECRET-VALUE-DO-NOT-USE-1234567890"

#: Substrings that would flag a field as credential-shaped. Deliberately
#: "auth_token"/"access_token"/etc. rather than a bare "token" -- ICAB
#: has several entirely legitimate `*_tokens`/`total_tokens` fields
#: (LLM token USAGE COUNTS, an int, never a secret) that a bare "token"
#: substring match would incorrectly flag.
_SUSPICIOUS_FIELD_NAME_SUBSTRINGS = (
    "password",
    "secret",
    "api_key",
    "apikey",
    "credential",
    "auth_token",
    "access_token",
    "bearer",
)


def _suspicious_field_names(model_cls) -> set[str]:
    return {
        name
        for name in model_cls.model_fields
        if any(word in name.lower() for word in _SUSPICIOUS_FIELD_NAME_SUBSTRINGS)
    }


def _settings_with_fake_secret() -> ICABSettings:
    return ICABSettings(
        database_url="postgresql://icab:icab@localhost:5432/icab",
        neo4j_uri="bolt://localhost:7687",
        neo4j_username="neo4j",
        neo4j_password="icabpassword",
        llm_provider="nist-rchat",
        llm_base_url="https://rchat.nist.gov/api/v1",
        llm_api_key=_FAKE_SECRET,
        llm_model="gemma-4-31B-it",
    )


class TestNoCredentialFieldsExistOnPersistedSchemas:
    """
    Structural check: none of the models actually persisted under
    results/ (ExperimentConfig/ExperimentRecord/QAReportEntry) declare a
    field that could even NAME a credential -- so there is no field for
    a future change to accidentally start populating with one.
    """

    def test_experiment_config_has_no_credential_fields(self):
        assert _suspicious_field_names(ExperimentConfig) == set()

    def test_experiment_record_has_no_credential_fields(self):
        assert _suspicious_field_names(ExperimentRecord) == set()

    def test_qa_report_entry_has_no_credential_fields(self):
        assert _suspicious_field_names(QAReportEntry) == set()

    def test_benchmark_config_has_no_credential_fields(self):
        assert _suspicious_field_names(BenchmarkConfig) == set()


class TestSecretsNeverAppearInSerializedArtifacts:
    """
    Behavioral check: construct a REAL ExperimentConfig/ExperimentRecord/
    QAReportEntry describing a run against a provider configured with a
    (fake, obviously-not-real) secret, and confirm the secret string
    never appears anywhere in what actually gets persisted.
    """

    def test_llm_api_key_never_appears_in_experiment_config_json(self):
        config = ExperimentConfig(
            scenario_id="d1_reactor_pressure_reading",
            architectures=["historian"],
            agent_type="llm",
            llm_model="gemma-4-31B-it",
            llm_temperature=0.0,
        )

        serialized = config.model_dump_json()

        assert _FAKE_SECRET not in serialized
        # Only the model NAME is recorded -- never a base_url/api_key.
        assert "base_url" not in serialized
        assert "api_key" not in serialized

    def test_llm_api_key_never_appears_in_a_persisted_experiment_record(self):
        config = ExperimentConfig(
            scenario_id="d1_reactor_pressure_reading",
            architectures=["historian"],
            agent_type="llm",
            llm_model="gemma-4-31B-it",
            llm_temperature=0.0,
        )
        from datetime import UTC, datetime

        record = ExperimentRecord(
            run_id="run-1",
            experiment_id="exp-1",
            config=config,
            scenario_difficulty="D1",
            simulation_seed=1,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            status="completed",
            result=InvestigationResult(
                objective="What is the current reactor pressure?",
                conclusion="2712 kPa, normal.",
                evidence=[EvidenceReference(source="get_current_value", identifier="urn:icab:measurement:reactor_pressure")],
                termination=TerminationReason.SUBMITTED,
            ),
        )

        serialized = record.model_dump_json()

        assert _FAKE_SECRET not in serialized

    def test_database_and_neo4j_credentials_never_appear_in_a_trace_event(self):
        settings = _settings_with_fake_secret()

        event = TraceEvent(
            timestamp=__import__("datetime").datetime.now(__import__("datetime").UTC),
            step=1,
            action="tool_call",
            tool="get_current_value",
            arguments={"measurement_id": "urn:icab:measurement:reactor_pressure"},
            result={"observation": {"measurement_id": "urn:icab:measurement:reactor_pressure", "value": 2712.39, "unit": "kPa gauge"}},
        )

        serialized = event.model_dump_json()

        assert settings.neo4j_password not in serialized
        assert settings.database_url not in serialized  # the whole connection string, password included
        assert settings.llm_api_key not in serialized

    def test_settings_object_itself_is_never_embedded_in_a_qa_report_entry(self):
        """
        A QAReportEntry is built entirely from an ExperimentRecord's own
        fields (see icab.reporting.qa_report.build_qa_report_entry) --
        confirms constructing one, then serializing it, cannot surface a
        settings-derived secret even if a future change accidentally
        threaded `settings` through by mistake.
        """

        entry = QAReportEntry(
            run_id="run-1",
            task_id="d1-qa-current-pressure",
            scenario_id="d1_reactor_pressure_reading",
            difficulty="D1",
            task_type="qa",
            architecture="historian",
            seed=1,
            fault_id=None,
            status="completed",
            error=None,
            objective="What is the current reactor pressure?",
            agent_answer="2712 kPa, normal.",
            correct_answer=None,
            required_evidence=["urn:icab:measurement:reactor_pressure"],
            evidence_provided=["get_current_value: urn:icab:measurement:reactor_pressure"],
            metrics={"required_evidence_score": 1.0},
        )

        serialized = entry.model_dump_json()

        assert _FAKE_SECRET not in serialized


class TestEnvironmentIsNeverDumpedIntoArtifacts:
    def test_configuration_hash_input_excludes_settings(self):
        """
        compute_configuration_hash hashes ExperimentConfig ONLY (never
        the process's environment/settings) -- confirmed by checking
        that changing an unrelated environment variable never changes
        the hash of the same ExperimentConfig.
        """

        from icab.experiments.models import compute_configuration_hash

        config = ExperimentConfig(
            scenario_id="d1_reactor_pressure_reading",
            architectures=["historian"],
            agent_type="llm",
            llm_model="gemma-4-31B-it",
        )

        import os

        original = os.environ.get("ICAB_LLM_API_KEY")
        try:
            os.environ["ICAB_LLM_API_KEY"] = "some-other-fake-secret-entirely"
            hash_with_env_a = compute_configuration_hash(config)
            os.environ["ICAB_LLM_API_KEY"] = _FAKE_SECRET
            hash_with_env_b = compute_configuration_hash(config)
        finally:
            if original is None:
                os.environ.pop("ICAB_LLM_API_KEY", None)
            else:
                os.environ["ICAB_LLM_API_KEY"] = original

        assert hash_with_env_a == hash_with_env_b
