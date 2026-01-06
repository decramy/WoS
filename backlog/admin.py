from django.contrib import admin
from django import forms
from .models import (
	Story,
	Label,
	LabelCategory,
	ValueFactorSection,
	ValueFactor,
	ValueFactorAnswer,
	StoryValueFactorScore,
	CostFactorSection,
	CostFactor,
	CostFactorAnswer,
	StoryCostFactorScore,
	StoryDependency,
	StoryHistory,
)


admin.site.register(ValueFactorSection)
admin.site.register(CostFactorSection)
admin.site.register(StoryDependency)


# =============================================================================
# Label Admin
# =============================================================================


class LabelInline(admin.TabularInline):
	model = Label
	extra = 1


@admin.register(LabelCategory)
class LabelCategoryAdmin(admin.ModelAdmin):
	list_display = ("name", "icon", "color", "label_count")
	search_fields = ("name",)
	inlines = [LabelInline]

	def label_count(self, obj):
		return obj.labels.count()
	label_count.short_description = "Labels"


@admin.register(Label)
class LabelAdmin(admin.ModelAdmin):
	list_display = ("name", "category", "color_preview")
	list_filter = ("category",)
	search_fields = ("name", "category__name")

	def color_preview(self, obj):
		from django.utils.html import format_html
		return format_html(
			'<span style="background:{}; color:white; padding:2px 8px; border-radius:4px;">{} {}</span>',
			obj.color, obj.icon, obj.name
		)
	color_preview.short_description = "Preview"


# =============================================================================
# Existing Admin Classes
# =============================================================================


@admin.register(StoryHistory)
class StoryHistoryAdmin(admin.ModelAdmin):
	list_display = ("story", "field_name", "old_value", "new_value", "changed_at")
	list_filter = ("field_name", "changed_at")
	search_fields = ("story__title", "field_name", "old_value", "new_value")
	readonly_fields = ("story", "field_name", "old_value", "new_value", "changed_at")
	ordering = ("-changed_at",)


class ValueFactorAnswerInline(admin.TabularInline):
	model = ValueFactorAnswer
	extra = 1


class AnswerModelChoiceField(forms.ModelChoiceField):
	def label_from_instance(self, obj):
		# Show as "score — description"; if description empty show score only
		desc = obj.description.strip() if getattr(obj, 'description', None) else ''
		if desc:
			return f"{obj.score} — {desc}"
		return f"{obj.score}"


@admin.register(ValueFactor)
class ValueFactorAdmin(admin.ModelAdmin):
	list_display = ("name", "section", "scoring_mode")
	list_filter = ("section", "scoring_mode")
	list_editable = ("scoring_mode",)
	inlines = [ValueFactorAnswerInline]


class CostFactorAnswerInline(admin.TabularInline):
	model = CostFactorAnswer
	extra = 1


@admin.register(CostFactor)
class CostFactorAdmin(admin.ModelAdmin):
	list_display = ("name", "section", "scoring_mode")
	list_filter = ("section", "scoring_mode")
	list_editable = ("scoring_mode",)
	inlines = [CostFactorAnswerInline]





