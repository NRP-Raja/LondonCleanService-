import pytest

from app import main as app_main


class FakeCursor:
    def __init__(self, user):
        self.user = user
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, query, params):
        self.params = params

    def fetchone(self):
        return self.user


class FakeConnection:
    def __init__(self, user):
        self.cursor_instance = FakeCursor(user)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def cursor(self):
        return self.cursor_instance


def enable_demo_auth(monkeypatch, environment="development"):
    monkeypatch.setattr(app_main, "DEMO_AUTH_ENABLED", True)
    monkeypatch.setattr(app_main, "ENVIRONMENT", environment)


def test_demo_switch_is_disabled_when_feature_flag_is_off(monkeypatch):
    monkeypatch.setattr(app_main, "DEMO_AUTH_ENABLED", False)
    monkeypatch.setattr(app_main, "ENVIRONMENT", "development")
    monkeypatch.setattr(app_main, "get_db", lambda: pytest.fail("Database must not be queried"))

    with pytest.raises(app_main.HTTPException) as error:
        app_main.demo_switch_role("customer")

    assert error.value.status_code == 404


@pytest.mark.parametrize("environment", ["production", "test", "qa"])
def test_demo_switch_is_disabled_outside_permitted_environments(monkeypatch, environment):
    enable_demo_auth(monkeypatch, environment)
    monkeypatch.setattr(app_main, "get_db", lambda: pytest.fail("Database must not be queried"))

    with pytest.raises(app_main.HTTPException) as error:
        app_main.demo_switch_role("customer")

    assert error.value.status_code == 404


def test_demo_switch_rejects_arbitrary_email(monkeypatch):
    enable_demo_auth(monkeypatch)
    monkeypatch.setattr(app_main, "get_db", lambda: pytest.fail("Database must not be queried"))

    with pytest.raises(app_main.HTTPException) as error:
        app_main.demo_switch_role("attacker@example.com")

    assert error.value.status_code == 400


@pytest.mark.parametrize(
    "account",
    [
        None,
        {
            "id": 4,
            "email": "oliver.smith@example.co.uk",
            "full_name": "Oliver Smith",
            "role": "customer",
            "avatar_url": None,
            "is_active": False,
        },
        {
            "id": 4,
            "email": "oliver.smith@example.co.uk",
            "full_name": "Oliver Smith",
            "role": "manager",
            "avatar_url": None,
            "is_active": True,
        },
    ],
)
def test_demo_switch_does_not_issue_token_for_missing_inactive_or_wrong_role_account(monkeypatch, account):
    enable_demo_auth(monkeypatch)
    monkeypatch.setattr(app_main, "get_db", lambda: FakeConnection(account))
    monkeypatch.setattr(app_main, "create_access_token", lambda payload: pytest.fail("Token must not be issued"))

    with pytest.raises(app_main.HTTPException) as error:
        app_main.demo_switch_role("customer")

    assert error.value.status_code == 404


def test_demo_switch_issues_token_for_approved_active_account(monkeypatch):
    enable_demo_auth(monkeypatch, "staging")
    account = {
        "id": 2,
        "email": "cleaner.elena@cleanlondon.co.uk",
        "full_name": "Elena Petrova",
        "role": "staff",
        "avatar_url": None,
        "is_active": True,
    }
    db = FakeConnection(account)
    issued_payloads = []
    monkeypatch.setattr(app_main, "get_db", lambda: db)
    monkeypatch.setattr(
        app_main,
        "create_access_token",
        lambda payload: issued_payloads.append(payload) or "approved-demo-token",
    )

    response = app_main.demo_switch_role("staff_elena")

    assert db.cursor_instance.params == ("cleaner.elena@cleanlondon.co.uk",)
    assert issued_payloads == [{"user_id": 2, "role": "staff"}]
    assert response["access_token"] == "approved-demo-token"
    assert response["user"]["email"] == account["email"]
    assert "is_active" not in response["user"]
