from app.ml import Classifier


def test_missing_model_never_generates_a_prediction(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("app.ml.settings.model_path", tmp_path / "best.pt")
    classifier = Classifier()

    status = classifier.load()

    assert status.ready is False
    assert "best.pt" in status.detail
