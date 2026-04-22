from django.contrib import admin

from .models import Attendance, Attendee, BroadcastMessage, Event, FormField, FormSubmission, FormTemplate


@admin.register(Attendee)
class AttendeeAdmin(admin.ModelAdmin):
    list_display = (
        "full_name",
        "email",
        "phone",
        "category",
        "communication_preference",
        "receive_future_emails",
        "created_at",
    )
    search_fields = ("full_name", "email", "phone", "rotary_club", "rotaract_club")
    list_filter = ("category", "communication_preference", "created_at")


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "event_date", "status", "announce_to_members", "created_by", "created_at")
    search_fields = ("title", "venue", "description")
    list_filter = ("status", "event_date")
    readonly_fields = ("public_id", "created_at", "updated_at")


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ("event", "attendee", "confirmed_at", "source")
    search_fields = ("event__title", "attendee__full_name", "attendee__email", "attendee__phone")
    list_filter = ("source", "confirmed_at")


@admin.register(FormTemplate)
class FormTemplateAdmin(admin.ModelAdmin):
    list_display = ("title", "is_active", "created_by", "created_at")
    list_filter = ("is_active", "created_at")
    search_fields = ("title", "description")
    readonly_fields = ("public_id", "created_at", "updated_at")


@admin.register(FormField)
class FormFieldAdmin(admin.ModelAdmin):
    list_display = ("template", "label", "key", "field_type", "required", "order")
    list_filter = ("field_type", "required")
    search_fields = ("label", "key", "template__title")


@admin.register(FormSubmission)
class FormSubmissionAdmin(admin.ModelAdmin):
    list_display = ("template", "email", "phone", "receive_future_emails", "submitted_at")
    list_filter = ("receive_future_emails", "submitted_at")
    search_fields = ("template__title", "email", "phone")


@admin.register(BroadcastMessage)
class BroadcastMessageAdmin(admin.ModelAdmin):
    list_display = ("title", "recipient_count", "sent_by", "created_at")
    search_fields = ("title", "body")

# Register your models here.
