from django.db import migrations

def populate_categorymasternew(apps, schema_editor):
    CategoryMaster = apps.get_model('category_master', 'CategoryMaster')
    CategoryMasterNew = apps.get_model('category_master', 'CategoryMasterNew')
    ComponentMaster = apps.get_model('components', 'ComponentMaster')

    referenced_ids = (
        CategoryMaster.objects
        .exclude(component__isnull=True)
        .values_list('component', flat=True)
        .distinct()
    )

    for comp_id in referenced_ids:
        if CategoryMasterNew.objects.filter(pk=comp_id).exists():
            continue
        try:
            comp = ComponentMaster.objects.get(pk=comp_id)
            name = getattr(comp, 'name', str(comp))
        except ComponentMaster.DoesNotExist:
            name = f"component-{comp_id}"
        CategoryMasterNew.objects.create(id=comp_id, name=name)

class Migration(migrations.Migration):
    dependencies = [
        ('category_master', '0003_categorymasternew_alter_categorymaster_component'),  # adjust if needed
        ('components', '0008_alter_componentmaster_cost_per_unit_and_more'),
  # replace with actual latest components migration
    ]
    operations = [
        migrations.RunPython(populate_categorymasternew, reverse_code=migrations.RunPython.noop),
    ]

