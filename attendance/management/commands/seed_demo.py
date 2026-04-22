import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from attendance.models import Attendance, Attendee, Event, FormField, FormSubmission, FormTemplate


class Command(BaseCommand):
    help = "Seed realistic demo data for presentation."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete previously seeded demo records before creating new ones.",
        )

    def handle(self, *args, **options):
        user = get_user_model().objects.order_by("id").first()
        if not user:
            raise CommandError("No user found. Create a user first, then run this command.")

        if options["reset"]:
            self._reset_demo()

        attendees = self._seed_attendees()
        custom_template = self._seed_custom_template(user)
        events = self._seed_events(user, custom_template)
        self._seed_attendance(attendees, events)
        self._seed_custom_submissions(attendees, custom_template)

        self.stdout.write(self.style.SUCCESS(f"Demo data ready. Event owner user: {user.username}"))

    def _reset_demo(self):
        Event.objects.filter(title__startswith="Demo:").delete()
        FormTemplate.objects.filter(title__startswith="Demo:").delete()
        Attendee.objects.filter(email__contains="@demo.keb").delete()

    def _seed_attendees(self):
        pool = [
            ("Alex Nsubuga", "alex.nsubuga@demo.keb", "+256700000101", "keb_member", "Kampala Early Bird", ""),
            ("Brenda Achieng", "brenda.achieng@demo.keb", "+256700000102", "rotarian_other_club", "Kampala South", ""),
            ("Charles Otema", "charles.otema@demo.keb", "+256700000103", "rotaractor", "", "Kampala City Rotaract"),
            ("Diana Nakato", "diana.nakato@demo.keb", "+256700000104", "guest", "", ""),
            ("Eric Mugisha", "eric.mugisha@demo.keb", "+256700000105", "usual_suspect", "Kampala Early Bird", ""),
            ("Faith Nanyonjo", "faith.nanyonjo@demo.keb", "+256700000106", "keb_member", "Kampala Early Bird", ""),
            ("George Kato", "george.kato@demo.keb", "+256700000107", "rotarian_other_club", "Entebbe", ""),
            ("Hellen Nabukeera", "hellen.nabukeera@demo.keb", "+256700000108", "rotaractor", "", "Makerere Rotaract"),
            ("Isaac Ssemanda", "isaac.ssemanda@demo.keb", "+256700000109", "guest", "", ""),
            ("Jane Tendo", "jane.tendo@demo.keb", "+256700000110", "usual_suspect", "Kampala Early Bird", ""),
            ("Kevin Byaruhanga", "kevin.byaruhanga@demo.keb", "+256700000111", "keb_member", "Kampala Early Bird", ""),
            ("Linda Nampijja", "linda.nampijja@demo.keb", "+256700000112", "guest", "", ""),
        ]

        attendees = []
        for full_name, email, phone, category, rotary_club, rotaract_club in pool:
            attendee, _ = Attendee.objects.update_or_create(
                email=email,
                defaults={
                    "full_name": full_name,
                    "phone": phone,
                    "category": category,
                    "rotary_club": rotary_club,
                    "rotaract_club": rotaract_club,
                    "communication_preference": "both",
                    "additional_comments": "Demo attendee profile",
                    "receive_future_emails": True,
                },
            )
            attendees.append(attendee)
        return attendees

    def _seed_custom_template(self, user):
        template, _ = FormTemplate.objects.update_or_create(
            title="Demo: Project Visit Registration",
            defaults={
                "description": "Custom event form for project visits and partner sign-ins.",
                "is_active": True,
                "created_by": user,
            },
        )

        desired_fields = [
            ("Role", "role", "select", True, "Member\nGuest Speaker\nPartner\nVolunteer", 1),
            ("Age", "age", "number", False, "", 2),
            ("Company or Organization", "company", "text", False, "", 3),
            ("Arrival Date", "arrival_date", "date", True, "", 4),
            ("Need transport support?", "needs_transport", "checkbox", False, "", 5),
            ("Notes", "notes", "textarea", False, "", 6),
        ]

        for label, key, field_type, required, options, order in desired_fields:
            FormField.objects.update_or_create(
                template=template,
                key=key,
                defaults={
                    "label": label,
                    "field_type": field_type,
                    "required": required,
                    "options": options,
                    "order": order,
                },
            )
        return template

    def _seed_events(self, user, custom_template):
        now = timezone.now()
        events_data = [
            ("Demo: Weekly Fellowship Breakfast", "Networking and weekly fellowship session.", "Fairway Hotel, Kampala", now + timedelta(days=1), "open", True, None),
            ("Demo: Community Health Outreach", "Volunteer health camp planning and deployment.", "Nakawa Community Grounds", now + timedelta(days=4), "open", True, None),
            ("Demo: Project Visit Registration", "Custom-form event for project site visit attendees.", "Mityana Project Site", now + timedelta(days=7), "open", True, custom_template),
            ("Demo: Youth Leadership Forum", "Mentorship circle with Rotaract and youth leaders.", "Mestil Hotel", now + timedelta(days=10), "open", True, None),
            ("Demo: Club Assembly - Quarterly", "Internal strategy and reporting meeting.", "Kabira Country Club", now + timedelta(days=13), "open", True, None),
        ]

        events = []
        for title, description, venue, event_date, status, is_link_active, template in events_data:
            event, _ = Event.objects.update_or_create(
                title=title,
                defaults={
                    "description": description,
                    "venue": venue,
                    "event_date": event_date,
                    "status": status,
                    "announce_to_members": False,
                    "is_link_active": is_link_active,
                    "form_template": template,
                    "created_by": user,
                },
            )
            events.append(event)
        return events

    def _seed_attendance(self, attendees, events):
        sources = ["link", "qr", "manual"]
        for event in events:
            attendees_for_event = random.sample(attendees, k=random.randint(5, 10))
            for attendee in attendees_for_event:
                Attendance.objects.get_or_create(
                    event=event,
                    attendee=attendee,
                    source=random.choice(sources),
                )

            if event.status == "open":
                repeat_people = random.sample(attendees_for_event, k=min(2, len(attendees_for_event)))
                for attendee in repeat_people:
                    Attendance.objects.create(
                        event=event,
                        attendee=attendee,
                        source=random.choice(sources),
                    )

    def _seed_custom_submissions(self, attendees, custom_template):
        roles = ["Member", "Guest Speaker", "Partner", "Volunteer"]
        for attendee in random.sample(attendees, k=8):
            payload = {
                "role": random.choice(roles),
                "age": random.randint(21, 58),
                "company": random.choice(["NSSF Uganda", "KCCA", "Makerere", "Private Sector Foundation", ""]),
                "arrival_date": (timezone.localdate() + timedelta(days=random.randint(1, 14))).isoformat(),
                "needs_transport": random.choice([True, False]),
                "notes": random.choice(
                    [
                        "Will arrive early.",
                        "Bringing one guest.",
                        "Need parking guidance.",
                        "",
                    ]
                ),
            }
            FormSubmission.objects.get_or_create(
                template=custom_template,
                email=attendee.email,
                defaults={
                    "attendee": attendee,
                    "phone": attendee.phone,
                    "payload": payload,
                    "receive_future_emails": True,
                },
            )
