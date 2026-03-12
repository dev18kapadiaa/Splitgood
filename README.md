# Splitgood - Expense Splitting Application

## Overview

Splitgood is a production-ready expense splitting web application (similar to Splitwise) built with Django and vanilla HTML/CSS/JS. Users can track shared expenses, manage group balances, and settle debts with friends, roommates, and trip companions.

**Core Features:**
- User authentication with email-based accounts
- Groups for organizing expense sharing
- Expense tracking with multiple split types (equal, unequal, percentage-based)
- Balance calculations and optimal settlement suggestions
- Activity feed and payment history
- Group invitations and member management
- Beautiful responsive UI with indigo/purple theme
- RAW/UNIFIED currency toggle with live FX rates and passive sign detection

## User Preferences

- Preferred communication style: Simple, everyday language
- Frontend: Django templates with vanilla HTML/CSS/JS (no React framework)
- Design: Modern, clean UI with CSS custom properties for theming

## System Architecture

### Backend Architecture

**Framework:** Django 5.x with server-rendered templates
- Primary application logic in the `core` Django app
- Uses Django's built-in authentication with a custom User model (UUID primary keys)
- Server-side rendering with Django templates (located in `templates/`)
- Minimal JavaScript for progressive enhancement (`static/js/main.js`)

**Database Models:**
- `User` - Extended AbstractUser with profile fields (display_name, currency, timezone, avatar_color)
- `Group` - Expense sharing groups with ownership and settings
- `GroupMembership` - Many-to-many relationship with roles (admin/member) and invitation status
- `Expense` - Individual expenses with split type configuration
- `ExpenseShare` - How each expense is divided among participants
- `Payment` - Settlement payments between users
- `Comment` - Threaded comments on expenses
- `Activity` - Audit log for group actions
- `GroupInvite` - Pending group invitations

**Split Strategies Supported:**
- Equal split among selected participants
- Unequal/custom amounts per participant
- Percentage-based splits

### Frontend Architecture

**Django Templates:**
- Full-featured responsive UI in `templates/`
- Base template with navigation and common elements
- Dedicated templates for auth, dashboard, groups, expenses, profile
- Custom CSS in `static/css/styles.css` with CSS variables for theming
- Progressive enhancement JavaScript in `static/js/main.js`

