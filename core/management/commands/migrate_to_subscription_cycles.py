from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models.user import UserProfile
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Migrate existing users from calendar month to subscription cycle billing'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN MODE - No changes will be made')
            )
        
        # Get all regular users
        all_users = UserProfile.objects.filter(user_type='user')
        
        self.stdout.write(f'Found {all_users.count()} regular users to migrate')
        
        migrated_count = 0
        skipped_count = 0
        
        for profile in all_users:
            # Skip if already has subscription cycle
            if profile.billing_cycle_end:
                self.stdout.write(f'  - {profile.user.username}: Already has billing cycle, skipping')
                skipped_count += 1
                continue
            
            # Migrate user to subscription cycle
            if not dry_run:
                self.migrate_user_to_subscription_cycle(profile)
                migrated_count += 1
                self.stdout.write(f'  ✓ {profile.user.username}: Migrated to subscription cycle')
            else:
                self.stdout.write(f'  → Would migrate {profile.user.username} to subscription cycle')
                migrated_count += 1
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Migration completed: {migrated_count} migrated, {skipped_count} skipped'
            )
        )

    def migrate_user_to_subscription_cycle(self, profile):
        """Migrate a single user to subscription cycle"""
        today = timezone.now().date()
        
        # Set subscription start date based on user creation date
        # This gives existing users their "anniversary" date
        if profile.created_at:
            # Use the day of month from creation, but current month/year
            creation_date = profile.created_at.date()
            try:
                # Try to use same day of month
                subscription_start = today.replace(day=creation_date.day)
                
                # If the date is in the future this month, use previous month
                if subscription_start > today:
                    if subscription_start.month == 1:
                        subscription_start = subscription_start.replace(
                            year=subscription_start.year - 1, 
                            month=12
                        )
                    else:
                        subscription_start = subscription_start.replace(
                            month=subscription_start.month - 1
                        )
            except ValueError:
                # Day doesn't exist in current month (e.g., Feb 30)
                # Use last day of previous month
                if today.month == 1:
                    subscription_start = today.replace(
                        year=today.year - 1, 
                        month=12, 
                        day=31
                    )
                else:
                    # Get last day of previous month
                    subscription_start = today.replace(month=today.month - 1, day=1)
                    subscription_start = subscription_start.replace(
                        day=28 if subscription_start.month == 2 else 30
                    )
        else:
            # Fallback: start cycle from today
            subscription_start = today
        
        # Set billing cycle end to 30 days from start
        billing_cycle_end = subscription_start + timedelta(days=30)
        
        # If billing cycle has already passed, extend to next cycle
        while billing_cycle_end <= today:
            billing_cycle_end += timedelta(days=30)
        
        # Update profile
        profile.subscription_start_date = subscription_start
        profile.billing_cycle_end = billing_cycle_end
        
        # Don't reset usage for existing users to avoid giving them extra quota
        # They'll get fresh quota on next renewal
        
        profile.save(update_fields=[
            'subscription_start_date', 
            'billing_cycle_end'
        ])
        
        logger.info(
            f'Migrated user {profile.user.username} to subscription cycle: '
            f'{subscription_start} to {billing_cycle_end}'
        )