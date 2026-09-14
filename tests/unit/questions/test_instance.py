"""Unit tests for icab.questions.instance -- QuestionInstance determinism and RepetitionMode."""

from __future__ import annotations

from icab.questions import QuestionInstance, RepetitionMode, instance_id_for


class TestQuestionInstanceDeterminism:
    def test_same_inputs_produce_the_same_instance_id(self):
        a = QuestionInstance.build(question_id="Q-1", scenario_id="s1", architectures=["historian", "knowledge_graph"], agent="llm")
        b = QuestionInstance.build(question_id="Q-1", scenario_id="s1", architectures=["knowledge_graph", "historian"], agent="llm")

        assert a.instance_id == b.instance_id  # architecture order doesn't matter
        assert a.architectures == b.architectures == ("historian", "knowledge_graph")

    def test_different_architectures_produce_different_instance_ids(self):
        a = QuestionInstance.build(question_id="Q-1", scenario_id="s1", architectures=["historian"], agent="llm")
        b = QuestionInstance.build(question_id="Q-1", scenario_id="s1", architectures=["knowledge_graph"], agent="llm")

        assert a.instance_id != b.instance_id

    def test_different_scenario_produces_a_different_instance(self):
        a = QuestionInstance.build(question_id="Q-1", scenario_id="s1", architectures=["historian"], agent="llm")
        b = QuestionInstance.build(question_id="Q-1", scenario_id="s2", architectures=["historian"], agent="llm")

        assert a.instance_id != b.instance_id

    def test_different_model_or_temperature_produces_a_different_instance(self):
        a = QuestionInstance.build(question_id="Q-1", scenario_id="s1", architectures=["historian"], agent="llm", llm_model="model-a", llm_temperature=0.0)
        b = QuestionInstance.build(question_id="Q-1", scenario_id="s1", architectures=["historian"], agent="llm", llm_model="model-b", llm_temperature=0.0)

        assert a.instance_id != b.instance_id

    def test_deterministic_across_independent_calls(self):
        first = instance_id_for(question_id="Q-1", scenario_id="s1", architectures=("historian", "knowledge_graph"), agent="llm", llm_model="m", llm_temperature=0.0)
        second = instance_id_for(question_id="Q-1", scenario_id="s1", architectures=("historian", "knowledge_graph"), agent="llm", llm_model="m", llm_temperature=0.0)

        assert first == second

    def test_instance_id_is_frozen_and_has_a_readable_prefix(self):
        instance = QuestionInstance.build(question_id="Q-1", scenario_id="s1", architectures=["historian"], agent="llm")

        assert instance.instance_id.startswith("Q-1--s1--historian--llm--")


class TestRepetitionMode:
    def test_two_modes_exist_and_are_distinct(self):
        assert RepetitionMode.EXACT != RepetitionMode.CONTROLLED_VARIATION
        assert RepetitionMode.EXACT.value == "exact"
        assert RepetitionMode.CONTROLLED_VARIATION.value == "controlled_variation"
