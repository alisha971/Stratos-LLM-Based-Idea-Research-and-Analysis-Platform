import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.clarification_schema import (
    ASKED_FIELDS_KEY,
    IDEA_CAPTURED_KEY,
    IDEA_SCHEMA_FIELDS,
    confidence_score,
    is_unknown,
    mark_unknown,
    serialize_for_downstream,
    unknown_directive,
    writer_view,
)
from app.services.evidence_bundle_service import EvidenceBundleService
from app.services.section_writer_service import SectionWriterService, is_gaps_section
from app.workers.clarification_worker import (
    IDEA_PIVOT_QUESTION,
    MAX_CLARIFICATION_TURNS,
    MAX_TOTAL_MESSAGES,
    MIN_CLARIFICATION_TURNS,
    SOCIAL_FALLBACK_REPLIES,
    _unknown_target_fields,
    merge_schema,
)


def _filled_schema(**overrides):
    schema = {
        "project_domain": "health/diabetes",
        "target_persona": "diabetic patients",
        "core_problem": "Patients do not know what they are supposed to eat.",
        "current_workaround": "Google, chatbots, doctors.",
        "proposed_solution": "food plan app",
        "differentiation": None,
    }
    schema.update(overrides)
    return schema


class ConfidenceScoreTests(unittest.TestCase):
    def test_unknown_marked_field_counts_as_resolved(self):
        schema = _filled_schema(
            differentiation=mark_unknown("differentiation", "research competitors")
        )
        self.assertEqual(confidence_score(schema), 1.0)

    def test_reserved_keys_do_not_inflate_score(self):
        schema = _filled_schema()
        schema[ASKED_FIELDS_KEY] = ["differentiation"]
        # 5 of 6 real fields filled, differentiation still null/unresolved.
        self.assertEqual(confidence_score(schema), round(5 / 6, 2))

    def test_all_null_schema_scores_zero(self):
        schema = {field: None for field in IDEA_SCHEMA_FIELDS}
        self.assertEqual(confidence_score(schema), 0.0)


class MergeSchemaTests(unittest.TestCase):
    def test_does_not_reopen_unknown_marked_field(self):
        existing = _filled_schema(
            differentiation=mark_unknown("differentiation", "research competitors")
        )
        incoming = {"differentiation": "Actually, real-time glucose sync"}

        merged = merge_schema(existing, incoming)

        self.assertTrue(is_unknown(merged["differentiation"]))

    def test_fills_a_still_null_field(self):
        existing = _filled_schema()
        incoming = {"differentiation": "Real-time glucose sync"}

        merged = merge_schema(existing, incoming)

        self.assertEqual(merged["differentiation"], "Real-time glucose sync")


class UnknownTargetFieldsGatingTests(unittest.TestCase):
    """Regression coverage for the bug where a single rich first message let
    the model fill five fields and declare the sixth unknown in the same
    turn -- collapsing the whole guided conversation into one exchange
    without differentiation ever actually being asked about."""

    def test_ignores_unknown_claim_for_a_field_never_asked(self):
        schema = _filled_schema()  # differentiation still null
        result = {
            "unknown_detected": True,
            "knowledge_gaps": {"differentiation": True},
        }

        # Nothing has been asked yet (turn 1) -- asked_before is empty.
        targets = _unknown_target_fields(result, schema, asked_before=[])

        self.assertEqual(targets, [])

    def test_accepts_unknown_claim_for_a_field_that_was_asked(self):
        schema = _filled_schema()
        result = {
            "unknown_detected": True,
            "knowledge_gaps": {"differentiation": True},
        }

        targets = _unknown_target_fields(
            result, schema, asked_before=["differentiation"]
        )

        self.assertEqual(targets, ["differentiation"])

    def test_falls_back_to_last_asked_field_when_gaps_unnamed(self):
        schema = _filled_schema()
        result = {"unknown_detected": True, "knowledge_gaps": {}}

        targets = _unknown_target_fields(
            result, schema, asked_before=["core_problem", "differentiation"]
        )

        self.assertEqual(targets, ["differentiation"])


