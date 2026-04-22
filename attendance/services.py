from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


def _get_logo_url():
    return getattr(
        settings,
        "EMAIL_LOGO_URL",
        "https://lh7-rt.googleusercontent.com/formsz/AN7BsVCO555mykrJa8wCgSU-sThPvkxoibc8l-neYhaOTUhQcnW0prdoJ86WW1p0PYIRJIHYY3Z47nm4FIj367YJhoJdrB45NLmHimCyJmYpftIeTxktm9Kbq6_eEGLSQZixjuBOK5Owi9-j-tBJk43mlhZc6blCep6T347ne0R6Dhz44zxoJFpE_jlYhXSmL9gnQEzuFy8KyV3hJj3n=w1080?key=3xl6ABnanH7cOznxJpMnqA",
    )


def _send_email(subject, recipients, text_template, html_template, context):
    if not recipients:
        return 0
    context = {**context, "email_logo_url": _get_logo_url()}
    body_text = render_to_string(text_template, context)
    body_html = render_to_string(html_template, context)

    sent = 0
    for email in recipients:
        message = EmailMultiAlternatives(
            subject=subject,
            body=body_text,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com"),
            to=[email],
        )
        message.attach_alternative(body_html, "text/html")
        try:
            message.send(fail_silently=False)
            sent += 1
        except Exception:
            continue
    return sent


def send_attendance_confirmation(attendee, event):
    if not attendee.email:
        return 0
    return _send_email(
        subject=f"Attendance confirmed: {event.title}",
        recipients=[attendee.email],
        text_template="attendance/emails/attendance_confirmation.txt",
        html_template="attendance/emails/attendance_confirmation.html",
        context={"attendee": attendee, "event": event},
    )


def send_event_announcement(event, recipients, event_url=""):
    return _send_email(
        subject=f"New Meeting Announcement: {event.title}",
        recipients=recipients,
        text_template="attendance/emails/event_announcement.txt",
        html_template="attendance/emails/event_announcement.html",
        context={"event": event, "event_url": event_url},
    )


def send_custom_form_announcement(custom_form, recipients, form_url=""):
    return _send_email(
        subject=f"Event Registration: {custom_form.title}",
        recipients=recipients,
        text_template="attendance/emails/custom_form_announcement.txt",
        html_template="attendance/emails/custom_form_announcement.html",
        context={"custom_form": custom_form, "form_url": form_url},
    )


def send_custom_form_confirmation(email, custom_form):
    if not email:
        return 0
    return _send_email(
        subject=f"Submission received: {custom_form.title}",
        recipients=[email],
        text_template="attendance/emails/custom_form_confirmation.txt",
        html_template="attendance/emails/custom_form_confirmation.html",
        context={"custom_form": custom_form},
    )


def send_broadcast_message(title, body, recipients):
    return _send_email(
        subject=title,
        recipients=recipients,
        text_template="attendance/emails/broadcast.txt",
        html_template="attendance/emails/broadcast.html",
        context={"title": title, "body": body},
    )
