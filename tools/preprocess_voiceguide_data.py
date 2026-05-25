from __future__ import annotations

import csv
import io
import math
import os
import shutil
import struct
import zipfile
from pathlib import Path

import pandas as pd


DOWNLOADS = Path(r"C:\Users\ghksw\Downloads")
ROOT = Path(r"C:\VoiceGuide\VoiceGuide")
OUT = ROOT / "data" / "processed" / "voiceguide"


SOURCES = {
    "welfare": DOWNLOADS / "서울시 사회복지시설(장애인지역사회재활시설) 목록.csv",
    "crosswalk_current": DOWNLOADS / "서울시 자치구 횡단보도 정보.csv",
    "crosswalk_signal_xlsx": DOWNLOADS / "서울특별시_자치구별 신호등 및 횡단보도 위치 및 현황_20230530.xlsx",
    "crosswalk_tgis_zip": DOWNLOADS / "횡단보도 위치 및 부착대 정보.zip",
    "audio_zip": DOWNLOADS / "A073_P_음향신호기.zip",
    "button_xlsx": DOWNLOADS / "A077_P.xlsx",
    "button_zip_legacy": DOWNLOADS / "A077_P.zip",
    "button_zip_latest": DOWNLOADS / "A077_P(20250417).zip",
    "mobility": DOWNLOADS / "전국교통약자이동지원센터정보표준데이터 (1).csv",
    "audio_definition": DOWNLOADS / "교통안전시설물 테이블 정의서(음향신호기).pdf",
    "crosswalk_definition": DOWNLOADS / "교통안전시설물 테이블 정의서(횡단보도).hwpx",
}


def ensure_dirs() -> None:
    for rel in [
        "00_manifest",
        "01_destination",
        "02_crosswalk_candidates",
        "03_pedestrian_support",
        "04_audio_signal",
        "05_ped_button",
        "06_mobility_support",
        "99_reference",
    ]:
        (OUT / rel).mkdir(parents=True, exist_ok=True)


def read_csv_kr(path: Path, **kwargs) -> pd.DataFrame:
    for enc in ("utf-8-sig", "cp949", "euc-kr", "utf-8"):
        try:
            return pd.read_csv(path, encoding=enc, **kwargs)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(path, **kwargs)


def clean_text(value):
    if pd.isna(value):
        return ""
    return str(value).replace("\r", " ").replace("\n", " ").strip()


def yn(value) -> bool:
    text = clean_text(value).upper()
    return text in {"Y", "YES", "TRUE", "1", "있음", "설치", "O"}


def to_number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def save_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def meridional_arc(phi: float, a: float, e2: float) -> float:
    e4 = e2 * e2
    e6 = e4 * e2
    return a * (
        (1 - e2 / 4 - 3 * e4 / 64 - 5 * e6 / 256) * phi
        - (3 * e2 / 8 + 3 * e4 / 32 + 45 * e6 / 1024) * math.sin(2 * phi)
        + (15 * e4 / 256 + 45 * e6 / 1024) * math.sin(4 * phi)
        - (35 * e6 / 3072) * math.sin(6 * phi)
    )


