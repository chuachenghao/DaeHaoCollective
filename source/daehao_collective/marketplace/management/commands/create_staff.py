from getpass import getpass

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from marketplace.models import Account, create_account, get_admin_profile


class Command(BaseCommand):
    help = "Create an administrator for the custom DaeHao Collective operations panel."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("email")

    def handle(self, *args, **options):
        username = options["username"].strip()
        email = options["email"].strip().lower()
        if (
            Account.objects.filter(username__iexact=username).exists()
            or Account.objects.filter(email__iexact=email).exists()
        ):
            raise CommandError("This username or email is already registered.")
        password = getpass("Password: ")
        if password != getpass("Confirm password: "):
            raise CommandError("Passwords do not match.")
        user = Account(username=username, email=email, role="ADMIN")
        try:
            user.full_clean(exclude=["password"])
            validate_password(password, user)
        except ValidationError as error:
            raise CommandError(" ".join(error.messages)) from error
        with transaction.atomic():
            user = create_account(username, email, password, "ADMIN")
            get_admin_profile(user)
        self.stdout.write(
            self.style.SUCCESS("Administrator created. Sign in at /operations/login/.")
        )
