"""
Comprehensive regression tests for the WoS (WSJF on Steroids) backlog application.

These tests cover:
- Model creation and relationships
- computed_status property logic
- Epic and Story CRUD operations
- Archiving functionality with cascade
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
    Epic,
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
)


class BaseTestCase(TestCase):
    """Base test case with common setup for all tests."""

    def setUp(self):
        """Set up test data used across multiple tests."""
        self.client = Client()
        
        # Create an epic
        self.epic = Epic.objects.create(
            title="Test Epic",
            description="Test Epic Description"
        )
        
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


class EpicModelTests(BaseTestCase):
    """Tests for Epic model."""

    def test_epic_creation(self):
        """Test epic is created with correct fields."""
        self.assertEqual(self.epic.title, "Test Epic")
        self.assertEqual(self.epic.description, "Test Epic Description")
        self.assertFalse(self.epic.archived)
        self.assertIsNotNone(self.epic.created_at)
        self.assertIsNotNone(self.epic.updated_at)

    def test_epic_str(self):
        """Test epic string representation."""
        self.assertEqual(str(self.epic), "Test Epic")

    def test_epic_archive(self):
        """Test epic can be archived."""
        self.epic.archived = True
        self.epic.save()
        self.epic.refresh_from_db()
        self.assertTrue(self.epic.archived)


class StoryModelTests(BaseTestCase):
    """Tests for Story model."""

    def test_story_creation(self):
        """Test story is created with correct fields."""
        story = Story.objects.create(
            epic=self.epic,
            title="Test Story",
            goal="Test Goal",
            workitems="Test Workitems"
        )
        self.assertEqual(story.title, "Test Story")
        self.assertEqual(story.goal, "Test Goal")
        self.assertEqual(story.workitems, "Test Workitems")
        self.assertEqual(story.epic, self.epic)
        self.assertFalse(story.archived)
        self.assertFalse(story.review_required)

    def test_story_str(self):
        """Test story string representation."""
        story = Story.objects.create(epic=self.epic, title="My Story")
        self.assertEqual(str(story), "My Story")

    def test_story_status_auto_update_to_refined(self):
        """Test status updates to 'refined' when goal and workitems are set."""
        story = Story.objects.create(
            epic=self.epic,
            title="Test Story",
            goal="Has goal",
            workitems="Has workitems"
        )
        self.assertEqual(story.status, Story.STATUS_REFINED)

    def test_story_status_remains_new_without_goal(self):
        """Test status remains 'new' when goal is missing."""
        story = Story.objects.create(
            epic=self.epic,
            title="Test Story",
            workitems="Has workitems"
        )
        self.assertEqual(story.status, Story.STATUS_NEW)

    def test_story_status_remains_new_without_workitems(self):
        """Test status remains 'new' when workitems is missing."""
        story = Story.objects.create(
            epic=self.epic,
            title="Test Story",
            goal="Has goal"
        )
        self.assertEqual(story.status, Story.STATUS_NEW)


class ComputedStatusTests(BaseTestCase):
    """Tests for Story.computed_status property - critical for status display."""

    def test_computed_status_idea_missing_title(self):
        """Test computed_status is 'idea' when title is missing."""
        story = Story.objects.create(epic=self.epic, title="")
        self.assertEqual(story.computed_status, "idea")

    def test_computed_status_idea_missing_goal(self):
        """Test computed_status is 'idea' when goal is missing."""
        story = Story.objects.create(
            epic=self.epic,
            title="Has Title",
            workitems="Has workitems"
        )
        self.assertEqual(story.computed_status, "idea")

    def test_computed_status_idea_missing_workitems(self):
        """Test computed_status is 'idea' when workitems is missing."""
        story = Story.objects.create(
            epic=self.epic,
            title="Has Title",
            goal="Has goal"
        )
        self.assertEqual(story.computed_status, "idea")

    def test_computed_status_idea_missing_scores(self):
        """Test computed_status is 'idea' when scores are missing."""
        story = Story.objects.create(
            epic=self.epic,
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
            epic=self.epic,
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
            epic=self.epic,
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
            epic=self.epic,
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
            epic=self.epic,
            title="Has Title",
            planned=timezone.now(),
            started=timezone.now(),
            finished=timezone.now()
        )
        self.assertEqual(story.computed_status, "done")

    def test_computed_status_blocked_priority(self):
        """Test blocked status takes priority over all others."""
        story = Story.objects.create(
            epic=self.epic,
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
            epic=self.epic,
            title="Has Title",
            started=timezone.now(),
            finished=timezone.now()
        )
        self.assertEqual(story.computed_status, "done")

    def test_computed_status_started_priority_over_planned(self):
        """Test started status takes priority over planned."""
        story = Story.objects.create(
            epic=self.epic,
            title="Has Title",
            planned=timezone.now(),
            started=timezone.now()
        )
        self.assertEqual(story.computed_status, "started")


class StoryHistoryTests(BaseTestCase):
    """Tests for StoryHistory model and tracking."""

    def test_story_history_creation(self):
        """Test history entry is created correctly."""
        story = Story.objects.create(epic=self.epic, title="Test Story")
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
        story = Story.objects.create(epic=self.epic, title="Test Story")
        h1 = StoryHistory.objects.create(story=story, field_name="First")
        h2 = StoryHistory.objects.create(story=story, field_name="Second")
        
        history = list(story.history.all())
        self.assertEqual(history[0].field_name, "Second")
        self.assertEqual(history[1].field_name, "First")


class StoryDependencyTests(BaseTestCase):
    """Tests for StoryDependency model."""

    def test_dependency_creation(self):
        """Test dependency is created correctly."""
        story1 = Story.objects.create(epic=self.epic, title="Story 1")
        story2 = Story.objects.create(epic=self.epic, title="Story 2")
        
        dep = StoryDependency.objects.create(story=story1, depends_on=story2)
        self.assertEqual(dep.story, story1)
        self.assertEqual(dep.depends_on, story2)

    def test_dependency_unique_constraint(self):
        """Test duplicate dependencies are not allowed."""
        story1 = Story.objects.create(epic=self.epic, title="Story 1")
        story2 = Story.objects.create(epic=self.epic, title="Story 2")
        
        StoryDependency.objects.create(story=story1, depends_on=story2)
        
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            StoryDependency.objects.create(story=story1, depends_on=story2)

    def test_dependency_related_names(self):
        """Test related names for dependencies and dependents."""
        story1 = Story.objects.create(epic=self.epic, title="Story 1")
        story2 = Story.objects.create(epic=self.epic, title="Story 2")
        
        StoryDependency.objects.create(story=story1, depends_on=story2)
        
        # story1 depends on story2
        self.assertEqual(story1.dependencies.count(), 1)
        self.assertEqual(story1.dependencies.first().depends_on, story2)
        
        # story2 has story1 as a dependent
        self.assertEqual(story2.dependents.count(), 1)
        self.assertEqual(story2.dependents.first().story, story1)


class EpicViewTests(BaseTestCase):
    """Tests for Epic-related views."""

    def test_overview_page_loads(self):
        """Test overview page loads successfully."""
        response = self.client.get(reverse('backlog:index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Epic")

    def test_overview_create_epic(self):
        """Test creating an epic via overview POST."""
        response = self.client.post(reverse('backlog:index'), {
            'action': 'create_epic',
            'title': 'New Epic',
            'description': 'New Description'
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Epic.objects.filter(title='New Epic').exists())

    def test_overview_edit_epic(self):
        """Test editing an epic via overview POST."""
        response = self.client.post(reverse('backlog:index'), {
            'action': 'edit_epic',
            'epic_id': self.epic.pk,
            'title': 'Updated Epic',
            'description': 'Updated Description'
        })
        self.assertEqual(response.status_code, 302)
        self.epic.refresh_from_db()
        self.assertEqual(self.epic.title, 'Updated Epic')

    def test_overview_delete_epic(self):
        """Test deleting an epic via overview POST."""
        response = self.client.post(reverse('backlog:index'), {
            'action': 'delete_epic',
            'epic_id': self.epic.pk
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Epic.objects.filter(pk=self.epic.pk).exists())

    def test_overview_archive_epic(self):
        """Test archiving an epic via overview POST."""
        story = Story.objects.create(epic=self.epic, title="Test Story")
        
        response = self.client.post(reverse('backlog:index'), {
            'action': 'archive_epic',
            'epic_id': self.epic.pk
        })
        self.assertEqual(response.status_code, 302)
        self.epic.refresh_from_db()
        story.refresh_from_db()
        self.assertTrue(self.epic.archived)
        self.assertTrue(story.archived)  # Cascade archive to stories

    def test_overview_unarchive_epic(self):
        """Test unarchiving an epic via overview POST."""
        self.epic.archived = True
        self.epic.save()
        
        response = self.client.post(reverse('backlog:index') + '?archived=1', {
            'action': 'unarchive_epic',
            'epic_id': self.epic.pk
        })
        self.assertEqual(response.status_code, 302)
        self.epic.refresh_from_db()
        self.assertFalse(self.epic.archived)

    def test_overview_unarchive_epic_does_not_unarchive_stories(self):
        """Test unarchiving an epic does NOT automatically unarchive its stories."""
        # Archive the epic and its stories
        story = Story.objects.create(epic=self.epic, title="Archived Story")
        self.epic.archived = True
        self.epic.save()
        story.archived = True
        story.save()
        
        # Unarchive the epic
        response = self.client.post(reverse('backlog:index') + '?archived=1', {
            'action': 'unarchive_epic',
            'epic_id': self.epic.pk
        })
        self.assertEqual(response.status_code, 302)
        self.epic.refresh_from_db()
        story.refresh_from_db()
        
        # Epic should be unarchived but story should remain archived
        self.assertFalse(self.epic.archived)
        self.assertTrue(story.archived)

    def test_overview_shows_unfinished_count_for_confirmation(self):
        """Test that overview page shows unfinished_count for archive confirmation dialog."""
        # Create stories with different statuses
        story_done = Story.objects.create(
            epic=self.epic, 
            title="Done Story",
            finished=timezone.now()
        )
        story_idea = Story.objects.create(
            epic=self.epic,
            title="Idea Story"
        )
        story_started = Story.objects.create(
            epic=self.epic,
            title="Started Story",
            started=timezone.now()
        )
        
        response = self.client.get(reverse('backlog:index'))
        self.assertEqual(response.status_code, 200)
        
        # Find the epic in context and check unfinished_count
        epics_data = response.context['epics']
        test_epic_data = next((e for e in epics_data if e['epic'].pk == self.epic.pk), None)
        self.assertIsNotNone(test_epic_data)
        
        # Should have 2 unfinished stories (idea + started, not done)
        self.assertEqual(test_epic_data['unfinished_count'], 2)

    def test_overview_unfinished_count_zero_when_all_done(self):
        """Test unfinished_count is 0 when all stories are done."""
        Story.objects.create(
            epic=self.epic,
            title="Done Story 1",
            finished=timezone.now()
        )
        Story.objects.create(
            epic=self.epic,
            title="Done Story 2",
            finished=timezone.now()
        )
        
        response = self.client.get(reverse('backlog:index'))
        epics_data = response.context['epics']
        test_epic_data = next((e for e in epics_data if e['epic'].pk == self.epic.pk), None)
        
        self.assertEqual(test_epic_data['unfinished_count'], 0)

    def test_overview_unfinished_count_excludes_archived_stories(self):
        """Test unfinished_count excludes archived stories."""
        # Create an unfinished but archived story - should not count
        Story.objects.create(
            epic=self.epic,
            title="Archived Idea",
            archived=True
        )
        # Create an unfinished non-archived story - should count
        Story.objects.create(
            epic=self.epic,
            title="Active Idea"
        )
        
        response = self.client.get(reverse('backlog:index'))
        epics_data = response.context['epics']
        test_epic_data = next((e for e in epics_data if e['epic'].pk == self.epic.pk), None)
        
        # Only the active unfinished story should be counted
        self.assertEqual(test_epic_data['unfinished_count'], 1)

    def test_overview_filter_archived(self):
        """Test filtering archived epics."""
        self.epic.archived = True
        self.epic.save()
        
        active_epic = Epic.objects.create(title="Active Epic XYZ123")
        
        # Non-archived view - should show active epic, not archived one
        response = self.client.get(reverse('backlog:index'))
        # The archived epic should not appear in the main list
        # Check for the epic title in the epics list context
        epics_in_response = [e['epic'].title for e in response.context['epics']]
        self.assertNotIn("Test Epic", epics_in_response)
        self.assertIn("Active Epic XYZ123", epics_in_response)
        
        # Archived view - should show archived epic, not active one
        response = self.client.get(reverse('backlog:index') + '?archived=1')
        epics_in_response = [e['epic'].title for e in response.context['epics']]
        self.assertIn("Test Epic", epics_in_response)
        self.assertNotIn("Active Epic XYZ123", epics_in_response)

    def test_create_epic_page(self):
        """Test create epic page loads."""
        response = self.client.get(reverse('backlog:create_epic'))
        self.assertEqual(response.status_code, 200)

    def test_create_epic_post(self):
        """Test creating epic via dedicated page."""
        response = self.client.post(reverse('backlog:create_epic'), {
            'title': 'Page Epic',
            'description': 'Created from page'
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Epic.objects.filter(title='Page Epic').exists())

    def test_edit_epic_page(self):
        """Test edit epic page loads."""
        response = self.client.get(reverse('backlog:edit_epic', args=[self.epic.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Epic")


class StoryViewTests(BaseTestCase):
    """Tests for Story-related views."""

    def test_stories_page_loads(self):
        """Test stories list page loads."""
        Story.objects.create(epic=self.epic, title="Test Story")
        response = self.client.get(reverse('backlog:stories'))
        self.assertEqual(response.status_code, 200)

    def test_stories_filter_by_epic(self):
        """Test filtering stories by epic."""
        epic2 = Epic.objects.create(title="Epic 2")
        story1 = Story.objects.create(epic=self.epic, title="Story Epic 1")
        story2 = Story.objects.create(epic=epic2, title="Story Epic 2")
        
        response = self.client.get(reverse('backlog:stories') + f'?epic={self.epic.pk}')
        self.assertContains(response, "Story Epic 1")
        self.assertNotContains(response, "Story Epic 2")

    def test_stories_filter_by_status(self):
        """Test filtering stories by computed status."""
        story_idea = Story.objects.create(epic=self.epic, title="Idea Story")
        story_done = Story.objects.create(
            epic=self.epic,
            title="Done Story",
            finished=timezone.now()
        )
        
        response = self.client.get(reverse('backlog:stories') + '?status=done')
        self.assertContains(response, "Done Story")
        self.assertNotContains(response, "Idea Story")

    def test_stories_filter_by_review_required(self):
        """Test filtering stories by review_required."""
        story_needs_review = Story.objects.create(
            epic=self.epic,
            title="Needs Review",
            review_required=True
        )
        story_no_review = Story.objects.create(
            epic=self.epic,
            title="No Review"
        )
        
        response = self.client.get(reverse('backlog:stories') + '?review=yes')
        self.assertContains(response, "Needs Review")
        self.assertNotContains(response, "No Review")

    def test_stories_delete_story(self):
        """Test deleting a story - critical regression test."""
        story = Story.objects.create(epic=self.epic, title="To Delete")
        
        response = self.client.post(reverse('backlog:stories'), {
            'action': 'delete_story',
            'story_id': story.pk
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Story.objects.filter(pk=story.pk).exists())

    def test_stories_archive_story(self):
        """Test archiving a story from list."""
        story = Story.objects.create(epic=self.epic, title="To Archive")
        
        response = self.client.post(reverse('backlog:stories'), {
            'action': 'archive_story',
            'story_id': story.pk
        })
        self.assertEqual(response.status_code, 302)
        story.refresh_from_db()
        self.assertTrue(story.archived)

    def test_stories_toggle_review(self):
        """Test toggling review_required from list."""
        story = Story.objects.create(epic=self.epic, title="Test Story")
        
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
        story = Story.objects.create(epic=self.epic, title="Test Story")
        response = self.client.get(reverse('backlog:refine_story', args=[story.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Story")

    def test_refine_story_title_save(self):
        """Test saving story title - critical regression test (was broken before)."""
        story = Story.objects.create(epic=self.epic, title="Original Title")
        
        response = self.client.post(reverse('backlog:refine_story', args=[story.pk]), {
            'title': 'Updated Title',
            'epic_id': self.epic.pk,
            'goal': 'Test Goal',
            'workitems': 'Test Workitems',
            'blocked': '',
        })
        self.assertEqual(response.status_code, 302)
        story.refresh_from_db()
        self.assertEqual(story.title, 'Updated Title')

    def test_refine_story_goal_save(self):
        """Test saving story goal."""
        story = Story.objects.create(epic=self.epic, title="Test Story")
        
        response = self.client.post(reverse('backlog:refine_story', args=[story.pk]), {
            'title': 'Test Story',
            'epic_id': self.epic.pk,
            'goal': 'New Goal',
            'workitems': '',
            'blocked': '',
        })
        self.assertEqual(response.status_code, 302)
        story.refresh_from_db()
        self.assertEqual(story.goal, 'New Goal')

    def test_refine_story_workitems_save(self):
        """Test saving story workitems."""
        story = Story.objects.create(epic=self.epic, title="Test Story")
        
        response = self.client.post(reverse('backlog:refine_story', args=[story.pk]), {
            'title': 'Test Story',
            'epic_id': self.epic.pk,
            'goal': '',
            'workitems': 'Work item 1\nWork item 2',
            'blocked': '',
        })
        self.assertEqual(response.status_code, 302)
        story.refresh_from_db()
        self.assertEqual(story.workitems, 'Work item 1\nWork item 2')

    def test_refine_story_change_epic(self):
        """Test changing story epic."""
        story = Story.objects.create(epic=self.epic, title="Test Story")
        epic2 = Epic.objects.create(title="Epic 2")
        
        response = self.client.post(reverse('backlog:refine_story', args=[story.pk]), {
            'title': 'Test Story',
            'epic_id': epic2.pk,
            'goal': '',
            'workitems': '',
            'blocked': '',
        })
        self.assertEqual(response.status_code, 302)
        story.refresh_from_db()
        self.assertEqual(story.epic, epic2)

    def test_refine_story_blocked(self):
        """Test setting blocked field."""
        story = Story.objects.create(epic=self.epic, title="Test Story")
        
        response = self.client.post(reverse('backlog:refine_story', args=[story.pk]), {
            'title': 'Test Story',
            'epic_id': self.epic.pk,
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
            epic=self.epic,
            title="Test Story",
            blocked="Was blocked"
        )
        
        response = self.client.post(reverse('backlog:refine_story', args=[story.pk]), {
            'remove_blocked': '1',
        })
        self.assertEqual(response.status_code, 302)
        story.refresh_from_db()
        self.assertEqual(story.blocked, '')

    def test_refine_story_archive(self):
        """Test archiving story from refine page."""
        story = Story.objects.create(epic=self.epic, title="Test Story")
        
        response = self.client.post(reverse('backlog:refine_story', args=[story.pk]), {
            'action': 'archive_story',
        })
        self.assertEqual(response.status_code, 302)
        story.refresh_from_db()
        self.assertTrue(story.archived)

    def test_refine_story_toggle_review(self):
        """Test toggling review_required from refine page."""
        story = Story.objects.create(epic=self.epic, title="Test Story")
        
        response = self.client.post(reverse('backlog:refine_story', args=[story.pk]), {
            'action': 'toggle_review',
        })
        self.assertEqual(response.status_code, 302)
        story.refresh_from_db()
        self.assertTrue(story.review_required)

    def test_refine_story_history_tracked(self):
        """Test that changes are tracked in history."""
        story = Story.objects.create(epic=self.epic, title="Original Title")
        
        response = self.client.post(reverse('backlog:refine_story', args=[story.pk]), {
            'title': 'New Title',
            'epic_id': self.epic.pk,
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
        story = Story.objects.create(epic=self.epic, title="Test Story")
        
        response = self.client.post(reverse('backlog:refine_story', args=[story.pk]), {
            'title': 'Test Story',
            'epic_id': self.epic.pk,
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
        story = Story.objects.create(epic=self.epic, title="Test Story")
        
        response = self.client.post(reverse('backlog:refine_story', args=[story.pk]), {
            'title': 'Test Story',
            'epic_id': self.epic.pk,
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
        story1 = Story.objects.create(epic=self.epic, title="Story 1")
        story2 = Story.objects.create(epic=self.epic, title="Story 2")
        
        response = self.client.post(reverse('backlog:refine_story', args=[story1.pk]), {
            'action': 'add_dependency',
            'dependency_story_id': story2.pk,
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            StoryDependency.objects.filter(story=story1, depends_on=story2).exists()
        )

    def test_refine_story_remove_dependency(self):
        """Test removing a dependency."""
        story1 = Story.objects.create(epic=self.epic, title="Story 1")
        story2 = Story.objects.create(epic=self.epic, title="Story 2")
        dep = StoryDependency.objects.create(story=story1, depends_on=story2)
        
        response = self.client.post(reverse('backlog:refine_story', args=[story1.pk]), {
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
        response = self.client.get(reverse('backlog:create_story_refine'))
        self.assertEqual(response.status_code, 200)

    def test_create_story_success(self):
        """Test successfully creating a new story."""
        response = self.client.post(reverse('backlog:create_story_refine'), {
            'title': 'New Story',
            'epic_id': self.epic.pk,
            'goal': 'Story Goal',
            'workitems': 'Story Workitems',
            'blocked': '',
        })
        self.assertEqual(response.status_code, 302)
        story = Story.objects.get(title='New Story')
        self.assertEqual(story.epic, self.epic)
        self.assertEqual(story.goal, 'Story Goal')
        self.assertEqual(story.workitems, 'Story Workitems')

    def test_create_story_history_created(self):
        """Test that history entry is created for new story."""
        response = self.client.post(reverse('backlog:create_story_refine'), {
            'title': 'New Story',
            'epic_id': self.epic.pk,
            'goal': '',
            'workitems': '',
            'blocked': '',
        })
        story = Story.objects.get(title='New Story')
        history = StoryHistory.objects.filter(story=story, field_name='Story created')
        self.assertTrue(history.exists())

    def test_create_story_missing_title(self):
        """Test creating story without title re-renders form."""
        response = self.client.post(reverse('backlog:create_story_refine'), {
            'title': '',
            'epic_id': self.epic.pk,
        })
        # Should re-render form, not create story
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Story.objects.filter(epic=self.epic).exists())


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
            epic=self.epic,
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
            epic=self.epic,
            title="Done Story",
            finished=timezone.now()
        )
        
        response = self.client.get(reverse('backlog:kanban'))
        self.assertContains(response, "Ready Story")
        self.assertContains(response, "Done Story")

    def test_kanban_move_to_planned(self):
        """Test moving a story to planned column."""
        story = Story.objects.create(
            epic=self.epic,
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
        story = Story.objects.create(epic=self.epic, title="Test Story")
        
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
        story = Story.objects.create(epic=self.epic, title="Test Story")
        
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
        story = Story.objects.create(epic=self.epic, title="Test Story")
        
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
            epic=self.epic,
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
        story = Story.objects.create(epic=self.epic, title="Test Story")
        
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
        story = Story.objects.create(epic=self.epic, title="Test Story")
        
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
            epic=self.epic,
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

    def test_report_filter_by_epic(self):
        """Test report filtering by epic."""
        epic2 = Epic.objects.create(title="Epic 2")
        Story.objects.create(epic=self.epic, title="Story 1")
        Story.objects.create(epic=epic2, title="Story 2")
        
        response = self.client.get(reverse('backlog:report') + f'?epic={self.epic.pk}')
        self.assertContains(response, "Story 1")
        self.assertNotContains(response, "Story 2")

    def test_report_filter_by_status(self):
        """Test report filtering by status."""
        Story.objects.create(epic=self.epic, title="Idea Story")
        Story.objects.create(
            epic=self.epic,
            title="Done Story",
            finished=timezone.now()
        )
        
        response = self.client.get(reverse('backlog:report') + '?status=done')
        self.assertContains(response, "Done Story")
        self.assertNotContains(response, "Idea Story")

    def test_report_excludes_archived(self):
        """Test report excludes archived stories."""
        story_active = Story.objects.create(epic=self.epic, title="Active Story")
        story_archived = Story.objects.create(
            epic=self.epic,
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
        story = Story.objects.create(epic=self.epic, title="Test Story")
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
        Story.objects.create(epic=self.epic, title="WBS Story")
        response = self.client.get(reverse('backlog:wbs'))
        self.assertContains(response, "WBS Story")

    def test_wbs_add_dependency(self):
        """Test adding dependency via WBS AJAX."""
        story1 = Story.objects.create(epic=self.epic, title="Story 1")
        story2 = Story.objects.create(epic=self.epic, title="Story 2")
        
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
        story = Story.objects.create(epic=self.epic, title="Story")
        
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
        story1 = Story.objects.create(epic=self.epic, title="Story 1")
        story2 = Story.objects.create(epic=self.epic, title="Story 2")
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
        story1 = Story.objects.create(epic=self.epic, title="Story 1")
        story2 = Story.objects.create(epic=self.epic, title="Story 2")
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
        Story.objects.create(epic=self.epic, title="Active Story WBS")
        Story.objects.create(epic=self.epic, title="Archived Story WBS", archived=True)
        
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
        """Test that default scores are created when a story is created."""
        story = Story.objects.create(epic=self.epic, title="New Story")
        
        # Check value factor scores were created
        vf_score = StoryValueFactorScore.objects.filter(
            story=story,
            valuefactor=self.value_factor
        ).first()
        self.assertIsNotNone(vf_score)
        self.assertEqual(vf_score.answer.score, 0)
        
        # Check cost factor scores were created
        cf_score = StoryCostFactorScore.objects.filter(
            story=story,
            costfactor=self.cost_factor
        ).first()
        self.assertIsNotNone(cf_score)
        self.assertEqual(cf_score.answer.score, 0)


class IntegrationTests(BaseTestCase):
    """Integration tests for complete workflows."""

    def test_complete_story_lifecycle(self):
        """Test complete story lifecycle from creation to done."""
        # Create story
        response = self.client.post(reverse('backlog:create_story_refine'), {
            'title': 'Lifecycle Story',
            'epic_id': self.epic.pk,
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

    def test_archive_epic_with_stories(self):
        """Test archiving an epic also archives its stories."""
        story1 = Story.objects.create(epic=self.epic, title="Story 1")
        story2 = Story.objects.create(epic=self.epic, title="Story 2")
        
        # Archive epic
        self.client.post(reverse('backlog:index'), {
            'action': 'archive_epic',
            'epic_id': self.epic.pk
        })
        
        self.epic.refresh_from_db()
        story1.refresh_from_db()
        story2.refresh_from_db()
        
        self.assertTrue(self.epic.archived)
        self.assertTrue(story1.archived)
        self.assertTrue(story2.archived)

    def test_dependency_chain(self):
        """Test creating a chain of dependencies."""
        story1 = Story.objects.create(epic=self.epic, title="Story 1")
        story2 = Story.objects.create(epic=self.epic, title="Story 2")
        story3 = Story.objects.create(epic=self.epic, title="Story 3")
        
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