from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models.user import UserProfile
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Process subscription cycles - handle renewals and expiries'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )
        parser.add_argument(
            '--initialize-existing',
            action='store_true',
            help='Initialize subscription cycles for existing users without billing_cycle_end',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        initialize_existing = options['initialize_existing']
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN MODE - No changes will be made')
            )
        
        today = timezone.now().date()
        
        # Initialize existing users without billing cycle
        if initialize_existing:
            self.initialize_existing_users(dry_run)
        
        # Process expired subscriptions
        self.process_expired_subscriptions(today, dry_run)
        
        # Process renewals
        self.process_renewals(today, dry_run)
        
        self.stdout.write(
            self.style.SUCCESS('Subscription cycle processing completed')
        )

    def initialize_existing_users(self, dry_run=False):
        """Initialize subscription cycles for existing users"""
        users_without_cycles = UserProfile.objects.filter(
            user_type='user',
            billing_cycle_end__isnull=True
        )
        
        count = users_without_cycles.count()
        self.stdout.write(f'Found {count} users without billing cycles')
        
        if not dry_run:
            for profile in users_without_cycles:
                profile.initialize_subscription_cycle()
                self.stdout.write(f'  ✓ Initialized cycle for {profile.user.username}')
        else:
            for profile in users_without_cycles:
                self.stdout.write(f'  → Would initialize cycle for {profile.user.username}')

    def process_expired_subscriptions(self, today, dry_run=False):
        """Process expired subscriptions"""
        expired_users = UserProfile.objects.filter(
            user_type='user',
            billing_cycle_end__lt=today,
            auto_renewal=False
        )
        
        count = expired_users.count()
        self.stdout.write(f'Found {count} expired subscriptions')
        
        for profile in expired_users:
            plan_before = profile.subscription_plan
            
            if not dry_run:
                profile.handle_subscription_expiry()
                logger.info(f'User {profile.user.username} subscription expired: {plan_before} → {profile.subscription_plan}')
                self.stdout.write(
                    f'  ✓ {profile.user.username}: {plan_before} → {profile.subscription_plan} (expired)'
                )
            else:
                self.stdout.write(
                    f'  → Would downgrade {profile.user.username}: {plan_before} → free (expired)'
                )

    def process_renewals(self, today, dry_run=False):
        """Process automatic renewals"""
        renewal_users = UserProfile.objects.filter(
            user_type='user',
            billing_cycle_end__lt=today,
            auto_renewal=True
        )
        
        count = renewal_users.count()
        self.stdout.write(f'Found {count} auto-renewal subscriptions')
        
        for profile in renewal_users:
            if not dry_run:
                profile.renew_subscription()
                logger.info(f'User {profile.user.username} subscription renewed: {profile.subscription_plan}')
                self.stdout.write(
                    f'  ✓ {profile.user.username}: {profile.subscription_plan} renewed for 30 days'
                )
            else:
                self.stdout.write(
                    f'  → Would renew {profile.user.username}: {profile.subscription_plan} for 30 days'
                )

    def get_subscription_stats(self):
        """Get current subscription statistics"""
        total_users = UserProfile.objects.filter(user_type='user').count()
        
        stats = {}
        for plan in ['free', 'pro', 'pro_plus']:
            count = UserProfile.objects.filter(
                user_type='user', 
                subscription_plan=plan
            ).count()
            stats[plan] = count
        
        expired_count = UserProfile.objects.filter(
            user_type='user',
            billing_cycle_end__lt=timezone.now().date()
        ).count()
        
        return {
            'total_users': total_users,
            'plan_distribution': stats,
            'expired_subscriptions': expired_count
        }