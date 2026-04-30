import io
import json
import math
import os
import pathlib
import re
import time
from datetime import datetime
from typing import Any, Literal, Optional
from urllib.parse import quote_plus

import cv2
import numpy as np
from PIL import Image, ImageOps
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from skimage.measure import label, regionprops
from skimage.morphology import skeletonize
from ultralytics import YOLO

app = FastAPI(title="Voice Guard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _get_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def _get_db_url() -> str:
    direct = os.getenv("DATABASE_URL")
    if direct:
        return direct

    host = _get_env("PGHOST")
    port = int(os.getenv("PGPORT", "5432"))
    dbname = os.getenv("PGDATABASE", "postgres")
    user = os.getenv("PGUSER", "postgres")
    password = _get_env("PGPASSWORD")
    sslmode = os.getenv("PGSSLMODE", "require")

    return (
        f"postgresql://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{quote_plus(dbname)}"
        f"?sslmode={quote_plus(sslmode)}"
    )


pool: ConnectionPool | None = None
ITEMS_TABLE = os.getenv("POSTGRES_ITEMS_TABLE", "items")
LANE_WEAR_TABLE = os.getenv("POSTGRES_LANE_WEAR_TABLE", "lane_wear_results")

STORE_ROOT = os.getenv("RG_STORE_DIR", "./RoadGlass")
ORIG_DIR = os.path.join(STORE_ROOT, "orig")
OVERLAY_DIR = os.path.join(STORE_ROOT, "overlay")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")

MODEL_PATH = os.getenv("YOLO_MODEL", "yolov11n-face.pt")
LANE_MODEL_PATH = os.getenv("YOLO_LANE_MODEL", "best_model.pt")
LP_MODEL_PATH = os.getenv("YOLO_LP_MODEL", "license-plate-v1x.pt")

FACE_CONF = float(os.getenv("FACE_CONF", "0.25"))
PLATE_CONF = float(os.getenv("PLATE_CONF", "0.25"))
BLUR_IOU = float(os.getenv("BLUR_IOU", "0.50"))
BLUR_STRENGTH = int(os.getenv("BLUR_STRENGTH", "31"))
PIXEL_SIZE = int(os.getenv("PIXEL_SIZE", "16"))
BLUR_METHOD = os.getenv("BLUR_METHOD", "gaussian")

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(20 * 1024 * 1024)))
ALLOWED_MIME = {"image/jpeg", "image/png"}

_model_face: YOLO | None = None
_model_lane: YOLO | None = None
_model_lp: YOLO | None = None

COLOR_MAP = {
    0: (0, 0, 255),
    1: (255, 0, 0),
    2: (180, 0, 0),
    3: (255, 255, 255),
    4: (200, 200, 200),
    5: (0, 255, 255),
    6: (0, 200, 200),
}
ALPHA_FILL = 0.35
CNT_THICK = 2


def _validate_identifier(name: str, env_name: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise RuntimeError(
            f"Invalid {env_name}. Use only letters/numbers/_ and must not start with a number."
        )
    return name


def _pool() -> ConnectionPool:
    if pool is None:
        raise RuntimeError("DB pool is not initialized")
    return pool


def _ensure_tables() -> None:
    items_sql = f"""
    CREATE TABLE IF NOT EXISTS "{ITEMS_TABLE}" (
        id BIGSERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        mode INT NULL,
        created_at TIMESTAMPTZ DEFAULT NOW()
    )
    """
    lane_wear_sql = f"""
    CREATE TABLE IF NOT EXISTS "{LANE_WEAR_TABLE}" (
        id BIGSERIAL PRIMARY KEY,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        image_name TEXT NULL,
        model TEXT NULL,
        width INT NULL,
        height INT NULL,
        runtime_ms DOUBLE PRECISION NULL,
        overall JSONB NOT NULL DEFAULT '{{}}'::jsonb,
        per_class JSONB NOT NULL DEFAULT '{{}}'::jsonb,
        gps_lat DOUBLE PRECISION NULL,
        gps_lon DOUBLE PRECISION NULL,
        timestamp TIMESTAMPTZ NULL,
        device_id TEXT NULL
    )
    """
    with _pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(items_sql)
            cur.execute(lane_wear_sql)


def _check_model_file(path: str, label: str) -> None:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"{label} model not found: {path}")


def get_face_model() -> YOLO:
    global _model_face
    if _model_face is None:
        _check_model_file(MODEL_PATH, "Face")
        _model_face = YOLO(MODEL_PATH)
    return _model_face


def get_lane_model() -> YOLO:
    global _model_lane
    if _model_lane is None:
        _check_model_file(LANE_MODEL_PATH, "Lane")
        _model_lane = YOLO(LANE_MODEL_PATH)
    return _model_lane


def get_lp_model() -> YOLO:
    global _model_lp
    if _model_lp is None:
        _check_model_file(LP_MODEL_PATH, "License plate")
        _model_lp = YOLO(LP_MODEL_PATH)
    return _model_lp


def _model_status(path: str) -> dict[str, Any]:
    return {"path": path, "exists": os.path.isfile(path)}


