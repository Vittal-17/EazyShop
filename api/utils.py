from django.utils import timezone

from .models import AdminLog


def log_admin_action(admin_user, action_description):
    """
    Helper function to record admin activity in the AdminLog model.
    """
    # Check if the user is authenticated, otherwise log as System
    admin = admin_user if admin_user and admin_user.is_authenticated else None
    
    AdminLog.objects.create(
        admin=admin,
        action=action_description,
        timestamp=timezone.now()
    )