from io import BytesIO

from datetime import date, datetime
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.db.models import Count, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.utils.text import slugify
from django.views import View
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import CreateView, DetailView, ListView, TemplateView

from .forms import (
    AttendanceSubmissionForm,
    BroadcastForm,
    CustomFormFieldWizardForm,
    CustomFormCreateForm,
    EventWizardForm,
    EventForm,
    build_custom_form_runtime,
)
from .models import Attendance, Attendee, BroadcastMessage, Event, FormField, FormSubmission, FormTemplate
from .services import (
    send_attendance_confirmation,
    send_broadcast_message,
    send_custom_form_announcement,
    send_custom_form_confirmation,
    send_event_announcement,
)
from .utils import build_qr_svg


def _consenting_emails():
    attendee_emails = set(
        Attendee.objects.exclude(email__isnull=True)
        .exclude(email="")
        .values_list("email", flat=True)
    )
    custom_form_emails = set(
        FormSubmission.objects.exclude(email__isnull=True)
        .exclude(email="")
        .values_list("email", flat=True)
    )
    return sorted(attendee_emails | custom_form_emails)


def _absolute_public_url(path: str) -> str:
    base = getattr(settings, "SYSTEM_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    return f"{base}{path}"


def _build_unique_key(raw_label: str, existing_keys):
    base = slugify(raw_label).replace("-", "_")
    if not base:
        base = "field"
    candidate = base
    i = 2
    while candidate in existing_keys:
        candidate = f"{base}_{i}"
        i += 1
    return candidate


def _resolve_custom_form_event(custom_form: FormTemplate, value: str | None):
    if value:
        explicit = custom_form.events.filter(public_id=value).first()
        if explicit:
            return explicit

    now = timezone.now()
    upcoming = (
        custom_form.events.filter(is_link_active=True, event_date__gte=now)
        .order_by("event_date")
        .first()
    )
    if upcoming:
        return upcoming
    return custom_form.events.filter(is_link_active=True).order_by("-event_date").first()


def _custom_form_autofill_payload(custom_form: FormTemplate, attendee: Attendee):
    latest_submission = (
        custom_form.submissions.filter(attendee=attendee).order_by("-submitted_at").first()
    )
    payload = dict(latest_submission.payload) if latest_submission else {}
    enriched = {
        "full_name": attendee.full_name or "",
        "name": attendee.full_name or "",
        "rotary_club": attendee.rotary_club or "",
        "rotaract_club": attendee.rotaract_club or "",
        "additional_comments": attendee.additional_comments or "",
        "communication_preference": attendee.communication_preference or "",
        "category": attendee.category or "",
    }
    for key, value in enriched.items():
        payload.setdefault(key, value)
    return _json_safe_payload(payload)


def _json_safe_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _json_safe_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_value(v) for v in value]
    return value


def _json_safe_payload(payload: dict):
    return {k: _json_safe_value(v) for k, v in payload.items()}


class HomeView(TemplateView):
    template_name = "attendance/home.html"


class PublicEventListView(ListView):
    model = Event
    template_name = "attendance/public/event_list.html"
    context_object_name = "events"

    def get_queryset(self):
        qs = Event.objects.filter(is_link_active=True).order_by("event_date")
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(title__icontains=q)
                | Q(description__icontains=q)
                | Q(venue__icontains=q)
            )
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["q"] = self.request.GET.get("q", "")
        return context


class UserLoginView(LoginView):
    template_name = "attendance/auth/login.html"
    redirect_authenticated_user = True

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["username"].widget.attrs.update({"class": "input-field", "placeholder": "Username"})
        form.fields["password"].widget.attrs.update({"class": "input-field", "placeholder": "Password"})
        return form


class UserLogoutView(LogoutView):
    next_page = "attendance:home"


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "attendance/dashboard/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["event_count"] = Event.objects.count()
        context["attendee_count"] = Attendee.objects.count()
        context["attendance_count"] = Attendance.objects.count()
        context["custom_form_count"] = FormTemplate.objects.count()
        context["upcoming_events"] = Event.objects.filter(event_date__gte=timezone.now())[:5]
        context["recent_attendances"] = Attendance.objects.select_related("event", "attendee")[:6]
        context["frequent_attendees"] = (
            Attendee.objects.annotate(total=Count("attendances")).filter(total__gt=0).order_by("-total")[:5]
        )
        context["low_participation"] = (
            Attendee.objects.annotate(total=Count("attendances")).order_by("total", "full_name")[:5]
        )
        return context