def read_image_from_upload(file: UploadFile) -> Image.Image:
    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(status_code=415, detail=f"Unsupported Content-Type: {file.content_type}")
    raw = file.file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large")
    img = Image.open(io.BytesIO(raw))
    try:
        return ImageOps.exif_transpose(img).convert("RGB")
    except Exception:
        return img.convert("RGB")


def pil_to_cv2(img: Image.Image) -> np.ndarray:
    arr = np.array(img, dtype=np.uint8)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def cv2_to_jpeg_bytes(img_bgr: np.ndarray, quality: int = 90) -> bytes:
    ok, buf = cv2.imencode(".jpg", img_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    if not ok:
        raise RuntimeError("JPEG encoding failed")
    return buf.tobytes()


def resize_long_edge(pil_img: Image.Image, max_edge: int) -> Image.Image:
    w, h = pil_img.size
    m = max(w, h)
    if m <= max_edge:
        return pil_img
    scale = max_edge / m
    return pil_img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)


def _save_jpg(path: str, img_bgr: np.ndarray, quality: int = 92) -> None:
    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(path, img_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    if not ok:
        raise RuntimeError(f"Failed to write image: {path}")


def _build_url(req: Optional[Request], path: str) -> str:
    if PUBLIC_BASE_URL:
        return f"{PUBLIC_BASE_URL}{path}"
    if req is not None:
        return f"{str(req.base_url).rstrip('/')}{path}"
    return path


def to_gray(img: np.ndarray) -> np.ndarray:
    return img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def sobel_magnitude(gray: np.ndarray) -> np.ndarray:
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    return cv2.magnitude(gx, gy)


def mask_to_skeleton(bin_mask: np.ndarray) -> np.ndarray:
    if bin_mask.dtype != np.uint8:
        bin_mask = bin_mask.astype(np.uint8)
    sk = skeletonize(bin_mask.astype(bool))
    return sk.astype(np.uint8)


def boundary_ring(mask: np.ndarray, ring: int = 2) -> tuple[np.ndarray, np.ndarray]:
    er = cv2.erode(mask, np.ones((3, 3), np.uint8), iterations=1)
    bd = cv2.subtract(mask, er)
    dil = cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=ring)
    outer = cv2.subtract(dil, mask)
    return bd, outer


def largest_component_ratio(mask: np.ndarray) -> tuple[float, int]:
    if mask.sum() == 0:
        return 0.0, 0
    lab = label(mask, connectivity=2)
    props = regionprops(lab)
    areas = np.array([p.area for p in props]) if props else np.array([])
    if len(areas) == 0:
        return 0.0, 0
    main = areas.max()
    return float(main / areas.sum()), int(len(areas))


def compute_metrics(frame_bgr: np.ndarray, lane_mask: np.ndarray, inst_scores=None) -> tuple[dict[str, Any], np.ndarray]:
    mask = (lane_mask > 0).astype(np.uint8)
    if mask.any():
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8), iterations=1)

    area = int(mask.sum())
    sk = mask_to_skeleton(mask) if area > 0 else mask
    sk_len = int(sk.sum()) if area > 0 else 0
    thickness = float(area / sk_len) if sk_len > 0 else 0.0
    main_ratio, cc_count = largest_component_ratio(mask) if area > 0 else (0.0, 0)

    gray = to_gray(frame_bgr)
    grad = sobel_magnitude(gray)
    bd, outer = boundary_ring(mask, ring=2) if area > 0 else (np.zeros_like(mask), np.zeros_like(mask))
    bd_vals = grad[bd.astype(bool)]
    outer_vals = grad[outer.astype(bool)]
    edge_contrast = float(bd_vals.mean() - outer_vals.mean()) if (bd_vals.size and outer_vals.size) else 0.0
    vis_score = float(np.mean(inst_scores)) if inst_scores is not None and len(inst_scores) else 1.0

    c_main = 1.0 - main_ratio
    c_cc = min(cc_count / 8.0, 1.0)
    c_th = 1.0 - np.tanh(thickness / 8.0)
    c_ed = 1.0 - np.tanh(max(edge_contrast, 0.0) / 20.0)
    c_vis = 1.0 - min(vis_score, 1.0)
    weights = {"main": 0.28, "cc": 0.22, "th": 0.22, "ed": 0.18, "vis": 0.10}
    wear = 100.0 * (
        weights["main"] * c_main
        + weights["cc"] * c_cc
        + weights["th"] * c_th
        + weights["ed"] * c_ed
        + weights["vis"] * c_vis
    )

    return {
        "area_px": area,
        "skeleton_len_px": sk_len,
        "thickness_px": float(thickness),
        "main_component_ratio": float(main_ratio),
        "cc_count": int(cc_count),
        "edge_contrast": float(edge_contrast),
        "visibility": float(vis_score),
        "wear_score": float(np.clip(wear, 0.0, 100.0)),
    }, mask


def _pca_main_angle(bin_mask: np.ndarray) -> Optional[float]:
    ys, xs = np.nonzero(bin_mask)
    if len(xs) < 20:
        return None
    pts = np.column_stack((xs, ys)).astype(np.float32)
    pts -= pts.mean(axis=0, keepdims=True)
    cov = np.cov(pts.T)
    eigvals, eigvecs = np.linalg.eig(cov)
    main_vec = eigvecs[:, np.argmax(eigvals)]
    return float(math.atan2(main_vec[1], main_vec[0]))