def tm5186_to_wgs84(x, y):
    if pd.isna(x) or pd.isna(y):
        return None, None

    # Seoul public traffic facility files use the Korea 2000 / Central Belt
    # family. This inverse TM is close enough for facility matching and maps.
    a = 6378137.0
    inv_f = 298.257222101
    f = 1 / inv_f
    e2 = 2 * f - f * f
    ep2 = e2 / (1 - e2)
    k0 = 1.0
    lat0 = math.radians(38.0)
    lon0 = math.radians(127.0)
    x0 = 200000.0
    y0 = 600000.0

    x_adj = float(x) - x0
    m = meridional_arc(lat0, a, e2) + (float(y) - y0) / k0
    mu = m / (a * (1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    phi1 = (
        mu
        + (3 * e1 / 2 - 27 * e1**3 / 32) * math.sin(2 * mu)
        + (21 * e1**2 / 16 - 55 * e1**4 / 32) * math.sin(4 * mu)
        + (151 * e1**3 / 96) * math.sin(6 * mu)
        + (1097 * e1**4 / 512) * math.sin(8 * mu)
    )
    sin_phi1 = math.sin(phi1)
    cos_phi1 = math.cos(phi1)
    tan_phi1 = math.tan(phi1)
    n1 = a / math.sqrt(1 - e2 * sin_phi1**2)
    r1 = a * (1 - e2) / (1 - e2 * sin_phi1**2) ** 1.5
    t1 = tan_phi1**2
    c1 = ep2 * cos_phi1**2
    d = x_adj / (n1 * k0)

    lat = phi1 - (n1 * tan_phi1 / r1) * (
        d**2 / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1**2 - 9 * ep2) * d**4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1**2 - 252 * ep2 - 3 * c1**2) * d**6 / 720
    )
    lon = lon0 + (
        d
        - (1 + 2 * t1 + c1) * d**3 / 6
        + (5 - 2 * c1 + 28 * t1 - 3 * c1**2 + 8 * ep2 + 24 * t1**2) * d**5 / 120
    ) / cos_phi1
    return round(math.degrees(lat), 8), round(math.degrees(lon), 8)


def add_lat_lon_from_xy(df: pd.DataFrame, x_col: str = "x", y_col: str = "y") -> pd.DataFrame:
    lats, lons = [], []
    for x, y in zip(df[x_col], df[y_col]):
        lat, lon = tm5186_to_wgs84(x, y)
        lats.append(lat)
        lons.append(lon)
    df["lat"] = lats
    df["lon"] = lons
    return df


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def nearest_flags(base: pd.DataFrame, target: pd.DataFrame, prefix: str, limit_m: float = 30.0) -> pd.DataFrame:
    target = target.dropna(subset=["lat", "lon"]).copy()
    grid = {}
    for row in target[["facility_id", "lat", "lon"]].itertuples(index=False):
        key = (int(row.lat * 1000), int(row.lon * 1000))
        grid.setdefault(key, []).append(row)

    has_values, id_values, dist_values = [], [], []
    for lat, lon in base[["lat", "lon"]].itertuples(index=False):
        if pd.isna(lat) or pd.isna(lon):
            has_values.append(False)
            id_values.append("")
            dist_values.append("")
            continue
        gx, gy = int(lat * 1000), int(lon * 1000)
        best = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for candidate in grid.get((gx + dx, gy + dy), []):
                    dist = haversine_m(lat, lon, candidate.lat, candidate.lon)
                    if best is None or dist < best[0]:
                        best = (dist, candidate.facility_id)
        if best and best[0] <= limit_m:
            has_values.append(True)
            id_values.append(best[1])
            dist_values.append(round(best[0], 1))
        else:
            has_values.append(False)
            id_values.append("")
            dist_values.append("")

    base[f"near_{prefix}_within_{int(limit_m)}m"] = has_values
    base[f"nearest_{prefix}_id"] = id_values
    base[f"nearest_{prefix}_distance_m"] = dist_values
    return base


def read_dbf_bytes(data: bytes, encoding: str = "cp949") -> pd.DataFrame:
    num_records = struct.unpack("<I", data[4:8])[0]
    header_len = struct.unpack("<H", data[8:10])[0]
    record_len = struct.unpack("<H", data[10:12])[0]
    fields = []
    off = 32
    while off < header_len and data[off] != 0x0D:
        desc = data[off : off + 32]
        name = desc[:11].split(b"\x00", 1)[0].decode("ascii", "ignore")
        fields.append((name, chr(desc[11]), desc[16], desc[17]))
        off += 32

    rows = []
    for i in range(num_records):
        start = header_len + i * record_len
        record = data[start : start + record_len]
        if not record or record[0:1] == b"*":
            continue
        pos = 1
        row = {}
        for name, field_type, length, decimals in fields:
            raw = record[pos : pos + length]
            pos += length
            text = raw.decode(encoding, errors="ignore").strip()
            if field_type in {"N", "F"}:
                row[name] = pd.to_numeric(text, errors="coerce") if text else None
            else:
                row[name] = text
        rows.append(row)
    return pd.DataFrame(rows)