class EventListView(LoginRequiredMixin, ListView):
    model = Event
    template_name = "attendance/dashboard/event_list.html"
    context_object_name = "events"

    def get_queryset(self):
        qs = Event.objects.annotate(attendance_total=Count("attendances"))
        query = self.request.GET.get("q", "").strip()
        if query:
            qs = qs.filter(
                Q(title__icontains=query)
                | Q(description__icontains=query)
                | Q(venue__icontains=query)
            )
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["q"] = self.request.GET.get("q", "")
        return context


class EventCreateView(LoginRequiredMixin, CreateView):
    model = Event
    form_class = EventForm
    template_name = "attendance/dashboard/event_form.html"

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        if self.object.announce_to_members:
            recipients = _consenting_emails()
            event_url = self.request.build_absolute_uri(self.object.get_public_url())
            sent = send_event_announcement(self.object, recipients, event_url=event_url)
            messages.success(self.request, f"Event created and announced to {sent} members.")
        else:
            messages.success(self.request, "Event created and QR link is ready.")
        return response

    def get_success_url(self):
        return reverse("attendance:event-detail", kwargs={"public_id": self.object.public_id})


class EventWizardView(LoginRequiredMixin, TemplateView):
    template_name = "attendance/dashboard/event_wizard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        wizard_form = kwargs.get("wizard_form")
        if wizard_form is None:
            has_custom_fields = len(self.request.session.get("event_wizard_fields", [])) > 0
            wizard_form = EventWizardForm(initial={"form_type": "custom" if has_custom_fields else "default"})
        context["wizard_form"] = wizard_form
        context["field_form"] = kwargs.get("field_form") or CustomFormFieldWizardForm(
            initial={"order": (len(self.request.session.get("event_wizard_fields", [])) + 1)}
        )
        context["fields"] = self.request.session.get("event_wizard_fields", [])
        return context

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action")
        if action == "reset":
            request.session["event_wizard_fields"] = []
            request.session.modified = True
            messages.info(request, "Wizard reset. Start again.")
            return redirect("attendance:event-wizard")

        if action == "add_field":
            field_form = CustomFormFieldWizardForm(request.POST)
            wizard_form = EventWizardForm(initial={"form_type": "custom"})
            if field_form.is_valid():
                fields = request.session.get("event_wizard_fields", [])
                item = field_form.cleaned_data.copy()
                existing_keys = {f["key"] for f in fields}
                item["key"] = _build_unique_key(item["label"], existing_keys)
                item["order"] = int(item["order"])
                item["required"] = bool(item["required"])
                fields.append(item)
                fields = sorted(fields, key=lambda f: (int(f["order"]), f["key"]))
                request.session["event_wizard_fields"] = fields
                request.session.modified = True
                messages.success(request, "Field added.")
                return redirect("attendance:event-wizard")
            messages.error(request, "Please correct the field details below.")
            return self.render_to_response(
                self.get_context_data(wizard_form=wizard_form, field_form=field_form)
            )

        wizard_form = EventWizardForm(request.POST)
        field_form = CustomFormFieldWizardForm(
            initial={"order": (len(request.session.get("event_wizard_fields", [])) + 1)}
        )
        if not wizard_form.is_valid():
            messages.error(request, "Please fix the event details.")
            return self.render_to_response(
                self.get_context_data(wizard_form=wizard_form, field_form=field_form)
            )

        data = wizard_form.cleaned_data
        custom_template = None
        if data["form_type"] == "custom":
            fields = request.session.get("event_wizard_fields", [])
            if not fields:
                messages.error(request, "Add at least one custom field before creating this event.")
                return self.render_to_response(
                    self.get_context_data(wizard_form=wizard_form, field_form=field_form)
                )
            custom_template = FormTemplate.objects.create(
                title=f"{data['title']} Registration",
                description=data.get("description", ""),
                is_active=data["is_link_active"],
                created_by=request.user,
            )
            for item in fields:
                FormField.objects.create(
                    template=custom_template,
                    label=item["label"],
                    key=item["key"],
                    field_type=item["field_type"],
                    required=item["required"],
                    options=item.get("options", ""),
                    order=item["order"],
                )

        event = Event.objects.create(
            title=data["title"],
            description=data.get("description", ""),
            venue=data.get("venue", ""),
            event_date=data["event_date"],
            status=data["status"],
            announce_to_members=False,
            is_link_active=data["is_link_active"],
            form_template=custom_template,
            created_by=request.user,
        )

        request.session["event_wizard_fields"] = []
        request.session.modified = True

        if data.get("send_invites_now"):
            recipients = _consenting_emails()
            event_url = _absolute_public_url(event.get_public_url())
            sent = send_event_announcement(event, recipients, event_url=event_url)
            messages.success(request, f"Event created and invitations sent to {sent} emails.")
        else:
            messages.success(request, "Event created successfully.")

        return redirect("attendance:event-detail", public_id=event.public_id)


