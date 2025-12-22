from django.db import models


class Epic(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class Story(models.Model):
    epic = models.ForeignKey(Epic, related_name="stories", on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    target = models.CharField(max_length=200, blank=True)
    workitems = models.TextField(blank=True)
    description = models.TextField(blank=True)
    STATUS_NEW = 'new'
    STATUS_REFINED = 'refined'
    STATUS_CHOICES = [(STATUS_NEW, 'New'), (STATUS_REFINED, 'Refined')]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        # ensure status is 'refined' when both target and workitems are provided
        has_target = bool(self.target and self.target.strip())
        has_work = bool(self.workitems and self.workitems.strip())
        desired = self.STATUS_REFINED if (has_target and has_work) else self.STATUS_NEW
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
