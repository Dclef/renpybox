import threading
from types import SimpleNamespace

from module.Engine.API import BingTranslate


def test_bing_posts_to_canonical_host_even_with_cn_region(monkeypatch):
    monkeypatch.setenv("translators_default_region", "CN")
    monkeypatch.setattr(BingTranslate, "_clients", threading.local())
    from translators.server import Bing, Tse

    calls = []
    html = '''<select id="tta_srcsl"><option value="en">English</option>
    <option value="zh-Hans">Chinese</option></select>
    <div id="tta_outGDCont" data-iid="translator.test"></div>
    <script>var config = {IG:"test"};</script>'''

    def get(url, *, headers, timeout):
        calls.append(("GET", url))
        return SimpleNamespace(text=html)

    def post(url, *, headers, data, timeout):
        calls.append(("POST", url.split("?", 1)[0]))
        assert data["fromLang"] == "en"
        assert data["to"] == "zh-Hans"
        assert data["text"] in {"Hello", "Thanks"}
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: [{"translations": [{"text": "Translated " + data["text"]}]}],
        )

    monkeypatch.setattr(Tse, "get_client_session", staticmethod(lambda *_: SimpleNamespace(get=get, post=post)))
    monkeypatch.setattr(Bing, "get_tk", lambda self, _: {"key": 123, "token": "test"})
    for text in ("Hello", "Thanks"):
        assert BingTranslate.translate_text(text, from_language="en", to_language="zh", timeout=5) == "Translated " + text
    assert calls == [
        ("GET", "https://www.bing.com/Translator"),
        ("POST", "https://www.bing.com/ttranslatev3"),
        ("POST", "https://www.bing.com/ttranslatev3"),
    ]