def shape_centroids_from_bytes(data: bytes) -> pd.DataFrame:
    rows = []
    offset = 100
    while offset + 8 <= len(data):
        rec_no, content_words = struct.unpack(">2i", data[offset : offset + 8])
        content_len = content_words * 2
        content = data[offset + 8 : offset + 8 + content_len]
        offset += 8 + content_len
        if len(content) < 4:
            continue
        shape_type = struct.unpack("<i", content[:4])[0]
        x = y = None
        if shape_type == 1 and len(content) >= 20:
            x, y = struct.unpack("<2d", content[4:20])
        elif shape_type in {3, 5, 13, 15, 23, 25, 31} and len(content) >= 44:
            xmin, ymin, xmax, ymax = struct.unpack("<4d", content[4:36])
            x, y = (xmin + xmax) / 2, (ymin + ymax) / 2
        rows.append({"shape_record_no": rec_no, "shape_type": shape_type, "x": x, "y": y})
    return pd.DataFrame(rows)


def dbf_from_zip(zip_path: Path, dbf_name: str) -> pd.DataFrame:
    with zipfile.ZipFile(zip_path) as zf:
        return read_dbf_bytes(zf.read(dbf_name))


def nested_shape_table(zip_path: Path, nested_suffix: str) -> pd.DataFrame:
    with zipfile.ZipFile(zip_path) as outer:
        nested_name = next(n for n in outer.namelist() if n.endswith(nested_suffix))
        with zipfile.ZipFile(io.BytesIO(outer.read(nested_name))) as inner:
            dbf_name = next(n for n in inner.namelist() if n.lower().endswith(".dbf"))
            shp_name = next(n for n in inner.namelist() if n.lower().endswith(".shp"))
            dbf = read_dbf_bytes(inner.read(dbf_name))
            shapes = shape_centroids_from_bytes(inner.read(shp_name))
    merged = pd.concat([dbf.reset_index(drop=True), shapes.reset_index(drop=True)], axis=1)
    return merged


def preprocess_welfare() -> pd.DataFrame:
    df = read_csv_kr(SOURCES["welfare"])
    out = pd.DataFrame(
        {
            "facility_id": df["시설코드"].map(clean_text),
            "facility_name": df["시설명"].map(clean_text),
            "facility_type": df["시설종류명(시설유형)"].map(clean_text),
            "facility_detail_type": df["시설종류상세명(시설종류)"].map(clean_text),
            "gu": df["시군구명"].map(clean_text),
            "address": df["시설주소"].map(clean_text),
            "phone": df["전화번호"].map(clean_text),
            "postal_code": df["우편번호"].map(clean_text),
        }
    )
    out["is_dongjak"] = out["gu"].eq("동작구")
    out["is_welfare_center"] = out["facility_type"].str.contains("장애인복지관", na=False)
    out["needs_geocoding"] = True
    save_csv(out, OUT / "01_destination" / "welfare_facilities_disability_community_rehab.csv")
    save_csv(out[out["is_dongjak"]], OUT / "01_destination" / "welfare_facilities_dongjak.csv")
    return out


