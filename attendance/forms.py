from django import forms
from django.core.exceptions import ValidationError

from .models import (
    Attendance,
    Attendee,
    BroadcastMessage,
    Event,
    FormField,
    FormSubmission,
    FormTemplate,
)


INPUT_CLASS = (
    "input-field"
)
SELECT_CLASS = (
    "select-field"
)


class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ["title", "description", "venue", "event_date", "status", "announce_to_members", "is_link_active"]
        widgets = {
            "title": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Weekly Rotary Meeting"}),
            "description": forms.Textarea(
                attrs={
                    "class": INPUT_CLASS,
                    "rows": 3,
                    "placeholder": "Add a short event note for attendees.",
                }
            ),
            "venue": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Kampala Serena Hotel"}),
            "event_date": forms.DateTimeInput(
                attrs={"class": INPUT_CLASS, "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "status": forms.Select(attrs={"class": SELECT_CLASS}),
            "announce_to_members": forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded border-gray-300 text-rotary-blue"}),
            "is_link_active": forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded border-gray-300 text-rotary-blue"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        value = self.initial.get("event_date") or getattr(self.instance, "event_date", None)
        if value:
            self.initial["event_date"] = value.strftime("%Y-%m-%dT%H:%M")


class AttendanceSubmissionForm(forms.Form):
    email = forms.EmailField(
        required=False,
        label="Email address",
        widget=forms.EmailInput(attrs={"class": INPUT_CLASS, "placeholder": "name@example.com"}),
    )
    phone = forms.CharField(
        required=False,
        label="Contact",
        widget=forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "+256..."}),
    )
    full_name = forms.CharField(
        required=False,
        label="Full Name",
        widget=forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Your full name"}),
    )
    category = forms.ChoiceField(
        required=True,
        label="Select your category *",
        choices=Attendee.CATEGORY_CHOICES,
        widget=forms.Select(attrs={"class": SELECT_CLASS}),
    )
    rotary_club = forms.CharField(
        required=False,
        label="Rotary Club",
        widget=forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "List of Rotary Clubs"}),
    )
    rotaract_club = forms.CharField(
        required=False,
        label="Rotaract Club",
        widget=forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "List of Rotaract Clubs"}),
    )
    communication_preference = forms.ChoiceField(
        required=True,
        label="How would you like to receive KEB information *",
        choices=Attendee.COMMUNICATION_CHOICES,
        widget=forms.Select(attrs={"class": SELECT_CLASS}),
    )
    additional_comments = forms.CharField(
        required=False,
        label="Additional comments",
        widget=forms.Textarea(
            attrs={
                "class": INPUT_CLASS,
                "rows": 3,
                "placeholder": "Anything the organizer should know.",
            }
        ),
    )
    receive_future_emails = forms.BooleanField(
        required=False,
        label="I want to receive future emails about Kampala Early Bird activities",
        widget=forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded border-gray-300 text-rotary-blue"}),
    )
    source = forms.ChoiceField(
        required=False,
        choices=Attendance.SOURCE_CHOICES,
        initial="link",
        widget=forms.HiddenInput(),
    )

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop("event")
        super().__init__(*args, **kwargs)
        self.existing_attendee = None

    def clean_email(self):
        email = self.cleaned_data.get("email")
        return (email or "").strip().lower()

    def clean_phone(self):
        phone = self.cleaned_data.get("phone")
        return (phone or "").strip()

    def clean(self):
        cleaned = super().clean()
        email = cleaned.get("email")
        phone = cleaned.get("phone")

        if not email and not phone:
            raise ValidationError("Please provide at least your email or phone number.")

        attendee_by_email = Attendee.objects.filter(email__iexact=email).first() if email else None
        attendee_by_phone = Attendee.objects.filter(phone=phone).first() if phone else None

        if attendee_by_email and attendee_by_phone and attendee_by_email.pk != attendee_by_phone.pk:
            raise ValidationError(
                "That email and phone belong to different profiles. Please use one matching identifier or contact the organizer."
            )

        self.existing_attendee = attendee_by_email or attendee_by_phone
        attendee = self.existing_attendee

        if attendee:
            cleaned.setdefault("full_name", attendee.full_name)
            cleaned.setdefault("category", attendee.category)
            cleaned.setdefault("communication_preference", attendee.communication_preference)
            cleaned.setdefault("rotary_club", attendee.rotary_club)
            cleaned.setdefault("rotaract_club", attendee.rotaract_club)

        if not cleaned.get("full_name"):
            self.add_error("full_name", "Full name is required.")
        if not cleaned.get("rotary_club"):
            self.add_error("rotary_club", "Rotary Club is required.")
        if not cleaned.get("rotaract_club"):
            self.add_error("rotaract_club", "Rotaract Club is required.")

        return cleaned

    def save(self):
        data = self.cleaned_data
        attendee = self.existing_attendee

        if attendee is None:
            attendee = Attendee()

        attendee.email = data.get("email") or attendee.email
        attendee.phone = data.get("phone") or attendee.phone
        attendee.full_name = data.get("full_name") or attendee.full_name
        attendee.category = data.get("category") or attendee.category or "usual_suspect"
        attendee.rotary_club = data.get("rotary_club", "")
        attendee.rotaract_club = data.get("rotaract_club", "")
        attendee.communication_preference = (
            data.get("communication_preference") or attendee.communication_preference or "both"
        )
        attendee.additional_comments = data.get("additional_comments", "")
        wants_updates = data.get("receive_future_emails")
        if wants_updates and attendee.communication_preference in {"email", "both"}:
            attendee.receive_future_emails = True
        attendee.save()

        attendance = Attendance.objects.create(
            event=self.event,
            attendee=attendee,
            source=data.get("source") or "link",
        )
        return attendee, attendance, True