@admin.register(Story)
class StoryAdmin(admin.ModelAdmin):
	# We build a dynamic ModelForm in `get_form` so the admin accepts
	# generated field names (vf_<id>) when validating fieldsets.
	list_display = ("title", "goal")
	list_filter = ("archived", "status")

	def get_form(self, request, obj=None, **kwargs):
		# Build a ModelForm subclass with one ModelChoiceField per ValueFactor
		attrs = {}

		class Meta:
			model = Story
			fields = "__all__"

		attrs['Meta'] = Meta

		# Add fields at class construction time so admin field checks pass
		for vf in ValueFactor.objects.select_related("section").order_by(
			"section__name", "name"
		):
			field_name = f"vf_{vf.id}"
			qs = vf.answers.order_by("score")
			attrs[field_name] = AnswerModelChoiceField(
				queryset=qs, required=True, label=vf.name, empty_label=None
			)

		# Cost factor fields
		for cf in CostFactor.objects.select_related("section").order_by(
			"section__name", "name"
		):
			field_name = f"cf_{cf.id}"
			qs = cf.answers.order_by("score")
			attrs[field_name] = AnswerModelChoiceField(
				queryset=qs, required=True, label=cf.name, empty_label=None
			)

		# Add __init__ to set initial values based on the instance
		def __init__(self, *args, **kwargs):
			super(type(self), self).__init__(*args, **kwargs)
			instance = kwargs.get('instance', getattr(self, 'instance', None))
			for vf in ValueFactor.objects.all():
				field_name = f"vf_{vf.id}"
				# Ensure a zero answer exists
				zero_ans, _ = ValueFactorAnswer.objects.get_or_create(
					valuefactor=vf, score=0, defaults={"description": "Default 0"}
				)
				if instance and getattr(instance, 'pk', None):
					sv = StoryValueFactorScore.objects.filter(story=instance, valuefactor=vf).first()
					if sv:
						self.initial[field_name] = sv.answer_id
					else:
						self.initial[field_name] = zero_ans.id
				else:
					self.initial[field_name] = zero_ans.id

			# Cost factor initial values
			for cf in CostFactor.objects.all():
				field_name = f"cf_{cf.id}"
				zero_ans, _ = CostFactorAnswer.objects.get_or_create(
					costfactor=cf, score=0, defaults={"description": "Default 0"}
				)
				if instance and getattr(instance, 'pk', None):
					sv = StoryCostFactorScore.objects.filter(story=instance, costfactor=cf).first()
					if sv:
						self.initial[field_name] = sv.answer_id
					else:
						self.initial[field_name] = zero_ans.id
				else:
					self.initial[field_name] = zero_ans.id

		attrs['__init__'] = __init__

		return type('StoryDynamicForm', (forms.ModelForm,), attrs)

	def get_fieldsets(self, request, obj=None):
		# Base story fields
		base_fields = ("title", "goal", "workitems")
		fieldsets = [(None, {"fields": base_fields})]

		# Add a fieldset per section with that section's valuefactors
		for section in ValueFactorSection.objects.prefetch_related("valuefactors").order_by("name"):
			vf_fields = [f"vf_{vf.id}" for vf in section.valuefactors.all().order_by("name")]
			if vf_fields:
				fieldsets.append((section.name, {"fields": vf_fields}))

		# Add a fieldset per cost section with that section's costfactors
		for section in CostFactorSection.objects.prefetch_related("costfactors").order_by("name"):
			cf_fields = [f"cf_{cf.id}" for cf in section.costfactors.all().order_by("name")]
			if cf_fields:
				fieldsets.append((f"Cost — {section.name}", {"fields": cf_fields}))

		return fieldsets

	def save_model(self, request, obj, form, change):
		# Save the story first
		super().save_model(request, obj, form, change)

		# Persist selected answers for each ValueFactor
		for vf in ValueFactor.objects.all():
			field_name = f"vf_{vf.id}"
			if field_name not in form.cleaned_data:
				continue
			answer = form.cleaned_data[field_name]
			if answer is None:
				continue
			# Ensure the answer belongs to the valuefactor
			if answer.valuefactor_id != vf.id:
				continue
			StoryValueFactorScore.objects.update_or_create(
				story=obj, valuefactor=vf, defaults={"answer": answer}
			)

		# Persist selected answers for each CostFactor
		for cf in CostFactor.objects.all():
			field_name = f"cf_{cf.id}"
			if field_name not in form.cleaned_data:
				continue
			answer = form.cleaned_data[field_name]
			if answer is None:
				continue
			if answer.costfactor_id != cf.id:
				continue
			StoryCostFactorScore.objects.update_or_create(
				story=obj, costfactor=cf, defaults={"answer": answer}
			)
