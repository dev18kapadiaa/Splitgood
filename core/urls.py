from django.urls import path
from django.views.generic import RedirectView
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('signup/', views.signup, name='signup'),
    path('signup/verify/', views.signup_verify, name='signup_verify'),
    path('login/', views.user_login, name='login'),
    path('logout/', views.user_logout, name='logout'),

    path('auth/google/', RedirectView.as_view(url='/accounts/google/login/', permanent=False), name='google_login'),
    path('auth/phone/', views.phone_login, name='phone_login'),
    path('auth/phone/verify/', views.phone_verify, name='phone_verify'),
    path('auth/oauth/phone/', views.oauth_phone_capture, name='oauth_phone_capture'),
    path('auth/oauth/phone/verify/', views.oauth_phone_verify, name='oauth_phone_verify'),

    path('forgot-password/', views.forgot_password, name='forgot_password'),
    path('forgot-password/verify/', views.reset_password_verify, name='reset_password_verify'),

    path('dashboard/', views.dashboard, name='dashboard'),
    path('profile/', views.profile, name='profile'),
    path('profile/update-phone/', views.profile_update_phone, name='profile_update_phone'),
    path('profile/verify-phone/', views.profile_verify_phone, name='profile_verify_phone'),
    path('activity/', views.activity_feed, name='activity_feed'),

    path('groups/', views.group_list, name='group_list'),
    path('groups/create/', views.group_create, name='group_create'),
    path('groups/<uuid:group_id>/', views.group_detail, name='group_detail'),
    path('groups/<uuid:group_id>/edit/', views.group_edit, name='group_edit'),
    path('groups/<uuid:group_id>/invite/', views.group_invite, name='group_invite'),
    path('groups/<uuid:group_id>/settle/', views.settle_up, name='settle_up'),
    path('groups/<uuid:group_id>/leave/', views.leave_group, name='leave_group'),

    path('groups/<uuid:group_id>/expenses/add/', views.expense_create, name='expense_create'),
    path('expenses/<uuid:expense_id>/', views.expense_detail, name='expense_detail'),
    path('expenses/<uuid:expense_id>/edit/', views.expense_edit, name='expense_edit'),
    path('expenses/<uuid:expense_id>/delete/', views.expense_delete, name='expense_delete'),

    path('api/fx-rates/', views.api_fx_rates, name='api_fx_rates'),
]