class MinimumTurnFloorTests(unittest.TestCase):
    """The 2-3 minute guided conversation must survive an eager model that
    tries to conclude on turn one."""

    def setUp(self):
        import json as _json
        from unittest.mock import patch

        self._json = _json
        self._patch = patch

    def _run(self, session_obj, chat_messages, llm_reply):
        from unittest.mock import MagicMock

        fake_db = MagicMock()
        fake_query = MagicMock()
        fake_db.query.return_value = fake_query
        fake_query.filter_by.return_value = fake_query
        fake_query.order_by.return_value = fake_query

        def first():
            return session_obj

        def all_():
            return chat_messages

        fake_query.first.side_effect = None
        fake_query.first.return_value = session_obj
        fake_query.all.return_value = chat_messages

        published = []
        with self._patch(
            "app.workers.clarification_worker.SessionLocal", return_value=fake_db
        ), self._patch(
            "app.workers.clarification_worker.generate_chat",
            return_value=self._json.dumps(llm_reply),
        ), self._patch(
            "app.workers.clarification_worker.publish_event",
            side_effect=lambda t, p: published.append((t, p)),
        ):
            from app.workers.clarification_worker import run_clarification

            run_clarification(session_obj.id)

        return published

    def test_single_rich_message_does_not_jump_straight_to_ready(self):
        """The exact bug: turn 1, five fields filled, differentiation
        declared unknown in the same turn. Must NOT publish
        clarification_ready -- the field was never actually asked about."""
        from app.db import models

        session_obj = models.Session(
            id="s1", user_id="u1", status="CLARIFYING", idea_description="x"
        )
        session_obj.clarification_schema = {}

        llm_reply = {
            "updated_schema": _filled_schema(),
            "hard_constraints": [],
            "hypotheses": [],
            "knowledge_gaps": {"differentiation": True},
            "research_directives": ["Investigate potential unique features."],
            "confidence_score": 0.83,
            "unknown_detected": True,
            "turn_fatigue": False,
            "mirror_summary": "Got it.",
            "next_question": "What's your unique angle?",
        }

        published = self._run(session_obj, [], llm_reply)

        self.assertFalse(
            any(t == "clarification_ready" for t, _ in published),
            "turn 1 must not conclude clarification -- differentiation was "
            "never asked about before being marked unknown",
        )
        update = next(p for t, p in published if t == "clarification_update")
        self.assertTrue(update["next_question"])

    def test_all_fields_resolved_early_still_waits_for_turn_floor(self):
        """Even with zero unknowns, hitting all six fields before
        MIN_CLARIFICATION_TURNS must not finish the conversation -- there
        must be a deepening question, not a jump to consent."""
        from app.db import models

        session_obj = models.Session(
            id="s1", user_id="u1", status="CLARIFYING", idea_description="x"
        )
        session_obj.clarification_schema = {}
        chat_messages = [
            models.ChatMessage(id="1", session_id="s1", role="user", message="x"),
        ]

        llm_reply = {
            "updated_schema": _filled_schema(differentiation="Real-time glucose sync"),
            "hard_constraints": [],
            "hypotheses": [],
            "knowledge_gaps": {},
            "research_directives": [],
            "confidence_score": 1.0,
            "unknown_detected": False,
            "turn_fatigue": False,
            "mirror_summary": "Got it.",
            "next_question": "",
        }

        self.assertLess(1, MIN_CLARIFICATION_TURNS)
        published = self._run(session_obj, chat_messages, llm_reply)

        self.assertFalse(any(t == "clarification_ready" for t, _ in published))
        update = next(p for t, p in published if t == "clarification_update")
        self.assertTrue(
            update["next_question"], "must ask a deepening question, not go silent"
        )

    def test_turn_cap_still_forces_completion_regardless_of_floor(self):
        from app.db import models

        session_obj = models.Session(
            id="s1", user_id="u1", status="CLARIFYING", idea_description="x"
        )
        session_obj.clarification_schema = {}
        chat_messages = [
            models.ChatMessage(id=str(i), session_id="s1", role="assistant", message="{}")
            for i in range(MAX_CLARIFICATION_TURNS - 1)
        ]

        llm_reply = {
            "updated_schema": {f: None for f in IDEA_SCHEMA_FIELDS},
            "hard_constraints": [],
            "hypotheses": [],
            "knowledge_gaps": {},
            "research_directives": [],
            "confidence_score": 0.0,
            "unknown_detected": False,
            "turn_fatigue": False,
            "mirror_summary": "Noted.",
            "next_question": "What's the core problem?",
        }

        published = self._run(session_obj, chat_messages, llm_reply)

        self.assertTrue(any(t == "clarification_ready" for t, _ in published))


