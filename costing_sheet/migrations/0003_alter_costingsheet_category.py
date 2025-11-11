# costing_sheet/migrations/0003_alter_costingsheet_category.py
from django.db import migrations, models

def clean_invalid_category_fks(apps, schema_editor):
    CostingSheet = apps.get_model('costing_sheet', 'CostingSheet')
    CategoryModel = apps.get_model('category_master', 'CategoryMaster')
    costing_table = CostingSheet._meta.db_table
    category_table = CategoryModel._meta.db_table

    # Set category_id = NULL where referenced category doesn't exist.
    # Works on SQLite/Postgres/MySQL.
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f'''
            UPDATE "{costing_table}"
            SET category_id = NULL
            WHERE category_id IS NOT NULL
            AND category_id NOT IN (SELECT id FROM "{category_table}");
        ''')

def noop_reverse(apps, schema_editor):
    # No safe reverse operation
    pass

class Migration(migrations.Migration):

    # Update dependency to match your actual previous migration file
    dependencies = [
        ('category_master', '0001_initial'),
        ('costing_sheet', '0002_rename_finishing_cost_costingsheet_shipping_inr_and_more'),
    ]

    operations = [
        # 1) Allow NULLs on the FK column so the cleanup update can set NULLs
        migrations.AlterField(
            model_name='costingsheet',
            name='category',
            field=models.ForeignKey(
                to='category_master.CategoryMaster',
                null=True,
                on_delete=models.SET_NULL,
            ),
        ),
        # 2) Clean invalid FK values (set to NULL)
        migrations.RunPython(clean_invalid_category_fks, reverse_code=noop_reverse),
        # 3) (OPTIONAL) If you want to enforce non-null later, create a separate migration
        # that assigns a default category to NULLs and then AlterField(null=False).
    ]