def preprocess_crosswalk_current() -> pd.DataFrame:
    df = read_csv_kr(SOURCES["crosswalk_current"])
    lat_raw = to_number(df["경도"])
    lon_raw = to_number(df["위도"])
    out = pd.DataFrame(
        {
            "crosswalk_id": df["횡단보도관리번호"].map(clean_text),
            "gu": df["시군구명"].map(clean_text),
            "address": df["소재지지번주소"].map(clean_text),
            "crosswalk_type": df["횡단보도종류"].map(clean_text),
            "lat": lat_raw,
            "lon": lon_raw,
            "is_elevated_crosswalk": df["고원식횡단보도유무"].map(yn),
            "has_pedestrian_signal": df["보행등유무"].map(yn),
            "has_audio_signal_declared": df["음향신호기설치여부"].map(yn),
            "has_pedestrian_button_declared": df["보행자작동신호기유무"].map(yn),
            "reference_date": df["데이터기준일자"].map(clean_text),
        }
    )
    out["source_note"] = "원본의 경도/위도 컬럼값이 서울 좌표 범위상 뒤바뀌어 있어 lat=경도, lon=위도로 정규화"
    out["declared_support_score"] = (
        out["has_pedestrian_signal"].astype(int)
        + out["has_audio_signal_declared"].astype(int) * 3
        + out["has_pedestrian_button_declared"].astype(int) * 2
        + out["is_elevated_crosswalk"].astype(int)
    )
    out["safe_candidate_by_declared_data"] = out["declared_support_score"] >= 3
    save_csv(out, OUT / "02_crosswalk_candidates" / "crosswalks_seoul_current.csv")
    save_csv(out[out["gu"].eq("동작구")], OUT / "02_crosswalk_candidates" / "crosswalks_dongjak_current.csv")
    return out


def preprocess_crosswalk_signal_xlsx() -> tuple[pd.DataFrame, pd.DataFrame]:
    cross = pd.read_excel(SOURCES["crosswalk_signal_xlsx"], sheet_name="횡단보도", header=3)
    cross = cross.drop(columns=[c for c in cross.columns if str(c).startswith("Unnamed")], errors="ignore")
    cross = cross.dropna(subset=["관리번호"])
    cross_out = pd.DataFrame(
        {
            "crosswalk_id": cross["관리번호"].map(clean_text),
            "gu": cross["자치구"].map(clean_text),
            "address": cross["주소"].map(clean_text),
            "intersection_name": cross["교차로명"].map(clean_text),
            "crosswalk_type": cross["횡단보도종류"].map(clean_text),
            "x": to_number(cross["X좌표"]),
            "y": to_number(cross["Y좌표"]),
            "road_type": cross["도로구분"].map(clean_text),
        }
    )
    cross_out = add_lat_lon_from_xy(cross_out)
    save_csv(cross_out, OUT / "02_crosswalk_candidates" / "crosswalks_signal_position_20230530.csv")

    lights = pd.read_excel(SOURCES["crosswalk_signal_xlsx"], sheet_name="보행등", header=3)
    lights = lights.drop(columns=[c for c in lights.columns if str(c).startswith("Unnamed")], errors="ignore")
    lights = lights.dropna(subset=["보행등관리번호"])
    light_out = pd.DataFrame(
        {
            "pedestrian_light_id": lights["보행등관리번호"].map(clean_text),
            "pole_id": lights["지주관리번호"].map(clean_text),
            "gu": lights["자치구"].map(clean_text),
            "address": lights["주소"].map(clean_text),
            "x": to_number(lights["X좌표"]),
            "y": to_number(lights["Y좌표"]),
            "road_type": lights["도로구분"].map(clean_text),
        }
    )
    light_out = add_lat_lon_from_xy(light_out)
    save_csv(light_out, OUT / "03_pedestrian_support" / "pedestrian_lights_20230530.csv")
    return cross_out, light_out


def preprocess_audio() -> pd.DataFrame:
    with zipfile.ZipFile(SOURCES["audio_zip"]) as zf:
        data = zf.read("A073_P.xlsx")
    df = pd.read_excel(io.BytesIO(data), sheet_name="워크시트 익스포트")
    out = pd.DataFrame(
        {
            "facility_id": df["MGRNU"].map(clean_text),
            "pole_id": df["A062_MGRNU"].map(clean_text),
            "direction_code": df["DRN_CDE"].map(clean_text),
            "install_date": df["ESB_YMD"].map(clean_text),
            "replace_date": df["CAE_YMD"].map(clean_text),
            "maker": df["MK_CPY"].map(clean_text),
            "x": to_number(df["XCE"]),
            "y": to_number(df["YCE"]),
            "status_code": df["STAT_CDE"].map(clean_text),
        }
    )
    out = add_lat_lon_from_xy(out)
    save_csv(out, OUT / "04_audio_signal" / "audio_signals.csv")
    save_csv(out.dropna(subset=["lat", "lon"]), OUT / "04_audio_signal" / "audio_signals_with_coordinates.csv")
    return out


