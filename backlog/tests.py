"""
Comprehensive regression tests for the WoS (WSJF on Steroids) backlog application.

These tests cover:
- Model creation and relationships
- computed_status property logic
- Story CRUD operations
- Archiving functionality
- History tracking
- Kanban board moves
- Report calculations
- WBS dependencies
- Story refinement
"""

import json
from datetime import timedelta

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from .models import (
    Story,
    ValueFactorSection,
    ValueFactor,
    ValueFactorAnswer,
    CostFactorSection,
    CostFactor,
    CostFactorAnswer,
    StoryValueFactorScore,
    StoryCostFactorScore,
    StoryDependency,
    StoryHistory,
    LabelCategory,
    Label,
)


class BaseTestCase(TestCase):
    """Base test case with common setup for all tests."""

    def setUp(self):
        """Set up test data used across multiple tests."""
        self.client = Client()
        
        # Create value factor section and factors
        self.value_section = ValueFactorSection.objects.create(
            name="Business Value",
            description="Measures business impact"
        )
        self.value_factor = ValueFactor.objects.create(
            section=self.value_section,
            name="Revenue Impact",
            description="Impact on revenue"
        )
        # Create value factor answers
        self.vf_answer_0 = ValueFactorAnswer.objects.create(
            valuefactor=self.value_factor,
            score=0,
            description="No impact"
        )
        self.vf_answer_5 = ValueFactorAnswer.objects.create(
            valuefactor=self.value_factor,
            score=5,
            description="Medium impact"
        )
        self.vf_answer_10 = ValueFactorAnswer.objects.create(
            valuefactor=self.value_factor,
            score=10,
            description="High impact"
        )
        
        # Create cost factor section and factors
        self.cost_section = CostFactorSection.objects.create(
            name="Development Cost",
            description="Measures development effort"
        )
        self.cost_factor = CostFactor.objects.create(
            section=self.cost_section,
            name="Engineering Hours",
            description="Hours to implement"
        )
        # Create cost factor answers
        self.cf_answer_0 = CostFactorAnswer.objects.create(
            costfactor=self.cost_factor,
            score=0,
            description="No effort"
        )
        self.cf_answer_2 = CostFactorAnswer.objects.create(
            costfactor=self.cost_factor,
            score=2,
            description="Low effort"
        )
        self.cf_answer_5 = CostFactorAnswer.objects.create(
            costfactor=self.cost_factor,
            score=5,
            description="Medium effort"
        )


class StoryModelTests(BaseTestCase):
    """Tests for Story model."""

    def test_story_creation(self):
        """Test story is created with correct fields."""
        story = Story.objects.create(
            title="Test Story",
            goal="Test Goal",
            workitems="Test Workitems"
        )
        self.assertEqual(story.title, "Test Story")
        self.assertEqual(story.goal, "Test Goal")
        self.assertEqual(story.workitems, "Test Workitems")
        self.assertFalse(story.archived)
        self.assertFalse(story.review_required)

    def test_story_str(self):
        """Test story string representation."""
        story = Story.objects.create(title="My Story")
        self.assertEqual(str(story), "My Story")

    def test_story_status_auto_update_to_refined(self):
        """Test status updates to 'refined' when goal and workitems are set."""
        story = Story.objects.create(
            title="Test Story",
            goal="Has goal",
            workitems="Has workitems"
        )
        self.assertEqual(story.status, Story.STATUS_REFINED)

    def test_story_status_remains_new_without_goal(self):
        """Test status remains 'new' when goal is missing."""
        story = Story.objects.create(
            title="Test Story",
            workitems="Has workitems"
        )
        self.assertEqual(story.status, Story.STATUS_NEW)

    def test_story_status_remains_new_without_workitems(self):
        """Test status remains 'new' when workitems is missing."""
        story = Story.objects.create(
            title="Test Story",
            goal="Has goal"
        )
        self.assertEqual(story.status, Story.STATUS_NEW)


class ComputedStatusTests(BaseTestCase):
    """Tests for Story.computed_status property - critical for status display."""

    def test_computed_status_idea_missing_title(self):
        """Test computed_status is 'idea' when title is missing."""
        story = Story.objects.create(title="")
        self.assertEqual(story.computed_status, "idea")

    def test_computed_status_idea_missing_goal(self):
        """Test computed_status is 'idea' when goal is missing."""
        story = Story.objects.create(
            title="Has Title",
            workitems="Has workitems"
        )
        self.assertEqual(story.computed_status, "idea")

    def test_computed_status_idea_missing_workitems(self):
        """Test computed_status is 'idea' when workitems is missing."""
        story = Story.objects.create(
            title="Has Title",
            goal="Has goal"
        )
        self.assertEqual(story.computed_status, "idea")

    def test_computed_status_idea_missing_scores(self):
        """Test computed_status is 'idea' when scores are missing."""
        story = Story.objects.create(
            title="Has Title",
            goal="Has goal",
            workitems="Has workitems"
        )
        # Delete any auto-created scores
        StoryValueFactorScore.objects.filter(story=story).delete()
        self.assertEqual(story.computed_status, "idea")

    def test_computed_status_ready_all_fields_complete(self):
        """Test computed_status is 'ready' when all fields and scores are complete."""
        story = Story.objects.create(
            title="Has Title",
            goal="Has goal",
            workitems="Has workitems"
        )
        # Ensure all scores are set
        StoryValueFactorScore.objects.update_or_create(
            story=story,
            valuefactor=self.value_factor,
            defaults={"answer": self.vf_answer_5}
        )
        StoryCostFactorScore.objects.update_or_create(
            story=story,
            costfactor=self.cost_factor,
            defaults={"answer": self.cf_answer_2}
        )
        self.assertEqual(story.computed_status, "ready")

    def test_computed_status_planned(self):
        """Test computed_status is 'planned' when planned datetime is set."""
        story = Story.objects.create(
            title="Has Title",
            goal="Has goal",
            workitems="Has workitems",
            planned=timezone.now()
        )
        StoryValueFactorScore.objects.update_or_create(
            story=story,
            valuefactor=self.value_factor,
            defaults={"answer": self.vf_answer_5}
        )
        StoryCostFactorScore.objects.update_or_create(
            story=story,
            costfactor=self.cost_factor,
            defaults={"answer": self.cf_answer_2}
        )
        self.assertEqual(story.computed_status, "planned")

    def test_computed_status_started(self):
        """Test computed_status is 'started' when started datetime is set."""
        story = Story.objects.create(
            title="Has Title",
            goal="Has goal",
            workitems="Has workitems",
            planned=timezone.now(),
            started=timezone.now()
        )
        self.assertEqual(story.computed_status, "started")

    def test_computed_status_done(self):
        """Test computed_status is 'done' when finished datetime is set."""
        story = Story.objects.create(
            title="Has Title",
            planned=timezone.now(),
            started=timezone.now(),
            finished=timezone.now()
        )
        self.assertEqual(story.computed_status, "done")

    def test_computed_status_blocked_priority(self):
        """Test blocked status takes priority over all others."""
        story = Story.objects.create(
            title="Has Title",
            goal="Has goal",
            workitems="Has workitems",
            planned=timezone.now(),
            started=timezone.now(),
            finished=timezone.now(),
            blocked="Some blocking reason"
        )
        self.assertEqual(story.computed_status, "blocked")

    def test_computed_status_done_priority_over_started(self):
        """Test done status takes priority over started."""
        story = Story.objects.create(
            title="Has Title",
            started=timezone.now(),
            finished=timezone.now()
        )
        self.assertEqual(story.computed_status, "done")

    def test_computed_status_started_priority_over_planned(self):
        """Test started status takes priority over planned."""
        story = Story.objects.create(
            title="Has Title",
            planned=timezone.now(),
            started=timezone.now()
        )
        self.assertEqual(story.computed_status, "started")


