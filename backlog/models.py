"""
Models for the WoS (WSJF on Steroids) backlog application.

This module defines the core data models:
- Story: Individual work items with goal and workitems
- LabelCategory/Label: Categorized labels for stories
- ValueFactorSection/ValueFactor/ValueFactorAnswer: Value scoring dimensions
- CostFactorSection/CostFactor/CostFactorAnswer: Cost scoring dimensions
- StoryValueFactorScore/StoryCostFactorScore: Score assignments per story
- StoryDependency: Dependency relationships between stories
- StoryHistory: Audit trail for story changes

The WSJF score is calculated as:
    Result = sum(value_section_averages) / sum(cost_section_averages)
"""
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


# =============================================================================
# Label Models
# =============================================================================


class LabelCategory(models.Model):
    """A category for grouping related labels with shared styling."""
    name = models.CharField(max_length=100)
    color = models.CharField(
        max_length=7, 
        default="#6b7280",
        help_text="Hex color code (e.g., #2563eb)"
    )
    icon = models.CharField(
        max_length=10, 
        default="🏷️",
        help_text="Emoji or short icon symbol"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "label category"
        verbose_name_plural = "label categories"
        ordering = ['name']

    def __str__(self):
        return f"{self.icon} {self.name}"


class Label(models.Model):
    """A label that can be attached to stories."""
    category = models.ForeignKey(
        LabelCategory, 
        related_name="labels", 
        on_delete=models.CASCADE
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, help_text="Optional description of this label")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "label"
        verbose_name_plural = "labels"
        ordering = ['category__name', 'name']
        unique_together = [['category', 'name']]

    def __str__(self):
        return f"{self.category.icon} {self.name}"

    @property
    def color(self):
        """Get color from parent category."""
        return self.category.color

    @property
    def icon(self):
        """Get icon from parent category."""
        return self.category.icon


# =============================================================================
# Story Model
# =============================================================================


class Story(models.Model):
    """A user story representing a unit of work to be prioritized and completed.
    
    Stories are scored using WSJF (Weighted Shortest Job First) methodology,
    with value factors and cost factors determining priority.
    """
    title = models.CharField(max_length=200)
    goal = models.CharField(max_length=200, blank=True)
    workitems = models.TextField(blank=True)
    labels = models.ManyToManyField(Label, related_name="stories", blank=True)
    planned = models.DateTimeField(null=True, blank=True, db_index=True)
    started = models.DateTimeField(null=True, blank=True, db_index=True)
    finished = models.DateTimeField(null=True, blank=True, db_index=True)
    blocked = models.TextField(blank=True)
    archived = models.BooleanField(default=False, db_index=True)
    review_required = models.BooleanField(default=False, db_index=True)
    STATUS_NEW = 'new'
    STATUS_REFINED = 'refined'
    STATUS_CHOICES = [(STATUS_NEW, 'New'), (STATUS_REFINED, 'Refined')]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def computed_status(self):
        """
        Returns the computed status based on:
        - 'blocked' if blocked field has text
        - 'done' if finished datetime is set
        - 'started' if started datetime is set
        - 'planned' if planned datetime is set
        - 'ready' if all text fields and scores are set
        - 'idea' if any score is undefined or any text field is empty
        
        Note: For optimal performance, prefetch 'scores' and 'cost_scores' before
        accessing this property on multiple stories.
        """
        # Priority order: blocked > done > started > planned > ready > idea
        if self.blocked and self.blocked.strip():
            return 'blocked'
        if self.finished:
            return 'done'
        if self.started:
            return 'started'
        if self.planned:
            return 'planned'
        
        # Check if all text fields are filled
        has_title = bool(self.title and self.title.strip())
        has_goal = bool(self.goal and self.goal.strip())
        has_workitems = bool(self.workitems and self.workitems.strip())
        
        if not (has_title and has_goal and has_workitems):
            return 'idea'
        
        # Use prefetched scores if available (avoids N+1 queries)
        if hasattr(self, '_prefetched_objects_cache'):
            # Get IDs of factors that have defined answers from prefetched data
            story_vf_ids = {s.valuefactor_id for s in self.scores.all() if s.answer_id is not None}
            story_cf_ids = {s.costfactor_id for s in self.cost_scores.all() if s.answer_id is not None}
        else:
            # Fallback to direct queries if not prefetched
            story_vf_ids = set(self.scores.filter(answer__isnull=False).values_list('valuefactor_id', flat=True))
            story_cf_ids = set(self.cost_scores.filter(answer__isnull=False).values_list('costfactor_id', flat=True))
        
        # Get all factor IDs (cached at class level for performance)
        all_vf_ids = Story._get_all_value_factor_ids()
        all_cf_ids = Story._get_all_cost_factor_ids()
        
        # Check if all factors have scores
        if not (all_vf_ids <= story_vf_ids and all_cf_ids <= story_cf_ids):
            return 'idea'
        
        return 'ready'
    
    # Class-level cache for factor IDs to avoid repeated queries
    _cached_value_factor_ids = None
    _cached_cost_factor_ids = None
    
    @classmethod
    def _get_all_value_factor_ids(cls):
        """Get all value factor IDs (cached at class level)."""
        if cls._cached_value_factor_ids is None:
            cls._cached_value_factor_ids = set(ValueFactor.objects.values_list('id', flat=True))
        return cls._cached_value_factor_ids
    
    @classmethod
    def _get_all_cost_factor_ids(cls):
        """Get all cost factor IDs (cached at class level)."""
        if cls._cached_cost_factor_ids is None:
            cls._cached_cost_factor_ids = set(CostFactor.objects.values_list('id', flat=True))
        return cls._cached_cost_factor_ids
    
    @classmethod
    def clear_factor_cache(cls):
        """Clear the cached factor IDs (call after adding/removing factors)."""
        cls._cached_value_factor_ids = None
        cls._cached_cost_factor_ids = None

    class Meta:
        verbose_name = "story"
        verbose_name_plural = "stories"
        ordering = ['title']
        # Single-field indexes are defined on fields using db_index=True
        # Additional composite indexes for common query patterns
        indexes = [
            models.Index(fields=['archived', 'status'], name='story_archived_status_idx'),
            models.Index(fields=['archived', 'created_at'], name='story_archived_created_idx'),
        ]

    def save(self, *args, **kwargs):
        """Auto-update status based on goal and workitems fields."""
        has_goal = bool(self.goal and self.goal.strip())
        has_work = bool(self.workitems and self.workitems.strip())
        desired = self.STATUS_REFINED if (has_goal and has_work) else self.STATUS_NEW
        if self.status != desired:
            self.status = desired
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


# =============================================================================
# Value Factor Models
# =============================================================================


class ValueFactorSection(models.Model):
    """A grouping of value factors (e.g., Business Value, User Experience)."""
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "value factor section"
        verbose_name_plural = "value factor sections"
        ordering = ['name']

    def __str__(self):
        return self.name


class ValueFactor(models.Model):
    """A single value factor that belongs to a section."""
    SCORING_ABSOLUTE = 'absolute'
    SCORING_RELATIVE = 'relative'
    SCORING_CHOICES = [
        (SCORING_ABSOLUTE, 'Absolute (use answer score)'),
        (SCORING_RELATIVE, 'Relative (use ranking)'),
    ]
    
    section = models.ForeignKey(ValueFactorSection, related_name="valuefactors", on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, help_text="Explains what this factor measures")
    scoring_mode = models.CharField(
        max_length=10,
        choices=SCORING_CHOICES,
        default=SCORING_ABSOLUTE,
        help_text="How this factor contributes to the score: absolute uses answer scores, relative uses rankings"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "value factor"
        verbose_name_plural = "value factors"
        ordering = ['section__name', 'name']

    def __str__(self):
        return f"{self.name} ({self.section.name})"


class ValueFactorAnswer(models.Model):
    """A possible answer/score option for a ValueFactor."""
    valuefactor = models.ForeignKey(ValueFactor, related_name="answers", on_delete=models.CASCADE)
    score = models.IntegerField(help_text="Numeric score for this answer")
    description = models.CharField(max_length=400, blank=True, help_text="Human-readable answer text")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "value factor answer"
        verbose_name_plural = "value factor answers"
        ordering = ['valuefactor', 'score']

    def __str__(self):
        return f"{self.description} ({self.score})"


class StoryValueFactorScore(models.Model):
    """Links a Story to a ValueFactor with the selected answer.
    
    Constraints:
    - The answer must belong to the specified valuefactor
    - Each story can have only one score per valuefactor
    - answer=None means "undefined" (not yet scored)
    - relative_rank is used for relative scoring (lower = higher priority)
    """
    story = models.ForeignKey(Story, related_name="scores", on_delete=models.CASCADE)
    valuefactor = models.ForeignKey(ValueFactor, related_name="scores", on_delete=models.CASCADE)
    answer = models.ForeignKey(
        ValueFactorAnswer, related_name="+", on_delete=models.PROTECT,
        null=True, blank=True, help_text="None means undefined/not yet scored"
    )
    relative_rank = models.IntegerField(
        null=True, blank=True,
        help_text="Relative ranking within this factor (1 = highest, None = not ranked)"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "story value score"
        verbose_name_plural = "story value scores"
        unique_together = ("story", "valuefactor")

    def clean(self):
        """Validate that answer belongs to the correct valuefactor."""
        if self.answer and self.answer.valuefactor_id != self.valuefactor_id:
            raise ValidationError("Answer must belong to the selected ValueFactor.")

    def __str__(self):
        return f"{self.story} — {self.valuefactor}: {self.answer}"


# =============================================================================
# Cost Factor Models
# =============================================================================


class CostFactorSection(models.Model):
    """A grouping of cost factors (e.g., Development Effort, Risk)."""
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "cost factor section"
        verbose_name_plural = "cost factor sections"
        ordering = ['name']

    def __str__(self):
        return self.name


class CostFactor(models.Model):
    """A single cost factor that belongs to a section."""
    SCORING_ABSOLUTE = 'absolute'
    SCORING_RELATIVE = 'relative'
    SCORING_CHOICES = [
        (SCORING_ABSOLUTE, 'Absolute (use answer score)'),
        (SCORING_RELATIVE, 'Relative (use ranking)'),
    ]
    
    section = models.ForeignKey(CostFactorSection, related_name="costfactors", on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, help_text="Explains what this factor measures")
    scoring_mode = models.CharField(
        max_length=10,
        choices=SCORING_CHOICES,
        default=SCORING_ABSOLUTE,
        help_text="How this factor contributes to the score: absolute uses answer scores, relative uses rankings"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "cost factor"
        verbose_name_plural = "cost factors"
        ordering = ['section__name', 'name']

    def __str__(self):
        return f"{self.name} ({self.section.name})"


class CostFactorAnswer(models.Model):
    """A possible answer/score option for a CostFactor."""
    costfactor = models.ForeignKey(CostFactor, related_name="answers", on_delete=models.CASCADE)
    score = models.IntegerField(help_text="Numeric score for this answer")
    description = models.CharField(max_length=400, blank=True, help_text="Human-readable answer text")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "cost factor answer"
        verbose_name_plural = "cost factor answers"
        ordering = ['costfactor', 'score']

    def __str__(self):
        return f"{self.description} ({self.score})"


class StoryCostFactorScore(models.Model):
    """Links a Story to a CostFactor with the selected answer.
    
    Constraints:
    - The answer must belong to the specified costfactor
    - Each story can have only one score per costfactor
    - answer=None means "undefined" (not yet scored)
    - relative_rank is used for relative scoring (lower = higher priority for cost)
    """
    story = models.ForeignKey(Story, related_name="cost_scores", on_delete=models.CASCADE)
    costfactor = models.ForeignKey(CostFactor, related_name="scores", on_delete=models.CASCADE)
    answer = models.ForeignKey(
        CostFactorAnswer, related_name="+", on_delete=models.PROTECT,
        null=True, blank=True, help_text="None means undefined/not yet scored"
    )
    relative_rank = models.IntegerField(
        null=True, blank=True,
        help_text="Relative ranking within this factor (1 = lowest cost, None = not ranked)"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "story cost score"
        verbose_name_plural = "story cost scores"
        unique_together = ("story", "costfactor")

    def clean(self):
        """Validate that answer belongs to the correct costfactor."""
        if self.answer and self.answer.costfactor_id != self.costfactor_id:
            raise ValidationError("Answer must belong to the selected CostFactor.")

    def __str__(self):
        return f"{self.story} — {self.costfactor}: {self.answer}"


# =============================================================================
# Story Relationships and History
# =============================================================================


@receiver(post_save, sender=Story)
def ensure_scores_for_story(sender, instance: Story, created, **kwargs):
    """Signal handler to create score records when a Story is created.
    
    Creates StoryValueFactorScore and StoryCostFactorScore records for each
    factor, with answer=None (undefined). This ensures all factors are tracked
    while clearly distinguishing "not yet scored" from an explicit score of 0.
    
    Uses bulk_create for efficiency.
    """
    if not created:
        return
    
    # Bulk create value scores
    value_factor_ids = list(ValueFactor.objects.values_list('id', flat=True))
    StoryValueFactorScore.objects.bulk_create([
        StoryValueFactorScore(story=instance, valuefactor_id=vf_id, answer=None)
        for vf_id in value_factor_ids
    ], ignore_conflicts=True)
    
    # Bulk create cost scores
    cost_factor_ids = list(CostFactor.objects.values_list('id', flat=True))
    StoryCostFactorScore.objects.bulk_create([
        StoryCostFactorScore(story=instance, costfactor_id=cf_id, answer=None)
        for cf_id in cost_factor_ids
    ], ignore_conflicts=True)


class StoryDependency(models.Model):
    """Represents a dependency relationship between two stories.
    
    The `story` depends on `depends_on`, meaning `depends_on` should be
    completed before work on `story` can begin.
    """
    story = models.ForeignKey(Story, related_name="dependencies", on_delete=models.CASCADE)
    depends_on = models.ForeignKey(Story, related_name="dependents", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "story dependency"
        verbose_name_plural = "story dependencies"
        unique_together = [['story', 'depends_on']]

    def __str__(self):
        return f"{self.story.title} → {self.depends_on.title}"


class StoryHistory(models.Model):
    """Audit trail for changes made to a story.
    
    Each record captures a single field change with old and new values.
    """
    story = models.ForeignKey(Story, related_name="history", on_delete=models.CASCADE)
    field_name = models.CharField(max_length=100, help_text="Name of the changed field")
    old_value = models.TextField(blank=True, null=True)
    new_value = models.TextField(blank=True, null=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "story history"
        verbose_name_plural = "story history entries"
        ordering = ['-changed_at']

    def __str__(self):
        return f"{self.story.title}: {self.field_name} changed at {self.changed_at}"