class SocialTurnTests(unittest.TestCase):
    """Intent triage: greetings/meta-questions get a friendly reply and a
    pivot back to the idea, without touching the schema or spending one of
    the MAX_CLARIFICATION_TURNS substantive turns."""

    def _run(self, session_obj, chat_messages, llm_reply):
        import json as _json
        from unittest.mock import MagicMock, patch

        fake_db = MagicMock()
        fake_query = MagicMock()
        fake_db.query.return_value = fake_query
        fake_query.filter_by.return_value = fake_query
        fake_query.order_by.return_value = fake_query
        fake_query.first.return_value = session_obj
        fake_query.all.return_value = chat_messages

        published = []
        with patch(
            "app.workers.clarification_worker.SessionLocal", return_value=fake_db
        ), patch(
            "app.workers.clarification_worker.generate_chat",
            return_value=_json.dumps(llm_reply),
        ), patch(
            "app.workers.clarification_worker.publish_event",
            side_effect=lambda t, p: published.append((t, p)),
        ):
            from app.workers.clarification_worker import run_clarification

            run_clarification(session_obj.id)

        return published, fake_db

    def _social_reply(self, intent, social_reply="", **overrides):
        reply = {
            "updated_schema": _filled_schema(),  # deliberately non-empty:
            # a social turn must ignore any schema the model returned
            "hard_constraints": [],
            "hypotheses": [],
            "knowledge_gaps": {},
            "research_directives": [],
            "confidence_score": 0.0,
            "unknown_detected": False,
            "turn_fatigue": False,
            "message_intent": intent,
            "social_reply": social_reply,
            "mirror_summary": "",
            "next_question": "",
        }
        reply.update(overrides)
        return reply

    def test_greeting_replies_and_pivots_without_touching_schema(self):
        import json

        from app.db import models

        session_obj = models.Session(
            id="s1", user_id="u1", status="CLARIFYING", idea_description="hi"
        )
        session_obj.clarification_schema = {}

        published, fake_db = self._run(
            session_obj, [], self._social_reply("greeting", "Hey there!")
        )

        self.assertFalse(any(t == "clarification_ready" for t, _ in published))
        update = next(p for t, p in published if t == "clarification_update")
        self.assertEqual(update["message_intent"], "greeting")
        self.assertEqual(update["mirror_summary"], "Hey there!")
        # Nothing known about the idea yet — pivot must ask for the idea.
        self.assertEqual(update["next_question"], IDEA_PIVOT_QUESTION)
        # The model's updated_schema was ignored entirely.
        self.assertEqual(session_obj.clarification_schema, {})

        # The persisted assistant message is flagged social so it never
        # counts toward the turn budget on later turns.
        stored = json.loads(fake_db.add.call_args[0][0].message)
        self.assertTrue(stored["social"])

    def test_meta_question_falls_back_to_honest_no_memory_reply(self):
        from app.db import models

        session_obj = models.Session(
            id="s1", user_id="u1", status="CLARIFYING", idea_description="x"
        )
        session_obj.clarification_schema = {}

        published, _ = self._run(
            session_obj, [], self._social_reply("meta_question")
        )

        update = next(p for t, p in published if t == "clarification_update")
        self.assertEqual(
            update["mirror_summary"], SOCIAL_FALLBACK_REPLIES["meta_question"]
        )

    def test_social_turns_do_not_consume_the_turn_budget(self):
        """MAX_CLARIFICATION_TURNS - 1 social exchanges must leave the full
        substantive budget intact: the next real turn is turn 1, not turn 5,
        so it must NOT conclude the session."""
        import json

        from app.db import models

        session_obj = models.Session(
            id="s1", user_id="u1", status="CLARIFYING", idea_description="x"
        )
        session_obj.clarification_schema = {}
        chat_messages = [
            models.ChatMessage(
                id=str(i),
                session_id="s1",
                role="assistant",
                message=json.dumps({"social": True, "mirror_summary": "Hey!"}),
            )
            for i in range(MAX_CLARIFICATION_TURNS - 1)
        ]

        substantive_reply = self._social_reply(
            "idea_content",
            updated_schema={f: None for f in IDEA_SCHEMA_FIELDS},
            next_question="What's the core problem?",
            mirror_summary="Noted.",
        )

        published, _ = self._run(session_obj, chat_messages, substantive_reply)

        self.assertFalse(
            any(t == "clarification_ready" for t, _ in published),
            "social turns must not count toward MAX_CLARIFICATION_TURNS",
        )
        update = next(p for t, p in published if t == "clarification_update")
        self.assertTrue(update["next_question"])

    def test_total_message_ceiling_forces_completion_once_idea_captured(self):
        """Chit-chat can't loop forever: past MAX_TOTAL_MESSAGES even a
        social message concludes the session -- provided an idea was
        actually captured at some point."""
        from app.db import models

        session_obj = models.Session(
            id="s1", user_id="u1", status="CLARIFYING", idea_description="x"
        )
        session_obj.clarification_schema = {IDEA_CAPTURED_KEY: True}
        chat_messages = [
            models.ChatMessage(id=str(i), session_id="s1", role="user", message="hi")
            for i in range(MAX_TOTAL_MESSAGES)
        ]

        published, _ = self._run(
            session_obj, chat_messages, self._social_reply("greeting", "Hi!")
        )

        self.assertTrue(any(t == "clarification_ready" for t, _ in published))

    def test_ceiling_does_not_conclude_when_no_idea_was_ever_given(self):
        """The garbage-report guard: 20 messages of pure small talk must NOT
        conclude into research, or the whole pipeline runs on "hi"."""
        from app.db import models

        session_obj = models.Session(
            id="s1", user_id="u1", status="CLARIFYING", idea_description="hi"
        )
        session_obj.clarification_schema = {}  # _idea_captured never set
        chat_messages = [
            models.ChatMessage(id=str(i), session_id="s1", role="user", message="hi")
            for i in range(MAX_TOTAL_MESSAGES + 5)
        ]

        published, _ = self._run(
            session_obj, chat_messages, self._social_reply("greeting", "Hi again!")
        )

        self.assertFalse(
            any(t == "clarification_ready" for t, _ in published),
            "pure chit-chat must never start research",
        )
        update = next(p for t, p in published if t == "clarification_update")
        self.assertTrue(update["next_question"], "must keep nudging for the idea")


