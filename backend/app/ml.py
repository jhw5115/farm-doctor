from dataclasses import dataclass

from app.config import settings

# 학습 산출물의 클래스명을 서비스 표준 코드로 정규화한다. ID 순서는 사용하지 않는다.
CLASS_CODE_MAP = {
    "apple_healthy": "apple_healthy",
    "normal": "apple_healthy",
    "apple_fire_blight": "apple_fire_blight",
    "fire_blight": "apple_fire_blight",
}
ALLOWED_CLASSES = {"apple_healthy", "apple_fire_blight"}


@dataclass
class ModelStatus:
    ready: bool
    detail: str


class Classifier:
    def __init__(self) -> None:
        self.model = None
        self.status = ModelStatus(False, "모델 파일 연결 대기 중")

    def load(self) -> ModelStatus:
        if not settings.model_path.is_file():
            self.status = ModelStatus(False, "best.pt 파일이 없습니다. 추론을 실행하지 않습니다.")
            return self.status
        try:
            from ultralytics import YOLO
            model = YOLO(str(settings.model_path))
            if model.task != "detect":
                self.status = ModelStatus(
                    False,
                    f"YOLO Detection 모델이 필요하지만 현재 모델 작업 유형은 '{model.task}'입니다.",
                )
                return self.status
            names = set(model.names.values()) if isinstance(model.names, dict) else set(model.names)
            normalized_names = {CLASS_CODE_MAP.get(name) for name in names}
            if normalized_names != ALLOWED_CLASSES or None in normalized_names:
                self.status = ModelStatus(False, "모델 클래스는 apple_healthy와 apple_fire_blight 두 개여야 합니다.")
                return self.status
            self.model = model
            self.status = ModelStatus(True, "2클래스 YOLO Detection 모델 준비 완료")
        except Exception as error:
            self.status = ModelStatus(False, f"모델을 불러올 수 없습니다: {error}")
        return self.status

    def predict(self, image_path: str) -> tuple[str, float, list[dict[str, float | str]]]:
        if not self.status.ready or self.model is None:
            raise RuntimeError(self.status.detail)
        result = self.model(image_path, verbose=False)[0]
        if result.boxes is None or len(result.boxes) == 0:
            raise RuntimeError("감지된 사과 정상 또는 과수화상병 대상이 없습니다.")
        best_index = int(result.boxes.conf.argmax().item())
        index = int(result.boxes.cls[best_index].item())
        names = self.model.names
        raw_code = names[index] if isinstance(names, dict) else names[index]
        class_code = CLASS_CODE_MAP.get(raw_code)
        if class_code not in ALLOWED_CLASSES:
            raise RuntimeError("허용되지 않은 모델 클래스입니다.")
        detections: list[dict[str, float | str]] = []
        for box in result.boxes:
            raw = names[int(box.cls.item())] if isinstance(names, dict) else names[int(box.cls.item())]
            code = CLASS_CODE_MAP.get(raw)
            if code not in ALLOWED_CLASSES:
                raise RuntimeError("허용되지 않은 모델 클래스입니다.")
            x1, y1, x2, y2 = (float(value) for value in box.xyxy[0].tolist())
            detections.append({"class_code": code, "confidence": float(box.conf.item()), "x1": x1, "y1": y1, "x2": x2, "y2": y2})
        return class_code, float(result.boxes.conf[best_index].item()), detections


classifier = Classifier()
