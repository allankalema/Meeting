import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Attendee(TimeStampedModel):
    CATEGORY_CHOICES = [
        ("usual_suspect", "Usual Suspect :)"),
        ("keb_member", "KEB Member"),
        ("rotarian_other_club", "Rotarian (Other Club)"),
        ("rotaractor", "Rotaractor"),
        ("guest", "Guest"),
    ]
    COMMUNICATION_CHOICES = [
        ("email", "Email"),
        ("tel", "Tel"),
        ("both", "Both"),
        ("none", "None"),
    ]

    full_name = models.CharField(max_length=180)
    email = models.EmailField(blank=True, null=True, unique=True)
    phone = models.CharField(max_length=30, blank=True, null=True, unique=True)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default="usual_suspect")
    rotary_club = models.CharField(max_length=180, blank=True)
    rotaract_club = models.CharField(max_length=180, blank=True)
    communication_preference = models.CharField(
        max_length=20,
        choices=COMMUNICATION_CHOICES,
        default="both",
    )
    additional_comments = models.TextField(blank=True)
    receive_future_emails = models.BooleanField(default=True)

    class Meta:
        ordering = ["full_name"]

    def clean(self):
        super().clean()
        if not self.email and not self.phone:
            raise ValidationError("At least one of email or phone is required.")

    def save(self, *args, **kwargs):
        self.email = (self.email or "").strip().lower() or None
        self.phone = (self.phone or "").strip() or None
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.full_name} ({self.email or self.phone})"


class Event(TimeStampedModel):
    STATUS_CHOICES = [
        ("open", "Open"),
        ("closed", "Closed"),
        ("archived", "Archived"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    title = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    venue = models.CharField(max_length=180, blank=True)
    event_date = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="open")
    announce_to_members = models.BooleanField(default=False)
    is_link_active = models.BooleanField(default=True)
    form_template = models.ForeignKey(
        "FormTemplate",
        on_delete=models.SET_NULL,
        related_name="events",
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="events",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-event_date"]

    def __str__(self):
        return self.title

    def get_public_url(self):
        return reverse("attendance:event-public", kwargs={"public_id": self.public_id})


class Attendance(models.Model):
    SOURCE_CHOICES = [
        ("qr", "QR Code"),
        ("link", "Direct Link"),
        ("manual", "Manual"),
    ]

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="attendances")
    attendee = models.ForeignKey(Attendee, on_delete=models.CASCADE, related_name="attendances")
    confirmed_at = models.DateTimeField(auto_now_add=True)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default="link")

    class Meta:
        ordering = ["-confirmed_at"]

    def __str__(self):
        return f"{self.attendee.full_name} - {self.event.title}"


class FormTemplate(TimeStampedModel):
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    title = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="custom_forms",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def get_public_url(self):
        return reverse("attendance:custom-form-public", kwargs={"public_id": self.public_id})


class FormField(TimeStampedModel):
    TYPE_TEXT = "text"
    TYPE_EMAIL = "email"
    TYPE_PHONE = "phone"
    TYPE_TEXTAREA = "textarea"
    TYPE_SELECT = "select"
    TYPE_CHECKBOX = "checkbox"
    TYPE_DATE = "date"
    TYPE_NUMBER = "number"

    FIELD_TYPE_CHOICES = [
        (TYPE_TEXT, "Text"),
        (TYPE_EMAIL, "Email"),
        (TYPE_PHONE, "Phone"),
        (TYPE_TEXTAREA, "Long Text"),
        (TYPE_SELECT, "Select"),
        (TYPE_CHECKBOX, "Checkbox"),
        (TYPE_DATE, "Date"),
        (TYPE_NUMBER, "Number"),
    ]

    template = models.ForeignKey(FormTemplate, on_delete=models.CASCADE, related_name="fields")
    label = models.CharField(max_length=180)
    key = models.SlugField(max_length=80)
    field_type = models.CharField(max_length=20, choices=FIELD_TYPE_CHOICES, default=TYPE_TEXT)
    required = models.BooleanField(default=False)
    options = models.TextField(blank=True, help_text="For select fields, use one option per line.")
    order = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["template", "key"],
                name="unique_field_key_per_template",
            )
        ]

    def __str__(self):
        return f"{self.template.title} - {self.label}"


class FormSubmission(models.Model):
    template = models.ForeignKey(FormTemplate, on_delete=models.CASCADE, related_name="submissions")
    attendee = models.ForeignKey(
        Attendee,
        on_delete=models.SET_NULL,
        related_name="custom_form_submissions",
        null=True,
        blank=True,
    )
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=30, blank=True, null=True)
    payload = models.JSONField(default=dict, blank=True)
    receive_future_emails = models.BooleanField(default=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"{self.template.title} submission at {self.submitted_at}"


class BroadcastMessage(TimeStampedModel):
    title = models.CharField(max_length=180)
    body = models.TextField()
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="broadcast_messages",
        null=True,
        blank=True,
    )
    recipient_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title
