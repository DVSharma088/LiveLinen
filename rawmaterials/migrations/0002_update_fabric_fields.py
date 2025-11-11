# rawmaterials/migrations/0002_update_fabric_fields.py
from __future__ import annotations
from decimal import Decimal
from django.db import migrations, models


def set_default_quality(apps, schema_editor):
    Fabric = apps.get_model("rawmaterials", "Fabric")
    Fabric.objects.filter(quality__isnull=True).update(quality=Decimal("0.00"))


class Migration(migrations.Migration):

    dependencies = [
        # REPLACE the string below with the last migration filename for rawmaterials.
        # Example: ('rawmaterials', '0001_initial') or ('rawmaterials', '0005_auto_20251028_1701')
        ('rawmaterials', '0001_initial'),
    ]

    operations = [
        # Rename existing columns to the new names (preserve data)
        migrations.RenameField(
            model_name='fabric',
            old_name='name',
            new_name='item_name',
        ),
        migrations.RenameField(
            model_name='fabric',
            old_name='width',
            new_name='fabric_width',
        ),
        migrations.RenameField(
            model_name='fabric',
            old_name='stock',
            new_name='stock_in_mtrs',
        ),
        migrations.RenameField(
            model_name='fabric',
            old_name='rate',
            new_name='cost_per_unit',
        ),

        # Add new fields that did not exist previously.
        migrations.AddField(
            model_name='fabric',
            name='quality',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0.00'),
                help_text='Quality as percentage (0 - 100).',
                max_digits=5
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='fabric',
            name='base_color',
            field=models.CharField(max_length=100, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='fabric',
            name='fabric_type',
            field=models.CharField(max_length=100, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='fabric',
            name='use_in',
            field=models.CharField(max_length=200, null=True, blank=True, help_text='Intended use (e.g., shirts, upholstery)'),
        ),

        # Ensure any null quality fields get set to 0.00 (for safety)
        migrations.RunPython(set_default_quality, reverse_code=migrations.RunPython.noop),
    ]