def _project_vals(bin_mask: np.ndarray, angle: float) -> np.ndarray:
    ys, xs = np.nonzero(bin_mask)
    if len(xs) == 0:
        return np.array([])
    c, s = math.cos(angle), math.sin(angle)
    t = xs * c + ys * s
    t = t - t.min()
    t = (t / (t.max() + 1e-6) * 1000.0).astype(int)
    return np.bincount(t, minlength=(t.max() + 1)).astype(np.float32)


def _periodicity_score(prof: np.ndarray) -> float:
    if prof.size < 16:
        return 0.0
    prof = (prof - prof.mean()) / (prof.std() + 1e-6)
    n = len(prof)
    f = np.fft.rfft(prof)
    acf = np.fft.irfft(f * np.conj(f), n=n).real
    acf = acf / (acf[0] + 1e-6)
    peak = float(np.max(acf[2 : n // 2])) if n // 2 > 2 else 0.0
    return float(np.clip(peak, 0.0, 1.0))


def _skeleton_largest_continuity(sk: np.ndarray) -> float:
    if sk.sum() == 0:
        return 0.0
    num, comp = cv2.connectedComponents(sk.astype(np.uint8), connectivity=8)
    if num <= 1:
        return 0.0
    counts = [(comp == i).sum() for i in range(1, num)]
    return float(max(counts) / (sk.sum() + 1e-6))


def _bbox_coverage(bin_mask: np.ndarray) -> float:
    ys, xs = np.nonzero(bin_mask)
    if len(xs) == 0:
        return 0.0
    x1, x2 = xs.min(), xs.max()
    y1, y2 = ys.min(), ys.max()
    bbox_area = (x2 - x1 + 1) * (y2 - y1 + 1)
    return float(bin_mask.sum() / (bbox_area + 1e-6))


def _centroids_and_angles(bin_mask: np.ndarray) -> tuple[list[Any], list[Any]]:
    lab = label(bin_mask, connectivity=2)
    props = regionprops(lab)
    cents = []
    angs = []
    for p in props:
        if p.area < 20:
            continue
        cents.append(p.centroid)
        angs.append(p.orientation)
    return cents, angs


def _angle_parallelism(angles: np.ndarray) -> float:
    if angles.size < 2:
        return 0.0
    mu = np.mean(angles)
    diffs = np.arctan2(np.sin(angles - mu), np.cos(angles - mu))
    std = np.std(diffs)
    return 1.0 - float(np.clip(std / (math.pi / 6), 0.0, 1.0))


def _spacing_cv_along_normal(centroids: np.ndarray, main_angle: float) -> float:
    if centroids.shape[0] < 3:
        return 1.0
    ang = main_angle + math.pi / 2.0
    c, s = math.cos(ang), math.sin(ang)
    proj = centroids[:, 1] * c + centroids[:, 0] * s
    proj = np.sort(proj)
    gaps = np.diff(proj)
    if np.mean(gaps) <= 1e-6:
        return 1.0
    return float(np.std(gaps) / (np.mean(gaps) + 1e-6))


def _pattern_from_name(cls_name: str) -> Optional[str]:
    name = cls_name.lower()
    if "cross" in name or "walk" in name or "zebra" in name:
        return "crosswalk"
    if "dotted" in name or "dashed" in name or "broken" in name:
        return "dotted"
    if "solid" in name or "stop_line" in name or "stop" in name:
        return "solid"
    return None


def _heuristic_pattern(bin_mask: np.ndarray, metrics_common: dict[str, Any]) -> str:
    cc = metrics_common.get("cc_count", 0)
    main_ratio = metrics_common.get("main_component_ratio", 0.0)
    if cc >= 6 and main_ratio < 0.6:
        return "dotted"
    cents, angs = _centroids_and_angles(bin_mask)
    if len(cents) >= 3:
        par = _angle_parallelism(np.array(angs, dtype=np.float32))
        if par > 0.6:
            return "crosswalk"
    return "solid"


def compute_pattern_metrics(
    bin_mask: np.ndarray,
    common: dict[str, Any],
    cls_name: str,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if bin_mask.sum() == 0:
        out["pattern"] = _pattern_from_name(cls_name) or "unknown"
        out["wear_score_pattern"] = common.get("wear_score", 0.0)
        out["wear_score_final"] = out["wear_score_pattern"]
        return out

    angle = _pca_main_angle(bin_mask)
    pattern = _pattern_from_name(cls_name) or _heuristic_pattern(bin_mask, common)
    out["pattern"] = pattern

    sk = mask_to_skeleton(bin_mask)
    length_cont = _skeleton_largest_continuity(sk)
    out["length_continuity"] = float(length_cont)

    if pattern == "solid":
        dist = cv2.distanceTransform((bin_mask > 0).astype(np.uint8), cv2.DIST_L2, 3)
        vals = dist[dist > 0] * 2.0
        width_cv = float(np.std(vals) / (np.mean(vals) + 1e-6)) if vals.size > 10 else 0.0
        out["width_cv"] = float(np.clip(width_cv, 0.0, 3.0))
        mcr = common.get("main_component_ratio", 0.0)
        th = common.get("thickness_px", 0.0)
        ed = common.get("edge_contrast", 0.0)
        wear_pat = 100.0 * (
            0.35 * (1.0 - mcr)
            + 0.25 * (1.0 - np.tanh(th / 8.0))
            + 0.25 * (1.0 - np.tanh(max(ed, 0.0) / 20.0))
            + 0.15 * np.clip(width_cv / 0.8, 0.0, 1.0)
            + 0.10 * (1.0 - length_cont)
        )
        out["wear_score_pattern"] = float(np.clip(wear_pat, 0.0, 100.0))
    elif pattern == "dotted":
        if angle is None:
            angle = 0.0
        prof = _project_vals(bin_mask, angle)
        periodicity = _periodicity_score(prof)
        out["periodicity"] = periodicity
        lab = label(bin_mask, connectivity=2)
        props = regionprops(lab)
        lengths = []
        min_t, max_t = np.inf, -np.inf
        c, s = math.cos(angle), math.sin(angle)
        for p in props:
            if p.area < 20:
                continue
            coords = p.coords
            ts = coords[:, 1] * c + coords[:, 0] * s
            lengths.append(float(ts.max() - ts.min() + 1.0))
            min_t = min(min_t, ts.min())
            max_t = max(max_t, ts.max())
        lengths_np = np.array(lengths, dtype=np.float32) if lengths else np.array([], np.float32)
        length_cv = float(np.std(lengths_np) / (np.mean(lengths_np) + 1e-6)) if lengths_np.size > 1 else 1.0
        duty_cycle = float(np.clip(lengths_np.sum() / max(max_t - min_t, 1.0), 0.0, 1.0)) if len(lengths) else 0.0
        out["length_cv"] = float(np.clip(length_cv, 0.0, 5.0))
        out["duty_cycle"] = duty_cycle
        ed = common.get("edge_contrast", 0.0)
        th = common.get("thickness_px", 0.0)
        duty_err = abs(duty_cycle - 0.5)
        wear_pat = 100.0 * (
            0.30 * np.clip(duty_err / 0.5, 0.0, 1.0)
            + 0.25 * np.clip(length_cv / 1.0, 0.0, 1.0)
            + 0.20 * (1.0 - np.clip(periodicity, 0.0, 1.0))
            + 0.15 * (1.0 - np.tanh(max(ed, 0.0) / 20.0))
            + 0.10 * (1.0 - np.tanh(th / 8.0))
        )
        out["wear_score_pattern"] = float(np.clip(wear_pat, 0.0, 100.0))
    elif pattern == "crosswalk":
        cents, angs = _centroids_and_angles(bin_mask)
        stripe_count = len(cents)
        out["stripe_count"] = int(stripe_count)
        parallelism = _angle_parallelism(np.array(angs, dtype=np.float32)) if stripe_count >= 2 else 0.0
        out["parallelism"] = float(parallelism)
        if angle is None:
            angle = float(np.mean(angs)) if stripe_count >= 2 else 0.0
        cents_np = np.array([(y, x) for (y, x) in cents], dtype=np.float32) if stripe_count > 0 else np.zeros((0, 2), np.float32)
        spacing_cv = _spacing_cv_along_normal(cents_np, angle) if stripe_count >= 3 else 1.0
        coverage_ratio = _bbox_coverage(bin_mask)
        out["spacing_cv"] = float(np.clip(spacing_cv, 0.0, 5.0))
        out["coverage_ratio"] = float(coverage_ratio)
        ed = common.get("edge_contrast", 0.0)
        wear_pat = 100.0 * (
            0.30 * np.clip(spacing_cv / 0.6, 0.0, 1.0)
            + 0.25 * (1.0 - np.clip(parallelism, 0.0, 1.0))
            + 0.15 * (1.0 - np.clip(coverage_ratio / 0.6, 0.0, 1.0))
            + 0.20 * (1.0 - np.tanh(max(ed, 0.0) / 20.0))
            + 0.10 * (1.0 - _skeleton_largest_continuity(mask_to_skeleton(bin_mask)))
        )
        out["wear_score_pattern"] = float(np.clip(wear_pat, 0.0, 100.0))
    else:
        out["wear_score_pattern"] = float(common.get("wear_score", 0.0))

    out["wear_score_final"] = float(max(common.get("wear_score", 0.0), out["wear_score_pattern"]))
    return out


def collect_class_masks(res, target_hw: tuple[int, int]) -> dict[int, dict[str, Any]]:
    height, width = target_hw
    out: dict[int, dict[str, Any]] = {}
    if res is None or getattr(res, "masks", None) is None:
        return out
    if getattr(res.masks, "data", None) is not None and len(res.masks.data) > 0:
        masks = res.masks.data.detach().cpu().numpy()
        classes = (
            res.boxes.cls.detach().cpu().numpy().astype(int)
            if res.boxes.cls is not None
            else np.zeros((masks.shape[0],), int)
        )
        confs = res.boxes.conf.detach().cpu().numpy().tolist() if res.boxes.conf is not None else [1.0] * masks.shape[0]
        for i, cid in enumerate(classes):
            mask = (masks[i] > 0.5).astype(np.uint8)
            if mask.shape != (height, width):
                mask = cv2.resize(mask, (width, height), interpolation=cv2.INTER_NEAREST)
            if cid not in out:
                out[cid] = {"mask": mask, "scores": [confs[i]]}
            else:
                out[cid]["mask"] = np.maximum(out[cid]["mask"], mask)
                out[cid]["scores"].append(confs[i])
        return out
    if getattr(res.masks, "xy", None) is not None and len(res.masks.xy) > 0:
        classes = (
            res.boxes.cls.detach().cpu().numpy().astype(int)
            if res.boxes.cls is not None
            else np.zeros((len(res.masks.xy),), int)
        )
        confs = res.boxes.conf.detach().cpu().numpy().tolist() if res.boxes.conf is not None else [1.0] * len(res.masks.xy)
        for i, cid in enumerate(classes):
            poly = res.masks.xy[i]
            canvas = np.zeros((height, width), np.uint8)
            if poly is not None and len(poly) >= 3:
                pts = np.array([[int(round(x)), int(round(y))] for x, y in poly], dtype=np.int32)
                pts[:, 0] = np.clip(pts[:, 0], 0, width - 1)
                pts[:, 1] = np.clip(pts[:, 1], 0, height - 1)
                cv2.fillPoly(canvas, [pts], 1)
            if cid not in out:
                out[cid] = {"mask": canvas, "scores": [confs[i]]}
            else:
                out[cid]["mask"] = np.maximum(out[cid]["mask"], canvas)
                out[cid]["scores"].append(confs[i])
    return out


def _detect_boxes(model: YOLO, frame_bgr: np.ndarray, conf: float, iou: float, imgsz: int) -> np.ndarray:
    res = model.predict(frame_bgr, conf=conf, iou=iou, imgsz=imgsz, verbose=False)[0]
    if res and res.boxes is not None and len(res.boxes) > 0:
        return res.boxes.xyxy.detach().cpu().numpy()
    return np.empty((0, 4), float)


def apply_blur(
    img_bgr: np.ndarray,
    boxes_xyxy: np.ndarray,
    method: str = "gaussian",
    blur_strength: int = 31,
    pixel_size: int = 16,
) -> np.ndarray:
    out = img_bgr.copy()
    height, width = out.shape[:2]
    for x1, y1, x2, y2 in boxes_xyxy:
        x1 = max(int(x1), 0)
        y1 = max(int(y1), 0)
        x2 = min(int(x2), width)
        y2 = min(int(y2), height)
        if x2 <= x1 or y2 <= y1:
            continue
        roi = out[y1:y2, x1:x2]
        if method == "pixelate":
            sh = max(1, (y2 - y1) // pixel_size)
            sw = max(1, (x2 - x1) // pixel_size)
            small = cv2.resize(roi, (sw, sh), interpolation=cv2.INTER_LINEAR)
            roi_blur = cv2.resize(small, (x2 - x1, y2 - y1), interpolation=cv2.INTER_NEAREST)
        else:
            kernel = blur_strength if blur_strength % 2 == 1 else blur_strength + 1
            roi_blur = cv2.GaussianBlur(roi, (kernel, kernel), 0)
        out[y1:y2, x1:x2] = roi_blur
    return out


def make_overlay_image(frame_bgr: np.ndarray, class_masks: dict[int, dict[str, Any]]) -> np.ndarray:
    out = frame_bgr.copy()
    for cid, data in class_masks.items():
        mask = data.get("mask")
        if mask is None or not np.any(mask):
            continue
        color = COLOR_MAP.get(int(cid), (0, 255, 0))
        color_img = np.zeros_like(out)
        color_img[mask.astype(bool)] = color
        out = cv2.addWeighted(out, 1.0, color_img, ALPHA_FILL, 0)
        contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(out, contours, -1, color, CNT_THICK)
    return out


def _insert_lane_wear_result(
    image_name: Optional[str],
    model_name: Optional[str],
    width: Optional[int],
    height: Optional[int],
    runtime_ms: Optional[float],
    overall: dict[str, Any],
    per_class: dict[str, Any],
    gps_lat: Optional[float],
    gps_lon: Optional[float],
    timestamp: Optional[datetime],
    device_id: Optional[str],
) -> dict[str, Any]:
    q = f"""
    INSERT INTO "{LANE_WEAR_TABLE}" (
        image_name, model, width, height, runtime_ms, overall, per_class,
        gps_lat, gps_lon, timestamp, device_id
    )
    VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s)
    RETURNING *
    """
    with _pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                q,
                (
                    image_name,
                    model_name,
                    width,
                    height,
                    runtime_ms,
                    json.dumps(overall),
                    json.dumps(per_class),
                    gps_lat,
                    gps_lon,
                    timestamp,
                    device_id,
                ),
            )
            row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=500, detail="Insert failed")
    return row


def _shape_lane_wear_row(row: dict[str, Any], req: Optional[Request] = None) -> dict[str, Any]:
    rid = row["id"]
    data = {
        "id": rid,
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        "image_name": row.get("image_name"),
        "model": row.get("model"),
        "image_size": {"width": row.get("width"), "height": row.get("height")},
        "runtime_ms": row.get("runtime_ms"),
        "overall": row.get("overall") or {},
        "per_class": row.get("per_class") or {},
        "gps_lat": row.get("gps_lat"),
        "gps_lon": row.get("gps_lon"),
        "timestamp": row["timestamp"].isoformat() if row.get("timestamp") else None,
        "device_id": row.get("device_id"),
    }
    if os.path.exists(os.path.join(ORIG_DIR, f"{rid}.jpg")):
        data["orig_url"] = _build_url(req, f"/lane_wear/image/{rid}/orig")
    if os.path.exists(os.path.join(OVERLAY_DIR, f"{rid}.jpg")):
        data["overlay_url"] = _build_url(req, f"/lane_wear/image/{rid}/overlay")
    return data


@app.on_event("startup")
def _startup() -> None:
    global pool
    _validate_identifier(ITEMS_TABLE, "POSTGRES_ITEMS_TABLE")
    _validate_identifier(LANE_WEAR_TABLE, "POSTGRES_LANE_WEAR_TABLE")
    if pool is None:
        pool = ConnectionPool(_get_db_url(), min_size=1, max_size=10, open=True)
    _ensure_tables()
    os.makedirs(ORIG_DIR, exist_ok=True)
    os.makedirs(OVERLAY_DIR, exist_ok=True)


@app.on_event("shutdown")
def _shutdown() -> None:
    global pool
    if pool is not None:
        pool.close()
        pool = None


@app.get("/health")
def health() -> dict[str, Any]:
    with _pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT 1 AS ok")
            row = cur.fetchone()
    return {
        "status": "ok",
        "db": row,
        "models": {
            "face": _model_status(MODEL_PATH),
            "lane": _model_status(LANE_MODEL_PATH),
            "license_plate": _model_status(LP_MODEL_PATH),
        },
    }


@app.get("/")
def read_root() -> dict[str, Any]:
    return {
        "service": "roadglass-lanewear-api",
        "message": "서버가 정상 작동 중입니다!",
        "endpoints": [
            "/health",
            "/items",
            "/items/{id}",
            "/detect",
            "/blur",
            "/lane_wear_infer",
            "/lane_wear/latest",
            "/lane_wear/recent",
            "/lane_wear/{id}",
            "/lane_wear/image/{id}/orig",
            "/lane_wear/image/{id}/overlay",
            "/stats/summary",
        ],
    }


class ItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    mode: Optional[int] = None


class ItemUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    mode: Optional[int] = None


class DetectRequest(BaseModel):
    mode: int


class LaneWearResultCreate(BaseModel):
    image_name: Optional[str] = Field(default=None, max_length=255)
    model: Optional[str] = Field(default=None, max_length=255)
    width: Optional[int] = Field(default=None, ge=1)
    height: Optional[int] = Field(default=None, ge=1)
    runtime_ms: Optional[float] = Field(default=None, ge=0)
    overall: dict[str, Any] = Field(default_factory=dict)
    per_class: dict[str, Any] = Field(default_factory=dict)
    gps_lat: Optional[float] = None
    gps_lon: Optional[float] = None
    timestamp: Optional[datetime] = None
    device_id: Optional[str] = Field(default=None, max_length=255)


@app.get("/items")
def list_items(limit: int = 50, offset: int = 0) -> dict[str, Any]:
    limit = max(0, min(limit, 200))
    offset = max(0, offset)
    q = f'SELECT * FROM "{ITEMS_TABLE}" ORDER BY id ASC LIMIT %s OFFSET %s'
    with _pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(q, (limit, offset))
            rows = cur.fetchall()
    return {"data": rows}


@app.get("/items/{item_id}")
def get_item(item_id: int) -> dict[str, Any]:
    q = f'SELECT * FROM "{ITEMS_TABLE}" WHERE id = %s'
    with _pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(q, (item_id,))
            row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"data": row}


@app.post("/items")
def create_item(payload: ItemCreate) -> dict[str, Any]:
    q = f'INSERT INTO "{ITEMS_TABLE}" (name, mode) VALUES (%s, %s) RETURNING *'
    with _pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(q, (payload.name, payload.mode))
            row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=500, detail="Insert failed")
    return {"data": row}


@app.patch("/items/{item_id}")
def update_item(item_id: int, payload: ItemUpdate) -> dict[str, Any]:
    updates = payload.model_dump()
    name = updates.get("name")
    mode = updates.get("mode")
    if name is None and mode is None:
        raise HTTPException(status_code=400, detail="No fields to update")
    q = f"""
    UPDATE "{ITEMS_TABLE}"
       SET name = COALESCE(%s, name),
           mode = COALESCE(%s, mode)
     WHERE id = %s
     RETURNING *
    """
    with _pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(q, (name, mode, item_id))
            row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"data": row}


@app.delete("/items/{item_id}")
def delete_item(item_id: int) -> dict[str, Any]:
    q = f'DELETE FROM "{ITEMS_TABLE}" WHERE id = %s RETURNING *'
    with _pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(q, (item_id,))
            row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"deleted": True, "data": row}


