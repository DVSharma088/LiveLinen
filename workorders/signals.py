from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import PackagingStage

@receiver(post_save, sender=PackagingStage)
def update_workorder_status_on_stage_save(sender, instance, **kwargs):
    instance.work_order.check_and_update_status()
