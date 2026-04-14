from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from bananaslides.modules.inpainting.base import Inpainter


class Cv2Inpainter(Inpainter):
    """Conservative text removal using OpenCV's Telea or Navier-Stokes inpainting."""

    backend_name = "cv2_telea"

    def __init__(
        self,
        *,
        radius: float = 3.0,
        method: str = "telea",
        feather_px: int = 2,
    ) -> None:
        self.radius = radius
        self.method = method
        self.feather_px = feather_px

    def inpaint(self, slide_image_path: Path, mask_path: Path, output_path: Path) -> Path:
        cv2 = self._import_cv2()
        image = np.asarray(Image.open(slide_image_path).convert("RGB"), dtype=np.uint8)
        mask = np.asarray(Image.open(mask_path).convert("L"), dtype=np.uint8)

        if not np.any(mask > 0):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(image).save(output_path)
            return output_path

        cv2_method = cv2.INPAINT_TELEA if self.method == "telea" else cv2.INPAINT_NS
        inpainted = cv2.inpaint(cv2.cvtColor(image, cv2.COLOR_RGB2BGR), mask, self.radius, cv2_method)
        inpainted = cv2.cvtColor(inpainted, cv2.COLOR_BGR2RGB)
        blended = self._blend(image, inpainted, mask)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(blended).save(output_path)
        return output_path

    def _blend(self, original: np.ndarray, inpainted: np.ndarray, mask: np.ndarray) -> np.ndarray:
        alpha = (mask > 0).astype(np.float32)
        if self.feather_px > 0:
            blurred = Image.fromarray((alpha * 255).astype(np.uint8), mode="L").filter(
                ImageFilter.GaussianBlur(radius=self.feather_px)
            )
            alpha = np.maximum(alpha, np.asarray(blurred, dtype=np.float32) / 255.0)
        alpha = alpha[..., None]
        blended = (original.astype(np.float32) * (1.0 - alpha)) + (inpainted.astype(np.float32) * alpha)
        return blended.clip(0, 255).astype(np.uint8)

    @staticmethod
    def _import_cv2():
        try:
            import cv2
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Telea backend requires OpenCV. Install opencv-python-headless first."
            ) from exc
        return cv2
