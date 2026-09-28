from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailOrUsernameBackend(ModelBackend):
    """Lets people sign in with either their username or their e-mail address."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if not username or password is None:
            return None
        user = UserModel._default_manager.filter(username__iexact=username).first()
        if user is None and "@" in username:
            matches = list(UserModel._default_manager.filter(email__iexact=username)[:2])
            user = matches[0] if len(matches) == 1 else None
        if user is None:
            # Run the hasher once to keep timing similar for unknown users.
            UserModel().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