@app.post("/detect")
def run_detection(payload: DetectRequest) -> dict[str, Any]:
    q = f'INSERT INTO "{ITEMS_TABLE}" (name, mode) VALUES (%s, %s) RETURNING *'
    with _pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(q, ("detection", payload.mode))
            row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=500, detail="Insert failed")
    return {"status": "success", "saved": row}


@app.post("/blur")
def blur(
    file: UploadFile = File(...),
    conf: float = Query(0.25, ge=0.01, le=1.0),
    iou: float = Query(0.50, ge=0.05, le=0.95),
    method: Literal["gaussian", "pixelate"] = Query("gaussian"),
    blur_strength: int = Query(31, ge=3, le=199),
    pixel_size: int = Query(16, ge=2, le=128),
    max_size: int = Query(1280, ge=320, le=4096),
    jpeg_quality: int = Query(90, ge=60, le=100),
):
    pil_img = read_image_from_upload(file)
    pil_img_rs = resize_long_edge(pil_img, max_size)
    img_bgr = pil_to_cv2(pil_img_rs)

    boxes_face = _detect_boxes(get_face_model(), img_bgr, conf, iou, max_size)
    try:
        boxes_plate = _detect_boxes(get_lp_model(), img_bgr, conf, iou, max_size)
    except Exception:
        boxes_plate = np.empty((0, 4), float)

    boxes = boxes_face if len(boxes_face) else np.empty((0, 4), float)
    if len(boxes_plate):
        boxes = np.concatenate([boxes, boxes_plate], axis=0) if len(boxes) else boxes_plate
    if len(boxes):
        img_bgr = apply_blur(
            img_bgr,
            boxes,
            method=method,
            blur_strength=blur_strength,
            pixel_size=pixel_size,
        )
    return Response(content=cv2_to_jpeg_bytes(img_bgr, quality=jpeg_quality), media_type="image/jpeg")