def preprocess_buttons() -> pd.DataFrame:
    frames = []
    xlsx = pd.read_excel(SOURCES["button_xlsx"], sheet_name="워크시트 익스포트")
    frames.append(("xlsx_download", xlsx))

    latest = dbf_from_zip(SOURCES["button_zip_latest"], "A077_P.dbf")
    frames.append(("zip_20250417", latest))

    legacy = dbf_from_zip(SOURCES["button_zip_legacy"], "A077_P.dbf")
    frames.append(("zip_legacy", legacy))

    normalized = []
    for source, df in frames:
        kind_col = "A077_KND_CDE" if "A077_KND_CDE" in df.columns else "A077_KND_C"
        pole_col = "PO_SI_MGRNU" if "PO_SI_MGRNU" in df.columns else "PO_SI_MGRN"
        out = pd.DataFrame(
            {
                "source_file": source,
                "facility_id": df["MGRNU"].map(clean_text),
                "pole_id": df["A062_MGRNU"].map(clean_text),
                "direction_code": df["DRN_CDE"].map(clean_text),
                "install_date": df["ESB_YMD"].map(clean_text),
                "replace_date": df["CAE_YMD"].map(clean_text),
                "maker": df["MK_CPY"].map(clean_text) if "MK_CPY" in df.columns else "",
                "x": to_number(df["XCE"]),
                "y": to_number(df["YCE"]),
                "button_type_code": df[kind_col].map(clean_text),
                "status_code": df["STAT_CDE"].map(clean_text),
                "pole_signal_id": df[pole_col].map(clean_text),
            }
        )
        out = add_lat_lon_from_xy(out)
        normalized.append(out)
        save_csv(out, OUT / "05_ped_button" / f"pedestrian_buttons_{source}.csv")

    all_buttons = pd.concat(normalized, ignore_index=True)
    all_buttons = all_buttons.sort_values(["facility_id", "source_file"]).drop_duplicates(
        subset=["facility_id"], keep="first"
    )
    save_csv(all_buttons, OUT / "05_ped_button" / "pedestrian_buttons_all_deduped.csv")
    return all_buttons


def preprocess_mobility() -> pd.DataFrame:
    df = read_csv_kr(SOURCES["mobility"])
    out = pd.DataFrame(
        {
            "center_name": df["교통약자이동지원센터명"].map(clean_text),
            "road_address": df["소재지도로명주소"].map(clean_text),
            "lot_address": df["소재지지번주소"].map(clean_text),
            "lat": to_number(df["위도"]),
            "lon": to_number(df["경도"]),
            "vehicle_count": to_number(df["보유차량대수"]),
            "vehicle_type": df["보유차량종류"].map(clean_text),
            "reservation_phone": df["예약접수전화번호"].map(clean_text),
            "reservation_url": df["예약접수인터넷주소"].map(clean_text),
            "app_service_name": df["앱서비스명"].map(clean_text),
            "inside_area": df["차량관내운행지역"].map(clean_text),
            "outside_area": df["차량관외운행지역"].map(clean_text),
            "use_target": df["차량이용대상"].map(clean_text),
            "use_charge": df["차량이용요금"].map(clean_text),
            "manager_name": df["관리기관명"].map(clean_text),
            "manager_phone": df["관리기관전화번호"].map(clean_text),
            "reference_date": df["데이터기준일자"].map(clean_text),
            "provider_name": df["제공기관명"].map(clean_text),
        }
    )
    area_text = (out["road_address"] + " " + out["lot_address"] + " " + out["inside_area"] + " " + out["outside_area"])
    out["is_seoul_or_capital_area_related"] = area_text.str.contains("서울|수도권|경기|인천", regex=True, na=False)
    save_csv(out, OUT / "06_mobility_support" / "mobility_support_centers_national.csv")
    save_csv(
        out[out["is_seoul_or_capital_area_related"]],
        OUT / "06_mobility_support" / "mobility_support_centers_seoul_capital_area.csv",
    )
    return out


