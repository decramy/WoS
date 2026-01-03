"""
Models for the WoS (WSJF on Steroids) backlog application.

This module defines the core data models:
- Epic: Container for related stories
- Story: Individual work items with goal and workitems
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
# Epic and Story Models
# =============================================================================


class Epic(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class Story(models.Model):
    epic = models.ForeignKey(Epic, related_name="stories", on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    goal = models.CharField(max_length=200, blank=True)
    workitems = models.TextField(blank=True)
    planned = models.DateTimeField(null=True, blank=True)
    started = models.DateTimeField(null=True, blank=True)
    finished = models.DateTimeField(null=True, blank=True)
    blocked = models.TextField(blank=True)
    archived = models.BooleanField(default=False)
    review_required = models.BooleanField(default=False)
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
        
        # Check if all value factors have scores
        all_value_factors = ValueFactor.objects.all()
        for vf in all_value_factors:
            if not self.scores.filter(valuefactor=vf).exists():
                return 'idea'
        
        # Check if all cost factors have scores
        all_cost_factors = CostFactor.objects.all()
        for cf in all_cost_factors:
            if not self.cost_scores.filter(costfactor=cf).exists():
                return 'idea'
        
        return 'ready'

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
    section = models.ForeignKey(ValueFactorSection, related_name="valuefactors", on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, help_text="Explains what this factor measures")
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
    """
    story = models.ForeignKey(Story, related_name="scores", on_delete=models.CASCADE)
    valuefactor = models.ForeignKey(ValueFactor, related_name="scores", on_delete=models.CASCADE)
    answer = models.ForeignKey(
        ValueFactorAnswer, related_name="+", on_delete=models.PROTECT,
        null=True, blank=True, help_text="None means undefined/not yet scored"
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
    section = models.ForeignKey(CostFactorSection, related_name="costfactors", on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, help_text="Explains what this factor measures")
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
    """
    story = models.ForeignKey(Story, related_name="cost_scores", on_delete=models.CASCADE)
    costfactor = models.ForeignKey(CostFactor, related_name="scores", on_delete=models.CASCADE)
    answer = models.ForeignKey(
        CostFactorAnswer, related_name="+", on_delete=models.PROTECT,
        null=True, blank=True, help_text="None means undefined/not yet scored"
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
    """
    if not created:
        return
    # For each ValueFactor create a StoryValueFactorScore with answer=None (undefined)
    for vf in ValueFactor.objects.all():
        StoryValueFactorScore.objects.get_or_create(
            story=instance,
            valuefactor=vf,
            defaults={"answer": None},
        )
    # For each CostFactor create a StoryCostFactorScore with answer=None (undefined)
    for cf in CostFactor.objects.all():
        StoryCostFactorScore.objects.get_or_create(
            story=instance,
            costfactor=cf,
            defaults={"answer": None},
        )


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
