from django.core.management.base import BaseCommand
from core.models import BusinessType


class Command(BaseCommand):
    help = 'Populate database with default business types'

    def handle(self, *args, **options):
        business_types = [
            ('Grocery Store', 'Retail grocery and food products'),
            ('Restaurant', 'Food service and dining'),
            ('Agriculture', 'Farming and agricultural products'),
            ('Retail Store', 'General retail merchandise'),
            ('E-commerce', 'Online retail and digital commerce'),
            ('Healthcare', 'Medical and health services'),
            ('Education', 'Educational services and institutions'),
            ('Real Estate', 'Property sales and management'),
            ('Automotive', 'Car sales and automotive services'),
            ('Technology', 'IT services and software'),
            ('Beauty & Wellness', 'Beauty, spa, and wellness services'),
            ('Professional Services', 'Consulting and professional services'),
            ('Manufacturing', 'Production and manufacturing'),
            ('Transportation', 'Logistics and transportation services'),
            ('Entertainment', 'Entertainment and event services'),
        ]

        created_count = 0
        for name, description in business_types:
            business_type, created = BusinessType.objects.get_or_create(
                name=name,
                defaults={'description': description}
            )
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Created business type: {name}')
                )

        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully populated {created_count} business types'
            )
        )