class CustomFormCreateForm(forms.ModelForm):
    announce_now = forms.BooleanField(
        required=False,
        label="Send invitation email immediately after creating this form",
        widget=forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded border-gray-300 text-rotary-blue"}),
    )

    class Meta:
        model = FormTemplate
        fields = ["title", "description", "is_active"]
        widgets = {
            "title": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Membership Update Form"}),
            "description": forms.Textarea(attrs={"class": INPUT_CLASS, "rows": 3}),
            "is_active": forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded border-gray-300 text-rotary-blue"}),
        }


class CustomFormFieldForm(forms.ModelForm):
    class Meta:
        model = FormField
        fields = ["label", "key", "field_type", "required", "options", "order"]
        widgets = {
            "label": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "key": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "full_name"}),
            "field_type": forms.Select(attrs={"class": SELECT_CLASS}),
            "required": forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded border-gray-300 text-rotary-blue"}),
            "options": forms.Textarea(
                attrs={
                    "class": INPUT_CLASS,
                    "rows": 3,
                    "placeholder": "Option one\nOption two\nOption three",
                }
            ),
            "order": forms.NumberInput(attrs={"class": INPUT_CLASS, "min": 1}),
        }


class BroadcastForm(forms.ModelForm):
    class Meta:
        model = BroadcastMessage
        fields = ["title", "body"]
        widgets = {
            "title": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Important Club Update"}),
            "body": forms.Textarea(attrs={"class": INPUT_CLASS, "rows": 6}),
        }


class EventWizardForm(forms.Form):
    FORM_TYPE_CHOICES = [
        ("default", "Use Default Attendance Form"),
        ("custom", "Build Custom Form For This Event"),
    ]

    title = forms.CharField(
        label="Event title",
        widget=forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Weekly Fellowship Meeting"}),
    )
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": INPUT_CLASS, "rows": 3}),
    )
    venue = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Kampala Serena Hotel"}),
    )
    event_date = forms.DateTimeField(
        widget=forms.DateTimeInput(
            attrs={"class": INPUT_CLASS, "type": "datetime-local"},
            format="%Y-%m-%dT%H:%M",
        ),
        input_formats=["%Y-%m-%dT%H:%M"],
    )
    status = forms.ChoiceField(choices=Event.STATUS_CHOICES, widget=forms.Select(attrs={"class": SELECT_CLASS}))
    is_link_active = forms.BooleanField(
        required=False,
        initial=True,
        label="Keep registration link active",
        widget=forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded border-gray-300 text-rotary-blue"}),
    )
    form_type = forms.ChoiceField(
        choices=FORM_TYPE_CHOICES,
        initial="default",
        widget=forms.RadioSelect(attrs={"class": "h-4 w-4 border-gray-300 text-rotary-blue"}),
    )
    send_invites_now = forms.BooleanField(
        required=False,
        label="Send invitations immediately after creating event",
        widget=forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded border-gray-300 text-rotary-blue"}),
    )