def preprocess_legacy_tgis() -> None:
    cross = nested_shape_table(SOURCES["crosswalk_tgis_zip"], ".zip")
    if "x" in cross.columns and "y" in cross.columns:
        cross = add_lat_lon_from_xy(cross)
    save_csv(cross, OUT / "99_reference" / "tgis_2021_crosswalk_shape_centroids.csv")

    # The second nested zip contains support/pole attachment geometry.
    with zipfile.ZipFile(SOURCES["crosswalk_tgis_zip"]) as outer:
        nested = [n for n in outer.namelist() if n.lower().endswith(".zip")][1]
        with zipfile.ZipFile(io.BytesIO(outer.read(nested))) as inner:
            dbf = read_dbf_bytes(inner.read(next(n for n in inner.namelist() if n.lower().endswith(".dbf"))))
            shp = shape_centroids_from_bytes(inner.read(next(n for n in inner.namelist() if n.lower().endswith(".shp"))))
    support = pd.concat([dbf.reset_index(drop=True), shp.reset_index(drop=True)], axis=1)
    if "x" not in support.columns and "XCE" in support.columns:
        support["x"] = to_number(support["XCE"])
        support["y"] = to_number(support["YCE"])
    support = add_lat_lon_from_xy(support)
    save_csv(support, OUT / "99_reference" / "tgis_2021_pole_attachment_shape_centroids.csv")


def build_support_scored_crosswalks(crosswalks: pd.DataFrame, audio: pd.DataFrame, buttons: pd.DataFrame) -> pd.DataFrame:
    scored = crosswalks.copy()
    scored = nearest_flags(scored, audio[["facility_id", "lat", "lon"]], "audio_signal", 30)
    scored = nearest_flags(scored, buttons[["facility_id", "lat", "lon"]], "pedestrian_button", 30)
    scored["has_audio_signal"] = scored["has_audio_signal_declared"] | scored["near_audio_signal_within_30m"]
    scored["has_pedestrian_button"] = scored["has_pedestrian_button_declared"] | scored["near_pedestrian_button_within_30m"]
    scored["support_score"] = (
        scored["has_pedestrian_signal"].astype(int)
        + scored["has_audio_signal"].astype(int) * 3
        + scored["has_pedestrian_button"].astype(int) * 2
        + scored["is_elevated_crosswalk"].astype(int)
    )
    scored["route_priority"] = pd.cut(
        scored["support_score"],
        bins=[-1, 0, 2, 4, 10],
        labels=["정보부족", "기본", "권장", "우선권장"],
    )
    cols = [
        "crosswalk_id",
        "gu",
        "address",
        "lat",
        "lon",
        "crosswalk_type",
        "is_elevated_crosswalk",
        "has_pedestrian_signal",
        "has_audio_signal",
        "has_pedestrian_button",
        "support_score",
        "route_priority",
        "nearest_audio_signal_id",
        "nearest_audio_signal_distance_m",
        "nearest_pedestrian_button_id",
        "nearest_pedestrian_button_distance_m",
        "reference_date",
    ]
    scored = scored[cols]
    save_csv(scored, OUT / "03_pedestrian_support" / "crosswalks_with_support_score.csv")
    save_csv(
        scored[scored["gu"].eq("동작구")].sort_values(["support_score"], ascending=False),
        OUT / "03_pedestrian_support" / "crosswalks_with_support_score_dongjak.csv",
    )
    return scored