class StoryHistoryTests(BaseTestCase):
    """Tests for StoryHistory model and tracking."""

    def test_story_history_creation(self):
        """Test history entry is created correctly."""
        story = Story.objects.create(title="Test Story")
        history = StoryHistory.objects.create(
            story=story,
            field_name="Title",
            old_value="Old Title",
            new_value="Test Story"
        )
        self.assertEqual(history.field_name, "Title")
        self.assertEqual(history.old_value, "Old Title")
        self.assertEqual(history.new_value, "Test Story")
        self.assertIsNotNone(history.changed_at)

    def test_story_history_ordering(self):
        """Test history entries are ordered by most recent first."""
        story = Story.objects.create(title="Test Story")
        h1 = StoryHistory.objects.create(story=story, field_name="First")
        h2 = StoryHistory.objects.create(story=story, field_name="Second")
        
        history = list(story.history.all())
        self.assertEqual(history[0].field_name, "Second")
        self.assertEqual(history[1].field_name, "First")


class StoryDependencyTests(BaseTestCase):
    """Tests for StoryDependency model."""

    def test_dependency_creation(self):
        """Test dependency is created correctly."""
        story1 = Story.objects.create(title="Story 1")
        story2 = Story.objects.create(title="Story 2")
        
        dep = StoryDependency.objects.create(story=story1, depends_on=story2)
        self.assertEqual(dep.story, story1)
        self.assertEqual(dep.depends_on, story2)

    def test_dependency_unique_constraint(self):
        """Test duplicate dependencies are not allowed."""
        story1 = Story.objects.create(title="Story 1")
        story2 = Story.objects.create(title="Story 2")
        
        StoryDependency.objects.create(story=story1, depends_on=story2)
        
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            StoryDependency.objects.create(story=story1, depends_on=story2)

    def test_dependency_related_names(self):
        """Test related names for dependencies and dependents."""
        story1 = Story.objects.create(title="Story 1")
        story2 = Story.objects.create(title="Story 2")
        
        StoryDependency.objects.create(story=story1, depends_on=story2)
        
        # story1 depends on story2
        self.assertEqual(story1.dependencies.count(), 1)
        self.assertEqual(story1.dependencies.first().depends_on, story2)
        
        # story2 has story1 as a dependent
        self.assertEqual(story2.dependents.count(), 1)
        self.assertEqual(story2.dependents.first().story, story1)