class IdeaCaptureTests(unittest.TestCase):
    """A session can be opened by a greeting, so idea_description starts
    provisional. It is user-visible (reports list label, report title), so
    the first substantive message must replace it."""

    def _run(self, session_obj, chat_messages, llm_reply):
        return SocialTurnTests._run(self, session_obj, chat_messages, llm_reply)

    def _substantive_reply(self, **overrides):
        reply = {
            "updated_schema": {f: None for f in IDEA_SCHEMA_FIELDS},
            "hard_constraints": [],
            "hypotheses": [],
            "knowledge_gaps": {},
            "research_directives": [],
            "confidence_score": 0.0,
            "unknown_detected": False,
            "turn_fatigue": False,
            "message_intent": "idea_content",
            "social_reply": "",
            "mirror_summary": "Got it.",
            "next_question": "Who is it for?",
        }
        reply.update(overrides)
        return reply

    def test_social_first_message_does_not_capture_an_idea(self):
        from app.db import models

        session_obj = models.Session(
            id="s1", user_id="u1", status="CLARIFYING", idea_description="hi"
        )
        session_obj.clarification_schema = {}
        chat_messages = [
            models.ChatMessage(id="1", session_id="s1", role="user", message="hi"),
        ]

        self._run(
            session_obj,
            chat_messages,
            SocialTurnTests._social_reply(self, "greeting", "Hey!"),
        )

        self.assertFalse(session_obj.clarification_schema.get(IDEA_CAPTURED_KEY))
        self.assertEqual(session_obj.idea_description, "hi")

    def test_first_substantive_message_backfills_idea_description(self):
        from app.db import models

        session_obj = models.Session(
            id="s1", user_id="u1", status="CLARIFYING", idea_description="hi"
        )
        session_obj.clarification_schema = {}
        chat_messages = [
            models.ChatMessage(id="1", session_id="s1", role="user", message="hi"),
            models.ChatMessage(
                id="2",
                session_id="s1",
                role="user",
                message="a meal plan app for diabetics",
            ),
        ]

        self._run(session_obj, chat_messages, self._substantive_reply())

        self.assertEqual(
            session_obj.idea_description, "a meal plan app for diabetics"
        )
        self.assertTrue(session_obj.clarification_schema[IDEA_CAPTURED_KEY])

    def test_later_messages_do_not_overwrite_the_captured_idea(self):
        from app.db import models

        session_obj = models.Session(
            id="s1",
            user_id="u1",
            status="CLARIFYING",
            idea_description="a meal plan app for diabetics",
        )
        session_obj.clarification_schema = {IDEA_CAPTURED_KEY: True}
        chat_messages = [
            models.ChatMessage(
                id="1",
                session_id="s1",
                role="user",
                message="a meal plan app for diabetics",
            ),
            models.ChatMessage(
                id="2", session_id="s1", role="user", message="mostly type 2 patients"
            ),
        ]

        self._run(session_obj, chat_messages, self._substantive_reply())

        self.assertEqual(
            session_obj.idea_description,
            "a meal plan app for diabetics",
            "answers to follow-up questions must not become the idea",
        )


