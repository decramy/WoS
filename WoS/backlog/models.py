from django.db import models


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
        # ensure status is 'refined' when both goal and workitems are provided
        has_goal = bool(self.goal and self.goal.strip())
        has_work = bool(self.workitems and self.workitems.strip())
        desired = self.STATUS_REFINED if (has_goal and has_work) else self.STATUS_NEW
        if self.status != desired:
            self.status = desired
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class ValueFactorSection(models.Model):
    """A grouping of value factors (examples: Fun, Environmental Impact)."""
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "valuefactor section"
        verbose_name_plural = "valuefactor sections"

    def __str__(self):
        return self.name


class ValueFactor(models.Model):
    """A single value factor that belongs to a section."""
    section = models.ForeignKey(ValueFactorSection, related_name="valuefactors", on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "valuefactor"
        verbose_name_plural = "valuefactors"

    def __str__(self):
        return f"{self.name} ({self.section.name})"


class ValueFactorAnswer(models.Model):
    """A possible answer for a ValueFactor with an associated score."""
    valuefactor = models.ForeignKey(ValueFactor, related_name="answers", on_delete=models.CASCADE)
    score = models.IntegerField()
    description = models.CharField(max_length=400, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "valuefactor answer"
        verbose_name_plural = "valuefactor answers"

    def __str__(self):
        return f"{self.description} ({self.score})"


class StoryValueFactorScore(models.Model):
    """Stores the selected answer for a given story and valuefactor.

    The `answer` must belong to `valuefactor`. A default answer with score
    0 will be used when a story is created.
    """
    story = models.ForeignKey(Story, related_name="scores", on_delete=models.CASCADE)
    valuefactor = models.ForeignKey(ValueFactor, related_name="scores", on_delete=models.CASCADE)
    answer = models.ForeignKey(ValueFactorAnswer, related_name="+", on_delete=models.PROTECT)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("story", "valuefactor")

    def clean(self):
        # Ensure the provided answer belongs to the same valuefactor
        if self.answer and self.answer.valuefactor_id != self.valuefactor_id:
            raise ValidationError("Answer must belong to the selected ValueFactor.")

    def __str__(self):
        return f"{self.story} — {self.valuefactor}: {self.answer}"


class CostFactorSection(models.Model):
    """A grouping of cost factors (examples: Development Cost, Infrastructure)."""
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "costfactor section"
        verbose_name_plural = "costfactor sections"

    def __str__(self):
        return self.name


class CostFactor(models.Model):
    """A single cost factor that belongs to a section."""
    section = models.ForeignKey(CostFactorSection, related_name="costfactors", on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "costfactor"
        verbose_name_plural = "costfactors"

    def __str__(self):
        return f"{self.name} ({self.section.name})"


class CostFactorAnswer(models.Model):
    """A possible answer for a CostFactor with an associated score."""
    costfactor = models.ForeignKey(CostFactor, related_name="answers", on_delete=models.CASCADE)
    score = models.IntegerField()
    description = models.CharField(max_length=400, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "costfactor answer"
        verbose_name_plural = "costfactor answers"

    def __str__(self):
        return f"{self.description} ({self.score})"


class StoryCostFactorScore(models.Model):
    """Stores the selected answer for a given story and costfactor.

    The `answer` must belong to `costfactor`. A default answer with score
    0 will be used when a story is created.
    """
    story = models.ForeignKey(Story, related_name="cost_scores", on_delete=models.CASCADE)
    costfactor = models.ForeignKey(CostFactor, related_name="scores", on_delete=models.CASCADE)
    answer = models.ForeignKey(CostFactorAnswer, related_name="+", on_delete=models.PROTECT)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("story", "costfactor")

    def clean(self):
        # Ensure the provided answer belongs to the same costfactor
        if self.answer and self.answer.costfactor_id != self.costfactor_id:
            raise ValidationError("Answer must belong to the selected CostFactor.")

    def __str__(self):
        return f"{self.story} — {self.costfactor}: {self.answer}"


# Signals: create default StoryValueFactorScore rows (score 0 answers) when a story is created
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.exceptions import ValidationError


def _get_or_create_zero_answer(vf: ValueFactor) -> ValueFactorAnswer:
    ans = vf.answers.filter(score=0).first()
    if ans:
        return ans
    return ValueFactorAnswer.objects.create(valuefactor=vf, score=0, description="Default 0")


def _get_or_create_zero_answer_cf(cf: 'CostFactor') -> 'CostFactorAnswer':
    ans = cf.answers.filter(score=0).first()
    if ans:
        return ans
    return CostFactorAnswer.objects.create(costfactor=cf, score=0, description="Default 0")


@receiver(post_save, sender=Story)
def ensure_scores_for_story(sender, instance: Story, created, **kwargs):
    if not created:
        return
    # For each ValueFactor create a StoryValueFactorScore using the 0 answer
    for vf in ValueFactor.objects.all():
        zero_ans = _get_or_create_zero_answer(vf)
        StoryValueFactorScore.objects.get_or_create(
            story=instance,
            valuefactor=vf,
            defaults={"answer": zero_ans},
        )
    # For each CostFactor create a StoryCostFactorScore using the 0 answer
    for cf in CostFactor.objects.all():
        zero_ans = _get_or_create_zero_answer_cf(cf)
        StoryCostFactorScore.objects.get_or_create(
            story=instance,
            costfactor=cf,
            defaults={"answer": zero_ans},
        )


class StoryDependency(models.Model):
    """A dependency relationship between stories. The story depends on depends_on."""
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
    """Tracks changes made to a story over time."""
    story = models.ForeignKey(Story, related_name="history", on_delete=models.CASCADE)
    field_name = models.CharField(max_length=100)
    old_value = models.TextField(blank=True, null=True)
    new_value = models.TextField(blank=True, null=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "story history"
        verbose_name_plural = "story histories"
        ordering = ['-changed_at']

    def __str__(self):
        return f"{self.story.title}: {self.field_name} changed at {self.changed_at}"
