class FakeUser:
    def __init__(self, name, uid):
        self._name = name
        self._id = uid

    def getUserName(self):
        return self._name

    def getId(self):
        return self._id


class FakeSecurityManager:
    def __init__(self, user):
        self._user = user

    def getUser(self):
        return self._user


def test_anonymous_special_user(monkeypatch):
    from plone.observability import auth

    monkeypatch.setattr(
        auth,
        "getSecurityManager",
        lambda: FakeSecurityManager(FakeUser("Anonymous User", None)),
    )
    assert auth.get_auth_info() == (False, None)


def test_authenticated_user(monkeypatch):
    from plone.observability import auth

    monkeypatch.setattr(
        auth,
        "getSecurityManager",
        lambda: FakeSecurityManager(FakeUser("alice", "alice-id")),
    )
    assert auth.get_auth_info() == (True, "alice-id")


def test_no_user_is_anonymous(monkeypatch):
    from plone.observability import auth

    monkeypatch.setattr(auth, "getSecurityManager", lambda: FakeSecurityManager(None))
    assert auth.get_auth_info() == (False, None)


def test_capture_auth_sets_environ_flag(monkeypatch):
    from plone.observability import auth

    monkeypatch.setattr(
        auth,
        "getSecurityManager",
        lambda: FakeSecurityManager(FakeUser("alice", "alice-id")),
    )

    class FakeRequest:
        def __init__(self):
            self.environ = {}

    class FakeEvent:
        def __init__(self, request):
            self.request = request

    request = FakeRequest()
    auth.capture_auth(FakeEvent(request))
    assert request.environ["plone.observability.authenticated"] is True