class SerializeForDownstreamTests(unittest.TestCase):
    def test_unknown_becomes_null_with_directive_surfaced(self):
        schema = _filled_schema(
            differentiation=mark_unknown(
                "differentiation", "Research competitor USPs in health/diabetes."
            )
        )

        clean, directives = serialize_for_downstream(schema)

        self.assertIsNone(clean["differentiation"])
        self.assertIn("Research competitor USPs in health/diabetes.", directives)

    def test_no_marker_substring_survives_serialization(self):
        import json

        schema = _filled_schema(
            differentiation=mark_unknown("differentiation", "Research competitors.")
        )
        clean, directives = serialize_for_downstream(schema)

        blob = json.dumps({"final_schema": clean, "research_directives": directives})
        self.assertNotIn("__unknown__", blob)


class UnknownDirectiveTests(unittest.TestCase):
    def test_differentiation_directive_names_competitors_and_interpolates(self):
        schema = _filled_schema()

        directive = unknown_directive("differentiation", schema)

        self.assertIn("competitor", directive.lower())
        self.assertIn("health/diabetes", directive)
        self.assertIn("diabetic patients", directive)


class WriterViewTests(unittest.TestCase):
    def test_drops_research_scaffolding_and_null_fields(self):
        import json

        clarified_summary = json.dumps(
            {
                "final_schema": {
                    "project_domain": "health/diabetes",
                    "target_persona": "diabetic patients",
                    "core_problem": None,
                    "current_workaround": None,
                    "proposed_solution": "food plan app",
                    "differentiation": None,
                },
                "research_directives": ["Research competitor USPs."],
                "knowledge_gaps": {"differentiation": True},
                "confidence_score": 1.0,
            }
        )

        view = writer_view(clarified_summary)

        self.assertEqual(
            view,
            {
                "project_domain": "health/diabetes",
                "target_persona": "diabetic patients",
                "proposed_solution": "food plan app",
            },
        )
        self.assertNotIn("research_directives", view)
        self.assertNotIn("differentiation", view)