@app.post("/lane_wear_infer")
def lane_wear_infer(
    request: Request,
    file: UploadFile = File(...),
    conf: float = Query(0.25, ge=0.01, le=1.0),
    iou: float = Query(0.50, ge=0.05, le=0.95),
    max_size: int = Query(1280, ge=320, le=4096),
    gps_lat: float = Form(...),
    gps_lon: float = Form(...),
    timestamp: datetime = Form(...),
    device_id: str = Form(...),
) -> dict[str, Any]:
    pil_img = read_image_from_upload(file)
    pil_img_rs = resize_long_edge(pil_img, max_size)
    frame = pil_to_cv2(pil_img_rs)
    height, width = frame.shape[:2]

    try:
        boxes_face = _detect_boxes(get_face_model(), frame, FACE_CONF, BLUR_IOU, max_size)
    except Exception:
        boxes_face = np.empty((0, 4), float)
    try:
        boxes_plate = _detect_boxes(get_lp_model(), frame, PLATE_CONF, BLUR_IOU, max_size)
    except Exception:
        boxes_plate = np.empty((0, 4), float)
    if len(boxes_face) or len(boxes_plate):
        all_boxes = boxes_face if len(boxes_face) else np.empty((0, 4), float)
        if len(boxes_plate):
            all_boxes = np.concatenate([all_boxes, boxes_plate], axis=0) if len(all_boxes) else boxes_plate
        frame = apply_blur(
            frame,
            all_boxes,
            method=BLUR_METHOD,
            blur_strength=BLUR_STRENGTH,
            pixel_size=PIXEL_SIZE,
        )

    model = get_lane_model()
    started = time.time()
    res = model.predict(frame, imgsz=max_size, conf=conf, iou=iou, verbose=False)[0]
    elapsed_ms = round((time.time() - started) * 1000.0, 2)
    names = getattr(model, "names", {})

    class_masks = collect_class_masks(res, (height, width))
    lane_union = np.zeros((height, width), np.uint8)
    all_scores: list[float] = []
    for data in class_masks.values():
        lane_union = np.maximum(lane_union, data["mask"])
        all_scores.extend(data["scores"])
    metrics_all, _ = compute_metrics(frame, lane_union, inst_scores=all_scores)

    per_class: dict[int, dict[str, Any]] = {}
    for cid, data in class_masks.items():
        metrics_class, _ = compute_metrics(frame, data["mask"], inst_scores=data["scores"])
        cls_name = str(names.get(int(cid), cid)) if isinstance(names, dict) else str(cid)
        metrics_pattern = compute_pattern_metrics(data["mask"], metrics_class, cls_name)
        merged = {
            k: (float(v) if isinstance(v, (int, float, np.floating)) else v)
            for k, v in metrics_class.items()
        }
        merged.update(
            {
                k: (float(v) if isinstance(v, (int, float, np.floating)) else v)
                for k, v in metrics_pattern.items()
            }
        )
        merged["class_name"] = cls_name
        per_class[int(cid)] = merged

    overall = {
        k: (float(v) if isinstance(v, (int, float, np.floating)) else v)
        for k, v in metrics_all.items()
    }
    row = _insert_lane_wear_result(
        image_name=getattr(file, "filename", None),
        model_name=os.path.basename(LANE_MODEL_PATH),
        width=width,
        height=height,
        runtime_ms=elapsed_ms,
        overall=overall,
        per_class=per_class,
        gps_lat=gps_lat,
        gps_lon=gps_lon,
        timestamp=timestamp,
        device_id=device_id,
    )

    orig_path = os.path.join(ORIG_DIR, f"{row['id']}.jpg")
    overlay_path = os.path.join(OVERLAY_DIR, f"{row['id']}.jpg")
    _save_jpg(orig_path, frame, quality=92)
    overlay_img = make_overlay_image(frame, class_masks)
    _save_jpg(overlay_path, overlay_img, quality=92)

    data = _shape_lane_wear_row(row, request)
    return {
        "status": "success",
        "model": os.path.basename(LANE_MODEL_PATH),
        "image_size": {"width": width, "height": height},
        "runtime_ms": elapsed_ms,
        "overall": overall,
        "per_class": per_class,
        "db_id": row["id"],
        "orig_url": data.get("orig_url"),
        "overlay_url": data.get("overlay_url"),
    }