class CustomFormFieldWizardForm(forms.ModelForm):
    class Meta:
        model = FormField
        fields = ["label", "field_type", "required", "options", "order"]
        widgets = {
            "label": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Field label"}),
            "field_type": forms.Select(attrs={"class": SELECT_CLASS}),
            "required": forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded border-gray-300 text-rotary-blue"}),
            "options": forms.Textarea(
                attrs={
                    "class": INPUT_CLASS,
                    "rows": 3,
                    "placeholder": "Only for select fields. One option per line.",
                }
            ),
            "order": forms.NumberInput(attrs={"class": "input-field w-24", "min": 1}),
        }

def build_custom_form_runtime(template: FormTemplate, post_data=None):
    class RuntimeForm(forms.Form):
        email = forms.EmailField(
            required=False,
            label="Email",
            widget=forms.EmailInput(attrs={"class": INPUT_CLASS}),
        )
        phone = forms.CharField(
            required=False,
            label="Contact",
            widget=forms.TextInput(attrs={"class": INPUT_CLASS}),
        )

        receive_future_emails = forms.BooleanField(
            required=False,
            label="I want to receive future emails about Kampala Early Bird meetings and updates",
            widget=forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded border-gray-300 text-rotary-blue"}),
        )

        def clean(self):
            cleaned = super().clean()
            if not cleaned.get("email") and not cleaned.get("phone"):
                raise ValidationError("Please provide at least your email or contact.")
            return cleaned

    for field in template.fields.all():
        attrs = {"class": INPUT_CLASS}
        if field.field_type == FormField.TYPE_TEXT:
            form_field = forms.CharField(required=field.required, label=field.label, widget=forms.TextInput(attrs=attrs))
        elif field.field_type == FormField.TYPE_EMAIL:
            form_field = forms.EmailField(required=field.required, label=field.label, widget=forms.EmailInput(attrs=attrs))
        elif field.field_type == FormField.TYPE_PHONE:
            form_field = forms.CharField(required=field.required, label=field.label, widget=forms.TextInput(attrs=attrs))
        elif field.field_type == FormField.TYPE_TEXTAREA:
            form_field = forms.CharField(
                required=field.required,
                label=field.label,
                widget=forms.Textarea(attrs={**attrs, "rows": 4}),
            )
        elif field.field_type == FormField.TYPE_SELECT:
            options = [o.strip() for o in field.options.splitlines() if o.strip()]
            choices = [("", "Select an option")] + [(o, o) for o in options]
            form_field = forms.ChoiceField(required=field.required, label=field.label, choices=choices, widget=forms.Select(attrs={"class": SELECT_CLASS}))
        elif field.field_type == FormField.TYPE_CHECKBOX:
            form_field = forms.BooleanField(
                required=field.required,
                label=field.label,
                widget=forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded border-gray-300 text-rotary-blue"}),
            )
        elif field.field_type == FormField.TYPE_DATE:
            form_field = forms.DateField(
                required=field.required,
                label=field.label,
                widget=forms.DateInput(attrs={**attrs, "type": "date"}),
            )
        else:
            form_field = forms.DecimalField(
                required=field.required,
                label=field.label,
                widget=forms.NumberInput(attrs={**attrs, "step": "any"}),
            )

        RuntimeForm.base_fields[field.key] = form_field

    return RuntimeForm(post_data) if post_data is not None else RuntimeForm()