**Design System:**
- Primary color: Indigo (#6366f1)
- Accent color: Purple (#8b5cf6)
- Clean card-based layouts with subtle shadows
- Responsive grid for all screen sizes

### URL Routes

**Authentication:**
- `/auth/login/` - Login page
- `/auth/signup/` - Registration page
- `/auth/logout/` - Logout action
- `/profile/` - User profile management

**Main Application:**
- `/` - Landing page (unauthenticated) or redirects to dashboard
- `/dashboard/` - User dashboard with balance, groups, activity
- `/groups/` - List of user's groups
- `/groups/create/` - Create new group
- `/groups/<uuid>/` - Group detail page
- `/groups/<uuid>/edit/` - Edit group
- `/groups/<uuid>/expenses/add/` - Add expense
- `/groups/<uuid>/expenses/<uuid>/` - Expense detail
- `/groups/<uuid>/settle/` - Record settlement payment

### Data Storage

**Primary Database:** PostgreSQL
- Django ORM for all database operations
- UUID primary keys for all models (better for distributed systems)
- Database migrations managed by Django (`core/migrations/`)

### Running the Application

The application is started via `python manage.py runserver` which spawns the Django development server:
```bash
python manage.py runserver 0.0.0.0::8000
```

**Management Commands:**
- `python manage.py migrate` - Apply database migrations
- `python manage.py seed_data` - Seed demo data (5 users, 2 groups, 11 expenses)
- `python manage.py collectstatic` - Collect static files for production

## Demo Accounts

After running `python manage.py seed_data`:
- **alice@example.com** / password123 - Member of "Roommates" and "Paris Trip 2025"
- **bob@example.com** / password123 - Admin of "Paris Trip 2025"
- **charlie@example.com** / password123 - Member of "Roommates"
- **diana@example.com** / password123 - Member of "Paris Trip 2025"
- **evan@example.com** / password123 - Member of "Paris Trip 2025"

## Environment Variables Required

- `DATABASE_URL` - PostgreSQL connection string
- `SESSION_SECRET` - Django secret key (falls back to insecure dev key if not set)

## Project Structure

```
├── core/                   # Main Django app
│   ├── models.py          # Data models (User, Group, Expense, etc.)
│   ├── views.py           # View functions
│   ├── forms.py           # Django forms
│   ├── urls.py            # URL routing
│   ├── admin.py           # Admin site configuration
│   └── management/        # Custom management commands
├── splitgood/             # Django project settings
│   ├── settings.py        # Project configuration
│   └── urls.py            # Root URL configuration
├── templates/             # Django templates
│   ├── base.html          # Base template
│   ├── auth/              # Authentication templates
│   └── core/              # App templates (dashboard, groups, etc.)
├── static/                # Static assets
│   ├── css/styles.css     # Main stylesheet
│   ├── js/main.js         # JavaScript enhancements
│   └── js/currency_toggle.js  # RAW/UNIFIED toggle logic
├── manage.py              # Django CLI
└── server/index.ts        # Wrapper to spawn Django server
```

## Recent Changes

- **2026-02-25**: RAW/UNIFIED currency toggle with live FX rates
  - **RAW mode (default)**: Shows per-currency balances exactly as stored, separate lines for each currency
  - **UNIFIED mode**: Converts all currencies to user-selected target currency using live FX rates, merges per-user-pair balances
  - **Passive sign detection**: In RAW mode, internally converts multi-currency balances to USD to determine overall sign (positive/negative/zero) for color coding
  - **Color logic**: GREEN = positive (owed to you), RED = negative (you owe), neutral = settled; applies globally on dashboard and group pages
  - **FX rate API**: `/api/fx-rates/` endpoint using Frankfurter API (free, no API key), cached for 10 minutes server-side
  - **Toggle reversibility**: Unified view is purely UI-only, never persists converted values, always recomputes from raw ledger
  - **Settlement protection**: Settle Up page has no toggle, always operates in RAW currency mode
  - **New files**: `core/fx_service.py` (FX rate fetching/caching), `static/js/currency_toggle.js` (toggle UI logic)
  - **Updated templates**: dashboard.html, group_detail.html (toggle bar, data attributes for JS), base.html (JS include)
  - **Updated CSS**: Toggle switch, currency selector, FX timestamp, unified badge styles
- **2026-02-23**: Phone login, forgot password & profile overhaul
  - **Phone login is login-only**: No account creation via phone. If phone not registered, user sees "Please sign up first" error. Removed `phone_set_name` view and route entirely.
  
  - **Profile email non-editable**: Email field is locked/disabled on profile page. Cannot be changed.
  - **Profile phone edit via overlay modal**: Clicking "Edit" opens a modal with country code + phone input. Uniqueness check before OTP send. OTP must verify before phone is saved. Old number replaced atomically.
  - **Profile save redirects to dashboard**: After saving profile changes, user is redirected to dashboard with success message instead of staying on profile page.
  - **New API endpoints**: `profile/update-phone/` (sends OTP for phone change), `profile/verify-phone/` (verifies OTP and saves new phone)
  - **Updated forms**: `ForgotPasswordForm` now has channel, email, country_code, phone fields. `UserProfileForm` only has display_name, currency, timezone (no email/phone).
- **2026-02-18**: Major auth/invitation overhaul
  - **Removed invitation acceptance flow**: Registered users are auto-added to groups immediately (status='accepted'), no pending state
  - **Auto-merge on signup**: Unregistered invitees get placeholder accounts; when they sign up, all ledger data (expenses, shares, payments, activity) is atomically transferred and placeholder is deleted
  - **Multi-step traditional signup**: Name (required), email, phone (required) with country code, password → OTP phone verification → account creation
  - **Google OAuth phone capture**: New OAuth users must verify phone number via OTP before account creation; sets is_oauth_only=True
  - **GroupMembership status**: Removed 'pending' status, only 'accepted' and 'placeholder' remain
  - **New views**: signup_verify, oauth_phone_capture, oauth_phone_verify, forgot_password, reset_password_verify, leave_group
  - **New templates**: signup_verify.html, oauth_phone_capture.html, oauth_phone_verify.html, forgot_password.html, reset_password_verify.html, leave_group_confirm.html
  - **Updated templates**: signup.html (required fields, country code), login.html (forgot password link), profile.html (phone, groups, ledger), group_detail.html (leave button), group_list.html (removed pending invites)
  - **Twilio credentials**: Configured TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER as secrets.
  - **Placeholder User system**: Unregistered invitees get shadow accounts (inactive Users with @placeholder.splitgood.local emails) that can participate in expenses/payments before accepting invites
  - **PersonIdentity.linked_user**: Changed from OneToOneField to ForeignKey (multiple identities per user), added placeholder_user OneToOneField
  - **GroupMembership 'placeholder' status**: Placeholder users have GroupMembership(status='placeholder'), removed 'declined' status
  - **Ledger transfer on acceptance**: Atomic reassignment of all ExpenseShare, Payment, Expense, Activity from placeholder_user to real_user when invite accepted
  - **Auto-linking on signup**: Matches PersonIdentities by email/phone, creates pending (not auto-accepted) memberships, marks invites as used
  - **Google OAuth**: django-allauth integration with auto-merging by email via CustomSocialAccountAdapter
  - **Phone OTP authentication**: Full flow (send code, verify, set name) with Twilio integration and graceful degradation
  - **Redesigned invitations**: Radio button channel selection (email/phone), dummy name requirements, PersonIdentity records for unregistered users
  - **Celery task system**: Database backend for async notifications (invites, expenses, payments, daily reminders, weekly summaries)
  - **Balance calculation fix**: Corrected formula to owed_to_user - user_owes - payments_received + payments_made
  - **New models**: PersonIdentity, PhoneOTP added to core/models.py
  - **New files**: core/adapters.py, core/tasks.py, splitgood/celery.py
  - **New templates**: phone_login.html, phone_verify.html, phone_set_name.html
  - **Updated templates**: login.html and signup.html now include Google OAuth button and phone login link
  - **Updated CSS**: Google button, auth divider, channel selector, pending identity badge styles
- **2026-01-30**: Complete Django expense-splitting application implemented
  - Full authentication system with email login
  - Group management with invitations
  - Expense tracking with 3 split strategies
  - Balance calculation and settlement suggestions
  - Activity feed and commenting
  - Modern responsive UI with CSS custom properties
  - Demo data seeding command
