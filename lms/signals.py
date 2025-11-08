from django.db.models.signals import post_save
from django.dispatch import receiver
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.contrib.auth.models import Group
from .models import Task, TaskAssignment, Notification

@receiver(post_save, sender=TaskAssignment)
def send_task_assignment_notification(sender, instance, created, **kwargs):
    if created:
        # 1. Save Notification to DB
        Notification.objects.create(
            user=instance.user,
            message=f'You have been assigned a new task: "{instance.task.title}"'
        )

        # 2. Send WebSocket event
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"user_{instance.user.id}",
            {
                "type": "send_notification",
                "message": f'You have been assigned a new task: "{instance.task.title}"'
            }
        )



@receiver(post_save, sender=Task)
def notify_admin_on_completion(sender, instance, **kwargs):
    if instance.completed:
        admin_group = Group.objects.filter(name="Admin").first()
        if not admin_group:
            return

        channel_layer = get_channel_layer()

        for admin in admin_group.user_set.all():
            Notification.objects.create(
                user=admin,
                message=f'Task "{instance.title}" has been marked completed by {instance.user.username}'
            )

            async_to_sync(channel_layer.group_send)(
                "notifications",
                {
                    "type": "send_notification",
                    "message": f'Task "{instance.title}" completed by {instance.user.username}'
                }
            )
