"""One AI sub-key per customer, inside the owner's account (accounts/provision.py)."""

from openjarvis.accounts import provision


class _Resp:
    def __init__(self, data, status=200):
        self._data, self.status_code = data, status

    def json(self):
        return self._data


class _Http:
    def __init__(self):
        self.calls = []

    def request(self, method, url, json, headers):
        self.calls.append((method, url, json, headers))
        if method == "POST":
            return _Resp({"key": "sk-or-cliente", "data": {"hash": "h1"}})
        return _Resp({"data": {}})


def test_nothing_without_the_owners_management_key(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_MANAGEMENT_KEY", raising=False)
    assert not provision.ensure("u1", http=_Http(), home=tmp_path)


def test_budget_is_the_plan_minus_the_margin(monkeypatch):
    monkeypatch.setenv("SERGIO_MARGEN", "0.4")
    assert provision.budget("go", usd=5) == 3.0
    assert provision.budget("free", usd=0) == provision.FREE_BUDGET_USD


def test_customer_key_life(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_MANAGEMENT_KEY", "mgmt")
    http = _Http()
    assert provision.ensure("u1", "go", http=http, home=tmp_path)
    method, url, body, headers = http.calls[0]
    assert method == "POST" and url.endswith("/keys")
    assert (
        body["limit_reset"] == "monthly" and headers["Authorization"] == "Bearer mgmt"
    )
    assert provision.key_for("u1", home=tmp_path) == "sk-or-cliente"
    assert (
        provision.ensure("u1", "go", http=http, home=tmp_path) and len(http.calls) == 1
    )
    assert provision.set_plan("u1", "work", http=http, home=tmp_path)
    assert http.calls[-1][0] == "PATCH" and http.calls[-1][1].endswith("/h1")
    assert provision.disable("u1", http=http, home=tmp_path)
    assert http.calls[-1][2] == {"disabled": True}
    assert provision.key_for("u1", home=tmp_path) == ""
    assert (tmp_path / "cuentas_claves.json").stat().st_mode & 0o077 == 0


def test_a_customer_goes_through_their_own_key():
    assert provision.customer_model("gemini-4-argon") == "openrouter/auto"
    assert (
        provision.customer_model("openrouter/x-ai/grok-4") == "openrouter/x-ai/grok-4"
    )
    from openjarvis.server.cloud_router import _load_keys

    mark = provision.CUSTOMER_KEY.set("sk-or-cliente")
    try:
        assert _load_keys()["OPENROUTER_API_KEY"] == "sk-or-cliente"
    finally:
        provision.CUSTOMER_KEY.reset(mark)
