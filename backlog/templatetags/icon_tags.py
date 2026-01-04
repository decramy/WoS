"""
Template tags for rendering icons (emoji or MDI).

Usage in templates:
    {% load icon_tags %}
    {% render_icon "mdi-bug" %}          -> <span class="mdi mdi-bug"></span>
    {% render_icon "🐛" %}               -> 🐛
    {{ icon_value|render_icon }}         -> works as filter too
"""
from django import template
from django.utils.safestring import mark_safe

register = template.Library()


def is_mdi_icon(icon_str):
    """Check if the icon string is an MDI icon reference."""
    if not icon_str:
        return False
    return icon_str.startswith('mdi-') or icon_str.startswith('mdi ')


@register.simple_tag
def render_icon(icon_str):
    """Render an icon - either MDI class or emoji."""
    if not icon_str:
        return ''
    
    if is_mdi_icon(icon_str):
        # Normalize: "mdi-bug" or "mdi bug" -> "mdi mdi-bug"
        icon_class = icon_str.strip()
        if icon_class.startswith('mdi '):
            # Already has "mdi " prefix, ensure proper format
            icon_class = icon_class.replace('mdi ', 'mdi mdi-', 1) if not 'mdi-' in icon_class else icon_class
        elif icon_class.startswith('mdi-'):
            # Add the base "mdi" class
            icon_class = f'mdi {icon_class}'
        return mark_safe(f'<span class="{icon_class}"></span>')
    
    # Return emoji as-is
    return icon_str


# Also register as a filter for convenience
@register.filter
def render_icon_filter(icon_str):
    """Filter version of render_icon."""
    return render_icon(icon_str)


@register.filter
def is_mdi(icon_str):
    """Check if an icon string is an MDI icon (for use in templates)."""
    return is_mdi_icon(icon_str)