def write_manifest(summary_rows: list[dict]) -> None:
    manifest = pd.DataFrame(summary_rows)
    save_csv(manifest, OUT / "00_manifest" / "processed_files_manifest.csv")

    readme = OUT / "README.md"
    lines = [
        "# VoiceGuide 데이터 전처리 결과",
        "",
        "이 폴더는 발표 시나리오의 필수 데이터 구분에 맞춰 원본을 정제한 결과입니다.",
        "",
        "## 전처리 원칙",
        "",
        "- CSV는 `utf-8-sig`로 통일했습니다.",
        "- 앱에서 바로 쓰기 쉽도록 `lat`, `lon`, `id`, `gu`, `address`, 시설 여부 컬럼을 표준화했습니다.",
        "- `서울시 자치구 횡단보도 정보.csv`의 원본 `경도/위도` 값은 실제 서울 좌표 범위상 뒤바뀌어 있어 `lat=경도`, `lon=위도`로 보정했습니다.",
        "- 서울 TM 계열 좌표(`XCE`, `YCE`, `X좌표`, `Y좌표`)는 WGS84 위경도로 변환한 `lat`, `lon`을 추가했습니다.",
        "- 횡단보도별 보행지원 점수는 `보행등 1점 + 음향신호기 3점 + 보행자작동신호기 2점 + 고원식 1점`으로 계산했습니다.",
        "- 목적지 시설 데이터는 좌표가 없어서 `needs_geocoding=True`로 표시했습니다. 지도 경로 탐색 전 주소 지오코딩이 필요합니다.",
        "",
        "## 핵심 파일",
        "",
        "- `01_destination/welfare_facilities_dongjak.csv`: 동작구 장애인지역사회재활시설 후보",
        "- `02_crosswalk_candidates/crosswalks_dongjak_current.csv`: 동작구 횡단보도 후보",
        "- `03_pedestrian_support/crosswalks_with_support_score_dongjak.csv`: 동작구 횡단보도 안전/설명가능성 점수",
        "- `04_audio_signal/audio_signals_with_coordinates.csv`: 음향신호기 좌표",
        "- `05_ped_button/pedestrian_buttons_all_deduped.csv`: 보행자작동신호기 좌표",
        "- `06_mobility_support/mobility_support_centers_seoul_capital_area.csv`: 서울/수도권 관련 이동지원센터",
        "",
    ]
    readme.write_text("\n".join(lines), encoding="utf-8")


def copy_reference_docs() -> None:
    for key in ("audio_definition", "crosswalk_definition"):
        src = SOURCES[key]
        if src.exists():
            shutil.copy2(src, OUT / "99_reference" / src.name)


def main() -> None:
    ensure_dirs()
    copy_reference_docs()

    welfare = preprocess_welfare()
    crosswalk_current = preprocess_crosswalk_current()
    crosswalk_xlsx, lights = preprocess_crosswalk_signal_xlsx()
    audio = preprocess_audio()
    buttons = preprocess_buttons()
    mobility = preprocess_mobility()
    preprocess_legacy_tgis()
    scored = build_support_scored_crosswalks(crosswalk_current, audio, buttons)

    summary_rows = []
    for path in sorted(OUT.rglob("*.csv")):
        try:
            rows = len(pd.read_csv(path, encoding="utf-8-sig"))
        except Exception:
            rows = ""
        summary_rows.append(
            {
                "file": str(path.relative_to(OUT)).replace("\\", "/"),
                "rows": rows,
                "purpose": path.parent.name,
            }
        )
    write_manifest(summary_rows)

    print("processed_root", OUT)
    print("welfare_rows", len(welfare))
    print("crosswalk_current_rows", len(crosswalk_current))
    print("crosswalk_xlsx_rows", len(crosswalk_xlsx))
    print("pedestrian_lights_rows", len(lights))
    print("audio_rows", len(audio))
    print("button_rows", len(buttons))
    print("mobility_rows", len(mobility))
    print("support_scored_rows", len(scored))


if __name__ == "__main__":
    main()