class UnresolvedDirectivesTests(unittest.TestCase):
    def test_directive_with_no_supporting_evidence_is_returned(self):
        service = EvidenceBundleService(db=None)
        service._load_evidence_items = lambda report_id: [
            {"title": "Diabetes meal planning apps", "quote": "Reviews of diet trackers."}
        ]

        import json

        clarified_summary = json.dumps(
            {
                "research_directives": [
                    "Identify unique selling points of blockchain payment rails.",
                ]
            }
        )

        unresolved = service.unresolved_directives("report-1", clarified_summary)

        self.assertEqual(
            unresolved,
            ["Identify unique selling points of blockchain payment rails."],
        )

    def test_well_covered_directive_is_omitted(self):
        service = EvidenceBundleService(db=None)
        service._load_evidence_items = lambda report_id: [
            {
                "title": "Diabetes meal planning competitor pricing",
                "quote": "Competitor pricing and meal planning feature comparison.",
            }
        ]

        import json

        clarified_summary = json.dumps(
            {
                "research_directives": [
                    "Compare competitor pricing and meal planning features.",
                ]
            }
        )

        unresolved = service.unresolved_directives("report-1", clarified_summary)

        self.assertEqual(unresolved, [])


class GapsSectionPromptBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.service = SectionWriterService(db=None)

    def test_gaps_section_prompt_contains_unresolved_gaps_block(self):
        context = {
            "report": {"id": "r1", "topic": "Food plan app", "clarified_summary": {}},
            "section": {"title": "Risks & Open Questions"},
            "outline_titles": ["Problem Context & Validation", "Risks & Open Questions"],
            "citation_map": {},
            "unresolved_gaps": ["Could not establish pricing for competitor X."],
        }

        prompt = self.service._build_prompt(context)

        self.assertIn("Could not establish pricing for competitor X.", prompt)

    def test_ordinary_section_prompt_has_empty_gaps_block(self):
        context = {
            "report": {"id": "r1", "topic": "Food plan app", "clarified_summary": {}},
            "section": {"title": "Competitor Landscape"},
            "outline_titles": ["Competitor Landscape", "Risks & Open Questions"],
            "citation_map": {},
        }

        prompt = self.service._build_prompt(context)

        self.assertNotIn("Could not establish", prompt)
        self.assertIn("[]", prompt)

    def test_is_gaps_section_matches_risks_title(self):
        self.assertTrue(is_gaps_section("Risks & Open Questions", []))

    def test_is_gaps_section_does_not_match_opportunities_and_gaps(self):
        # "Opportunities & Gaps" is a findings section, not the risks section --
        # "gap"/"gaps" alone must not trigger a match.
        self.assertFalse(is_gaps_section("Opportunities & Gaps", []))

    def test_is_gaps_section_falls_back_to_last_section_when_unnamed(self):
        outline = [
            type("S", (), {"title": "Problem Context & Validation"})(),
            type("S", (), {"title": "Wrap-up"})(),
        ]
        self.assertTrue(is_gaps_section("Wrap-up", outline))
        self.assertFalse(is_gaps_section("Problem Context & Validation", outline))


if __name__ == "__main__":
    unittest.main()