class StoryViewTests(BaseTestCase):
    """Tests for Story-related views."""

    def test_stories_page_loads(self):
        """Test stories list page loads."""
        Story.objects.create(title="Test Story")
        response = self.client.get(reverse('backlog:stories'))
        self.assertEqual(response.status_code, 200)

    def test_stories_filter_by_status(self):
        """Test filtering stories by computed status."""
        story_idea = Story.objects.create(title="Idea Story")
        story_done = Story.objects.create(
            title="Done Story",
            finished=timezone.now()
        )
        
        response = self.client.get(reverse('backlog:stories') + '?status=done')
        self.assertContains(response, "Done Story")
        self.assertNotContains(response, "Idea Story")

    def test_stories_filter_by_review_required(self):
        """Test filtering stories by review_required."""
        story_needs_review = Story.objects.create(
            title="Needs Review",
            review_required=True
        )
        story_no_review = Story.objects.create(
            title="No Review"
        )
        
        response = self.client.get(reverse('backlog:stories') + '?review=yes')
        self.assertContains(response, "Needs Review")
        self.assertNotContains(response, "No Review")

    def test_stories_delete_story(self):
        """Test deleting a story - critical regression test."""
        story = Story.objects.create(title="To Delete")
        
        response = self.client.post(reverse('backlog:stories'), {
            'action': 'delete_story',
            'story_id': story.pk
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Story.objects.filter(pk=story.pk).exists())

    def test_stories_archive_story(self):
        """Test archiving a story from list."""
        story = Story.objects.create(title="To Archive")
        
        response = self.client.post(reverse('backlog:stories'), {
            'action': 'archive_story',
            'story_id': story.pk
        })
        self.assertEqual(response.status_code, 302)
        story.refresh_from_db()
        self.assertTrue(story.archived)

    def test_stories_toggle_review(self):
        """Test toggling review_required from list."""
        story = Story.objects.create(title="Test Story")
        
        response = self.client.post(reverse('backlog:stories'), {
            'action': 'toggle_review',
            'story_id': story.pk
        })
        self.assertEqual(response.status_code, 302)
        story.refresh_from_db()
        self.assertTrue(story.review_required)


class RefineStoryTests(BaseTestCase):
    """Tests for story refinement - critical functionality."""

    def test_refine_page_loads(self):
        """Test refine page loads for existing story."""
        story = Story.objects.create(title="Test Story")
        response = self.client.get(reverse('backlog:story_detail', args=[story.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Story")

    def test_refine_story_title_save(self):
        """Test saving story title - critical regression test (was broken before)."""
        story = Story.objects.create(title="Original Title")
        
        response = self.client.post(reverse('backlog:story_detail', args=[story.pk]), {
            'title': 'Updated Title',
            'goal': 'Test Goal',
            'workitems': 'Test Workitems',
            'blocked': '',
        })
        self.assertEqual(response.status_code, 302)
        story.refresh_from_db()
        self.assertEqual(story.title, 'Updated Title')

    def test_refine_story_goal_save(self):
        """Test saving story goal."""
        story = Story.objects.create(title="Test Story")
        
        response = self.client.post(reverse('backlog:story_detail', args=[story.pk]), {
            'title': 'Test Story',
            'goal': 'New Goal',
            'workitems': '',
            'blocked': '',
        })
        self.assertEqual(response.status_code, 302)
        story.refresh_from_db()
        self.assertEqual(story.goal, 'New Goal')

    def test_refine_story_workitems_save(self):
        """Test saving story workitems."""
        story = Story.objects.create(title="Test Story")
        
        response = self.client.post(reverse('backlog:story_detail', args=[story.pk]), {
            'title': 'Test Story',
            'goal': '',
            'workitems': 'Work item 1\nWork item 2',
            'blocked': '',
        })
        self.assertEqual(response.status_code, 302)
        story.refresh_from_db()
        self.assertEqual(story.workitems, 'Work item 1\nWork item 2')

    def test_refine_story_blocked(self):
        """Test setting blocked field."""
        story = Story.objects.create(title="Test Story")
        
        response = self.client.post(reverse('backlog:story_detail', args=[story.pk]), {
            'title': 'Test Story',
            'goal': '',
            'workitems': '',
            'blocked': 'Waiting for approval',
        })
        self.assertEqual(response.status_code, 302)
        story.refresh_from_db()
        self.assertEqual(story.blocked, 'Waiting for approval')
        self.assertEqual(story.computed_status, 'blocked')

    def test_refine_story_remove_blocked(self):
        """Test removing blocked status."""
        story = Story.objects.create(
            title="Test Story",
            blocked="Was blocked"
        )
        
        response = self.client.post(reverse('backlog:story_detail', args=[story.pk]), {
            'remove_blocked': '1',
        })
        self.assertEqual(response.status_code, 302)
        story.refresh_from_db()
        self.assertEqual(story.blocked, '')

    def test_refine_story_archive(self):
        """Test archiving story from refine page."""
        story = Story.objects.create(title="Test Story")
        
        response = self.client.post(reverse('backlog:story_detail', args=[story.pk]), {
            'action': 'archive_story',
        })
        self.assertEqual(response.status_code, 302)
        story.refresh_from_db()
        self.assertTrue(story.archived)

    def test_refine_story_toggle_review(self):
        """Test toggling review_required from refine page."""
        story = Story.objects.create(title="Test Story")
        
        response = self.client.post(reverse('backlog:story_detail', args=[story.pk]), {
            'action': 'toggle_review',
        })
        self.assertEqual(response.status_code, 302)
        story.refresh_from_db()
        self.assertTrue(story.review_required)

    def test_refine_story_history_tracked(self):
        """Test that changes are tracked in history."""
        story = Story.objects.create(title="Original Title")
        
        response = self.client.post(reverse('backlog:story_detail', args=[story.pk]), {
            'title': 'New Title',
            'goal': 'New Goal',
            'workitems': '',
            'blocked': '',
        })
        
        # Check history was created
        history = StoryHistory.objects.filter(story=story)
        self.assertTrue(history.filter(field_name='Title').exists())
        self.assertTrue(history.filter(field_name='Goal').exists())

    def test_refine_story_value_factor_score(self):
        """Test saving value factor scores."""
        story = Story.objects.create(title="Test Story")
        
        response = self.client.post(reverse('backlog:story_detail', args=[story.pk]), {
            'title': 'Test Story',
            'goal': '',
            'workitems': '',
            'blocked': '',
            f'vf_{self.value_factor.pk}': str(self.vf_answer_10.pk),
        })
        self.assertEqual(response.status_code, 302)
        
        score = StoryValueFactorScore.objects.get(story=story, valuefactor=self.value_factor)
        self.assertEqual(score.answer, self.vf_answer_10)

    def test_refine_story_cost_factor_score(self):
        """Test saving cost factor scores."""
        story = Story.objects.create(title="Test Story")
        
        response = self.client.post(reverse('backlog:story_detail', args=[story.pk]), {
            'title': 'Test Story',
            'goal': '',
            'workitems': '',
            'blocked': '',
            f'cf_{self.cost_factor.pk}': str(self.cf_answer_5.pk),
        })
        self.assertEqual(response.status_code, 302)
        
        score = StoryCostFactorScore.objects.get(story=story, costfactor=self.cost_factor)
        self.assertEqual(score.answer, self.cf_answer_5)

    def test_refine_story_add_dependency(self):
        """Test adding a dependency."""
        story1 = Story.objects.create(title="Story 1")
        story2 = Story.objects.create(title="Story 2")
        
        response = self.client.post(reverse('backlog:story_detail', args=[story1.pk]), {
            'action': 'add_dependency',
            'dependency_story_id': story2.pk,
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            StoryDependency.objects.filter(story=story1, depends_on=story2).exists()
        )

    def test_refine_story_remove_dependency(self):
        """Test removing a dependency."""
        story1 = Story.objects.create(title="Story 1")
        story2 = Story.objects.create(title="Story 2")
        dep = StoryDependency.objects.create(story=story1, depends_on=story2)
        
        response = self.client.post(reverse('backlog:story_detail', args=[story1.pk]), {
            'action': 'remove_dependency',
            'dependency_id': dep.pk,
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            StoryDependency.objects.filter(story=story1, depends_on=story2).exists()
        )


class CreateStoryTests(BaseTestCase):
    """Tests for story creation."""

    def test_create_story_page_loads(self):
        """Test create story page loads."""
        response = self.client.get(reverse('backlog:story_create'))
        self.assertEqual(response.status_code, 200)

    def test_create_story_success(self):
        """Test successfully creating a new story."""
        response = self.client.post(reverse('backlog:story_create'), {
            'title': 'New Story',
            'goal': 'Story Goal',
            'workitems': 'Story Workitems',
            'blocked': '',
        })
        self.assertEqual(response.status_code, 302)
        story = Story.objects.get(title='New Story')
        self.assertEqual(story.goal, 'Story Goal')
        self.assertEqual(story.workitems, 'Story Workitems')

    def test_create_story_history_created(self):
        """Test that history entry is created for new story."""
        response = self.client.post(reverse('backlog:story_create'), {
            'title': 'New Story',
            'goal': '',
            'workitems': '',
            'blocked': '',
        })
        story = Story.objects.get(title='New Story')
        history = StoryHistory.objects.filter(story=story, field_name='Story created')
        self.assertTrue(history.exists())

    def test_create_story_missing_title(self):
        """Test creating story without title re-renders form."""
        response = self.client.post(reverse('backlog:story_create'), {
            'title': '',
        })
        # Should re-render form, not create story
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Story.objects.filter(title='').exists())


class KanbanViewTests(BaseTestCase):
    """Tests for Kanban board functionality."""

    def test_kanban_page_loads(self):
        """Test kanban page loads."""
        response = self.client.get(reverse('backlog:kanban'))
        self.assertEqual(response.status_code, 200)

    def test_kanban_columns_populated(self):
        """Test kanban shows stories in correct columns."""
        # Create stories with different statuses
        story_ready = Story.objects.create(
            title="Ready Story",
            goal="Goal",
            workitems="Work"
        )
        StoryValueFactorScore.objects.update_or_create(
            story=story_ready,
            valuefactor=self.value_factor,
            defaults={"answer": self.vf_answer_5}
        )
        StoryCostFactorScore.objects.update_or_create(
            story=story_ready,
            costfactor=self.cost_factor,
            defaults={"answer": self.cf_answer_2}
        )
        
        story_done = Story.objects.create(
            title="Done Story",
            finished=timezone.now()
        )
        
        response = self.client.get(reverse('backlog:kanban'))
        self.assertContains(response, "Ready Story")
        self.assertContains(response, "Done Story")

    def test_kanban_move_to_planned(self):
        """Test moving a story to planned column."""
        story = Story.objects.create(
            title="Test Story",
            goal="Goal",
            workitems="Work"
        )
        StoryValueFactorScore.objects.update_or_create(
            story=story,
            valuefactor=self.value_factor,
            defaults={"answer": self.vf_answer_5}
        )
        StoryCostFactorScore.objects.update_or_create(
            story=story,
            costfactor=self.cost_factor,
            defaults={"answer": self.cf_answer_2}
        )
        
        response = self.client.post(
            reverse('backlog:kanban_move'),
            data=json.dumps({'story_id': story.pk, 'target': 'planned'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        story.refresh_from_db()
        self.assertIsNotNone(story.planned)
        self.assertEqual(story.computed_status, 'planned')

    def test_kanban_move_to_doing(self):
        """Test moving a story to doing column."""
        story = Story.objects.create(title="Test Story")
        
        response = self.client.post(
            reverse('backlog:kanban_move'),
            data=json.dumps({'story_id': story.pk, 'target': 'doing'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        story.refresh_from_db()
        self.assertIsNotNone(story.started)
        self.assertEqual(story.computed_status, 'started')

    def test_kanban_move_to_blocked(self):
        """Test moving a story to blocked column."""
        story = Story.objects.create(title="Test Story")
        
        response = self.client.post(
            reverse('backlog:kanban_move'),
            data=json.dumps({
                'story_id': story.pk,
                'target': 'blocked',
                'blocked_reason': 'Waiting for API'
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        story.refresh_from_db()
        self.assertEqual(story.blocked, 'Waiting for API')
        self.assertEqual(story.computed_status, 'blocked')

    def test_kanban_move_to_done(self):
        """Test moving a story to done column."""
        story = Story.objects.create(title="Test Story")
        
        response = self.client.post(
            reverse('backlog:kanban_move'),
            data=json.dumps({'story_id': story.pk, 'target': 'done'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        story.refresh_from_db()
        self.assertIsNotNone(story.finished)
        self.assertEqual(story.computed_status, 'done')

    def test_kanban_move_to_backlog(self):
        """Test moving a story back to backlog clears dates."""
        story = Story.objects.create(
            title="Test Story",
            planned=timezone.now(),
            started=timezone.now()
        )
        
        response = self.client.post(
            reverse('backlog:kanban_move'),
            data=json.dumps({'story_id': story.pk, 'target': 'backlog'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        story.refresh_from_db()
        self.assertIsNone(story.planned)
        self.assertIsNone(story.started)
        self.assertIsNone(story.finished)
        self.assertEqual(story.blocked, '')

    def test_kanban_move_history_tracked(self):
        """Test that kanban moves are tracked in history."""
        story = Story.objects.create(title="Test Story")
        
        response = self.client.post(
            reverse('backlog:kanban_move'),
            data=json.dumps({'story_id': story.pk, 'target': 'done'}),
            content_type='application/json'
        )
        
        # Check history was created
        history = StoryHistory.objects.filter(story=story)
        self.assertTrue(history.filter(field_name='Status (Kanban)').exists())

    def test_kanban_move_invalid_target(self):
        """Test kanban move with invalid target returns error."""
        story = Story.objects.create(title="Test Story")
        
        response = self.client.post(
            reverse('backlog:kanban_move'),
            data=json.dumps({'story_id': story.pk, 'target': 'invalid'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)

    def test_kanban_move_missing_data(self):
        """Test kanban move with missing data returns error."""
        response = self.client.post(
            reverse('backlog:kanban_move'),
            data=json.dumps({'story_id': ''}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)


class ReportViewTests(BaseTestCase):
    """Tests for Report view."""

    def test_report_page_loads(self):
        """Test report page loads."""
        response = self.client.get(reverse('backlog:report'))
        self.assertEqual(response.status_code, 200)

    def test_report_shows_stories(self):
        """Test report shows stories with scores."""
        story = Story.objects.create(
            title="Test Story",
            goal="Goal",
            workitems="Work"
        )
        StoryValueFactorScore.objects.update_or_create(
            story=story,
            valuefactor=self.value_factor,
            defaults={"answer": self.vf_answer_10}
        )
        StoryCostFactorScore.objects.update_or_create(
            story=story,
            costfactor=self.cost_factor,
            defaults={"answer": self.cf_answer_2}
        )
        
        response = self.client.get(reverse('backlog:report'))
        self.assertContains(response, "Test Story")

    def test_report_filter_by_status(self):
        """Test report filtering by status."""
        Story.objects.create(title="Idea Story")
        Story.objects.create(
            title="Done Story",
            finished=timezone.now()
        )
        
        response = self.client.get(reverse('backlog:report') + '?status=done')
        self.assertContains(response, "Done Story")
        self.assertNotContains(response, "Idea Story")

    def test_report_excludes_archived(self):
        """Test report excludes archived stories."""
        story_active = Story.objects.create(title="Active Story")
        story_archived = Story.objects.create(
            title="Archived Story",
            archived=True
        )
        
        response = self.client.get(reverse('backlog:report'))
        self.assertContains(response, "Active Story")
        self.assertNotContains(response, "Archived Story")

    def test_report_has_tweak_mode_button(self):
        """Test report page has tweak mode button for temporary score adjustments."""
        response = self.client.get(reverse('backlog:report'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="toggle-tweak-mode"')
        self.assertContains(response, 'Tweak Mode')

    def test_report_has_reset_button(self):
        """Test report page has reset button for tweak mode."""
        response = self.client.get(reverse('backlog:report'))
        self.assertContains(response, 'id="reset-tweaks"')

    def test_report_value_cells_have_tweak_attributes(self):
        """Test report value cells have data attributes needed for tweak mode."""
        story = Story.objects.create(title="Test Story")
        StoryValueFactorScore.objects.update_or_create(
            story=story,
            valuefactor=self.value_factor,
            defaults={"answer": self.vf_answer_10}
        )
        StoryCostFactorScore.objects.update_or_create(
            story=story,
            costfactor=self.cost_factor,
            defaults={"answer": self.cf_answer_2}
        )
        
        response = self.client.get(reverse('backlog:report'))
        content = response.content.decode('utf-8')
        
        # Check for value-total-cell with data attributes
        self.assertIn('class="value-total-cell"', content)
        # Value is now the average of section scores (10.0 for single factor)
        self.assertIn('data-original="10', content)
        
        # Check for cost-total-cell with data attributes
        self.assertIn('class="cost-total-cell"', content)
        # Cost is now the average of section scores (2.0 for single factor)
        self.assertIn('data-original="2', content)
        
        # Check for tweak input fields
        self.assertIn('class="tweak-input"', content)

    def test_report_has_tweak_hint(self):
        """Test report page has tweak mode hint that explains the feature."""
        response = self.client.get(reverse('backlog:report'))
        self.assertContains(response, 'id="tweak-hint"')
        self.assertContains(response, 'Tweak Mode Active')
        self.assertContains(response, 'NOT saved')


class WBSViewTests(BaseTestCase):
    """Tests for Work Breakdown Structure view."""

    def test_wbs_page_loads(self):
        """Test WBS page loads."""
        response = self.client.get(reverse('backlog:wbs'))
        self.assertEqual(response.status_code, 200)

    def test_wbs_shows_stories(self):
        """Test WBS shows stories."""
        Story.objects.create(title="WBS Story")
        response = self.client.get(reverse('backlog:wbs'))
        self.assertContains(response, "WBS Story")

    def test_wbs_add_dependency(self):
        """Test adding dependency via WBS AJAX."""
        story1 = Story.objects.create(title="Story 1")
        story2 = Story.objects.create(title="Story 2")
        
        response = self.client.post(
            reverse('backlog:wbs_add_dependency'),
            data=json.dumps({
                'story_id': story1.pk,
                'depends_on_id': story2.pk
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertTrue(
            StoryDependency.objects.filter(story=story1, depends_on=story2).exists()
        )

    def test_wbs_add_dependency_self(self):
        """Test cannot add dependency on self."""
        story = Story.objects.create(title="Story")
        
        response = self.client.post(
            reverse('backlog:wbs_add_dependency'),
            data=json.dumps({
                'story_id': story.pk,
                'depends_on_id': story.pk
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)

    def test_wbs_add_duplicate_dependency(self):
        """Test cannot add duplicate dependency."""
        story1 = Story.objects.create(title="Story 1")
        story2 = Story.objects.create(title="Story 2")
        StoryDependency.objects.create(story=story1, depends_on=story2)
        
        response = self.client.post(
            reverse('backlog:wbs_add_dependency'),
            data=json.dumps({
                'story_id': story1.pk,
                'depends_on_id': story2.pk
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)

    def test_wbs_remove_dependency(self):
        """Test removing dependency via WBS AJAX."""
        story1 = Story.objects.create(title="Story 1")
        story2 = Story.objects.create(title="Story 2")
        StoryDependency.objects.create(story=story1, depends_on=story2)
        
        response = self.client.post(
            reverse('backlog:wbs_remove_dependency'),
            data=json.dumps({
                'story_id': story1.pk,
                'depends_on_id': story2.pk
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertFalse(
            StoryDependency.objects.filter(story=story1, depends_on=story2).exists()
        )

    def test_wbs_excludes_archived(self):
        """Test WBS excludes archived stories from the main view."""
        Story.objects.create(title="Active Story WBS")
        Story.objects.create(title="Archived Story WBS", archived=True)
        
        response = self.client.get(reverse('backlog:wbs'))
        # Check the stories in the context (not HTML which may have dropdown with all stories)
        stories_in_response = [s['title'] for s in response.context['stories']]
        self.assertIn("Active Story WBS", stories_in_response)
        self.assertNotIn("Archived Story WBS", stories_in_response)


class HealthCheckTests(BaseTestCase):
    """Tests for health check endpoint."""

    def test_health_check_ok(self):
        """Test health check returns OK."""
        response = self.client.get(reverse('backlog:health'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'ok')


class ScoreSignalTests(BaseTestCase):
    """Tests for automatic score creation on story creation."""

    def test_scores_created_on_story_creation(self):
        """Test that score records are created when a story is created.
        
        Score records are created with answer=None (undefined), not with a
        default score of 0. This distinguishes 'not yet scored' from an
        explicit score of 0.
        """
        story = Story.objects.create(title="New Story")
        
        # Check value factor score record was created with answer=None
        vf_score = StoryValueFactorScore.objects.filter(
            story=story,
            valuefactor=self.value_factor
        ).first()
        self.assertIsNotNone(vf_score)
        self.assertIsNone(vf_score.answer)  # Undefined, not scored yet
        
        # Check cost factor score record was created with answer=None
        cf_score = StoryCostFactorScore.objects.filter(
            story=story,
            costfactor=self.cost_factor
        ).first()
        self.assertIsNotNone(cf_score)
        self.assertIsNone(cf_score.answer)  # Undefined, not scored yet


class IntegrationTests(BaseTestCase):
    """Integration tests for complete workflows."""

    def test_complete_story_lifecycle(self):
        """Test complete story lifecycle from creation to done."""
        # Create story
        response = self.client.post(reverse('backlog:story_create'), {
            'title': 'Lifecycle Story',
            'goal': 'Test the lifecycle',
            'workitems': 'Create, refine, plan, start, finish',
            'blocked': '',
        })
        story = Story.objects.get(title='Lifecycle Story')
        
        # Delete the auto-created scores so we start from 'idea' status
        StoryValueFactorScore.objects.filter(story=story).delete()
        StoryCostFactorScore.objects.filter(story=story).delete()
        story.refresh_from_db()
        self.assertEqual(story.computed_status, 'idea')  # Missing scores
        
        # Set scores
        StoryValueFactorScore.objects.update_or_create(
            story=story,
            valuefactor=self.value_factor,
            defaults={"answer": self.vf_answer_10}
        )
        StoryCostFactorScore.objects.update_or_create(
            story=story,
            costfactor=self.cost_factor,
            defaults={"answer": self.cf_answer_2}
        )
        story.refresh_from_db()
        self.assertEqual(story.computed_status, 'ready')
        
        # Move to planned
        self.client.post(
            reverse('backlog:kanban_move'),
            data=json.dumps({'story_id': story.pk, 'target': 'planned'}),
            content_type='application/json'
        )
        story.refresh_from_db()
        self.assertEqual(story.computed_status, 'planned')
        
        # Move to doing
        self.client.post(
            reverse('backlog:kanban_move'),
            data=json.dumps({'story_id': story.pk, 'target': 'doing'}),
            content_type='application/json'
        )
        story.refresh_from_db()
        self.assertEqual(story.computed_status, 'started')
        
        # Move to done
        self.client.post(
            reverse('backlog:kanban_move'),
            data=json.dumps({'story_id': story.pk, 'target': 'done'}),
            content_type='application/json'
        )
        story.refresh_from_db()
        self.assertEqual(story.computed_status, 'done')
        
        # Verify history was tracked
        history = StoryHistory.objects.filter(story=story)
        self.assertGreater(history.count(), 0)

    def test_dependency_chain(self):
        """Test creating a chain of dependencies."""
        story1 = Story.objects.create(title="Story 1")
        story2 = Story.objects.create(title="Story 2")
        story3 = Story.objects.create(title="Story 3")
        
        # story1 depends on story2
        StoryDependency.objects.create(story=story1, depends_on=story2)
        # story2 depends on story3
        StoryDependency.objects.create(story=story2, depends_on=story3)
        
        # Verify chain
        self.assertEqual(story1.dependencies.count(), 1)
        self.assertEqual(story2.dependencies.count(), 1)
        self.assertEqual(story3.dependencies.count(), 0)
        
        # Verify reverse relationships
        self.assertEqual(story1.dependents.count(), 0)
        self.assertEqual(story2.dependents.count(), 1)
        self.assertEqual(story3.dependents.count(), 1)


class DashboardViewTests(BaseTestCase):
    """Test cases for the dashboard view."""

    def test_dashboard_view_loads(self):
        """Test that the dashboard view loads successfully."""
        response = self.client.get(reverse('backlog:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'backlog/dashboard.html')

    def test_dashboard_context_has_required_keys(self):
        """Test that dashboard context contains all required data."""
        response = self.client.get(reverse('backlog:dashboard'))
        self.assertIn('needs_scoring', response.context)
        self.assertIn('needs_refinement', response.context)
        self.assertIn('rotting_stories', response.context)
        self.assertIn('review_required', response.context)
        self.assertIn('summary', response.context)
        self.assertIn('thresholds', response.context)

    def test_dashboard_summary_counts(self):
        """Test that summary counts are correct."""
        response = self.client.get(reverse('backlog:dashboard'))
        summary = response.context['summary']
        
        self.assertIn('total_stories', summary)
        self.assertIn('needs_scoring', summary)
        self.assertIn('needs_refinement', summary)
        self.assertIn('rotting', summary)
        self.assertIn('review_required', summary)
        self.assertIn('healthy', summary)

    def test_needs_scoring_when_factors_exist_before_story(self):
        """Test that new stories need scoring since they have undefined (None) answers.
        
        Note: The signal creates score records with answer=None when a story is
        created. This means 'needs scoring' since undefined != scored.
        """
        # Create story (will auto-create score records with answer=None)
        story = Story.objects.create(
            title="Story with Undefined Scores",
            goal="Test goal",
            workitems="Test workitems"
        )
        
        # Story should have score records but with answer=None (undefined)
        self.assertTrue(story.scores.exists())
        self.assertTrue(story.cost_scores.exists())
        self.assertIsNone(story.scores.first().answer)
        self.assertIsNone(story.cost_scores.first().answer)
        
        response = self.client.get(reverse('backlog:dashboard'))
        needs_scoring = [item['story'].id for item in response.context['needs_scoring']]
        
        # Story SHOULD be in needs_scoring since answers are None (undefined)
        self.assertIn(story.id, needs_scoring)

    def test_needs_scoring_when_new_factor_added(self):
        """Test that story needs scoring when a new factor is added after creation."""
        # Create story first
        story = Story.objects.create(
            title="Story Missing New Factor",
            goal="Test goal",
            workitems="Test workitems"
        )
        
        # Now add a new value factor (story won't have a score for this)
        new_section = ValueFactorSection.objects.create(
            name="New Section",
            description="New section description"
        )
        new_factor = ValueFactor.objects.create(
            section=new_section,
            name="New Factor",
            description="New factor description"
        )
        ValueFactorAnswer.objects.create(
            valuefactor=new_factor,
            score=5,
            description="New answer"
        )
        
        response = self.client.get(reverse('backlog:dashboard'))
        needs_scoring = [item['story'].id for item in response.context['needs_scoring']]
        
        # Story should be in needs_scoring since it's missing the new factor
        self.assertIn(story.id, needs_scoring)

    def test_needs_refinement_detection(self):
        """Test that stories in idea status are detected as needing refinement."""
        # Create story without goal and workitems (idea status)
        story = Story.objects.create(
            title="Idea Story"
        )
        
        response = self.client.get(reverse('backlog:dashboard'))
        needs_refinement = [item['story'].id for item in response.context['needs_refinement']]
        
        self.assertIn(story.id, needs_refinement)

    def test_refined_story_not_in_needs_refinement(self):
        """Test that fully refined stories (with scores) are not in needs_refinement."""
        story = Story.objects.create(
            title="Refined Story",
            goal="Clear goal",
            workitems="Work to do"
        )
        # Set actual scores (not just undefined) for the story to be truly "ready"
        story.scores.update(answer=self.vf_answer_5)
        story.cost_scores.update(answer=self.cf_answer_2)
        
        response = self.client.get(reverse('backlog:dashboard'))
        needs_refinement = [item['story'].id for item in response.context['needs_refinement']]
        
        self.assertNotIn(story.id, needs_refinement)

    def test_rotting_blocked_story(self):
        """Test that stories blocked for too long are detected as rotting."""
        story = Story.objects.create(
            title="Blocked Story",
            goal="Test goal",
            workitems="Test workitems",
            blocked="Waiting for API"
        )
        # Force update the updated_at to bypass auto_now
        Story.objects.filter(pk=story.pk).update(
            updated_at=timezone.now() - timedelta(days=10)
        )
        
        response = self.client.get(reverse('backlog:dashboard'))
        rotting = [item['story'].id for item in response.context['rotting_stories']]
        
        self.assertIn(story.id, rotting)

    def test_rotting_started_story(self):
        """Test that stories started but not progressing are detected as rotting."""
        story = Story.objects.create(
            title="Stalled Story",
            goal="Test goal",
            workitems="Test workitems",
            started=timezone.now() - timedelta(days=20)  # Started 20 days ago
        )
        
        response = self.client.get(reverse('backlog:dashboard'))
        rotting = [item['story'].id for item in response.context['rotting_stories']]
        
        self.assertIn(story.id, rotting)

    def test_rotting_planned_story(self):
        """Test that stories planned but not started are detected as rotting."""
        story = Story.objects.create(
            title="Planned Story",
            goal="Test goal",
            workitems="Test workitems",
            planned=timezone.now() - timedelta(days=35)  # Planned 35 days ago
        )
        
        response = self.client.get(reverse('backlog:dashboard'))
        rotting = [item['story'].id for item in response.context['rotting_stories']]
        
        self.assertIn(story.id, rotting)

    def test_review_required_detection(self):
        """Test that stories flagged for review are detected."""
        story = Story.objects.create(
            title="Review Story",
            goal="Test goal",
            workitems="Test workitems",
            review_required=True
        )
        
        response = self.client.get(reverse('backlog:dashboard'))
        review_required = [item['story'].id for item in response.context['review_required']]
        
        self.assertIn(story.id, review_required)

    def test_archived_stories_excluded(self):
        """Test that archived stories are excluded from the dashboard."""
        story = Story.objects.create(
            title="Archived Story",
            archived=True
        )
        
        response = self.client.get(reverse('backlog:dashboard'))
        
        # Check all lists
        all_story_ids = set()
        for item in response.context['needs_scoring']:
            all_story_ids.add(item['story'].id)
        for item in response.context['needs_refinement']:
            all_story_ids.add(item['story'].id)
        for item in response.context['rotting_stories']:
            all_story_ids.add(item['story'].id)
        for item in response.context['review_required']:
            all_story_ids.add(item['story'].id)
        
        self.assertNotIn(story.id, all_story_ids)

    def test_dashboard_thresholds_present(self):
        """Test that rotation thresholds are passed to template."""
        response = self.client.get(reverse('backlog:dashboard'))
        thresholds = response.context['thresholds']
        
        self.assertIn('started_days', thresholds)
        self.assertIn('planned_days', thresholds)
        self.assertIn('blocked_days', thresholds)
        
        # Verify default values
        self.assertEqual(thresholds['started_days'], 14)
        self.assertEqual(thresholds['planned_days'], 30)
        self.assertEqual(thresholds['blocked_days'], 7)

    def test_dashboard_healthy_count(self):
        """Test that healthy count is calculated correctly."""
        # Create a story with all factors scored (auto-scored with 0)
        # and with goal/workitems set (so not in idea status)
        story = Story.objects.create(
            title="Healthy Story",
            goal="Clear goal",
            workitems="Work items",
            review_required=False
        )
        
        # Update any default 0 scores to meaningful values
        for score in story.scores.all():
            score.answer = self.vf_answer_5
            score.save()
        for score in story.cost_scores.all():
            score.answer = self.cf_answer_2
            score.save()
        
        response = self.client.get(reverse('backlog:dashboard'))
        
        # The healthy story should be counted
        self.assertGreaterEqual(response.context['summary']['healthy'], 1)

    def test_rotting_stories_sorted_by_days(self):
        """Test that rotting stories are sorted by days descending."""
        # Create stories with different rotting durations
        Story.objects.create(
            title="Less Stale",
            goal="Goal",
            workitems="Work",
            started=timezone.now() - timedelta(days=15)
        )
        Story.objects.create(
            title="More Stale",
            goal="Goal",
            workitems="Work",
            started=timezone.now() - timedelta(days=30)
        )
        
        response = self.client.get(reverse('backlog:dashboard'))
        rotting = response.context['rotting_stories']
        
        if len(rotting) >= 2:
            # Most stale should come first
            self.assertGreaterEqual(rotting[0]['days'], rotting[-1]['days'])

    def test_housekeeping_context_present(self):
        """Test that housekeeping data is in dashboard context."""
        response = self.client.get(reverse('backlog:dashboard'))
        self.assertIn('housekeeping', response.context)
        housekeeping = response.context['housekeeping']
        self.assertIn('issues', housekeeping)
        self.assertIn('total_issues', housekeeping)

    def test_housekeeping_orphan_value_scores_cleanup(self):
        """Test cleanup of orphaned value factor scores.
        
        Note: Since Django's CASCADE delete normally prevents orphans, we use
        raw SQL to simulate database corruption/manual edits that could cause orphans.
        """
        from django.db import connection
        
        # Create a story and score it
        story = Story.objects.create(
            title="Story to Delete",
            goal="Goal",
            workitems="Work"
        )
        story_id = story.id
        
        # Score the story
        score = story.scores.first()
        score.answer = self.vf_answer_5
        score.save()
        
        # Verify score exists
        self.assertTrue(StoryValueFactorScore.objects.filter(story_id=story_id).exists())
        
        # Use raw SQL to delete story without cascade (simulate DB corruption)
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA foreign_keys=OFF")
            cursor.execute("DELETE FROM backlog_story WHERE id = %s", [story_id])
            cursor.execute("PRAGMA foreign_keys=ON")
        
        # Verify orphan score exists
        orphan_count = StoryValueFactorScore.objects.filter(story_id=story_id).count()
        self.assertGreater(orphan_count, 0)
        
        # Perform cleanup
        response = self.client.post(
            reverse('backlog:dashboard'),
            {'action': 'cleanup_orphan_value_scores'}
        )
        self.assertRedirects(response, reverse('backlog:dashboard'))
        
        # Verify orphan scores are cleaned up
        self.assertEqual(
            StoryValueFactorScore.objects.filter(story_id=story_id).count(),
            0
        )
        
        # Clean up any remaining orphan cost scores to avoid teardown issues
        StoryCostFactorScore.objects.filter(story_id=story_id).delete()

    def test_housekeeping_orphan_cost_scores_cleanup(self):
        """Test cleanup of orphaned cost factor scores.
        
        Note: Since Django's CASCADE delete normally prevents orphans, we use
        raw SQL to simulate database corruption/manual edits that could cause orphans.
        """
        from django.db import connection
        
        # Create a story and score it
        story = Story.objects.create(
            title="Story to Delete",
            goal="Goal",
            workitems="Work"
        )
        story_id = story.id
        
        # Score the story
        score = story.cost_scores.first()
        score.answer = self.cf_answer_2
        score.save()
        
        # Verify score exists
        self.assertTrue(StoryCostFactorScore.objects.filter(story_id=story_id).exists())
        
        # Use raw SQL to delete story without cascade (simulate DB corruption)
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA foreign_keys=OFF")
            cursor.execute("DELETE FROM backlog_story WHERE id = %s", [story_id])
            cursor.execute("PRAGMA foreign_keys=ON")
        
        # Verify orphan score exists
        orphan_count = StoryCostFactorScore.objects.filter(story_id=story_id).count()
        self.assertGreater(orphan_count, 0)
        
        # Perform cleanup
        response = self.client.post(
            reverse('backlog:dashboard'),
            {'action': 'cleanup_orphan_cost_scores'}
        )
        self.assertRedirects(response, reverse('backlog:dashboard'))
        
        # Verify orphan scores are cleaned up
        self.assertEqual(
            StoryCostFactorScore.objects.filter(story_id=story_id).count(),
            0
        )
        
        # Clean up any remaining orphan value scores to avoid teardown issues
        StoryValueFactorScore.objects.filter(story_id=story_id).delete()

    def test_housekeeping_orphan_dependencies_cleanup(self):
        """Test cleanup of orphaned dependencies.
        
        Note: Since Django's CASCADE delete normally prevents orphans, we use
        raw SQL to simulate database corruption/manual edits that could cause orphans.
        """
        from django.db import connection
        
        # Create two stories
        story1 = Story.objects.create(
            title="Story 1",
            goal="Goal",
            workitems="Work"
        )
        story2 = Story.objects.create(
            title="Story 2",
            goal="Goal",
            workitems="Work"
        )
        story2_id = story2.id
        
        # Create a dependency
        dep = StoryDependency.objects.create(
            story=story1,
            depends_on=story2
        )
        
        # Use raw SQL to delete story2 without cascade (simulate DB corruption)
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA foreign_keys=OFF")
            cursor.execute("DELETE FROM backlog_story WHERE id = %s", [story2_id])
            cursor.execute("PRAGMA foreign_keys=ON")
        
        # Verify orphan dependency exists
        self.assertTrue(StoryDependency.objects.filter(depends_on_id=story2_id).exists())
        
        # Perform cleanup
        response = self.client.post(
            reverse('backlog:dashboard'),
            {'action': 'cleanup_orphan_dependencies'}
        )
        self.assertRedirects(response, reverse('backlog:dashboard'))
        
        # Verify orphan dependency is cleaned up
        self.assertFalse(StoryDependency.objects.filter(depends_on_id=story2_id).exists())
        
        # Clean up any remaining orphan scores to avoid teardown issues
        StoryValueFactorScore.objects.filter(story_id=story2_id).delete()
        StoryCostFactorScore.objects.filter(story_id=story2_id).delete()

    def test_housekeeping_orphan_history_cleanup(self):
        """Test cleanup of orphaned history entries.
        
        Note: Since Django's CASCADE delete normally prevents orphans, we use
        raw SQL to simulate database corruption/manual edits that could cause orphans.
        """
        from django.db import connection
        
        # Create a story
        story = Story.objects.create(
            title="Story to Delete",
            goal="Goal",
            workitems="Work"
        )
        story_id = story.id
        
        # Create history entry
        StoryHistory.objects.create(
            story=story,
            field_name='title',
            old_value='Old Title',
            new_value='Story to Delete'
        )
        
        # Verify history exists
        self.assertTrue(StoryHistory.objects.filter(story_id=story_id).exists())
        
        # Use raw SQL to delete story without cascade (simulate DB corruption)
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA foreign_keys=OFF")
            cursor.execute("DELETE FROM backlog_story WHERE id = %s", [story_id])
            cursor.execute("PRAGMA foreign_keys=ON")
        
        # Verify orphan history exists
        self.assertTrue(StoryHistory.objects.filter(story_id=story_id).exists())
        
        # Perform cleanup
        response = self.client.post(
            reverse('backlog:dashboard'),
            {'action': 'cleanup_orphan_history'}
        )
        self.assertRedirects(response, reverse('backlog:dashboard'))
        
        # Verify orphan history is cleaned up
        self.assertFalse(StoryHistory.objects.filter(story_id=story_id).exists())
        
        # Clean up any remaining orphan scores to avoid teardown issues
        StoryValueFactorScore.objects.filter(story_id=story_id).delete()
        StoryCostFactorScore.objects.filter(story_id=story_id).delete()

    def test_housekeeping_summary_count(self):
        """Test that housekeeping count appears in summary."""
        response = self.client.get(reverse('backlog:dashboard'))
        summary = response.context['summary']
        self.assertIn('housekeeping', summary)

    def test_statistics_context_present(self):
        """Test that statistics data is in dashboard context."""
        response = self.client.get(reverse('backlog:dashboard'))
        self.assertIn('statistics', response.context)
        statistics = response.context['statistics']
        
        # Check all expected keys
        self.assertIn('total_stories', statistics)
        self.assertIn('active_stories', statistics)
        self.assertIn('archived_stories', statistics)
        self.assertIn('status_counts', statistics)
        self.assertIn('recently_completed', statistics)
        self.assertIn('oldest_open', statistics)
        self.assertIn('stories_with_deps', statistics)
        self.assertIn('blocking_stories', statistics)

    def test_statistics_counts_correct(self):
        """Test that statistics counts are accurate."""
        # Create some additional stories
        story1 = Story.objects.create(
            title="Active Story",
            goal="Goal",
            workitems="Work"
        )
        story2 = Story.objects.create(
            title="Archived Story",
            archived=True
        )
        
        response = self.client.get(reverse('backlog:dashboard'))
        statistics = response.context['statistics']
        
        # Check that counts reflect the data
        self.assertEqual(statistics['archived_stories'], 1)
        self.assertGreaterEqual(statistics['active_stories'], 1)

    def test_review_required_shown_first(self):
        """Test that review required section appears before other sections in template."""
        response = self.client.get(reverse('backlog:dashboard'))
        content = response.content.decode()
        
        # Find positions of section headers
        review_pos = content.find('👀 Review Required')
        scoring_pos = content.find('🎯 Stories Needing Scoring')
        
        # Review should appear before scoring
        self.assertTrue(review_pos > 0)
        self.assertTrue(scoring_pos > 0)
        self.assertLess(review_pos, scoring_pos)


class LabelFilterTests(BaseTestCase):
    """Tests for the label filter functionality across views."""

    def setUp(self):
        """Set up test data including labels."""
        super().setUp()
        from .models import LabelCategory, Label
        
        # Create label categories
        self.category1 = LabelCategory.objects.create(
            name="Feature Area",
            color="#FF5733",
            icon="💻"
        )
        self.category2 = LabelCategory.objects.create(
            name="Priority",
            color="#33FF57",
            icon="🔥"
        )
        
        # Create labels
        self.label1 = Label.objects.create(
            category=self.category1,
            name="Frontend"
        )
        self.label2 = Label.objects.create(
            category=self.category1,
            name="Backend"
        )
        self.label3 = Label.objects.create(
            category=self.category2,
            name="High Priority"
        )
        
        # Create stories with different labels
        self.story_frontend = Story.objects.create(
            title="Frontend Story",
            goal="Build frontend",
            workitems="UI work"
        )
        self.story_frontend.labels.add(self.label1)
        
        self.story_backend = Story.objects.create(
            title="Backend Story",
            goal="Build backend",
            workitems="API work"
        )
        self.story_backend.labels.add(self.label2)
        
        self.story_both = Story.objects.create(
            title="Full Stack Story",
            goal="Build everything",
            workitems="All work"
        )
        self.story_both.labels.add(self.label1, self.label2, self.label3)
        
        self.story_no_labels = Story.objects.create(
            title="Unlabeled Story",
            goal="No labels",
            workitems="No work"
        )

    def test_stories_list_no_filter(self):
        """Test stories list without label filter shows all stories."""
        response = self.client.get(reverse('backlog:stories'))
        self.assertEqual(response.status_code, 200)
        # Should show all 4 stories
        stories = [s['story'] for s in response.context['stories']]
        self.assertEqual(len(stories), 4)

    def test_stories_list_single_label_filter(self):
        """Test filtering by a single label."""
        response = self.client.get(reverse('backlog:stories'), {'labels': str(self.label1.id)})
        self.assertEqual(response.status_code, 200)
        stories = [s['story'] for s in response.context['stories']]
        # Should show Frontend Story and Full Stack Story
        self.assertEqual(len(stories), 2)
        story_titles = {s.title for s in stories}
        self.assertIn("Frontend Story", story_titles)
        self.assertIn("Full Stack Story", story_titles)

    def test_stories_list_multiple_labels_filter_and(self):
        """Test filtering by multiple labels uses AND logic."""
        # Filter by both Frontend and High Priority labels
        # Only Full Stack Story has BOTH labels
        labels_param = f"{self.label1.id},{self.label3.id}"
        response = self.client.get(reverse('backlog:stories'), {'labels': labels_param})
        self.assertEqual(response.status_code, 200)
        stories = [s['story'] for s in response.context['stories']]
        # Should only show Full Stack Story (has both Frontend and High Priority)
        self.assertEqual(len(stories), 1)
        self.assertEqual(stories[0].title, "Full Stack Story")

    def test_stories_list_label_filter_context(self):
        """Test that label filter context is passed to template."""
        response = self.client.get(reverse('backlog:stories'))
        self.assertIn('label_categories', response.context)
        self.assertIn('selected_labels', response.context)
        self.assertIn('selected_labels_objects', response.context)
        self.assertIn('labels_param', response.context)
        # Should have 2 categories
        self.assertEqual(len(response.context['label_categories']), 2)

    def test_selected_labels_objects_populated(self):
        """Test that selected_labels_objects contains Label objects with category info."""
        # Filter by frontend label
        response = self.client.get(reverse('backlog:stories'), {'labels': str(self.label1.id)})
        self.assertEqual(response.status_code, 200)
        selected_objs = response.context['selected_labels_objects']
        self.assertEqual(len(selected_objs), 1)
        self.assertEqual(selected_objs[0].name, "Frontend")
        self.assertEqual(selected_objs[0].category.name, "Feature Area")

    def test_report_view_label_filter(self):
        """Test label filtering on report view."""
        response = self.client.get(reverse('backlog:report'), {'labels': str(self.label1.id)})
        self.assertEqual(response.status_code, 200)
        rows = response.context['rows']
        # Should show Frontend Story and Full Stack Story
        self.assertEqual(len(rows), 2)
        story_titles = {r['story'].title for r in rows}
        self.assertIn("Frontend Story", story_titles)
        self.assertIn("Full Stack Story", story_titles)

    def test_kanban_view_label_filter(self):
        """Test label filtering on kanban view."""
        # Make some stories ready for kanban
        self.story_frontend.status = 'ready'
        self.story_frontend.save()
        self.story_backend.status = 'ready'
        self.story_backend.save()
        
        response = self.client.get(reverse('backlog:kanban'), {'labels': str(self.label1.id)})
        self.assertEqual(response.status_code, 200)
        self.assertIn('label_categories', response.context)
        self.assertIn('selected_labels', response.context)

    def test_wbs_view_label_filter(self):
        """Test label filtering on WBS view."""
        response = self.client.get(reverse('backlog:wbs'), {'labels': str(self.label1.id)})
        self.assertEqual(response.status_code, 200)
        stories = response.context['stories']
        # Should show only stories with Frontend label
        self.assertEqual(len(stories), 2)

    def test_invalid_labels_param_handled(self):
        """Test that invalid labels parameter is handled gracefully."""
        # Test with invalid format
        response = self.client.get(reverse('backlog:stories'), {'labels': 'abc,xyz'})
        self.assertEqual(response.status_code, 200)
        # Should show all stories (invalid params ignored)
        stories = [s['story'] for s in response.context['stories']]
        self.assertEqual(len(stories), 4)

    def test_labels_filter_preserves_other_params(self):
        """Test that label filter works with other query parameters."""
        # To have computed_status = 'ready', story needs all text fields and scores set
        # Mark the frontend story as planned (which sets computed_status directly)
        from django.utils import timezone
        self.story_frontend.planned = timezone.now()
        self.story_frontend.save()
        
        # Filter by label AND status
        response = self.client.get(reverse('backlog:stories'), {
            'labels': str(self.label1.id),
            'status': 'planned'
        })
        self.assertEqual(response.status_code, 200)
        stories = [s['story'] for s in response.context['stories']]
        # Only Frontend Story should match (has label1 and status=planned)
        # Full Stack Story also has label1 but its computed_status is 'idea'
        self.assertEqual(len(stories), 1)
        self.assertEqual(stories[0].title, "Frontend Story")

    def test_empty_labels_param_shows_all(self):
        """Test that empty labels parameter shows all stories."""
        response = self.client.get(reverse('backlog:stories'), {'labels': ''})
        self.assertEqual(response.status_code, 200)
        stories = [s['story'] for s in response.context['stories']]


class BulkActionsTests(BaseTestCase):
    """Test cases for bulk actions on stories."""

    def setUp(self):
        super().setUp()
        # Create test stories
        self.story1 = Story.objects.create(title="Story 1", goal="Goal 1", workitems="Work 1")
        self.story2 = Story.objects.create(title="Story 2", goal="Goal 2", workitems="Work 2")
        self.story3 = Story.objects.create(title="Story 3", goal="Goal 3", workitems="Work 3")
        
        # Create a label category and label for testing
        self.bulk_category = LabelCategory.objects.create(name="Bulk Test", color="#ff0000")
        self.bulk_label = Label.objects.create(category=self.bulk_category, name="Bulk Label")

    def test_bulk_archive_stories(self):
        """Test bulk archiving multiple stories."""
        response = self.client.post(reverse('backlog:stories_bulk_action'), {
            'action': 'archive',
            'story_ids': f'{self.story1.id},{self.story2.id}',
            'next': reverse('backlog:stories'),
        })
        self.assertEqual(response.status_code, 302)
        
        self.story1.refresh_from_db()
        self.story2.refresh_from_db()
        self.story3.refresh_from_db()
        
        self.assertTrue(self.story1.archived)
        self.assertTrue(self.story2.archived)
        self.assertFalse(self.story3.archived)

    def test_bulk_unarchive_stories(self):
        """Test bulk unarchiving multiple stories."""
        self.story1.archived = True
        self.story1.save()
        self.story2.archived = True
        self.story2.save()
        
        response = self.client.post(reverse('backlog:stories_bulk_action'), {
            'action': 'unarchive',
            'story_ids': f'{self.story1.id},{self.story2.id}',
            'next': reverse('backlog:stories'),
        })
        self.assertEqual(response.status_code, 302)
        
        self.story1.refresh_from_db()
        self.story2.refresh_from_db()
        
        self.assertFalse(self.story1.archived)
        self.assertFalse(self.story2.archived)

    def test_bulk_set_review_required(self):
        """Test bulk setting review required flag."""
        response = self.client.post(reverse('backlog:stories_bulk_action'), {
            'action': 'set_review',
            'story_ids': f'{self.story1.id},{self.story2.id}',
            'next': reverse('backlog:stories'),
        })
        self.assertEqual(response.status_code, 302)
        
        self.story1.refresh_from_db()
        self.story2.refresh_from_db()
        self.story3.refresh_from_db()
        
        self.assertTrue(self.story1.review_required)
        self.assertTrue(self.story2.review_required)
        self.assertFalse(self.story3.review_required)

    def test_bulk_clear_review(self):
        """Test bulk clearing review required flag."""
        self.story1.review_required = True
        self.story1.save()
        self.story2.review_required = True
        self.story2.save()
        
        response = self.client.post(reverse('backlog:stories_bulk_action'), {
            'action': 'clear_review',
            'story_ids': f'{self.story1.id},{self.story2.id}',
            'next': reverse('backlog:stories'),
        })
        self.assertEqual(response.status_code, 302)
        
        self.story1.refresh_from_db()
        self.story2.refresh_from_db()
        
        self.assertFalse(self.story1.review_required)
        self.assertFalse(self.story2.review_required)

    def test_bulk_set_blocked(self):
        """Test bulk setting blocked reason."""
        response = self.client.post(reverse('backlog:stories_bulk_action'), {
            'action': 'set_blocked',
            'story_ids': f'{self.story1.id},{self.story2.id}',
            'blocked_reason': 'Waiting for API',
            'next': reverse('backlog:stories'),
        })
        self.assertEqual(response.status_code, 302)
        
        self.story1.refresh_from_db()
        self.story2.refresh_from_db()
        self.story3.refresh_from_db()
        
        self.assertEqual(self.story1.blocked, 'Waiting for API')
        self.assertEqual(self.story2.blocked, 'Waiting for API')
        self.assertEqual(self.story3.blocked, '')

    def test_bulk_add_labels(self):
        """Test bulk adding labels to stories."""
        response = self.client.post(reverse('backlog:stories_bulk_action'), {
            'action': 'add_labels',
            'story_ids': f'{self.story1.id},{self.story2.id}',
            'label_ids': str(self.bulk_label.id),
            'next': reverse('backlog:stories'),
        })
        self.assertEqual(response.status_code, 302)
        
        self.assertTrue(self.story1.labels.filter(id=self.bulk_label.id).exists())
        self.assertTrue(self.story2.labels.filter(id=self.bulk_label.id).exists())
        self.assertFalse(self.story3.labels.filter(id=self.bulk_label.id).exists())

    def test_bulk_delete_stories(self):
        """Test bulk deleting stories."""
        story1_id = self.story1.id
        story2_id = self.story2.id
        
        response = self.client.post(reverse('backlog:stories_bulk_action'), {
            'action': 'delete',
            'story_ids': f'{story1_id},{story2_id}',
            'next': reverse('backlog:stories'),
        })
        self.assertEqual(response.status_code, 302)
        
        self.assertFalse(Story.objects.filter(id=story1_id).exists())
        self.assertFalse(Story.objects.filter(id=story2_id).exists())
        self.assertTrue(Story.objects.filter(id=self.story3.id).exists())

    def test_bulk_action_no_stories_selected(self):
        """Test bulk action with no stories selected."""
        response = self.client.post(reverse('backlog:stories_bulk_action'), {
            'action': 'archive',
            'story_ids': '',
            'next': reverse('backlog:stories'),
        })
        self.assertEqual(response.status_code, 302)
        # Stories should remain unchanged
        self.story1.refresh_from_db()
        self.assertFalse(self.story1.archived)