class EventDetailView(LoginRequiredMixin, DetailView):
    model = Event
    template_name = "attendance/dashboard/event_detail.html"
    context_object_name = "event"

    def get_object(self, queryset=None):
        queryset = queryset or self.get_queryset()
        return get_object_or_404(queryset, public_id=self.kwargs["public_id"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        event = self.object
        public_url = _absolute_public_url(event.get_public_url())
        context["public_url"] = public_url
        context["qr_svg"] = mark_safe(build_qr_svg(public_url))
        context["attendances"] = event.attendances.select_related("attendee")
        context["recipient_count"] = len(_consenting_emails())
        return context


@require_POST
def event_send_invites_view(request, public_id):
    if not request.user.is_authenticated:
        return redirect("attendance:login")
    event = get_object_or_404(Event, public_id=public_id)
    if not event.is_link_active:
        messages.warning(request, "Activate the event link before sending invitations.")
        return redirect("attendance:event-detail", public_id=event.public_id)
    recipients = _consenting_emails()
    event_url = _absolute_public_url(event.get_public_url())
    sent = send_event_announcement(event, recipients, event_url=event_url)
    messages.success(request, f"Event invitation sent to {sent} members.")
    return redirect("attendance:event-detail", public_id=event.public_id)


@require_POST
def event_toggle_link_view(request, public_id):
    if not request.user.is_authenticated:
        return redirect("attendance:login")
    event = get_object_or_404(Event, public_id=public_id)
    event.is_link_active = not event.is_link_active
    event.save(update_fields=["is_link_active"])
    state = "active" if event.is_link_active else "inactive"
    messages.success(request, f"Event registration link is now {state}.")
    return redirect("attendance:event-detail", public_id=event.public_id)


class AttendeeListView(LoginRequiredMixin, ListView):
    model = Attendee
    template_name = "attendance/dashboard/attendee_list.html"
    context_object_name = "attendees"
    paginate_by = 25

    def get_queryset(self):
        qs = Attendee.objects.annotate(attendance_total=Count("attendances"))
        query = self.request.GET.get("q", "").strip()
        if query:
            qs = qs.filter(
                Q(full_name__icontains=query)
                | Q(email__icontains=query)
                | Q(phone__icontains=query)
            )
        return qs.distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["q"] = self.request.GET.get("q", "")
        return context


class AttendeeDetailView(LoginRequiredMixin, DetailView):
    model = Attendee
    template_name = "attendance/dashboard/attendee_detail.html"
    context_object_name = "attendee"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["history"] = self.object.attendances.select_related("event")
        return context


class CustomFormListView(LoginRequiredMixin, ListView):
    model = FormTemplate
    template_name = "attendance/dashboard/custom_form_list.html"
    context_object_name = "custom_forms"

    def get_queryset(self):
        return FormTemplate.objects.annotate(submission_total=Count("submissions"))


class CustomFormCreateView(LoginRequiredMixin, CreateView):
    model = FormTemplate
    form_class = CustomFormCreateForm
    template_name = "attendance/dashboard/custom_form_create.html"

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        if form.cleaned_data.get("announce_now"):
            recipients = _consenting_emails()
            form_url = self.request.build_absolute_uri(self.object.get_public_url())
            sent = send_custom_form_announcement(self.object, recipients, form_url=form_url)
            messages.success(self.request, f"Custom form created and announced to {sent} members.")
        else:
            messages.success(self.request, "Custom form created. Add fields next.")
        return response

    def get_success_url(self):
        return reverse("attendance:custom-form-detail", kwargs={"public_id": self.object.public_id})


class CustomFormDetailView(LoginRequiredMixin, DetailView):
    model = FormTemplate
    template_name = "attendance/dashboard/custom_form_detail.html"
    context_object_name = "custom_form"

    def get_object(self, queryset=None):
        queryset = queryset or self.get_queryset()
        return get_object_or_404(queryset, public_id=self.kwargs["public_id"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        custom_form = self.object
        context["field_form"] = kwargs.get("field_form") or CustomFormFieldWizardForm(
            initial={"order": (custom_form.fields.count() + 1)}
        )
        context["submissions"] = custom_form.submissions.all()[:50]
        context["public_url"] = _absolute_public_url(custom_form.get_public_url())
        context["recipient_count"] = len(_consenting_emails())
        return context


@require_POST
def custom_form_add_field_view(request, public_id):
    if not request.user.is_authenticated:
        return redirect("attendance:login")
    custom_form = get_object_or_404(FormTemplate, public_id=public_id)
    form = CustomFormFieldWizardForm(request.POST)
    if form.is_valid():
        field = form.save(commit=False)
        field.template = custom_form
        existing = set(custom_form.fields.values_list("key", flat=True))
        field.key = _build_unique_key(field.label, existing)
        field.save()
        messages.success(request, "Field added to custom form.")
        next_order = custom_form.fields.count() + 1
        return redirect("attendance:custom-form-detail", public_id=custom_form.public_id)
    else:
        messages.error(request, "Could not add field. Please check the highlighted errors.")
        view = CustomFormDetailView()
        view.setup(request, public_id=public_id)
        view.object = custom_form
        return view.render_to_response(view.get_context_data(field_form=form))


@require_POST
def custom_form_toggle_view(request, public_id):
    if not request.user.is_authenticated:
        return redirect("attendance:login")
    custom_form = get_object_or_404(FormTemplate, public_id=public_id)
    custom_form.is_active = not custom_form.is_active
    custom_form.save(update_fields=["is_active"])
    state = "activated" if custom_form.is_active else "deactivated"
    messages.success(request, f"Custom form {state}.")
    return redirect("attendance:custom-form-detail", public_id=custom_form.public_id)


@require_POST
def custom_form_send_invites_view(request, public_id):
    if not request.user.is_authenticated:
        return redirect("attendance:login")
    custom_form = get_object_or_404(FormTemplate, public_id=public_id)
    if not custom_form.is_active:
        messages.warning(request, "Activate the form before sending invitations.")
        return redirect("attendance:custom-form-detail", public_id=custom_form.public_id)
    if not custom_form.fields.exists():
        messages.warning(request, "Add at least one field before sending invitations.")
        return redirect("attendance:custom-form-detail", public_id=custom_form.public_id)
    recipients = _consenting_emails()
    form_url = _absolute_public_url(custom_form.get_public_url())
    sent = send_custom_form_announcement(custom_form, recipients, form_url=form_url)
    messages.success(request, f"Custom form invitation sent to {sent} members.")
    return redirect("attendance:custom-form-detail", public_id=custom_form.public_id)


def custom_form_public_view(request, public_id):
    custom_form = get_object_or_404(FormTemplate, public_id=public_id)
    linked_active_event_exists = custom_form.events.filter(is_link_active=True).exists()
    if not custom_form.is_active and not linked_active_event_exists and not request.user.is_authenticated:
        return render(
            request,
            "attendance/public/link_inactive.html",
            {
                "page_title": "Form Unavailable",
                "headline": "This registration page is currently unavailable.",
                "message": "Please check back later or contact the organizer for an updated link.",
            },
            status=200,
        )
    selected_event = _resolve_custom_form_event(
        custom_form,
        request.POST.get("event_public_id") or request.GET.get("event"),
    )

    if request.method == "POST":
        runtime_form = build_custom_form_runtime(custom_form, request.POST)
        if runtime_form.is_valid():
            data = runtime_form.cleaned_data
            email = (data.get("email") or "").strip().lower()
            phone = (data.get("phone") or "").strip()
            payload = _json_safe_payload({k: v for k, v in data.items() if k not in {"email", "phone"}})

            attendee_by_email = Attendee.objects.filter(email__iexact=email).first() if email else None
            attendee_by_phone = Attendee.objects.filter(phone=phone).first() if phone else None
            if attendee_by_email and attendee_by_phone and attendee_by_email.pk != attendee_by_phone.pk:
                runtime_form.add_error(None, "The email and contact belong to different records.")
            else:
                attendee = attendee_by_email or attendee_by_phone
                if attendee is None:
                    attendee = Attendee(
                        full_name=str(payload.get("full_name") or payload.get("name") or "KEB Member"),
                        email=email or None,
                        phone=phone or None,
                        category="usual_suspect",
                        communication_preference="both" if email else "tel",
                        rotary_club=str(payload.get("rotary_club") or ""),
                        rotaract_club=str(payload.get("rotaract_club") or ""),
                    )
                if email:
                    attendee.email = email
                if phone:
                    attendee.phone = phone
                attendee.receive_future_emails = True
                attendee.save()

                FormSubmission.objects.create(
                    template=custom_form,
                    attendee=attendee,
                    email=email or None,
                    phone=phone or None,
                    payload=payload,
                    receive_future_emails=True,
                )
                if selected_event:
                    Attendance.objects.create(
                        event=selected_event,
                        attendee=attendee,
                        source="link",
                    )
                send_custom_form_confirmation(
                    attendee.email,
                    custom_form,
                    event=selected_event,
                    attendee=attendee,
                )
                return render(
                    request,
                    "attendance/public/custom_form_success.html",
                    {"custom_form": custom_form, "attendee": attendee, "event": selected_event},
                )
    else:
        runtime_form = build_custom_form_runtime(custom_form)

    return render(
        request,
        "attendance/public/custom_form_public.html",
        {"custom_form": custom_form, "runtime_form": runtime_form, "event": selected_event},
    )


class BroadcastCreateView(LoginRequiredMixin, CreateView):
    model = BroadcastMessage
    form_class = BroadcastForm
    template_name = "attendance/dashboard/broadcast_create.html"

    def form_valid(self, form):
        form.instance.sent_by = self.request.user
        recipients = _consenting_emails()
        sent = send_broadcast_message(form.instance.title, form.instance.body, recipients)
        form.instance.recipient_count = sent
        messages.success(self.request, f"Alert sent to {sent} recipients.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("attendance:dashboard")


def event_attendance_view(request, public_id):
    event = get_object_or_404(Event, public_id=public_id)
    if not event.is_link_active and not request.user.is_authenticated:
        return render(
            request,
            "attendance/public/link_inactive.html",
            {
                "page_title": "Registration Closed",
                "headline": "This event registration link is currently inactive.",
                "message": "The organizer may reactivate it soon. Please check back later.",
                "event": event,
            },
            status=200,
        )
    if event.form_template_id:
        custom_url = reverse("attendance:custom-form-public", kwargs={"public_id": event.form_template.public_id})
        return redirect(f"{custom_url}?event={event.public_id}")
    if event.status != "open" and request.method == "POST":
        raise Http404("This event is not open for confirmation.")

    if request.method == "POST":
        form = AttendanceSubmissionForm(request.POST, event=event)
        if form.is_valid():
            attendee, attendance, created = form.save()
            send_attendance_confirmation(attendee, event)
            return render(
                request,
                "attendance/public/attendance_success.html",
                {"event": event, "attendee": attendee, "attendance": attendance, "created": created},
            )
    else:
        initial_source = "qr" if request.GET.get("src") == "qr" else "link"
        form = AttendanceSubmissionForm(event=event, initial={"source": initial_source})

    return render(request, "attendance/public/event_attendance.html", {"event": event, "form": form})


class EventLookupView(View):
    http_method_names = ["post"]

    def post(self, request, public_id):
        get_object_or_404(Event, public_id=public_id)
        email = (request.POST.get("email") or "").strip().lower()
        phone = (request.POST.get("phone") or "").strip()
        if not email and not phone:
            return JsonResponse({"found": False})

        attendee_by_email = Attendee.objects.filter(email__iexact=email).first() if email else None
        attendee_by_phone = Attendee.objects.filter(phone=phone).first() if phone else None

        if attendee_by_email and attendee_by_phone and attendee_by_email.pk != attendee_by_phone.pk:
            return JsonResponse(
                {
                    "found": False,
                    "conflict": True,
                    "message": "Email and phone belong to different attendees.",
                },
                status=409,
            )

        attendee = attendee_by_email or attendee_by_phone
        if not attendee:
            return JsonResponse({"found": False})

        return JsonResponse(
            {
                "found": True,
                "attendee": {
                    "full_name": attendee.full_name,
                    "email": attendee.email or "",
                    "phone": attendee.phone or "",
                    "category": attendee.category,
                    "rotary_club": attendee.rotary_club,
                    "rotaract_club": attendee.rotaract_club,
                    "communication_preference": attendee.communication_preference,
                    "additional_comments": attendee.additional_comments,
                    "receive_future_emails": attendee.receive_future_emails,
                },
            }
        )


class CustomFormLookupView(View):
    http_method_names = ["post"]

    def post(self, request, public_id):
        custom_form = get_object_or_404(FormTemplate, public_id=public_id)
        email = (request.POST.get("email") or "").strip().lower()
        phone = (request.POST.get("phone") or "").strip()
        if not email and not phone:
            return JsonResponse({"found": False})

        attendee_by_email = Attendee.objects.filter(email__iexact=email).first() if email else None
        attendee_by_phone = Attendee.objects.filter(phone=phone).first() if phone else None

        if attendee_by_email and attendee_by_phone and attendee_by_email.pk != attendee_by_phone.pk:
            return JsonResponse(
                {
                    "found": False,
                    "conflict": True,
                    "message": "Email and contact belong to different records.",
                },
                status=409,
            )

        attendee = attendee_by_email or attendee_by_phone
        if not attendee:
            return JsonResponse({"found": False})

        payload = _custom_form_autofill_payload(custom_form, attendee)
        return JsonResponse(
            {
                "found": True,
                "attendee": {
                    "email": attendee.email or "",
                    "phone": attendee.phone or "",
                    "payload": payload,
                },
            }
        )


@require_GET
def event_qr_download_view(request, public_id):
    from reportlab.graphics import renderPDF
    from reportlab.graphics.barcode import qr
    from reportlab.graphics.shapes import Drawing
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    event = get_object_or_404(Event, public_id=public_id)
    if not request.user.is_authenticated:
        return redirect("attendance:login")

    public_url = _absolute_public_url(event.get_public_url())
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    pdf.setTitle(f"{event.title} Attendance Sheet")
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(20 * mm, height - 25 * mm, event.title)
    pdf.setFont("Helvetica", 10)
    pdf.drawString(20 * mm, height - 32 * mm, f"Date: {event.event_date.strftime('%d %b %Y %I:%M %p')}")
    if event.venue:
        pdf.drawString(20 * mm, height - 38 * mm, f"Venue: {event.venue}")
    pdf.drawString(20 * mm, height - 44 * mm, f"Public Link: {public_url}")

    qr_code = qr.QrCodeWidget(public_url)
    bounds = qr_code.getBounds()
    qr_width = bounds[2] - bounds[0]
    qr_height = bounds[3] - bounds[1]
    drawing = Drawing(42 * mm, 42 * mm, transform=[42 * mm / qr_width, 0, 0, 42 * mm / qr_height, 0, 0])
    drawing.add(qr_code)
    renderPDF.draw(drawing, pdf, width - 70 * mm, height - 70 * mm)

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(20 * mm, height - 56 * mm, "Recent attendees")
    y = height - 64 * mm
    pdf.setFont("Helvetica", 10)
    for idx, rec in enumerate(event.attendances.select_related("attendee")[:18], start=1):
        line = f"{idx}. {rec.attendee.full_name} | {rec.attendee.email or '-'} | {rec.confirmed_at.strftime('%d %b %Y %I:%M %p')}"
        pdf.drawString(20 * mm, y, line[:115])
        y -= 6 * mm
        if y < 20 * mm:
            pdf.showPage()
            y = height - 20 * mm

    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="event-{event.public_id}.pdf"'
    return response


def custom_permission_denied_view(request, exception):
    return render(request, "errors/403.html", status=403)


def custom_page_not_found_view(request, exception):
    return render(request, "errors/404.html", status=404)


def custom_server_error_view(request):
    return render(request, "errors/500.html", status=500)
