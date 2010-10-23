#
# Copyright (c) 2009 Brad Taylor <brad@getcoded.net>
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU Affero General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from django.utils.translation import ugettext_lazy as _

from django.contrib.auth.forms import UserChangeForm, PasswordChangeForm
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse
from django.contrib import messages

from django.shortcuts import render_to_response
from django.http import HttpResponseRedirect, HttpResponseNotAllowed
from django.template import RequestContext
from django.conf import settings

from snowy.accounts.models import UserProfile
from snowy.accounts.forms import InternationalizationForm, OpenIDRegistrationFormUniqueUser, EmailChangeForm

from django_openid_auth import auth
import django_openid_auth.views

def openid_registration(request, template_name='registration/registration_form.html'):
    registration_form = OpenIDRegistrationFormUniqueUser(request.POST or None)

    try:
        openid_response = request.session['openid_response']
    except KeyError:
        return HttpResponseNotAllowed(_(u'No openid_response object for this session!'))

    try:
        attributes = auth._extract_user_details(openid_response)
        registration_form.fields['username'].initial = attributes['nickname']
        registration_form.fields['email'].initial = attributes['email']
    except KeyError:
        pass

    if registration_form.is_valid():
        user = authenticate(openid_response=openid_response,
                            username=registration_form.cleaned_data.get('username', ''),
                            create_user=True)
        # Clear the openid_response from the session so it can't be used to create another account
        del request.session['openid_response']

        if user is not None:
            email = registration_form.cleaned_data.get('email')
            if email:
                user.email = email
            if getattr(settings, 'MODERATE_NEW_USERS', False):
                user.is_active = False

            user.save()
            user.get_profile().save()
            if user.is_active:
                login(request, user)
                return HttpResponseRedirect(settings.LOGIN_REDIRECT_URL)
            else:
                if not getattr(settings, 'MODERATE_NEW_USERS', False):
                    return HttpResponseNotAllowed(_(u'Disabled account'))
                else:
                    return render_to_response("registration/moderated.html", {'user': user,},
                                              context_instance=RequestContext(request))
        else:
            return HttpResponseNotAllowed(_(u'Unknown user'))

    return render_to_response(template_name,
                              {'form' : registration_form},
                              context_instance=RequestContext(request))

def openid_begin(request, **kwargs):
    """A wrapper view around the login_begin view in
    django_openid_auth that features a nicer error display"""
    return django_openid_auth.views.login_begin(request, render_failure=render_openid_failure,
                                                   **kwargs)

def openid_complete(request, **kwargs):
    """A wrapper view around the login_complete view in
    django_openid_auth that features a nicer error page"""
    return django_openid_auth.views.login_complete(request, render_failure=render_openid_failure,
                                                   **kwargs)

def render_openid_failure(request, message, status=403, **kwargs):
    """A wrapper view around the login page to display an error message above
    the login form"""
    # the most common error is a mistyped URL - make the error message less cryptic for this case
    # TODO: Put this "error message correction" in a better place - maybe django_openid_auth
    error_message = unicode(message)
    if error_message.find("OpenID discovery error: Error fetching XRDS document:") > -1:
        error_message = unicode(_("OpenID endpoint not found. Please check your OpenID."))

    messages.add_message(request, messages.ERROR, _("Error logging in: ") + error_message)
    return HttpResponseRedirect(reverse('openid-login'))

@login_required
def accounts_preferences(request, template_name='accounts/preferences.html'):
    user = request.user
    profile = user.get_profile()

    if 'password_form' in request.POST:
        password_form = PasswordChangeForm(user, data=request.POST)
        if password_form.is_valid():
            password_form.save()
    else:
        password_form = PasswordChangeForm(user)

    if 'email_form' in request.POST:
        email_form = EmailChangeForm(request.POST, instance=user)
        if email_form.is_valid():
            email_form.save()
    else:
        email_form = EmailChangeForm(instance=user)

    if 'i18n_form' in request.POST:
        i18n_form = InternationalizationForm(request.POST, instance=profile)
        if i18n_form.is_valid():
            i18n_form.save()
    else:
        i18n_form = InternationalizationForm(instance=profile)

    return render_to_response(template_name,
                              {'user': user, 'i18n_form': i18n_form,
                               'password_form': password_form,
                               'email_form' : email_form},
                              context_instance=RequestContext(request))
