# finished_products/migrations/0004_populate_unique_skus.py
from django.db import migrations
import re

def _first_two_alpha(value):
    if not value:
        return "XX"
    letters = re.findall(r'[A-Za-z]', value)
    out = ''.join(letters[:2]).upper()
    if len(out) == 0:
        return "XX"
    if len(out) == 1:
        return out + "X"
    return out

def generate_unique_skus(apps, schema_editor):
    FinishedProduct = apps.get_model('finished_products', 'FinishedProduct')
    # We keep an in-memory set to avoid duplicates created during this run,
    # and we also check DB to avoid conflicts with existing values.
    used = set(FinishedProduct.objects.exclude(sku__isnull=True).exclude(sku__exact='').values_list('sku', flat=True))

    for p in FinishedProduct.objects.all().order_by('pk'):
        # compute base using same algorithm as model
        base = (
            _first_two_alpha(p.name) +
            _first_two_alpha(p.fabric_color_name) +
            _first_two_alpha(p.fabric_pattern) +
            ((p.size or '').upper())
        )
        candidate = base.upper()
        suffix = 0
        # Avoid collision with DB or our used set
        while candidate in used or FinishedProduct.objects.filter(sku=candidate).exclude(pk=p.pk).exists():
            suffix += 1
            candidate = f"{base.upper()}-{suffix}"
        # Save candidate
        p.sku = candidate
        p.save(update_fields=['sku'])
        used.add(candidate)

def noop_reverse(apps, schema_editor):
    # irreversible: keep a no-op reverse (you could set all skus to NULL if needed)
    pass

class Migration(migrations.Migration):

    dependencies = [
        ('finished_products', '0003_remove_finishedproduct_description_and_more'),
    ]

    operations = [
        migrations.RunPython(generate_unique_skus, reverse_code=noop_reverse),
    ]