@app.api_route("/lane_wear/image/{result_id}/{kind}", methods=["GET", "HEAD"])
def get_lane_wear_image_kind(result_id: int, kind: Literal["orig", "overlay"]):
    path = os.path.join(ORIG_DIR if kind == "orig" else OVERLAY_DIR, f"{result_id}.jpg")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"image not found: {kind} {result_id}")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


@app.api_route("/lane_wear/image/{result_id}", methods=["GET", "HEAD"])
def get_lane_wear_image_query(
    result_id: int,
    type: Literal["orig", "overlay"] = Query("orig"),
):
    return get_lane_wear_image_kind(result_id, type)


@app.get("/lane_wear/latest")
def get_lane_wear_latest(request: Request, image_name: Optional[str] = None) -> dict[str, Any]:
    q = f'SELECT * FROM "{LANE_WEAR_TABLE}"'
    params: list[Any] = []
    if image_name:
        q += " WHERE image_name = %s"
        params.append(image_name)
    q += " ORDER BY created_at DESC LIMIT 1"
    with _pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(q, params)
            row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="No data")
    return _shape_lane_wear_row(row, request)


@app.get("/lane_wear/recent")
def get_lane_wear_recent(request: Request, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    q = f'SELECT * FROM "{LANE_WEAR_TABLE}" ORDER BY created_at DESC LIMIT %s OFFSET %s'
    with _pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(q, (limit, offset))
            rows = cur.fetchall()
    return [_shape_lane_wear_row(row, request) for row in rows]


@app.get("/lane_wear/{result_id}")
def get_lane_wear(request: Request, result_id: int) -> dict[str, Any]:
    q = f'SELECT * FROM "{LANE_WEAR_TABLE}" WHERE id = %s'
    with _pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(q, (result_id,))
            row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Lane wear result not found")
    return _shape_lane_wear_row(row, request)


@app.get("/stats/summary")
def get_stats_summary(
    window_h: int = Query(default=24, ge=1, le=24 * 30),
    warning: float = Query(default=40.0, ge=0.0, le=100.0),
    critical: float = Query(default=70.0, ge=0.0, le=100.0),
) -> dict[str, Any]:
    q_window = f"""
    SELECT
        COUNT(*) AS detections,
        COUNT(DISTINCT CASE WHEN device_id IS NOT NULL THEN device_id END) AS active_devices,
        COALESCE(SUM(CASE WHEN COALESCE((overall->>'wear_score')::float, 0) >= %s THEN 1 ELSE 0 END), 0) AS alerts_critical,
        COALESCE(
            SUM(
                CASE
                    WHEN COALESCE((overall->>'wear_score')::float, 0) >= %s
                     AND COALESCE((overall->>'wear_score')::float, 0) < %s
                    THEN 1 ELSE 0
                END
            ),
            0
        ) AS alerts_warning
    FROM "{LANE_WEAR_TABLE}"
    WHERE created_at >= NOW() - (%s * INTERVAL '1 hour')
    """
    q_device = f"""
    WITH latest AS (
        SELECT DISTINCT ON (device_id)
            device_id,
            COALESCE((overall->>'wear_score')::float, 0) AS wear
        FROM "{LANE_WEAR_TABLE}"
        WHERE device_id IS NOT NULL
        ORDER BY device_id, created_at DESC
    )
    SELECT
        COALESCE(SUM(CASE WHEN wear < %s THEN 1 ELSE 0 END), 0) AS ok,
        COALESCE(SUM(CASE WHEN wear >= %s AND wear < %s THEN 1 ELSE 0 END), 0) AS warning_cnt,
        COALESCE(SUM(CASE WHEN wear >= %s THEN 1 ELSE 0 END), 0) AS critical_cnt
    FROM latest
    """
    with _pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(q_window, (critical, warning, critical, window_h))
            window_row = cur.fetchone() or {}
            cur.execute(q_device, (warning, warning, critical, critical))
            device_row = cur.fetchone() or {}
    return {
        "window_h": window_h,
        "thresholds": {"warning": warning, "critical": critical},
        "detections": int(window_row.get("detections", 0) or 0),
        "active_devices": int(window_row.get("active_devices", 0) or 0),
        "alerts": {
            "warning": int(window_row.get("alerts_warning", 0) or 0),
            "critical": int(window_row.get("alerts_critical", 0) or 0),
        },
        "device_status": {
            "ok": int(device_row.get("ok", 0) or 0),
            "warning": int(device_row.get("warning_cnt", 0) or 0),
            "critical": int(device_row.get("critical_cnt", 0) or 0),
        },
    }