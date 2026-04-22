# Meeting Attendance System

## Attendance Flow
- Organizer creates an event from `Dashboard -> Create event`.
- System generates a public event attendance URL and QR code (`SVG`) for sharing.
- Attendee opens the public event page and confirms attendance.
- Attendance is unique per attendee per event to prevent duplicate check-ins.

## Auto-fill Flow
- Public form starts with `email` and `phone/contact`.
- Lookup runs against saved attendee profiles using `email OR phone`.
- If a match is found, the rest of attendee fields auto-fill instantly.
- If no match is found, attendee fills details normally and profile is saved for reuse.
- If both email and phone are entered but map to different profiles, submission is blocked to avoid bad merges.

## Organizer Workflow
- Log in from `/login/`.
- Open `/dashboard/` for the custom organizer dashboard.
- Create and manage events at `/dashboard/events/`.
- Open event detail to copy the attendance URL and download QR code.
- Send event invitations from event detail (`Send Invitations`) to all consented members.
- Build custom forms from `/dashboard/custom-forms/`, publish/deactivate them, and view submissions.
- Send club-wide alerts from `/dashboard/alerts/new/`.
- View all attendees at `/dashboard/attendees/` and inspect attendance history per attendee.

## QR Code Generation
- QR codes are generated from each event's public URL.
- Event detail page renders the QR preview and provides downloadable `SVG`.
- Install dependency:
  - `pip install qrcode`

## Email Setup (Environment Variables)
- Email delivery is now environment-driven through SMTP.
- Copy `.env.example` values into your environment and set real credentials:
  - `EMAIL_BACKEND`
  - `EMAIL_HOST`
  - `EMAIL_PORT`
  - `EMAIL_HOST_USER`
  - `EMAIL_HOST_PASSWORD`
  - `EMAIL_USE_TLS`
  - `EMAIL_USE_SSL`
  - `DEFAULT_FROM_EMAIL`
  - `EMAIL_LOGO_URL`
- Attendance confirmations, event invitations, custom-form invitations, and broadcast alerts use branded HTML + text templates.

## Notes
- One constant attendance form is used for all events.
- Organizers can also create additional custom forms with custom fields.
- Member email consent is tracked and used for invitation/broadcast targeting.
- Database defaults to SQLite (`db.sqlite3`) unless changed in Django settings.
