from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.template.loader import render_to_string
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse

def build_verification_link(request, user):
    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    path = reverse('verify_email', kwargs={'uidb64': uidb64, 'token': token})
    # Absolute URL
    return request.build_absolute_uri(path)

def send_verification_email(request, user):
    link = build_verification_link(request, user)
    subject = "Confirmá tu email — Mas Finanzas"
    body_txt = render_to_string('emails/verify_email.txt', {'user': user, 'link': link})
    body_html = render_to_string('emails/verify_email.html', {'user': user, 'link': link})
    send_mail(
        subject,
        body_txt,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        html_message=body_html,
    )
