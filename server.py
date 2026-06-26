#!/usr/bin/env python3
"""Dar al Sultan CFO & Production Application — Phase 3.1 Cloud Demo.
Dependency-free Python web application with cloud/demo configuration support.

The free demo build intentionally uses a seeded SQLite database on ephemeral
storage. Production deployment will migrate the same application data model to
PostgreSQL after owner approval.
"""

from __future__ import annotations

import base64
import calendar
import csv
import hashlib
import hmac
import io
import json
import mimetypes
import os
import re
import secrets
import shutil
import sqlite3
import struct
import sys
import threading
import urllib.parse
import webbrowser
import zipfile
import zlib
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
CLOUD_MODE = os.environ.get("DAS_CLOUD_MODE", "0") == "1"
DEMO_MODE = os.environ.get("DAS_DEMO_MODE", "0") == "1"
DEMO_SEED_PATH = BASE_DIR / "demo_seed.db"
DEFAULT_DB_PATH = BASE_DIR / "dar_al_sultan.db"
DB_PATH = Path(os.environ.get("DAS_DB_PATH", str(DEFAULT_DB_PATH))).expanduser().resolve()
BACKUP_DIR = Path(os.environ.get("DAS_BACKUP_DIR", str(BASE_DIR / "backups"))).expanduser().resolve()
HOST = os.environ.get("HOST", "0.0.0.0" if CLOUD_MODE else "127.0.0.1")
PORT = int(os.environ.get("PORT", "8080"))
APP_VERSION = "3.2-mobile-cloud-demo"


def prepare_demo_database() -> None:
    """Copy the bundled seed database to the configured writable location."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DEMO_MODE and not DB_PATH.exists():
        source = DEMO_SEED_PATH if DEMO_SEED_PATH.exists() else DEFAULT_DB_PATH
        if source.exists() and source.resolve() != DB_PATH:
            shutil.copy2(source, DB_PATH)


SESSIONS: dict[str, dict[str, Any]] = {}
SESSION_LOCK = threading.Lock()

PERMISSION_CATALOG = {
    "dashboard": ("General", "Dashboard", "View management dashboard and branch overview"),
    "alert_read": ("Alerts", "View Alerts", "View role and branch based management alerts"),
    "alert_manage": ("Alerts", "Manage Alert Settings", "Edit alert thresholds and module settings"),
    "budget_read": ("Budgets", "View Budgets", "View targets, budgets and variance reports"),
    "budget_write": ("Budgets", "Edit Budgets", "Create and revise monthly budgets"),
    "budget_approve": ("Budgets", "Approve / Lock Budgets", "Approve, lock, close and unlock budgets"),
    "payroll_read": ("Payroll", "View Payroll", "View salary and payroll details"),
    "payroll_write": ("Payroll", "Edit Payroll", "Create and update monthly payroll"),
    "attendance_read": ("Attendance", "View Attendance", "View employee attendance"),
    "attendance_write": ("Attendance", "Record Attendance", "Add and remove attendance entries"),
    "orders_read": ("Orders", "View Orders", "View customer orders and delivery status"),
    "orders_write": ("Orders", "Manage Orders", "Add, edit and update customer orders"),
    "membership_read": ("Membership", "View Membership", "View customers, cards and commissions"),
    "membership_write": ("Membership", "Manage Membership", "Add customers, issue cards and use balances"),
    "finance_read": ("Financials", "View Financials", "View income, expenses and profit figures"),
    "finance_write": ("Financials", "Manage Financials", "Add, edit and delete income/expense entries"),
    "production_read": ("Production", "View Production", "View production summaries and daily entries"),
    "production_write": ("Production", "Record Production", "Add, edit and delete production entries"),
    "employees": ("Employees", "View Employees", "View employee profiles and work categories"),
    "employee_write": ("Employees", "Manage Employees", "Add and edit employee profiles"),
    "reports": ("Reports", "Export Reports", "Download operational and management reports"),
    "audit": ("Administration", "View Audit Log", "View system activity and change history"),
    "users": ("Administration", "Manage Users & Roles", "Create users and configure role permissions"),
    "backup": ("Administration", "Database Backup", "Download a database backup"),
    "company_settings_read": ("Company", "View Company Settings", "View company profile and owner settings"),
    "company_settings_write": ("Company", "Manage Company Settings", "Edit company profile, branding, branches and owner settings"),
}

DEFAULT_ROLE_DEFINITIONS = {
    "Owner": {
        "description": "Full company access including users, permissions, finance and backups.",
        "permissions": set(PERMISSION_CATALOG),
    },
    "Administrator": {
        "description": "Full operational and administrative access.",
        "permissions": set(PERMISSION_CATALOG),
    },
    "Accountant": {
        "description": "Financials, budgets, payroll, membership, reports and attendance.",
        "permissions": {"dashboard","alert_read","budget_read","budget_write","payroll_read","payroll_write","attendance_read","attendance_write","orders_read","orders_write","membership_read","membership_write","finance_read","finance_write","production_read","employees","reports","backup","company_settings_read"},
    },
    "Branch Manager": {
        "description": "Operational control for the assigned branch without user administration.",
        "permissions": {"dashboard","alert_read","budget_read","attendance_read","attendance_write","orders_read","orders_write","membership_read","membership_write","finance_read","finance_write","production_read","production_write","employees","employee_write","reports"},
    },
    "Production Supervisor": {
        "description": "Production, attendance and order updates for the assigned branch.",
        "permissions": {"dashboard","alert_read","attendance_read","attendance_write","orders_read","orders_write","production_read","production_write","employees","reports"},
    },
    "Sales Agent": {
        "description": "Customer, membership card and assigned-branch order access.",
        "permissions": {"dashboard","orders_read","membership_read","membership_write","reports"},
    },
    "Viewer": {
        "description": "Read-only operational dashboard and reports.",
        "permissions": {"dashboard","alert_read","orders_read","production_read","employees","reports"},
    },
}

# Fallback used only before role tables are initialized.
ROLE_PERMISSIONS = {name: spec["permissions"] for name, spec in DEFAULT_ROLE_DEFINITIONS.items()}


PRODUCTION_ACTIVITIES = (
    "Body", "Joint/Side", "Daraz", "VIP Design", "Button",
    "Alteration", "Cutting", "Iron", "Sample"
)

ORDER_STATUSES = (
    "New Booking", "Measurement", "Cutting", "Body Making",
    "Daraz/Design", "Button", "Ironing", "Quality Check",
    "Ready", "Delivered", "Cancelled"
)

ORDER_ITEM_TYPES = (
    "Dishdasha", "Kids Dishdasha", "Kumma", "Musar",
    "Assa", "Khanjar", "Alteration", "Other"
)

MEMBERSHIP_STATUSES = ("Active", "Suspended", "Expired", "Closed")
MEMBERSHIP_TRANSACTION_TYPES = ("Purchase", "Refund", "Adjustment Credit", "Adjustment Debit")
ATTENDANCE_STATUSES = ("Present", "Absent", "Leave", "Half Day", "Weekly Off", "Holiday")
PAYROLL_STATUSES = ("Draft", "Approved", "Paid")
BUDGET_STATUSES = ("Draft", "Approved", "Locked", "Closed")

DEFAULT_ROLE_SKILLS = {
    "Body Making": ("Body", "Joint/Side"),
    "Daraz Maker": ("Daraz",),
    "VIP Design Maker": ("VIP Design",),
    "Master Cutter": ("Cutting",),
    "Alteration + Button": ("Alteration", "Button"),
    "Ironing": ("Iron",),
}


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def current_month_key() -> str:
    return datetime.now().strftime("%Y-%m")


def month_date_range(month: str, cap_current: bool = True) -> tuple[str, str]:
    dt = datetime.strptime(month, "%Y-%m").date()
    days = calendar.monthrange(dt.year, dt.month)[1]
    start = dt.replace(day=1)
    end = dt.replace(day=days)
    today = datetime.now().date()
    if cap_current and dt.year == today.year and dt.month == today.month:
        end = today
    return start.isoformat(), end.isoformat()


def current_month_range() -> tuple[str, str]:
    return month_date_range(current_month_key())


SUPPORTED_LANGUAGES = ("en", "ar")
DEFAULT_LANGUAGE = "en"

# Company profile defaults — intentionally blank so the app ships with no
# client-specific branding. Each deployment fills these in from
# Settings → Company Profile without any code change.
COMPANY_PROFILE_FIELDS = (
    "company_name",
    "company_subtitle",
    "currency_label",
    "company_address",
    "company_phone",
    "company_email",
    "company_website",
    "company_vat",
    "demo_mode",
    "demo_banner_text",
)
DEFAULT_COMPANY_PROFILE = {
    "company_name": "",
    "company_subtitle": "",
    "currency_label": "OMR",
    "company_address": "",
    "company_phone": "",
    "company_email": "",
    "company_website": "",
    "company_vat": "",
    "demo_mode": "1",
    "demo_banner_text": "CLOUD DEMO \u00b7 SAMPLE DATA \u00b7 OWNER PRESENTATION VERSION",
}
# Owner-level informational targets (additive; do not feed existing calculations).
OWNER_TARGET_FIELDS = ("monthly_production_target", "monthly_income_target")
DEFAULT_OWNER_TARGETS = {
    "monthly_production_target": "0",
    "monthly_income_target": "0",
}


def normalize_language(value: Any, fallback: str = DEFAULT_LANGUAGE) -> str:
    code = str(value or "").strip().lower()
    return code if code in SUPPORTED_LANGUAGES else fallback


def get_setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO app_settings(key,value) VALUES (?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def setting_enabled(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    text = str(value).strip().lower()
    if not text:
        return default
    if text in {"0", "false", "off", "no"}:
        return False
    if text in {"1", "true", "on", "yes"}:
        return True
    return default


def get_company_profile(conn: sqlite3.Connection) -> dict[str, Any]:
    profile = dict(DEFAULT_COMPANY_PROFILE)
    for field in COMPANY_PROFILE_FIELDS:
        profile[field] = get_setting(conn, field, DEFAULT_COMPANY_PROFILE[field])
    profile["currency_label"] = (profile.get("currency_label") or DEFAULT_COMPANY_PROFILE["currency_label"]).strip() or DEFAULT_COMPANY_PROFILE["currency_label"]
    profile["demo_mode"] = setting_enabled(profile.get("demo_mode"), default=True)
    profile["demo_banner_text"] = (profile.get("demo_banner_text") or DEFAULT_COMPANY_PROFILE["demo_banner_text"]).strip() or DEFAULT_COMPANY_PROFILE["demo_banner_text"]
    # No hardcoded company-name fallback: the profile stays blank until a value
    # is saved, so a fresh deployment shows no default brand.
    profile["company_logo_updated"] = get_setting(conn, "company_logo_updated", "")
    profile["has_custom_logo"] = bool(get_setting(conn, "company_logo_data", ""))
    return profile


def get_owner_targets(conn: sqlite3.Connection) -> dict[str, str]:
    targets = dict(DEFAULT_OWNER_TARGETS)
    for field in OWNER_TARGET_FIELDS:
        targets[field] = get_setting(conn, field, DEFAULT_OWNER_TARGETS[field])
    return targets


def profile_slug(profile: dict[str, Any]) -> str:
    text = str(profile.get("company_name") or "company").strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return slug or "company"


def branch_label(branch: str | None) -> str:
    return "All Branches" if not branch or branch == "All" else str(branch)


def date_range_label(start: str | None, end: str | None) -> str:
    if start and end:
        return f"{start} to {end}"
    return start or end or "Selected period"


def format_report_money(value: Any, currency: str) -> str:
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        amount = 0.0
    return f"{currency} {amount:,.3f}"


def format_report_number(value: Any, decimals: int = 2) -> str:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return str(value or "")
    if abs(number - int(number)) < 0.000001:
        return f"{int(number):,}"
    return f"{number:,.{decimals}f}".rstrip("0").rstrip(".")


def _pdf_safe_text(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value if value is not None else "")).strip()
    return text.encode("cp1252", "replace").decode("cp1252")


def _pdf_literal(value: Any) -> str:
    text = _pdf_safe_text(value)
    return "(" + text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ")"


def _pdf_num(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _pdf_text_width(value: Any, size: float, bold: bool = False) -> float:
    return len(_pdf_safe_text(value)) * size * (0.55 if bold else 0.50)


def _pdf_wrap_text(value: Any, width: float, size: float, max_lines: int = 3) -> list[str]:
    text = _pdf_safe_text(value)
    if not text:
        return [""]
    max_chars = max(5, int(width / max(size * 0.48, 1)))
    words = text.split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        if not current:
            current = word
        elif len(current) + 1 + len(word) <= max_chars:
            current += " " + word
        else:
            lines.append(current)
            current = word
        while len(current) > max_chars:
            lines.append(current[:max_chars - 1] + "-")
            current = current[max_chars - 1:]
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = (lines[-1][: max(0, max_chars - 3)] + "...").strip()
    return lines or [""]


def _jpeg_report_image(data: bytes) -> dict[str, Any] | None:
    if not data.startswith(b"\xff\xd8"):
        return None
    i = 2
    sof_markers = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    while i + 8 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        while i < len(data) and data[i] == 0xFF:
            i += 1
        if i >= len(data):
            break
        marker = data[i]
        i += 1
        if marker in {0x01, 0xD0, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9}:
            continue
        if i + 2 > len(data):
            break
        length = int.from_bytes(data[i : i + 2], "big")
        if length < 2 or i + length > len(data):
            break
        if marker in sof_markers and length >= 8:
            bits = data[i + 2]
            height = int.from_bytes(data[i + 3 : i + 5], "big")
            width = int.from_bytes(data[i + 5 : i + 7], "big")
            components = data[i + 7]
            colorspace = "/DeviceGray" if components == 1 else "/DeviceCMYK" if components == 4 else "/DeviceRGB"
            return {"width": width, "height": height, "bits": bits, "colorspace": colorspace, "filter": "/DCTDecode", "data": data}
        i += length
    return None


def _paeth_predictor(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def _png_report_image(data: bytes) -> dict[str, Any] | None:
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    pos = 8
    width = height = bit_depth = color_type = 0
    palette: bytes | None = None
    idat = bytearray()
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        chunk_type = data[pos + 4 : pos + 8]
        chunk_data = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type = struct.unpack(">IIBB", chunk_data[:10])
        elif chunk_type == b"PLTE":
            palette = chunk_data
        elif chunk_type == b"IDAT":
            idat.extend(chunk_data)
        elif chunk_type == b"IEND":
            break
    if not width or not height or bit_depth != 8 or color_type not in {0, 2, 3, 4, 6}:
        return None
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color_type]
    row_len = width * channels
    try:
        raw = zlib.decompress(bytes(idat))
    except zlib.error:
        return None
    bpp = channels
    out = bytearray()
    prev = bytearray(row_len)
    offset = 0
    for _ in range(height):
        if offset >= len(raw):
            return None
        filter_type = raw[offset]
        offset += 1
        scan = bytearray(raw[offset : offset + row_len])
        offset += row_len
        if len(scan) != row_len:
            return None
        recon = bytearray(row_len)
        for i, value in enumerate(scan):
            left = recon[i - bpp] if i >= bpp else 0
            above = prev[i]
            upper_left = prev[i - bpp] if i >= bpp else 0
            if filter_type == 0:
                recon[i] = value
            elif filter_type == 1:
                recon[i] = (value + left) & 0xFF
            elif filter_type == 2:
                recon[i] = (value + above) & 0xFF
            elif filter_type == 3:
                recon[i] = (value + ((left + above) // 2)) & 0xFF
            elif filter_type == 4:
                recon[i] = (value + _paeth_predictor(left, above, upper_left)) & 0xFF
            else:
                return None
        if color_type == 2:
            out.extend(recon)
        elif color_type == 6:
            for i in range(0, len(recon), 4):
                out.extend(recon[i : i + 3])
        elif color_type == 0:
            for gray in recon:
                out.extend((gray, gray, gray))
        elif color_type == 4:
            for i in range(0, len(recon), 2):
                gray = recon[i]
                out.extend((gray, gray, gray))
        elif color_type == 3:
            if not palette:
                return None
            for idx in recon:
                p = idx * 3
                out.extend(palette[p : p + 3] if p + 3 <= len(palette) else b"\x00\x00\x00")
        prev = recon
    return {"width": width, "height": height, "bits": 8, "colorspace": "/DeviceRGB", "filter": "/FlateDecode", "data": zlib.compress(bytes(out))}


def parse_report_image(data: bytes, mime: str) -> dict[str, Any] | None:
    mime = (mime or "").lower()
    if "jpeg" in mime or "jpg" in mime:
        return _jpeg_report_image(data)
    if "png" in mime:
        return _png_report_image(data)
    return None


class PdfReportDocument:
    width = 842.0
    height = 595.0
    margin = 34.0
    body_top = 430.0
    footer_top = 68.0

    def __init__(self, title: str, profile: dict[str, Any], branch: str, period: str, logo: dict[str, Any] | None = None):
        self.title = title
        self.profile = profile
        self.branch = branch_label(branch)
        self.period = period
        self.currency = str(profile.get("currency_label") or DEFAULT_COMPANY_PROFILE["currency_label"]).strip() or DEFAULT_COMPANY_PROFILE["currency_label"]
        self.generated = now_iso()
        self.logo = logo
        self.pages: list[list[str]] = []
        self.y = self.body_top

    def add_page(self) -> None:
        self.pages.append([])
        self.y = self.body_top

    @property
    def ops(self) -> list[str]:
        if not self.pages:
            self.add_page()
        return self.pages[-1]

    def rect(self, x: float, y: float, w: float, h: float, fill: str = "1 1 1", stroke: str | None = None) -> None:
        op = f"q {fill} rg {_pdf_num(x)} {_pdf_num(y)} {_pdf_num(w)} {_pdf_num(h)} re f Q"
        self.ops.append(op)
        if stroke:
            self.ops.append(f"q {stroke} RG 0.6 w {_pdf_num(x)} {_pdf_num(y)} {_pdf_num(w)} {_pdf_num(h)} re S Q")

    def text(self, x: float, y: float, value: Any, size: float = 8, bold: bool = False, color: str = "0.09 0.13 0.20", align: str = "left") -> None:
        text = _pdf_safe_text(value)
        if align == "right":
            x -= _pdf_text_width(text, size, bold)
        elif align == "center":
            x -= _pdf_text_width(text, size, bold) / 2
        font = "/F2" if bold else "/F1"
        self.ops.append(f"BT {color} rg {font} {_pdf_num(size)} Tf {_pdf_num(x)} {_pdf_num(y)} Td {_pdf_literal(text)} Tj ET")

    def add_summary(self, items: list[tuple[str, str]]) -> None:
        if not items:
            return
        if self.y - 46 < self.footer_top:
            self.add_page()
        usable = self.width - 2 * self.margin
        cols = min(4, max(1, len(items)))
        gap = 8.0
        card_w = (usable - gap * (cols - 1)) / cols
        row_h = 42.0
        for idx, (label, value) in enumerate(items[:4]):
            x = self.margin + idx * (card_w + gap)
            y = self.y - row_h
            self.ops.append(f"q 0.96 0.97 0.98 rg {_pdf_num(x)} {_pdf_num(y)} {_pdf_num(card_w)} {_pdf_num(row_h)} re f Q")
            self.ops.append(f"q 0.82 0.72 0.47 RG 0.7 w {_pdf_num(x)} {_pdf_num(y)} {_pdf_num(card_w)} {_pdf_num(row_h)} re S Q")
            self.text(x + 8, y + 25, label.upper(), 6.4, bold=True, color="0.45 0.49 0.55")
            self.text(x + 8, y + 10, value, 10.5, bold=True, color="0.06 0.10 0.17")
        self.y -= row_h + 14

    def _draw_table_header(self, headers: list[str], widths: list[float], x0: float, font_size: float) -> None:
        header_h = 22.0
        if self.y - header_h < self.footer_top:
            self.add_page()
        self.ops.append(f"q 0.07 0.12 0.19 rg {_pdf_num(x0)} {_pdf_num(self.y - header_h)} {_pdf_num(sum(widths))} {_pdf_num(header_h)} re f Q")
        x = x0
        for idx, header in enumerate(headers):
            lines = _pdf_wrap_text(header, widths[idx] - 8, font_size, 2)
            for line_idx, line in enumerate(lines):
                self.text(x + 4, self.y - 9 - line_idx * (font_size + 1.2), line, font_size, bold=True, color="1 1 1")
            x += widths[idx]
        self.y -= header_h

    def add_table(self, headers: list[str], rows: list[list[Any]], widths: list[float] | None = None,
                  aligns: list[str] | None = None, totals: list[list[Any]] | None = None) -> None:
        if not self.pages:
            self.add_page()
        usable = self.width - 2 * self.margin
        col_count = len(headers)
        if widths:
            total = sum(widths)
            widths = [w / total * usable for w in widths]
        else:
            widths = [usable / col_count for _ in headers]
        aligns = aligns or ["left"] * col_count
        font_size = 7.1 if col_count <= 10 else 6.3 if col_count <= 14 else 5.7
        line_h = font_size + 2.2
        x0 = self.margin
        self._draw_table_header(headers, widths, x0, font_size)
        all_rows = [(row, False) for row in rows] + [(row, True) for row in (totals or [])]
        if not all_rows:
            all_rows = [(["No rows found for this filter."] + [""] * (col_count - 1), False)]
        for idx, (row, is_total) in enumerate(all_rows):
            cell_lines = [_pdf_wrap_text(row[i] if i < len(row) else "", widths[i] - 8, font_size, 3) for i in range(col_count)]
            row_h = max(20.0, max(len(lines) for lines in cell_lines) * line_h + 8)
            if self.y - row_h < self.footer_top:
                self.add_page()
                self._draw_table_header(headers, widths, x0, font_size)
            fill = "0.98 0.96 0.89" if is_total else "0.985 0.988 0.992" if idx % 2 else "1 1 1"
            self.ops.append(f"q {fill} rg {_pdf_num(x0)} {_pdf_num(self.y - row_h)} {_pdf_num(usable)} {_pdf_num(row_h)} re f Q")
            row_line_y = self.y - row_h
            self.ops.append(f"q 0.86 0.88 0.90 RG 0.35 w {_pdf_num(x0)} {_pdf_num(row_line_y)} m {_pdf_num(x0 + usable)} {_pdf_num(row_line_y)} l S Q")
            x = x0
            for col, lines in enumerate(cell_lines):
                for line_idx, line in enumerate(lines):
                    baseline = self.y - 12 - line_idx * line_h
                    if aligns[col] == "right":
                        self.text(x + widths[col] - 4, baseline, line, font_size, bold=is_total, color="0.08 0.11 0.16", align="right")
                    else:
                        self.text(x + 4, baseline, line, font_size, bold=is_total, color="0.08 0.11 0.16")
                x += widths[col]
            self.y -= row_h

    def _header_ops(self) -> list[str]:
        ops: list[str] = []
        old_pages = self.pages
        self.pages = [ops]
        logo_x, logo_y, logo_w, logo_h = self.margin, 516.0, 58.0, 42.0
        if self.logo:
            aspect = max(0.1, float(self.logo["width"]) / max(1.0, float(self.logo["height"])))
            draw_w = min(62.0, logo_h * aspect)
            draw_h = min(44.0, draw_w / aspect)
            ops.append(f"q {_pdf_num(draw_w)} 0 0 {_pdf_num(draw_h)} {_pdf_num(logo_x)} {_pdf_num(logo_y)} cm /Im1 Do Q")
        else:
            ops.append(f"q 0.96 0.97 0.98 rg {_pdf_num(logo_x)} {_pdf_num(logo_y)} {_pdf_num(logo_h)} {_pdf_num(logo_h)} re f Q")
            ops.append(f"q 0.67 0.54 0.28 RG 0.9 w {_pdf_num(logo_x)} {_pdf_num(logo_y)} {_pdf_num(logo_h)} {_pdf_num(logo_h)} re S Q")
            self.text(logo_x + logo_h / 2, logo_y + 15, "N", 14, bold=True, color="0.67 0.54 0.28", align="center")
        text_x = self.margin + 74
        company = self.profile.get("company_name") or "Company Dashboard"
        subtitle = self.profile.get("company_subtitle") or "Management Report"
        contacts = [self.profile.get("company_phone"), self.profile.get("company_email"), self.profile.get("company_address"), self.profile.get("company_website")]
        contact = " | ".join(str(x).strip() for x in contacts if str(x or "").strip())
        self.text(text_x, 548, company, 14, bold=True, color="0.06 0.10 0.17")
        self.text(text_x, 532, subtitle, 8.5, color="0.36 0.40 0.46")
        if contact:
            for line_idx, line in enumerate(_pdf_wrap_text(contact, 340, 7, 2)):
                self.text(text_x, 516 - line_idx * 10, line, 7, color="0.38 0.43 0.49")
        right = self.width - self.margin
        self.text(right, 548, self.title, 17, bold=True, color="0.06 0.10 0.17", align="right")
        meta = [("Branch", self.branch), ("Period", self.period), ("Generated", self.generated), ("Currency", self.currency)]
        y = 528.0
        for label, value in meta:
            self.text(right - 155, y, label.upper(), 6.4, bold=True, color="0.50 0.53 0.58")
            self.text(right, y, value, 7.4, color="0.18 0.22 0.28", align="right")
            y -= 11
        ops.append(f"q 0.07 0.12 0.19 RG 1.2 w {_pdf_num(self.margin)} 485 m {_pdf_num(self.width - self.margin)} 485 l S Q")
        ops.append(f"q 0.79 0.65 0.35 RG 2.4 w {_pdf_num(self.margin)} 481 m {_pdf_num(self.margin + 135)} 481 l S Q")
        self.pages = old_pages
        return ops

    def _footer_ops(self, page: int, total: int) -> list[str]:
        ops: list[str] = []
        old_pages = self.pages
        self.pages = [ops]
        y = 34.0
        ops.append(f"q 0.84 0.86 0.89 RG 0.6 w {_pdf_num(self.margin)} 52 m {_pdf_num(self.width - self.margin)} 52 l S Q")
        self.text(self.margin, y, "Powered by Nexa Business Solutions", 7.4, bold=True, color="0.37 0.30 0.17")
        contact = str(self.profile.get("company_website") or self.profile.get("company_email") or self.profile.get("company_phone") or "").strip()
        if contact:
            self.text(self.width / 2, y, contact, 7.0, color="0.38 0.43 0.49", align="center")
        self.text(self.width - self.margin, y, f"Page {page} of {total}", 7.4, color="0.38 0.43 0.49", align="right")
        self.pages = old_pages
        return ops

    def build(self) -> bytes:
        if not self.pages:
            self.add_page()
        objects: list[bytes] = []

        def add_object(body: bytes) -> int:
            objects.append(body)
            return len(objects)

        font_regular = add_object(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
        font_bold = add_object(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
        image_obj = None
        if self.logo:
            img = self.logo
            image_body = (
                f"<< /Type /XObject /Subtype /Image /Width {int(img['width'])} /Height {int(img['height'])} "
                f"/ColorSpace {img['colorspace']} /BitsPerComponent {int(img.get('bits') or 8)} /Filter {img['filter']} "
                f"/Length {len(img['data'])} >>\nstream\n"
            ).encode("latin-1") + img["data"] + b"\nendstream"
            image_obj = add_object(image_body)
        pages_obj = add_object(b"")
        page_ids: list[int] = []
        total_pages = len(self.pages)
        resources = f"<< /Font << /F1 {font_regular} 0 R /F2 {font_bold} 0 R >>"
        if image_obj:
            resources += f" /XObject << /Im1 {image_obj} 0 R >>"
        resources += " >>"
        for idx, body_ops in enumerate(self.pages, start=1):
            stream_text = "\n".join(self._header_ops() + body_ops + self._footer_ops(idx, total_pages))
            stream = stream_text.encode("latin-1", "replace")
            content_obj = add_object(f"<< /Length {len(stream)} >>\nstream\n".encode("latin-1") + stream + b"\nendstream")
            page_obj = add_object(
                f"<< /Type /Page /Parent {pages_obj} 0 R /MediaBox [0 0 {_pdf_num(self.width)} {_pdf_num(self.height)}] "
                f"/Resources {resources} /Contents {content_obj} 0 R >>".encode("latin-1")
            )
            page_ids.append(page_obj)
        objects[pages_obj - 1] = f"<< /Type /Pages /Kids [{' '.join(f'{p} 0 R' for p in page_ids)}] /Count {len(page_ids)} >>".encode("latin-1")
        catalog_obj = add_object(f"<< /Type /Catalog /Pages {pages_obj} 0 R >>".encode("latin-1"))
        pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0]
        for idx, body in enumerate(objects, start=1):
            offsets.append(len(pdf))
            pdf.extend(f"{idx} 0 obj\n".encode("latin-1"))
            pdf.extend(body)
            pdf.extend(b"\nendobj\n")
        xref = len(pdf)
        pdf.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("latin-1"))
        for offset in offsets[1:]:
            pdf.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))
        pdf.extend(f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_obj} 0 R >>\nstartxref\n{xref}\n%%EOF".encode("latin-1"))
        return bytes(pdf)


def month_name(month_key: str) -> str:
    dt = datetime.strptime(month_key, "%Y-%m")
    return dt.strftime("%B %Y")


def add_months(date_text: str, months: int) -> str:
    dt = datetime.strptime(date_text, "%Y-%m-%d")
    month_index = dt.month - 1 + int(months)
    year = dt.year + month_index // 12
    month = month_index % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return datetime(year, month, day).strftime("%Y-%m-%d")


def db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    if CLOUD_MODE:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 180_000)
    return salt.hex(), digest.hex()


def verify_password(password: str, salt_hex: str, digest_hex: str) -> bool:
    _, actual = hash_password(password, bytes.fromhex(salt_hex))
    return hmac.compare_digest(actual, digest_hex)


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    if column not in table_columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def migrate_schema(conn: sqlite3.Connection) -> None:
    # Phase 2.5: payroll and attendance fields.
    ensure_column(conn, "employees", "base_salary", "REAL NOT NULL DEFAULT 0")
    # Phase 2.4.1: manual card numbering and sales-agent commission tracking.
    ensure_column(conn, "membership_cards", "sales_agent_id", "INTEGER")
    ensure_column(conn, "membership_cards", "sales_agent_name", "TEXT NOT NULL DEFAULT ''")
    ensure_column(conn, "membership_cards", "commission_rate", "REAL NOT NULL DEFAULT 10")
    ensure_column(conn, "membership_cards", "commission_amount", "REAL NOT NULL DEFAULT 0")
    # Phase 3.5: per-user interface language preference (en/ar).
    ensure_column(conn, "users", "language", "TEXT NOT NULL DEFAULT 'en'")
    # Phase 3.6: grant Company Profile / Owner Settings permissions on existing,
    # already-seeded databases (seed_data only seeds roles that have none).
    grant_company_settings_permissions(conn)


def grant_company_settings_permissions(conn: sqlite3.Connection) -> None:
    """Idempotently grant the company-settings permissions to the right roles.

    Owner and Administrator get full access (read + write); Accountant gets
    read-only. Other roles are intentionally left without access. Uses
    INSERT OR IGNORE so it is safe to run on every startup."""
    grants = {
        "Owner": ("company_settings_read", "company_settings_write"),
        "Administrator": ("company_settings_read", "company_settings_write"),
        "Accountant": ("company_settings_read",),
    }
    for role_name, permissions in grants.items():
        role = conn.execute("SELECT id FROM roles WHERE name=?", (role_name,)).fetchone()
        if not role:
            continue
        for permission in permissions:
            conn.execute(
                "INSERT OR IGNORE INTO role_permissions(role_id,permission) VALUES (?,?)",
                (role["id"], permission),
            )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_membership_agent_issue ON membership_cards(sales_agent_id,issue_date)")
    conn.execute("""UPDATE membership_cards SET sales_agent_name=COALESCE((SELECT name FROM employees WHERE employees.id=membership_cards.sales_agent_id),'')
                    WHERE TRIM(COALESCE(sales_agent_name,''))='' AND sales_agent_id IS NOT NULL""")
    # Preserve legacy Body production that previously stored completed pieces in ready_pcs.
    # When no Joint/Side entry exists for that employee/date, create the missing paired entry.
    conn.execute("""INSERT INTO production_entries(date,branch,employee_id,activity,quantity,ready_pcs,ot_hours,notes,entered_by,created_at,updated_at)
        SELECT b.date,b.branch,b.employee_id,'Joint/Side',b.ready_pcs,0,0,
               'Migrated from legacy completed-body value',b.entered_by,b.created_at,b.updated_at
        FROM production_entries b
        WHERE b.activity='Body' AND b.ready_pcs>0
          AND EXISTS (SELECT 1 FROM employee_skills es WHERE es.employee_id=b.employee_id AND es.activity='Joint/Side')
          AND NOT EXISTS (SELECT 1 FROM production_entries j WHERE j.employee_id=b.employee_id AND j.date=b.date AND j.activity='Joint/Side')""")


def init_db() -> None:
    prepare_demo_database()
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    with db_connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                full_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                role TEXT NOT NULL,
                branch TEXT NOT NULL DEFAULT 'All',
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS role_permissions (
                role_id INTEGER NOT NULL,
                permission TEXT NOT NULL,
                PRIMARY KEY(role_id, permission),
                FOREIGN KEY(role_id) REFERENCES roles(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_role_permissions_role ON role_permissions(role_id);

            CREATE TABLE IF NOT EXISTS branches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                branch TEXT NOT NULL,
                role TEXT NOT NULL,
                daily_target REAL NOT NULL DEFAULT 0,
                monthly_target REAL NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                UNIQUE(name, branch)
            );

            CREATE TABLE IF NOT EXISTS employee_skills (
                employee_id INTEGER NOT NULL,
                activity TEXT NOT NULL,
                PRIMARY KEY(employee_id, activity),
                FOREIGN KEY(employee_id) REFERENCES employees(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS finance_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                branch TEXT NOT NULL,
                type TEXT NOT NULL CHECK(type IN ('Income','Expense')),
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                amount REAL NOT NULL,
                payment_method TEXT NOT NULL DEFAULT 'Other',
                reference TEXT NOT NULL DEFAULT '',
                entered_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS pos_import_batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_name TEXT NOT NULL DEFAULT '',
                file_hash TEXT NOT NULL DEFAULT '',
                branch_override TEXT NOT NULL DEFAULT 'Auto Detect',
                post_to_finance INTEGER NOT NULL DEFAULT 1,
                revenue_basis TEXT NOT NULL DEFAULT 'Total Amount',
                rows_total INTEGER NOT NULL DEFAULT 0,
                inserted_count INTEGER NOT NULL DEFAULT 0,
                updated_count INTEGER NOT NULL DEFAULT 0,
                unchanged_count INTEGER NOT NULL DEFAULT 0,
                invalid_count INTEGER NOT NULL DEFAULT 0,
                customer_count INTEGER NOT NULL DEFAULT 0,
                imported_by TEXT NOT NULL,
                imported_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS pos_sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_no TEXT UNIQUE NOT NULL,
                sale_datetime TEXT NOT NULL,
                sale_date TEXT NOT NULL,
                branch TEXT NOT NULL,
                customer_name TEXT NOT NULL DEFAULT '',
                contact_number TEXT NOT NULL DEFAULT '',
                location TEXT NOT NULL DEFAULT '',
                payment_status TEXT NOT NULL DEFAULT '',
                payment_method TEXT NOT NULL DEFAULT '',
                total_amount REAL NOT NULL DEFAULT 0,
                total_paid REAL NOT NULL DEFAULT 0,
                sell_due REAL NOT NULL DEFAULT 0,
                sell_return_due REAL NOT NULL DEFAULT 0,
                shipping_status TEXT NOT NULL DEFAULT '',
                total_items REAL NOT NULL DEFAULT 0,
                added_by TEXT NOT NULL DEFAULT '',
                sell_note TEXT NOT NULL DEFAULT '',
                staff_note TEXT NOT NULL DEFAULT '',
                shipping_details TEXT NOT NULL DEFAULT '',
                customer_id INTEGER,
                finance_entry_id INTEGER,
                import_batch_id INTEGER,
                source_file TEXT NOT NULL DEFAULT '',
                raw_json TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(customer_id) REFERENCES customers(id),
                FOREIGN KEY(finance_entry_id) REFERENCES finance_entries(id),
                FOREIGN KEY(import_batch_id) REFERENCES pos_import_batches(id)
            );

            CREATE INDEX IF NOT EXISTS idx_pos_sales_date_branch ON pos_sales(sale_date,branch);
            CREATE INDEX IF NOT EXISTS idx_pos_sales_customer_phone ON pos_sales(contact_number);
            CREATE INDEX IF NOT EXISTS idx_pos_sales_status ON pos_sales(payment_status);
            CREATE INDEX IF NOT EXISTS idx_pos_import_date ON pos_import_batches(imported_at);

            CREATE TABLE IF NOT EXISTS customer_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_no TEXT UNIQUE NOT NULL,
                booking_date TEXT NOT NULL,
                due_date TEXT NOT NULL,
                branch TEXT NOT NULL,
                customer_name TEXT NOT NULL,
                phone TEXT NOT NULL DEFAULT '',
                item_type TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                assigned_employee_id INTEGER,
                status TEXT NOT NULL DEFAULT 'New Booking',
                total_amount REAL NOT NULL DEFAULT 0,
                advance_amount REAL NOT NULL DEFAULT 0,
                notes TEXT NOT NULL DEFAULT '',
                entered_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                delivered_at TEXT,
                FOREIGN KEY(assigned_employee_id) REFERENCES employees(id)
            );

            CREATE INDEX IF NOT EXISTS idx_orders_branch_status ON customer_orders(branch,status);
            CREATE INDEX IF NOT EXISTS idx_orders_due_date ON customer_orders(due_date);

            CREATE TABLE IF NOT EXISTS production_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                branch TEXT NOT NULL,
                employee_id INTEGER NOT NULL,
                activity TEXT NOT NULL,
                quantity REAL NOT NULL DEFAULT 0,
                ready_pcs REAL NOT NULL DEFAULT 0,
                ot_hours REAL NOT NULL DEFAULT 0,
                notes TEXT NOT NULL DEFAULT '',
                entered_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(employee_id) REFERENCES employees(id)
            );

            CREATE TABLE IF NOT EXISTS production_daily_ready (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                branch TEXT NOT NULL,
                total_ready_completed INTEGER NOT NULL DEFAULT 0,
                notes TEXT NOT NULL DEFAULT '',
                entered_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(date, branch)
            );

            CREATE INDEX IF NOT EXISTS idx_production_daily_ready_date_branch
                ON production_daily_ready(date, branch);

            CREATE TABLE IF NOT EXISTS monthly_financials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                month_key TEXT NOT NULL,
                branch TEXT NOT NULL,
                income REAL NOT NULL DEFAULT 0,
                expenses REAL NOT NULL DEFAULT 0,
                ready_pcs REAL NOT NULL DEFAULT 0,
                locked INTEGER NOT NULL DEFAULT 0,
                UNIQUE(month_key, branch)
            );

            CREATE TABLE IF NOT EXISTS production_monthly_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                month_key TEXT NOT NULL,
                employee_id INTEGER NOT NULL,
                activity TEXT NOT NULL,
                quantity REAL NOT NULL DEFAULT 0,
                ready_pcs REAL NOT NULL DEFAULT 0,
                ot_hours REAL NOT NULL DEFAULT 0,
                UNIQUE(month_key, employee_id, activity),
                FOREIGN KEY(employee_id) REFERENCES employees(id)
            );

            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                phone TEXT NOT NULL DEFAULT '',
                email TEXT NOT NULL DEFAULT '',
                branch TEXT NOT NULL,
                address TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                active INTEGER NOT NULL DEFAULT 1,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_customers_branch_name ON customers(branch,name);
            CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers(phone);

            CREATE TABLE IF NOT EXISTS membership_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                sale_price REAL NOT NULL DEFAULT 0,
                wallet_balance REAL NOT NULL DEFAULT 0,
                benefit_amount REAL NOT NULL DEFAULT 0,
                validity_months INTEGER NOT NULL DEFAULT 12,
                free_deliveries INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS membership_cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                card_no TEXT UNIQUE NOT NULL,
                customer_id INTEGER NOT NULL,
                plan_id INTEGER NOT NULL,
                branch TEXT NOT NULL,
                issue_date TEXT NOT NULL,
                expiry_date TEXT NOT NULL,
                sale_price REAL NOT NULL DEFAULT 0,
                opening_balance REAL NOT NULL DEFAULT 0,
                current_balance REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'Active',
                payment_method TEXT NOT NULL DEFAULT 'Other',
                sales_agent_id INTEGER,
                commission_rate REAL NOT NULL DEFAULT 10,
                commission_amount REAL NOT NULL DEFAULT 0,
                notes TEXT NOT NULL DEFAULT '',
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(customer_id) REFERENCES customers(id),
                FOREIGN KEY(plan_id) REFERENCES membership_plans(id),
                FOREIGN KEY(sales_agent_id) REFERENCES employees(id)
            );

            CREATE INDEX IF NOT EXISTS idx_membership_branch_status ON membership_cards(branch,status);
            CREATE INDEX IF NOT EXISTS idx_membership_expiry ON membership_cards(expiry_date);

            CREATE TABLE IF NOT EXISTS membership_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                card_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                type TEXT NOT NULL,
                amount REAL NOT NULL,
                reference TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                entered_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(card_id) REFERENCES membership_cards(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS attendance_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                employee_id INTEGER NOT NULL,
                branch TEXT NOT NULL,
                status TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                entered_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(date, employee_id),
                FOREIGN KEY(employee_id) REFERENCES employees(id)
            );

            CREATE INDEX IF NOT EXISTS idx_attendance_date_branch ON attendance_records(date,branch);

            CREATE TABLE IF NOT EXISTS payroll_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                month_key TEXT NOT NULL,
                employee_id INTEGER NOT NULL,
                branch TEXT NOT NULL,
                basic_salary REAL NOT NULL DEFAULT 0,
                commission REAL NOT NULL DEFAULT 0,
                bonus REAL NOT NULL DEFAULT 0,
                overtime_hours REAL NOT NULL DEFAULT 0,
                overtime_amount REAL NOT NULL DEFAULT 0,
                other_allowance REAL NOT NULL DEFAULT 0,
                advance_deduction REAL NOT NULL DEFAULT 0,
                other_deductions REAL NOT NULL DEFAULT 0,
                net_salary REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'Draft',
                notes TEXT NOT NULL DEFAULT '',
                entered_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                paid_at TEXT,
                UNIQUE(month_key, employee_id),
                FOREIGN KEY(employee_id) REFERENCES employees(id)
            );

            CREATE INDEX IF NOT EXISTS idx_payroll_month_branch ON payroll_records(month_key,branch);

            CREATE TABLE IF NOT EXISTS expense_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE COLLATE NOCASE NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                default_warning_percent REAL NOT NULL DEFAULT 80,
                created_by TEXT NOT NULL DEFAULT 'System',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS budget_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                month_key TEXT NOT NULL,
                branch TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Draft',
                locked INTEGER NOT NULL DEFAULT 0,
                notes TEXT NOT NULL DEFAULT '',
                created_by TEXT NOT NULL,
                approved_by TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(month_key, branch)
            );

            CREATE TABLE IF NOT EXISTS budget_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER NOT NULL,
                category_id INTEGER NOT NULL,
                budget_amount REAL NOT NULL DEFAULT 0,
                warning_percent REAL NOT NULL DEFAULT 80,
                notes TEXT NOT NULL DEFAULT '',
                updated_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(plan_id, category_id),
                FOREIGN KEY(plan_id) REFERENCES budget_plans(id) ON DELETE CASCADE,
                FOREIGN KEY(category_id) REFERENCES expense_categories(id)
            );

            CREATE TABLE IF NOT EXISTS budget_revisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                budget_item_id INTEGER NOT NULL,
                old_amount REAL NOT NULL DEFAULT 0,
                new_amount REAL NOT NULL DEFAULT 0,
                old_warning_percent REAL NOT NULL DEFAULT 80,
                new_warning_percent REAL NOT NULL DEFAULT 80,
                reason TEXT NOT NULL DEFAULT '',
                changed_by TEXT NOT NULL,
                changed_at TEXT NOT NULL,
                FOREIGN KEY(budget_item_id) REFERENCES budget_items(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS income_targets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER UNIQUE NOT NULL,
                shop_sales_target REAL NOT NULL DEFAULT 0,
                membership_target REAL NOT NULL DEFAULT 0,
                other_income_target REAL NOT NULL DEFAULT 0,
                min_profit_margin REAL NOT NULL DEFAULT 20,
                notes TEXT NOT NULL DEFAULT '',
                updated_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(plan_id) REFERENCES budget_plans(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_budget_plan_month_branch ON budget_plans(month_key,branch);
            CREATE INDEX IF NOT EXISTS idx_budget_item_plan ON budget_items(plan_id);
            CREATE INDEX IF NOT EXISTS idx_budget_revision_item ON budget_revisions(budget_item_id);

            CREATE TABLE IF NOT EXISTS notification_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                branch TEXT UNIQUE NOT NULL,
                membership_expiry_days INTEGER NOT NULL DEFAULT 30,
                low_production_percent REAL NOT NULL DEFAULT 80,
                attendance_reminder_hour INTEGER NOT NULL DEFAULT 18,
                production_reminder_hour INTEGER NOT NULL DEFAULT 18,
                payroll_reminder_day INTEGER NOT NULL DEFAULT 25,
                income_lag_tolerance_percent REAL NOT NULL DEFAULT 5,
                order_alerts INTEGER NOT NULL DEFAULT 1,
                budget_alerts INTEGER NOT NULL DEFAULT 1,
                membership_alerts INTEGER NOT NULL DEFAULT 1,
                attendance_alerts INTEGER NOT NULL DEFAULT 1,
                production_alerts INTEGER NOT NULL DEFAULT 1,
                payroll_alerts INTEGER NOT NULL DEFAULT 1,
                updated_by TEXT NOT NULL DEFAULT 'System',
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS notification_reads (
                user_id INTEGER NOT NULL,
                alert_key TEXT NOT NULL,
                read_at TEXT NOT NULL,
                PRIMARY KEY(user_id, alert_key),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_notification_reads_user ON notification_reads(user_id,read_at);

            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT NOT NULL,
                action TEXT NOT NULL,
                module TEXT NOT NULL,
                record_id TEXT NOT NULL DEFAULT '',
                details TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            );
            """
        )
        migrate_schema(conn)
        seed_data(conn)


def seed_data(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO app_settings(key,value) VALUES (?,?)",
        ("default_language", DEFAULT_LANGUAGE),
    )
    for key, value in {**DEFAULT_COMPANY_PROFILE, **DEFAULT_OWNER_TARGETS}.items():
        conn.execute("INSERT OR IGNORE INTO app_settings(key,value) VALUES (?,?)", (key, value))
    for branch in ("Al Khoud", "Azaiba", "Nizwa"):
        conn.execute("INSERT OR IGNORE INTO branches(name) VALUES (?)", (branch,))

    for role_name, spec in DEFAULT_ROLE_DEFINITIONS.items():
        conn.execute(
            "INSERT OR IGNORE INTO roles(name,description,active,created_at,updated_at) VALUES (?,?,1,?,?)",
            (role_name, spec["description"], now_iso(), now_iso()),
        )
        role_row = conn.execute("SELECT id FROM roles WHERE name=?", (role_name,)).fetchone()
        existing_permissions = conn.execute("SELECT COUNT(*) FROM role_permissions WHERE role_id=?", (role_row["id"],)).fetchone()[0]
        if existing_permissions == 0:
            for permission in sorted(spec["permissions"]):
                conn.execute("INSERT OR IGNORE INTO role_permissions(role_id,permission) VALUES (?,?)", (role_row["id"], permission))

    plan_rows = [
        ("Diamond", 2900, 4000, 1100, 24, -1),
        ("Elite", 365, 500, 135, 24, -1),
        ("Silver", 165, 250, 85, 12, 5),
        ("Golden", 200, 400, 200, 12, -1),
    ]
    for plan in plan_rows:
        conn.execute(
            """INSERT OR IGNORE INTO membership_plans(name,sale_price,wallet_balance,benefit_amount,validity_months,free_deliveries,active,created_at,updated_at)
            VALUES (?,?,?,?,?,?,1,?,?)""",
            (*plan, now_iso(), now_iso()),
        )

    default_expense_categories = [
        "Fabric Purchase", "Salaries", "Overtime", "Rent", "Marketing", "Operations",
        "Food", "Electricity", "Water", "Internet", "Transportation", "Packaging",
        "Delivery", "Maintenance", "Government Charges", "Petty Cash", "Other"
    ]
    for category_name in default_expense_categories:
        conn.execute(
            "INSERT OR IGNORE INTO expense_categories(name,active,default_warning_percent,created_by,created_at,updated_at) VALUES (?,1,80,'System',?,?)",
            (category_name, now_iso(), now_iso()),
        )
    # Keep the category master aligned with historical expense entries.
    for row in conn.execute("SELECT DISTINCT TRIM(category) name FROM finance_entries WHERE type='Expense' AND TRIM(category)<>''"):
        conn.execute(
            "INSERT OR IGNORE INTO expense_categories(name,active,default_warning_percent,created_by,created_at,updated_at) VALUES (?,1,80,'Migration',?,?)",
            (row["name"], now_iso(), now_iso()),
        )

    user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if user_count == 0:
        accounts = [
            ("owner", "Dar al Sultan Owner", "Owner@2026", "Owner", "All"),
            ("admin", "Saad Khan", "Admin@2026", "Administrator", "All"),
            ("accountant", "Company Accountant", "Accounts@2026", "Accountant", "All"),
            ("supervisor", "Al Khoud Supervisor", "Production@2026", "Production Supervisor", "Al Khoud"),
            ("viewer", "Management Viewer", "Viewer@2026", "Viewer", "All"),
        ]
        for username, full_name, password, role, branch in accounts:
            salt, digest = hash_password(password)
            conn.execute(
                "INSERT INTO users(username,full_name,password_hash,salt,role,branch,created_at) VALUES (?,?,?,?,?,?,?)",
                (username, full_name, digest, salt, role, branch, now_iso()),
            )

    employee_rows = [
        ("Arshad Ansari", "Al Khoud", "Body Making", 10, 250),
        ("Bilal Ahmed", "Al Khoud", "Body Making", 10, 250),
        ("Riyaz Ahmed", "Al Khoud", "Body Making", 10, 250),
        ("Talib Ahmed", "Al Khoud", "Daraz Maker", 9, 225),
        ("Ramzan", "Al Khoud", "VIP Design Maker", 9, 225),
        ("Muzaffar", "Al Khoud", "VIP Design Maker", 9, 225),
        ("Dilshad", "Al Khoud", "Master Cutter", 12, 300),
        ("Siraj", "Al Khoud", "Alteration + Button", 9, 220),
        ("Jakie", "Al Khoud", "Ironing", 12, 300),
        ("Nasir", "Al Khoud", "Daraz Maker", 9, 225),
        ("Waheed", "Azaiba", "Daraz Maker", 9, 225),
        ("Belal", "Azaiba", "Body Making", 10, 250),
        ("Nasim Ali", "Azaiba", "Daraz Maker", 9, 225),
        ("Nasim Ahmed", "Azaiba", "Daraz Maker", 9, 225),
    ]
    for row in employee_rows:
        conn.execute(
            "INSERT OR IGNORE INTO employees(name,branch,role,daily_target,monthly_target) VALUES (?,?,?,?,?)",
            row,
        )

    # Phase 2.2 migration: every employee can have one or more production categories.
    for emp in conn.execute("SELECT id,role FROM employees"):
        existing_skills = conn.execute(
            "SELECT COUNT(*) FROM employee_skills WHERE employee_id=?", (emp["id"],)
        ).fetchone()[0]
        if existing_skills == 0:
            for activity in DEFAULT_ROLE_SKILLS.get(emp["role"], ("Sample",)):
                conn.execute(
                    "INSERT OR IGNORE INTO employee_skills(employee_id,activity) VALUES (?,?)",
                    (emp["id"], activity),
                )

    if conn.execute("SELECT COUNT(*) FROM monthly_financials").fetchone()[0] == 0:
        data = {
            "2026-01": {"Al Khoud": (9898, 7918.40, 340), "Azaiba": (6511.40, 5209.10, 272), "Nizwa": (0, 0, 0)},
            "2026-02": {"Al Khoud": (9042, 7233.60, 330), "Azaiba": (6921.40, 5537.10, 268), "Nizwa": (0, 0, 0)},
            "2026-03": {"Al Khoud": (10350, 8280, 365), "Azaiba": (7120, 5696, 270), "Nizwa": (780, 624, 20)},
            "2026-04": {"Al Khoud": (10850, 8680, 380), "Azaiba": (7580, 6064, 282), "Nizwa": (950, 760, 26)},
            "2026-05": {"Al Khoud": (12200, 9700, 410), "Azaiba": (8550, 6800, 280), "Nizwa": (1750, 1400, 30)},
        }
        for month_key, branch_values in data.items():
            for branch, vals in branch_values.items():
                conn.execute(
                    "INSERT INTO monthly_financials(month_key,branch,income,expenses,ready_pcs,locked) VALUES (?,?,?,?,?,1)",
                    (month_key, branch, vals[0], vals[1], vals[2]),
                )

    if conn.execute("SELECT COUNT(*) FROM finance_entries").fetchone()[0] == 0:
        entries = [
            ("2026-06-01","Al Khoud","Income","Shop Sales","Sales 1–3 June",1750,"Visa","AK-JUN-01"),
            ("2026-06-04","Al Khoud","Income","Membership Cards","Elite and Silver card sales",730,"Online","AK-MEM-01"),
            ("2026-06-08","Al Khoud","Income","Shop Sales","Sales 4–8 June",1420,"Visa","AK-JUN-02"),
            ("2026-06-02","Al Khoud","Expense","Fabric Purchase","Monthly fabric purchase — batch 1",1600,"Bank","AK-FAB-01"),
            ("2026-06-05","Al Khoud","Expense","Salaries","Salary and overtime allocation",900,"Bank","AK-SAL-01"),
            ("2026-06-09","Al Khoud","Expense","Operations","Food, delivery and supplies",400,"Cash","AK-OPS-01"),
            ("2026-06-01","Azaiba","Income","Shop Sales","Sales 1–4 June",1200,"Visa","AZ-JUN-01"),
            ("2026-06-05","Azaiba","Income","Membership Cards","Membership card sales",365,"Online","AZ-MEM-01"),
            ("2026-06-09","Azaiba","Income","Shop Sales","Sales 5–9 June",1135,"Visa","AZ-JUN-02"),
            ("2026-06-03","Azaiba","Expense","Fabric Purchase","Fabric transfer and purchase",1100,"Bank","AZ-FAB-01"),
            ("2026-06-06","Azaiba","Expense","Salaries","Salary allocation",700,"Bank","AZ-SAL-01"),
            ("2026-06-09","Azaiba","Expense","Marketing","Branch marketing and delivery",300,"Cash","AZ-MKT-01"),
            ("2026-06-03","Nizwa","Income","Shop Sales","Sales and bookings",650,"Visa","NZ-JUN-01"),
            ("2026-06-09","Nizwa","Income","Shop Sales","Sales and balance collections",600,"Cash","NZ-JUN-02"),
            ("2026-06-04","Nizwa","Expense","Rent","Rent allocation",500,"Bank","NZ-RENT-01"),
            ("2026-06-08","Nizwa","Expense","Operations","Delivery and branch operations",420,"Cash","NZ-OPS-01"),
        ]
        for e in entries:
            conn.execute(
                """INSERT INTO finance_entries(date,branch,type,category,description,amount,payment_method,reference,entered_by,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (*e, "System Seed", now_iso(), now_iso()),
            )

    if conn.execute("SELECT COUNT(*) FROM customer_orders").fetchone()[0] == 0:
        employee_map = {r["name"]: r["id"] for r in conn.execute("SELECT id,name FROM employees")}
        sample_orders = [
            ("DAS-2026-0001","2026-06-01","2026-06-09","Al Khoud","Ahmed Al Balushi","99112233","Dishdasha",2,employee_map.get("Arshad Ansari"),"Body Making",120,60,"Premium white fabric"),
            ("DAS-2026-0002","2026-06-02","2026-06-12","Al Khoud","Salim Al Harthy","99224411","Dishdasha",1,employee_map.get("Ramzan"),"Daraz/Design",85,40,"VIP design"),
            ("DAS-2026-0003","2026-06-03","2026-06-10","Azaiba","Khalid Al Amri","99887722","Dishdasha",2,employee_map.get("Waheed"),"Ready",140,100,"Call customer when ready"),
            ("DAS-2026-0004","2026-06-04","2026-06-15","Azaiba","Mohammed Al Rawahi","99335577","Kids Dishdasha",3,employee_map.get("Belal"),"Cutting",105,50,"Three sizes"),
            ("DAS-2026-0005","2026-06-05","2026-06-08","Nizwa","Said Al Busaidi","99776655","Dishdasha",1,None,"Quality Check",70,70,"Production handled by Al Khoud"),
            ("DAS-2026-0006","2026-06-06","2026-06-10","Al Khoud","Abdullah Al Shuaibi","99001122","Musar",1,None,"Delivered",45,45,"Delivered on time"),
        ]
        for order in sample_orders:
            delivered_at = "2026-06-10 18:00:00" if order[9] == "Delivered" else None
            conn.execute(
                """INSERT INTO customer_orders(order_no,booking_date,due_date,branch,customer_name,phone,item_type,quantity,assigned_employee_id,status,total_amount,advance_amount,notes,entered_by,created_at,updated_at,delivered_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (*order, "System Seed", now_iso(), now_iso(), delivered_at),
            )

    if conn.execute("SELECT COUNT(*) FROM production_entries").fetchone()[0] == 0:
        emp_map = {r["name"]: r["id"] for r in conn.execute("SELECT id,name FROM employees")}
        rows: list[tuple] = []

        def add(date: str, employee: str, branch: str, activity: str, qty: float, ready: float = 0, ot: float = 0) -> None:
            rows.append((date, branch, emp_map[employee], activity, qty, ready, ot, "", "System Seed", now_iso(), now_iso()))

        days = [1,2,3,4,6,7,8,9,10]
        ar_body = [5,4,5,4,6,5,5,5,6]
        ar_joint = [3,3,4,3,4,3,3,3,4]
        for i, d in enumerate(days):
            date = f"2026-06-{d:02d}"
            add(date,"Arshad Ansari","Al Khoud","Body",ar_body[i],0,1 if i==1 else 0)
            add(date,"Arshad Ansari","Al Khoud","Joint/Side",ar_joint[i],ar_joint[i])

        series = {
            ("Bilal Ahmed","Al Khoud","Body"): ([4,5,4,5,4,5,5,5,5],[2,3,2,3,2,3,2,3,3]),
            ("Ramzan","Al Khoud","VIP Design"): ([4,4,5,4,4,4,4,4,5],[4,4,5,4,4,4,4,4,5]),
            ("Talib Ahmed","Al Khoud","Daraz"): ([5,4,5,4,5,4,5,4,4],[5,4,5,4,5,4,5,4,4]),
            ("Waheed","Azaiba","Daraz"): ([4,4,3,4,4,3,4,4,4],[4,4,3,4,4,3,4,4,4]),
            ("Belal","Azaiba","Body"): ([5,4,5,5,4,5,4,5,5],[2,3,2,3,2,3,2,2,3]),
            ("Dilshad","Al Khoud","Cutting"): ([12,14,13,12,15,14,13,14,15],[0]*9),
            ("Jakie","Al Khoud","Iron"): ([11,12,10,13,12,11,13,12,14],[2,2,2,2,2,2,2,2,2]),
            ("Nasim Ali","Azaiba","Daraz"): ([3,4,3,4,3,4,3,4,3],[2,2,2,2,2,2,2,2,2]),
        }
        for (employee, branch, activity), (qtys, readies) in series.items():
            for i, d in enumerate(days):
                add(f"2026-06-{d:02d}", employee, branch, activity, qtys[i], readies[i], 1.5 if employee=="Talib Ahmed" and d==10 else 0)

        conn.executemany(
            """INSERT INTO production_entries(date,branch,employee_id,activity,quantity,ready_pcs,ot_hours,notes,entered_by,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""", rows,
        )

    if conn.execute("SELECT COUNT(*) FROM production_monthly_history").fetchone()[0] == 0:
        employee_rows = list(conn.execute("SELECT id,name,role FROM employees"))
        month_factors = {"2026-01": 0.88, "2026-02": 0.92, "2026-03": 1.00, "2026-04": 1.05, "2026-05": 1.12}
        base_by_role = {
            "Body Making": ("Body", 135, 100),
            "Daraz Maker": ("Daraz", 125, 112),
            "VIP Design Maker": ("VIP Design", 118, 105),
            "Master Cutter": ("Cutting", 285, 0),
            "Alteration + Button": ("Button", 150, 92),
            "Ironing": ("Iron", 270, 118),
        }
        for emp in employee_rows:
            activity, base_qty, base_ready = base_by_role.get(emp["role"], ("Other", 100, 80))
            for idx, (month_key, factor) in enumerate(month_factors.items()):
                variation = ((emp["id"] * 7 + idx * 3) % 11) - 5
                qty = max(0, round(base_qty * factor + variation))
                ready = max(0, round(base_ready * factor + variation/2))
                ot = max(0, round((idx + emp["id"] % 4) * 1.5, 1))
                conn.execute(
                    "INSERT OR IGNORE INTO production_monthly_history(month_key,employee_id,activity,quantity,ready_pcs,ot_hours) VALUES (?,?,?,?,?,?)",
                    (month_key, emp["id"], activity, qty, ready, ot),
                )
                if emp["name"] == "Arshad Ansari":
                    body_map = {"2026-01":125,"2026-02":132,"2026-03":140,"2026-04":146,"2026-05":154}
                    joint_map = {"2026-01":98,"2026-02":102,"2026-03":110,"2026-04":114,"2026-05":120}
                    ready_map = {"2026-01":95,"2026-02":100,"2026-03":108,"2026-04":112,"2026-05":118}
                    conn.execute("DELETE FROM production_monthly_history WHERE month_key=? AND employee_id=?", (month_key, emp["id"]))
                    conn.execute(
                        "INSERT INTO production_monthly_history(month_key,employee_id,activity,quantity,ready_pcs,ot_hours) VALUES (?,?,?,?,?,?)",
                        (month_key, emp["id"], "Body", body_map[month_key], 0, ot),
                    )
                    conn.execute(
                        "INSERT INTO production_monthly_history(month_key,employee_id,activity,quantity,ready_pcs,ot_hours) VALUES (?,?,?,?,?,?)",
                        (month_key, emp["id"], "Joint/Side", joint_map[month_key], ready_map[month_key], 0),
                    )

    # Phase 2.7: editable alert thresholds for consolidated and branch views.
    for alert_branch in ("All", "Al Khoud", "Azaiba", "Nizwa"):
        conn.execute(
            """INSERT OR IGNORE INTO notification_settings(
            branch,membership_expiry_days,low_production_percent,attendance_reminder_hour,
            production_reminder_hour,payroll_reminder_day,income_lag_tolerance_percent,
            updated_by,updated_at) VALUES (?,?,?,?,?,?,?,?,?)""",
            (alert_branch,30,80,18,18,25,5,"System",now_iso()),
        )


def json_bytes(data: Any) -> bytes:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


def log_audit(conn: sqlite3.Connection, user: dict[str, Any], action: str, module: str, record_id: Any = "", details: str = "") -> None:
    conn.execute(
        "INSERT INTO audit_logs(user_id,username,action,module,record_id,details,created_at) VALUES (?,?,?,?,?,?,?)",
        (user.get("id"), user.get("username", "System"), action, module, str(record_id), details[:1000], now_iso()),
    )


class AppHandler(BaseHTTPRequestHandler):
    server_version = "DarAlSultan/3.1"

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if CLOUD_MODE:
            self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        super().end_headers()

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string()}] {fmt % args}")

    def send_json(self, data: Any, status: int = 200, headers: dict[str, str] | None = None) -> None:
        body = json_bytes(data)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if headers:
            for k, v in headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, message: str, status: int = 400) -> None:
        self.send_json({"ok": False, "error": message}, status)

    def parse_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length > 15_000_000:
            raise ValueError("Request too large (maximum 15 MB)")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid JSON") from exc

    def query(self) -> dict[str, list[str]]:
        return urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)

    def path_only(self) -> str:
        return urllib.parse.urlparse(self.path).path

    def get_session_token(self) -> str | None:
        raw = self.headers.get("Cookie")
        if not raw:
            return None
        jar = cookies.SimpleCookie()
        try:
            jar.load(raw)
            return jar.get("das_session").value if jar.get("das_session") else None
        except cookies.CookieError:
            return None

    def current_user(self) -> dict[str, Any] | None:
        token = self.get_session_token()
        if not token:
            return None
        with SESSION_LOCK:
            session = SESSIONS.get(token)
            if not session:
                return None
            if datetime.now() - session["last_seen"] > timedelta(hours=12):
                SESSIONS.pop(token, None)
                return None
            session["last_seen"] = datetime.now()
            return session["user"]

    def require_user(self) -> dict[str, Any] | None:
        user = self.current_user()
        if not user:
            self.send_error_json("Authentication required", 401)
            return None
        return user

    def permissions_for_role(self, role: str) -> set[str]:
        try:
            with db_connect() as conn:
                rows = conn.execute("""SELECT rp.permission FROM role_permissions rp
                    JOIN roles r ON r.id=rp.role_id WHERE r.name=? AND r.active=1""", (role,)).fetchall()
            if rows:
                return {r["permission"] for r in rows}
        except sqlite3.Error:
            pass
        return set(ROLE_PERMISSIONS.get(role, set()))

    def has_permission(self, user: dict[str, Any], permission: str) -> bool:
        return permission in self.permissions_for_role(user.get("role", ""))

    def require_permission(self, user: dict[str, Any], permission: str) -> bool:
        if not self.has_permission(user, permission):
            self.send_error_json("You do not have permission for this action", 403)
            return False
        return True

    def allowed_branch(self, user: dict[str, Any], requested: str | None) -> str:
        assigned = user.get("branch", "All")
        if assigned != "All":
            return assigned
        return requested or "All"

    def serve_static(self) -> None:
        path = self.path_only()
        if path == "/":
            file_path = STATIC_DIR / "index.html"
        else:
            rel = path.lstrip("/")
            file_path = (STATIC_DIR / rel).resolve()
            if STATIC_DIR.resolve() not in file_path.parents:
                self.send_error(403)
                return
        if not file_path.exists() or not file_path.is_file():
            self.send_error(404)
            return
        content = file_path.read_bytes()
        ctype = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:
        path = self.path_only()
        try:
            if not path.startswith("/api/"):
                self.serve_static()
                return
            if path == "/api/health":
                with db_connect() as conn:
                    default_language = normalize_language(get_setting(conn, "default_language", DEFAULT_LANGUAGE))
                    profile = get_company_profile(conn)
                self.send_json({
                    "ok": True,
                    "version": APP_VERSION,
                    "cloud_mode": CLOUD_MODE,
                    "runtime_demo_mode": DEMO_MODE,
                    "demo_mode": profile["demo_mode"],
                    "demo_banner_text": profile["demo_banner_text"],
                    "database": "SQLite demo" if DEMO_MODE else "SQLite local",
                    "default_language": default_language,
                    "supported_languages": list(SUPPORTED_LANGUAGES),
                    "company_name": profile["company_name"],
                    "company_subtitle": profile["company_subtitle"],
                    "currency_label": profile["currency_label"],
                    "company_phone": profile["company_phone"],
                    "company_email": profile["company_email"],
                    "company_address": profile["company_address"],
                    "company_website": profile["company_website"],
                    "company_logo_updated": profile["company_logo_updated"],
                    "has_custom_logo": profile["has_custom_logo"],
                    "time": now_iso(),
                })
                return
            if path == "/api/company/logo":
                self.handle_company_logo()
                return
            user = self.require_user()
            if not user:
                return
            if path == "/api/me":
                safe = {k: user[k] for k in ("id","username","full_name","role","branch","active")}
                safe["language"] = normalize_language(user.get("language"))
                safe["permissions"] = sorted(self.permissions_for_role(user["role"]))
                self.send_json({"ok": True, "user": safe})
            elif path == "/api/settings":
                self.handle_settings_get(user)
            elif path == "/api/company/profile":
                self.handle_company_profile_get(user)
            elif path == "/api/company/targets":
                self.handle_company_targets_get(user)
            elif path == "/api/branches/manage":
                self.handle_branches_manage_get(user)
            elif path == "/api/branches":
                with db_connect() as conn:
                    branches = [dict(r) for r in conn.execute("SELECT id,name FROM branches WHERE active=1 ORDER BY id")]
                self.send_json({"ok": True, "branches": branches})
            elif path == "/api/roles":
                self.handle_roles(user)
            elif path == "/api/dashboard":
                self.handle_dashboard(user)
            elif path == "/api/notifications":
                self.handle_notifications(user)
            elif path == "/api/employees":
                self.handle_employees(user)
            elif path == "/api/orders":
                self.handle_orders_list(user)
            elif path == "/api/membership":
                self.handle_membership_list(user)
            elif path == "/api/membership/plans":
                self.handle_membership_plans(user)
            elif path == "/api/membership/transactions":
                self.handle_membership_transactions(user)
            elif path == "/api/membership/commissions":
                self.handle_membership_commissions(user)
            elif path == "/api/customers":
                self.handle_customers(user)
            elif path == "/api/budget":
                self.handle_budget_overview(user)
            elif path == "/api/budget/categories":
                self.handle_budget_categories(user)
            elif path == "/api/payroll":
                self.handle_payroll_list(user)
            elif path == "/api/attendance":
                self.handle_attendance_list(user)
            elif path == "/api/production":
                self.handle_production_list(user)
            elif path == "/api/production-ready":
                self.handle_production_ready_list(user)
            elif path == "/api/production/history":
                self.handle_production_history(user)
            elif path == "/api/finance":
                self.handle_finance_list(user)
            elif path == "/api/pos-sales":
                self.handle_pos_sales_list(user)
            elif path == "/api/pos-sales/imports":
                self.handle_pos_import_batches(user)
            elif path == "/api/sales/import/template.csv":
                self.handle_sales_import_template_csv(user)
            elif path == "/api/sales/import/template.xlsx":
                self.handle_sales_import_template_xlsx(user)
            elif path == "/api/audit":
                self.handle_audit(user)
            elif path == "/api/users":
                self.handle_users(user)
            elif path == "/api/export/finance.csv":
                self.handle_export_finance(user)
            elif path == "/api/export/finance.pdf":
                self.handle_export_finance_pdf(user)
            elif path == "/api/export/production.csv":
                self.handle_export_production(user)
            elif path == "/api/export/production.pdf":
                self.handle_export_production_pdf(user)
            elif path == "/api/export/orders.csv":
                self.handle_export_orders(user)
            elif path == "/api/export/orders.pdf":
                self.handle_export_orders_pdf(user)
            elif path == "/api/export/membership.csv":
                self.handle_export_membership(user)
            elif path == "/api/export/membership.pdf":
                self.handle_export_membership_pdf(user)
            elif path == "/api/export/membership_commissions.csv":
                self.handle_export_membership_commissions(user)
            elif path == "/api/export/membership_commissions.pdf":
                self.handle_export_membership_commissions_pdf(user)
            elif path == "/api/export/budget.csv":
                self.handle_export_budget(user)
            elif path == "/api/export/budget.pdf":
                self.handle_export_budget_pdf(user)
            elif path == "/api/export/notifications.csv":
                self.handle_export_notifications(user)
            elif path == "/api/export/notifications.pdf":
                self.handle_export_notifications_pdf(user)
            elif path == "/api/export/payroll.csv":
                self.handle_export_payroll(user)
            elif path == "/api/export/payroll.pdf":
                self.handle_export_payroll_pdf(user)
            elif path == "/api/export/attendance.csv":
                self.handle_export_attendance(user)
            elif path == "/api/export/attendance.pdf":
                self.handle_export_attendance_pdf(user)
            elif path == "/api/export/pos-sales.csv":
                self.handle_export_pos_sales(user)
            elif path == "/api/export/pos-sales.pdf":
                self.handle_export_pos_sales_pdf(user)
            elif path == "/api/backup":
                self.handle_backup(user)
            else:
                self.send_error_json("Endpoint not found", 404)
        except Exception as exc:
            print("GET error:", repr(exc))
            self.send_error_json("Unexpected server error", 500)

    def do_POST(self) -> None:
        path = self.path_only()
        try:
            if path == "/api/login":
                self.handle_login()
                return
            user = self.require_user()
            if not user:
                return
            if path == "/api/logout":
                self.handle_logout(user)
            elif path == "/api/me/language":
                self.handle_user_language_save(user)
            elif path == "/api/settings":
                self.handle_settings_save(user)
            elif path == "/api/company/profile":
                self.handle_company_profile_save(user)
            elif path == "/api/company/targets":
                self.handle_company_targets_save(user)
            elif path == "/api/branches/manage":
                self.handle_branch_create(user)
            elif path == "/api/notifications/read":
                self.handle_notification_read(user)
            elif path == "/api/notifications/settings":
                self.handle_notification_settings_save(user)
            elif path == "/api/budget/plan":
                self.handle_budget_plan_save(user)
            elif path == "/api/budget/copy":
                self.handle_budget_copy(user)
            elif path == "/api/budget/status":
                self.handle_budget_status(user)
            elif path == "/api/budget/categories":
                self.handle_budget_category_create(user)
            elif path == "/api/payroll":
                self.handle_payroll_save(user)
            elif path == "/api/attendance":
                self.handle_attendance_save(user)
            elif path == "/api/production":
                self.handle_production_create(user)
            elif path == "/api/production-ready":
                self.handle_production_ready_save(user)
            elif path == "/api/orders":
                self.handle_order_create(user)
            elif path == "/api/customers":
                self.handle_customer_create(user)
            elif path == "/api/membership/cards":
                self.handle_membership_card_create(user)
            elif path == "/api/membership/plans":
                self.handle_membership_plan_create(user)
            elif path == "/api/membership/transactions":
                self.handle_membership_transaction_create(user)
            elif path == "/api/employees":
                self.handle_employee_create(user)
            elif path == "/api/finance":
                self.handle_finance_create(user)
            elif path == "/api/pos-sales/preview":
                self.handle_pos_sales_preview(user)
            elif path == "/api/pos-sales/import":
                self.handle_pos_sales_import(user)
            elif path == "/api/users":
                self.handle_user_create(user)
            elif path == "/api/roles":
                self.handle_role_create(user)
            else:
                self.send_error_json("Endpoint not found", 404)
        except ValueError as exc:
            self.send_error_json(str(exc), 400)
        except sqlite3.IntegrityError as exc:
            self.send_error_json(f"Database validation error: {exc}", 400)
        except Exception as exc:
            print("POST error:", repr(exc))
            self.send_error_json("Unexpected server error", 500)

    def do_PUT(self) -> None:
        path = self.path_only()
        try:
            user = self.require_user()
            if not user:
                return
            if path.startswith("/api/branches/manage/"):
                self.handle_branch_update(user, int(path.rsplit("/",1)[1]))
            elif path.startswith("/api/budget/categories/"):
                self.handle_budget_category_update(user, int(path.rsplit("/",1)[1]))
            elif path.startswith("/api/production/"):
                self.handle_production_update(user, int(path.rsplit("/",1)[1]))
            elif path.startswith("/api/orders/"):
                self.handle_order_update(user, int(path.rsplit("/",1)[1]))
            elif path.startswith("/api/customers/"):
                self.handle_customer_update(user, int(path.rsplit("/",1)[1]))
            elif path.startswith("/api/membership/cards/"):
                self.handle_membership_card_update(user, int(path.rsplit("/",1)[1]))
            elif path.startswith("/api/membership/plans/"):
                self.handle_membership_plan_update(user, int(path.rsplit("/",1)[1]))
            elif path.startswith("/api/employees/"):
                self.handle_employee_update(user, int(path.rsplit("/",1)[1]))
            elif path.startswith("/api/finance/"):
                self.handle_finance_update(user, int(path.rsplit("/",1)[1]))
            elif path.startswith("/api/users/"):
                self.handle_user_update(user, int(path.rsplit("/",1)[1]))
            elif path.startswith("/api/roles/"):
                self.handle_role_update(user, int(path.rsplit("/",1)[1]))
            else:
                self.send_error_json("Endpoint not found", 404)
        except (ValueError, TypeError, sqlite3.IntegrityError) as exc:
            self.send_error_json(str(exc), 400)
        except Exception as exc:
            print("PUT error:", repr(exc))
            self.send_error_json("Unexpected server error", 500)

    def do_DELETE(self) -> None:
        path = self.path_only()
        try:
            user = self.require_user()
            if not user:
                return
            if path.startswith("/api/attendance/"):
                self.handle_attendance_delete(user, int(path.rsplit("/",1)[1]))
            elif path.startswith("/api/production-ready/"):
                self.handle_production_ready_delete(user, int(path.rsplit("/",1)[1]))
            elif path.startswith("/api/production/"):
                self.handle_production_delete(user, int(path.rsplit("/",1)[1]))
            elif path.startswith("/api/orders/"):
                self.handle_order_delete(user, int(path.rsplit("/",1)[1]))
            elif path.startswith("/api/membership/cards/"):
                self.handle_membership_card_delete(user, int(path.rsplit("/",1)[1]))
            elif path.startswith("/api/pos-sales/"):
                self.handle_pos_sale_delete(user, int(path.rsplit("/",1)[1]))
            elif path.startswith("/api/finance/"):
                self.handle_finance_delete(user, int(path.rsplit("/",1)[1]))
            else:
                self.send_error_json("Endpoint not found", 404)
        except Exception as exc:
            print("DELETE error:", repr(exc))
            self.send_error_json("Unexpected server error", 500)

    def handle_login(self) -> None:
        data = self.parse_json()
        username = str(data.get("username", "")).strip().lower()
        password = str(data.get("password", ""))
        if not username or not password:
            raise ValueError("Username and password are required")
        with db_connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
            if not row or not row["active"] or not verify_password(password, row["salt"], row["password_hash"]):
                self.send_error_json("Invalid username or password", 401)
                return
            user = dict(row)
            token = secrets.token_urlsafe(32)
            with SESSION_LOCK:
                SESSIONS[token] = {"user": user, "last_seen": datetime.now()}
            log_audit(conn, user, "LOGIN", "Authentication", user["id"], "Successful login")
        cookie_secure = "; Secure" if CLOUD_MODE else ""
        headers = {"Set-Cookie": f"das_session={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=43200{cookie_secure}"}
        safe = {k: user[k] for k in ("id","username","full_name","role","branch","active")}
        safe["language"] = normalize_language(user.get("language"))
        safe["permissions"] = sorted(self.permissions_for_role(user["role"]))
        self.send_json({"ok": True, "user": safe}, headers=headers)

    def handle_logout(self, user: dict[str, Any]) -> None:
        token = self.get_session_token()
        if token:
            with SESSION_LOCK:
                SESSIONS.pop(token, None)
        with db_connect() as conn:
            log_audit(conn, user, "LOGOUT", "Authentication", user["id"], "User logged out")
        self.send_json({"ok": True}, headers={"Set-Cookie": f"das_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0{'; Secure' if CLOUD_MODE else ''}"})

    def handle_user_language_save(self, user: dict[str, Any]) -> None:
        data = self.parse_json()
        language = normalize_language(data.get("language"), fallback="")
        if not language:
            raise ValueError("Unsupported language")
        with db_connect() as conn:
            conn.execute("UPDATE users SET language=? WHERE id=?", (language, user["id"]))
        user["language"] = language
        self.send_json({"ok": True, "language": language})

    def handle_settings_get(self, user: dict[str, Any]) -> None:
        with db_connect() as conn:
            default_language = normalize_language(get_setting(conn, "default_language", DEFAULT_LANGUAGE))
        self.send_json({
            "ok": True,
            "default_language": default_language,
            "supported_languages": list(SUPPORTED_LANGUAGES),
            "can_manage": self.has_permission(user, "users"),
        })

    def handle_settings_save(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "users"):
            return
        data = self.parse_json()
        language = normalize_language(data.get("default_language"), fallback="")
        if not language:
            raise ValueError("Unsupported language")
        with db_connect() as conn:
            set_setting(conn, "default_language", language)
            log_audit(conn, user, "UPDATE", "Settings", "default_language", f"Set company default language to {language}")
        self.send_json({"ok": True, "default_language": language})

    # ---- Company Profile & Owner Settings (Phase 3.6) ----
    LOGO_MIME_EXT = {
        "image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg",
        "image/webp": "webp", "image/svg+xml": "svg",
    }
    MAX_LOGO_BYTES = 2 * 1024 * 1024

    def handle_company_logo(self) -> None:
        """Public: serve the active company logo. When no custom logo has been
        uploaded, return a neutral generic placeholder (no client branding)."""
        with db_connect() as conn:
            data_b64 = get_setting(conn, "company_logo_data", "")
            mime = get_setting(conn, "company_logo_mime", "")
        if data_b64:
            try:
                content = base64.b64decode(data_b64)
            except Exception:
                content = b""
            if content:
                self.send_response(200)
                self.send_header("Content-Type", mime or "image/png")
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(content)
                return
        # No custom logo uploaded — serve a neutral generic placeholder so the
        # app assumes no client-specific branding by default.
        placeholder = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="240" height="160" '
            'viewBox="0 0 240 160">'
            '<rect x="3" y="3" width="234" height="154" rx="16" fill="none" '
            'stroke="#9ba7b7" stroke-width="2" stroke-dasharray="7 7" opacity="0.45"/>'
            '<g fill="none" stroke="#9ba7b7" stroke-width="2.5" opacity="0.55" '
            'stroke-linecap="round" stroke-linejoin="round">'
            '<rect x="84" y="52" width="72" height="56" rx="8"/>'
            '<circle cx="104" cy="72" r="7"/>'
            '<path d="M88 104 L110 82 L128 98 L140 88 L152 104"/>'
            '</g></svg>'
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "image/svg+xml")
        self.send_header("Content-Length", str(len(placeholder)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(placeholder)

    def handle_company_profile_get(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "company_settings_read"):
            return
        with db_connect() as conn:
            profile = get_company_profile(conn)
        profile["can_manage"] = self.has_permission(user, "company_settings_write")
        self.send_json({"ok": True, "profile": profile})

    def handle_company_profile_save(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "company_settings_write"):
            return
        data = self.parse_json()
        name = str(data.get("company_name", "")).strip()
        if not name:
            raise ValueError("Company name is required")
        currency_label = str(data.get("currency_label", DEFAULT_COMPANY_PROFILE["currency_label"])).strip().upper()
        if not currency_label:
            currency_label = DEFAULT_COMPANY_PROFILE["currency_label"]
        if len(currency_label) > 12:
            raise ValueError("Currency label must be 12 characters or fewer")
        demo_banner_text = str(data.get("demo_banner_text", DEFAULT_COMPANY_PROFILE["demo_banner_text"])).strip()
        if not demo_banner_text:
            demo_banner_text = DEFAULT_COMPANY_PROFILE["demo_banner_text"]
        if len(demo_banner_text) > 160:
            raise ValueError("Demo banner text must be 160 characters or fewer")
        values = {
            "company_name": name,
            "company_subtitle": str(data.get("company_subtitle", "")).strip(),
            "currency_label": currency_label,
            "company_address": str(data.get("company_address", "")).strip(),
            "company_phone": str(data.get("company_phone", "")).strip(),
            "company_email": str(data.get("company_email", "")).strip(),
            "company_website": str(data.get("company_website", "")).strip(),
            "company_vat": str(data.get("company_vat", "")).strip(),
            "demo_mode": "1" if setting_enabled(data.get("demo_mode"), default=True) else "0",
            "demo_banner_text": demo_banner_text,
        }
        logo_data = data.get("logo_data")
        logo_mime = str(data.get("logo_mime", "")).strip().lower()
        remove_logo = bool(data.get("remove_logo"))
        with db_connect() as conn:
            for key, value in values.items():
                set_setting(conn, key, value)
            if remove_logo:
                set_setting(conn, "company_logo_data", "")
                set_setting(conn, "company_logo_mime", "")
                set_setting(conn, "company_logo_updated", now_iso())
            elif logo_data:
                raw = str(logo_data)
                if "," in raw and raw.strip().lower().startswith("data:"):
                    header, raw = raw.split(",", 1)
                    if not logo_mime and ":" in header and ";" in header:
                        logo_mime = header.split(":", 1)[1].split(";", 1)[0].strip().lower()
                try:
                    decoded = base64.b64decode(raw)
                except Exception:
                    raise ValueError("Logo file could not be read")
                if len(decoded) > self.MAX_LOGO_BYTES:
                    raise ValueError("Logo must be 2 MB or smaller")
                if logo_mime not in self.LOGO_MIME_EXT:
                    raise ValueError("Logo must be a PNG, JPG, WEBP or SVG image")
                set_setting(conn, "company_logo_data", base64.b64encode(decoded).decode("ascii"))
                set_setting(conn, "company_logo_mime", logo_mime)
                set_setting(conn, "company_logo_updated", now_iso())
            profile = get_company_profile(conn)
            log_audit(conn, user, "UPDATE", "Company", "profile", f"Updated company profile ({name})")
        profile["can_manage"] = True
        self.send_json({"ok": True, "profile": profile})

    def handle_company_targets_get(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "company_settings_read"):
            return
        with db_connect() as conn:
            targets = get_owner_targets(conn)
        targets["can_manage"] = self.has_permission(user, "company_settings_write")
        self.send_json({"ok": True, "targets": targets})

    def handle_company_targets_save(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "company_settings_write"):
            return
        data = self.parse_json()
        saved = {}
        with db_connect() as conn:
            for field in OWNER_TARGET_FIELDS:
                value = float(data.get(field, 0) or 0)
                if value < 0:
                    raise ValueError("Targets cannot be negative")
                set_setting(conn, field, str(value))
                saved[field] = str(value)
            log_audit(conn, user, "UPDATE", "Company", "targets", "Updated company-level targets")
        self.send_json({"ok": True, "targets": saved})

    def handle_branches_manage_get(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "company_settings_read"):
            return
        with db_connect() as conn:
            rows = []
            for r in conn.execute("SELECT id,name,active FROM branches ORDER BY id"):
                branch = dict(r)
                branch["employee_count"] = conn.execute(
                    "SELECT COUNT(*) FROM employees WHERE branch=?", (branch["name"],)
                ).fetchone()[0]
                rows.append(branch)
        self.send_json({
            "ok": True, "branches": rows,
            "can_manage": self.has_permission(user, "company_settings_write"),
        })

    def handle_branch_create(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "company_settings_write"):
            return
        name = str(self.parse_json().get("name", "")).strip()
        if not name:
            raise ValueError("Branch name is required")
        with db_connect() as conn:
            if conn.execute("SELECT 1 FROM branches WHERE name=?", (name,)).fetchone():
                raise ValueError("A branch with this name already exists")
            cur = conn.execute("INSERT INTO branches(name,active) VALUES (?,1)", (name,))
            log_audit(conn, user, "CREATE", "Company", cur.lastrowid, f"Added branch {name}")
        self.send_json({"ok": True, "id": cur.lastrowid}, 201)

    def handle_branch_update(self, user: dict[str, Any], branch_id: int) -> None:
        if not self.require_permission(user, "company_settings_write"):
            return
        data = self.parse_json()
        with db_connect() as conn:
            existing = conn.execute("SELECT * FROM branches WHERE id=?", (branch_id,)).fetchone()
            if not existing:
                self.send_error_json("Branch not found", 404); return
            old_name = existing["name"]
            new_name = str(data.get("name", old_name)).strip()
            active = int(bool(data.get("active", existing["active"])))
            if not new_name:
                raise ValueError("Branch name is required")
            dup = conn.execute("SELECT 1 FROM branches WHERE name=? AND id<>?", (new_name, branch_id)).fetchone()
            if dup:
                raise ValueError("A branch with this name already exists")
            if new_name != old_name:
                # Safe relabel: cascade the rename across every table that stores
                # a branch name, so existing records stay consistent. This only
                # renames labels; it does not alter any calculation.
                for table_row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ).fetchall():
                    table = table_row["name"]
                    if table == "branches":
                        continue
                    if "branch" in table_columns(conn, table):
                        conn.execute(f"UPDATE {table} SET branch=? WHERE branch=?", (new_name, old_name))
            conn.execute("UPDATE branches SET name=?,active=? WHERE id=?", (new_name, active, branch_id))
            log_audit(conn, user, "UPDATE", "Company", branch_id,
                      f"Branch {old_name} -> {new_name} | active={active}")
        self.send_json({"ok": True})

    def handle_dashboard(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "dashboard"):
            return
        q = self.query()
        branch = self.allowed_branch(user, q.get("branch", ["All"])[0])
        current_start, current_end = current_month_range()
        current_month = current_start[:7]
        with db_connect() as conn:
            params: list[Any] = []
            branch_clause = ""
            if branch != "All":
                branch_clause = " AND branch=?"
                params.append(branch)
            historical = list(conn.execute(
                f"""SELECT month_key,SUM(income) income,SUM(expenses) expenses,SUM(ready_pcs) ready_pcs
                FROM monthly_financials WHERE month_key < ?{branch_clause}
                GROUP BY month_key ORDER BY month_key""", [current_month, *params]
            ))
            current_fin = conn.execute(
                f"""SELECT COALESCE(SUM(CASE WHEN type='Income' THEN amount ELSE 0 END),0) income,
                COALESCE(SUM(CASE WHEN type='Expense' THEN amount ELSE 0 END),0) expenses
                FROM finance_entries WHERE date BETWEEN ? AND ?{branch_clause}""", [current_start, current_end, *params]
            ).fetchone()
            prod_params = [current_start, current_end, *params]
            prod_rows = list(conn.execute(
                f"""SELECT employee_id,
                SUM(CASE WHEN activity='Body' THEN quantity ELSE 0 END) body,
                SUM(CASE WHEN activity='Joint/Side' THEN quantity ELSE 0 END) joint_side,
                SUM(CASE WHEN activity NOT IN ('Body','Joint/Side') THEN quantity ELSE 0 END) other_qty
                FROM production_entries WHERE date BETWEEN ? AND ?{branch_clause}
                GROUP BY employee_id""", prod_params
            ))
            entry_count = conn.execute(
                f"SELECT COUNT(*) c FROM production_entries WHERE date BETWEEN ? AND ?{branch_clause}", prod_params
            ).fetchone()["c"]
            calculated_stage_pcs = round(sum(min(float(r["body"] or 0),float(r["joint_side"] or 0))+float(r["other_qty"] or 0) for r in prod_rows),3)
            ready_row = conn.execute(
                f"""SELECT COALESCE(SUM(total_ready_completed),0) ready_pcs,COUNT(*) ready_days
                FROM production_daily_ready WHERE date BETWEEN ? AND ?{branch_clause}""",
                [current_start, current_end, *params],
            ).fetchone()
            current_prod = {
                "ready_pcs": int(ready_row["ready_pcs"] or 0),
                "ready_days": int(ready_row["ready_days"] or 0),
                "calculated_stage_pcs": calculated_stage_pcs,
                "entries": entry_count,
                "active_employees": len(prod_rows),
            }
            order_summary = conn.execute(
                f"""SELECT
                COUNT(CASE WHEN status NOT IN ('Delivered','Cancelled') THEN 1 END) pending_orders,
                COUNT(CASE WHEN status='Ready' THEN 1 END) ready_orders,
                COUNT(CASE WHEN due_date < date('now') AND status NOT IN ('Delivered','Cancelled') THEN 1 END) overdue_orders,
                COUNT(CASE WHEN status='Delivered' AND booking_date BETWEEN ? AND ? THEN 1 END) delivered_orders
                FROM customer_orders WHERE 1=1{branch_clause}""",
                [current_start, current_end, *params],
            ).fetchone()
            conn.execute("UPDATE membership_cards SET status='Expired',updated_at=? WHERE expiry_date < date('now') AND status='Active'", (now_iso(),))
            membership_summary = conn.execute(
                f"""SELECT
                COUNT(CASE WHEN status='Active' AND expiry_date >= date('now') THEN 1 END) active_cards,
                COUNT(CASE WHEN status='Active' AND expiry_date BETWEEN date('now') AND date('now','+30 day') THEN 1 END) expiring_cards,
                COALESCE(SUM(CASE WHEN status='Active' THEN current_balance ELSE 0 END),0) wallet_outstanding,
                COALESCE(SUM(CASE WHEN issue_date BETWEEN ? AND ? THEN sale_price ELSE 0 END),0) month_card_sales
                FROM membership_cards WHERE 1=1{branch_clause}""",
                [current_start, current_end, *params],
            ).fetchone()
            branch_rows = list(conn.execute(
                """SELECT b.name branch,
                COALESCE(SUM(CASE WHEN f.type='Income' THEN f.amount ELSE 0 END),0) income,
                COALESCE(SUM(CASE WHEN f.type='Expense' THEN f.amount ELSE 0 END),0) expenses
                FROM branches b LEFT JOIN finance_entries f ON b.name=f.branch AND f.date BETWEEN ? AND ?
                WHERE b.active=1 GROUP BY b.name ORDER BY b.id""",
                [current_start, current_end],
            ))
        monthly = [
            {"month_key": r["month_key"], "month": month_name(r["month_key"]), "income": r["income"], "expenses": r["expenses"], "ready_pcs": r["ready_pcs"]}
            for r in historical
        ]
        monthly.append({"month_key":current_month,"month":month_name(current_month)+" MTD","income":current_fin["income"],"expenses":current_fin["expenses"],"ready_pcs":current_prod["ready_pcs"]})
        can_see_finance = self.has_permission(user, "finance_read")
        payload = {
            "ok": True,
            "branch": branch,
            "can_see_finance": can_see_finance,
            "current": {
                "income": current_fin["income"] if can_see_finance else None,
                "expenses": current_fin["expenses"] if can_see_finance else None,
                "profit": current_fin["income"] - current_fin["expenses"] if can_see_finance else None,
                "ready_pcs": current_prod["ready_pcs"],
                "ready_completed_days": current_prod["ready_days"],
                "calculated_stage_pcs": current_prod["calculated_stage_pcs"],
                "production_entries": current_prod["entries"],
                "active_employees": current_prod["active_employees"],
                "pending_orders": order_summary["pending_orders"],
                "ready_orders": order_summary["ready_orders"],
                "overdue_orders": order_summary["overdue_orders"],
                "delivered_orders": order_summary["delivered_orders"],
                "active_membership_cards": membership_summary["active_cards"],
                "expiring_membership_cards": membership_summary["expiring_cards"],
                "membership_wallet_outstanding": membership_summary["wallet_outstanding"] if can_see_finance else None,
                "membership_sales": membership_summary["month_card_sales"] if can_see_finance else None,
            },
            "monthly": monthly if can_see_finance else [{"month_key":m["month_key"],"month":m["month"],"ready_pcs":m["ready_pcs"]} for m in monthly],
            "branches": [dict(r) for r in branch_rows] if can_see_finance else [],
        }
        self.send_json(payload)

    def employee_skills(self, conn: sqlite3.Connection, employee_id: int) -> list[str]:
        return [r["activity"] for r in conn.execute(
            "SELECT activity FROM employee_skills WHERE employee_id=? ORDER BY activity",
            (employee_id,),
        )]

    def handle_employees(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "employees"):
            return
        q = self.query()
        branch = self.allowed_branch(user, q.get("branch", ["All"])[0])
        include_inactive = (
            q.get("include_inactive", ["0"])[0] == "1"
            and self.has_permission(user, "employee_write")
        )
        current_start, current_end = current_month_range()
        with db_connect() as conn:
            sql = "SELECT * FROM employees WHERE 1=1"
            params: list[Any] = []
            if not include_inactive:
                sql += " AND active=1"
            if branch != "All":
                sql += " AND branch=?"; params.append(branch)
            sql += " ORDER BY active DESC,branch,name"
            rows = [dict(r) for r in conn.execute(sql, params)]
            for emp in rows:
                emp["categories"] = self.employee_skills(conn, emp["id"])
                totals = conn.execute(
                    """SELECT COALESCE(SUM(quantity),0) quantity,COALESCE(SUM(ot_hours),0) ot_hours,
                    COALESCE(SUM(CASE WHEN activity='Body' THEN quantity ELSE 0 END),0) body,
                    COALESCE(SUM(CASE WHEN activity='Joint/Side' THEN quantity ELSE 0 END),0) joint_side,
                    COALESCE(SUM(CASE WHEN activity NOT IN ('Body','Joint/Side') THEN quantity ELSE 0 END),0) other_qty
                    FROM production_entries WHERE employee_id=? AND date BETWEEN ? AND ?""",
                    (emp["id"], current_start, current_end),
                ).fetchone()
                emp.update(dict(totals))
                emp["ready_pcs"] = round(min(float(totals["body"] or 0),float(totals["joint_side"] or 0))+float(totals["other_qty"] or 0),3)
                emp["full_body_produced"] = round(min(float(totals["body"] or 0),float(totals["joint_side"] or 0)),3)
        self.send_json({
            "ok": True, "employees": rows, "branch": branch,
            "activities": list(PRODUCTION_ACTIVITIES),
            "can_write": self.has_permission(user, "employee_write"),
        })

    def validate_employee_data(
        self, data: dict[str, Any], existing: sqlite3.Row | None = None
    ) -> tuple[str, str, str, float, float, int, list[str]]:
        def val(key: str, default: Any = "") -> Any:
            return data.get(key, existing[key] if existing else default)

        name = str(val("name")).strip()
        branch = str(val("branch")).strip()
        role = str(val("role")).strip()
        daily_target = float(val("daily_target", 0) or 0)
        monthly_target = float(val("monthly_target", 0) or 0)
        active = int(bool(data.get("active", existing["active"] if existing else True)))
        raw_categories = data.get("categories")
        if raw_categories is None and existing is not None:
            categories: list[str] = []
        elif isinstance(raw_categories, list):
            categories = list(dict.fromkeys(str(x).strip() for x in raw_categories if str(x).strip()))
        else:
            raise ValueError("Work categories must be provided as a list")
        if not name or not branch or not role:
            raise ValueError("Employee name, branch and designation are required")
        if daily_target < 0 or monthly_target < 0:
            raise ValueError("Targets cannot be negative")
        invalid = [x for x in categories if x not in PRODUCTION_ACTIVITIES]
        if invalid:
            raise ValueError("Invalid work category selected")
        return name, branch, role, daily_target, monthly_target, active, categories

    def handle_employee_create(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "employee_write"):
            return
        data = self.parse_json()
        values = self.validate_employee_data(data)
        base_salary = float(data.get("base_salary", 0) or 0)
        if base_salary < 0:
            raise ValueError("Basic salary cannot be negative")
        if not self.validate_branch_write(user, values[1]):
            return
        with db_connect() as conn:
            branch_exists = conn.execute(
                "SELECT 1 FROM branches WHERE name=? AND active=1", (values[1],)
            ).fetchone()
            if not branch_exists:
                raise ValueError("Selected branch is not active")
            cur = conn.execute(
                """INSERT INTO employees(name,branch,role,daily_target,monthly_target,active,base_salary)
                VALUES (?,?,?,?,?,?,?)""", (*values[:6], base_salary)
            )
            for activity in values[6]:
                conn.execute(
                    "INSERT INTO employee_skills(employee_id,activity) VALUES (?,?)",
                    (cur.lastrowid, activity),
                )
            log_audit(
                conn, user, "CREATE", "Employees", cur.lastrowid,
                f"{values[0]} | {values[1]} | {', '.join(values[6])}",
            )
        self.send_json({"ok": True, "id": cur.lastrowid}, 201)

    def handle_employee_update(self, user: dict[str, Any], employee_id: int) -> None:
        if not self.require_permission(user, "employee_write"):
            return
        data = self.parse_json()
        with db_connect() as conn:
            existing = conn.execute(
                "SELECT * FROM employees WHERE id=?", (employee_id,)
            ).fetchone()
            if not existing:
                self.send_error_json("Employee not found", 404); return
            values = self.validate_employee_data(data, existing)
            base_salary = float(data.get("base_salary", existing["base_salary"] if "base_salary" in existing.keys() else 0) or 0)
            if base_salary < 0:
                raise ValueError("Basic salary cannot be negative")
            if not self.validate_branch_write(user, values[1]):
                return
            categories = values[6] if "categories" in data else self.employee_skills(conn, employee_id)
            conn.execute(
                """UPDATE employees SET name=?,branch=?,role=?,daily_target=?,monthly_target=?,active=?,base_salary=?
                WHERE id=?""", (*values[:6], base_salary, employee_id)
            )
            conn.execute("DELETE FROM employee_skills WHERE employee_id=?", (employee_id,))
            for activity in categories:
                conn.execute(
                    "INSERT INTO employee_skills(employee_id,activity) VALUES (?,?)",
                    (employee_id, activity),
                )
            log_audit(
                conn, user, "UPDATE", "Employees", employee_id,
                f"{values[0]} | {values[1]} | active={values[5]} | {', '.join(categories)}",
            )
        self.send_json({"ok": True})

    def payroll_context(self, user: dict[str, Any]) -> tuple[str, str]:
        q = self.query()
        branch = self.allowed_branch(user, q.get("branch", ["All"])[0])
        month = q.get("month", [current_month_key()])[0]
        try:
            datetime.strptime(month, "%Y-%m")
        except ValueError as exc:
            raise ValueError("Invalid payroll month") from exc
        return branch, month


    def budget_context(self, user: dict[str, Any]) -> tuple[str, str]:
        q = self.query()
        month = q.get("month", [current_month_key()])[0]
        try:
            datetime.strptime(month, "%Y-%m")
        except ValueError as exc:
            raise ValueError("Invalid budget month") from exc
        branch = self.allowed_branch(user, q.get("branch", ["All"])[0])
        return branch, month

    def budget_month_bounds(self, month: str) -> tuple[str, str, int, int]:
        dt = datetime.strptime(month, "%Y-%m")
        days = calendar.monthrange(dt.year, dt.month)[1]
        start, end = month_date_range(month)
        today = datetime.now().date()
        if dt.year == today.year and dt.month == today.month:
            elapsed = today.day
        elif (dt.year, dt.month) < (today.year, today.month):
            elapsed = days
        else:
            elapsed = 0
        return start, end, days, elapsed

    def handle_budget_categories(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "budget_read"):
            return
        with db_connect() as conn:
            rows = [dict(r) for r in conn.execute(
                "SELECT * FROM expense_categories ORDER BY active DESC,name COLLATE NOCASE"
            )]
        self.send_json({"ok": True, "categories": rows, "can_write": self.has_permission(user, "budget_write")})

    def validate_budget_category(self, data: dict[str, Any], existing: sqlite3.Row | None = None) -> tuple[str, int, float]:
        name = str(data.get("name", existing["name"] if existing else "")).strip()
        active = 1 if bool(data.get("active", existing["active"] if existing else True)) else 0
        warning = float(data.get("default_warning_percent", existing["default_warning_percent"] if existing else 80))
        if not name:
            raise ValueError("Expense category name is required")
        if warning < 1 or warning > 100:
            raise ValueError("Warning limit must be between 1% and 100%")
        return name, active, warning

    def handle_budget_category_create(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "budget_write"):
            return
        name, active, warning = self.validate_budget_category(self.parse_json())
        with db_connect() as conn:
            cur = conn.execute(
                "INSERT INTO expense_categories(name,active,default_warning_percent,created_by,created_at,updated_at) VALUES (?,?,?,?,?,?)",
                (name, active, warning, user["full_name"], now_iso(), now_iso()),
            )
            log_audit(conn, user, "CREATE", "Budget Category", cur.lastrowid, f"Added expense category {name}")
        self.send_json({"ok": True, "id": cur.lastrowid}, 201)

    def handle_budget_category_update(self, user: dict[str, Any], category_id: int) -> None:
        if not self.require_permission(user, "budget_write"):
            return
        data = self.parse_json()
        with db_connect() as conn:
            existing = conn.execute("SELECT * FROM expense_categories WHERE id=?", (category_id,)).fetchone()
            if not existing:
                self.send_error_json("Expense category not found", 404)
                return
            name, active, warning = self.validate_budget_category(data, existing)
            old_name = existing["name"]
            conn.execute(
                "UPDATE expense_categories SET name=?,active=?,default_warning_percent=?,updated_at=? WHERE id=?",
                (name, active, warning, now_iso(), category_id),
            )
            if old_name.lower() != name.lower():
                conn.execute("UPDATE finance_entries SET category=? WHERE type='Expense' AND lower(category)=lower(?)", (name, old_name))
            log_audit(conn, user, "UPDATE", "Budget Category", category_id, f"{old_name} → {name}; active={active}")
        self.send_json({"ok": True})

    def get_or_create_budget_plan(self, conn: sqlite3.Connection, month: str, branch: str, user: dict[str, Any]) -> sqlite3.Row:
        row = conn.execute("SELECT * FROM budget_plans WHERE month_key=? AND branch=?", (month, branch)).fetchone()
        if row:
            return row
        cur = conn.execute(
            "INSERT INTO budget_plans(month_key,branch,status,locked,notes,created_by,created_at,updated_at) VALUES (?,?,'Draft',0,'',?,?,?)",
            (month, branch, user["full_name"], now_iso(), now_iso()),
        )
        return conn.execute("SELECT * FROM budget_plans WHERE id=?", (cur.lastrowid,)).fetchone()

    def handle_budget_overview(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "budget_read"):
            return
        branch, month = self.budget_context(user)
        start, end, days_in_month, elapsed_days = self.budget_month_bounds(month)
        with db_connect() as conn:
            category_rows = [dict(r) for r in conn.execute("SELECT * FROM expense_categories ORDER BY active DESC,name COLLATE NOCASE")]
            branches = [r["name"] for r in conn.execute("SELECT name FROM branches WHERE active=1 ORDER BY id")]
            if user["branch"] != "All":
                branches = [user["branch"]]
            selected_branches = branches if branch == "All" else [branch]
            placeholders = ",".join("?" for _ in selected_branches)

            plan_rows = [dict(r) for r in conn.execute(
                f"SELECT * FROM budget_plans WHERE month_key=? AND branch IN ({placeholders}) ORDER BY branch",
                [month, *selected_branches],
            )]
            plan_ids = [r["id"] for r in plan_rows]
            item_rows: list[dict[str, Any]] = []
            target_rows: list[dict[str, Any]] = []
            revision_rows: list[dict[str, Any]] = []
            if plan_ids:
                ph = ",".join("?" for _ in plan_ids)
                item_rows = [dict(r) for r in conn.execute(
                    f"""SELECT bi.*,bp.branch,ec.name category_name,ec.active category_active
                    FROM budget_items bi JOIN budget_plans bp ON bp.id=bi.plan_id
                    JOIN expense_categories ec ON ec.id=bi.category_id
                    WHERE bi.plan_id IN ({ph})""", plan_ids)]
                target_rows = [dict(r) for r in conn.execute(
                    f"""SELECT it.*,bp.branch FROM income_targets it JOIN budget_plans bp ON bp.id=it.plan_id
                    WHERE it.plan_id IN ({ph})""", plan_ids)]
                revision_rows = [dict(r) for r in conn.execute(
                    f"""SELECT br.*,ec.name category_name,bp.branch,bp.month_key
                    FROM budget_revisions br JOIN budget_items bi ON bi.id=br.budget_item_id
                    JOIN expense_categories ec ON ec.id=bi.category_id
                    JOIN budget_plans bp ON bp.id=bi.plan_id
                    WHERE bi.plan_id IN ({ph}) ORDER BY br.id DESC LIMIT 100""", plan_ids)]

            actual_expenses = [dict(r) for r in conn.execute(
                f"""SELECT branch,category,SUM(amount) actual FROM finance_entries
                WHERE type='Expense' AND date BETWEEN ? AND ? AND branch IN ({placeholders})
                GROUP BY branch,category""", [start, end, *selected_branches])]
            actual_income = [dict(r) for r in conn.execute(
                f"""SELECT branch,category,SUM(amount) actual FROM finance_entries
                WHERE type='Income' AND date BETWEEN ? AND ? AND branch IN ({placeholders})
                GROUP BY branch,category""", [start, end, *selected_branches])]

        budget_map: dict[int, dict[str, Any]] = {}
        for item in item_rows:
            entry = budget_map.setdefault(item["category_id"], {"budget": 0.0, "warning_sum": 0.0, "warning_count": 0, "notes": []})
            entry["budget"] += float(item["budget_amount"] or 0)
            entry["warning_sum"] += float(item["warning_percent"] or 80)
            entry["warning_count"] += 1
            if item["notes"]:
                entry["notes"].append(item["notes"])
        actual_map: dict[str, float] = {}
        for row in actual_expenses:
            key = row["category"].strip().lower()
            actual_map[key] = actual_map.get(key, 0.0) + float(row["actual"] or 0)

        category_lookup = {r["name"].strip().lower(): r for r in category_rows}
        # Include historical categories that are not yet in the master list.
        for row in actual_expenses:
            key = row["category"].strip().lower()
            if key not in category_lookup:
                category_rows.append({"id": None, "name": row["category"], "active": 0, "default_warning_percent": 80})

        rows = []
        for category in category_rows:
            item = budget_map.get(category.get("id"), {})
            budget_amount = float(item.get("budget", 0))
            actual = float(actual_map.get(category["name"].strip().lower(), 0))
            if not category.get("active") and budget_amount == 0 and actual == 0:
                continue
            warning = (item.get("warning_sum", 0) / item.get("warning_count", 1)) if item.get("warning_count") else float(category.get("default_warning_percent", 80))
            used = (actual / budget_amount * 100) if budget_amount > 0 else (100 if actual > 0 else 0)
            if budget_amount <= 0 and actual > 0:
                status = "No Budget"
            elif used > 100:
                status = "Over Budget"
            elif used >= warning:
                status = "Warning"
            else:
                status = "Within Budget"
            rows.append({
                "category_id": category.get("id"), "category": category["name"], "active": category.get("active", 0),
                "budget": round(budget_amount, 3), "actual": round(actual, 3),
                "remaining": round(budget_amount - actual, 3), "used_percent": round(used, 1),
                "warning_percent": round(warning, 1), "status": status,
                "notes": " | ".join(dict.fromkeys(item.get("notes", []))),
            })
        rows.sort(key=lambda x: (x["status"] not in ("Over Budget", "No Budget", "Warning"), x["category"].lower()))

        target = {"shop_sales_target": 0.0, "membership_target": 0.0, "other_income_target": 0.0, "min_profit_margin": 20.0, "notes": ""}
        if target_rows:
            for key in ("shop_sales_target", "membership_target", "other_income_target"):
                target[key] = round(sum(float(r[key] or 0) for r in target_rows), 3)
            target["min_profit_margin"] = round(sum(float(r["min_profit_margin"] or 20) for r in target_rows) / len(target_rows), 2)
            target["notes"] = " | ".join(r["notes"] for r in target_rows if r["notes"])
        actual_shop = sum(float(r["actual"] or 0) for r in actual_income if r["category"].strip().lower() == "shop sales")
        actual_membership = sum(float(r["actual"] or 0) for r in actual_income if r["category"].strip().lower() == "membership cards")
        actual_total_income = sum(float(r["actual"] or 0) for r in actual_income)
        actual_other = actual_total_income - actual_shop - actual_membership
        total_target = target["shop_sales_target"] + target["membership_target"] + target["other_income_target"]
        total_budget = sum(r["budget"] for r in rows)
        total_actual_expense = sum(r["actual"] for r in rows)
        actual_profit = actual_total_income - total_actual_expense
        actual_margin = (actual_profit / actual_total_income * 100) if actual_total_income else 0
        projected_income = actual_total_income / elapsed_days * days_in_month if elapsed_days else 0
        projected_expense = total_actual_expense / elapsed_days * days_in_month if elapsed_days else 0
        projected_profit = projected_income - projected_expense
        projected_margin = projected_profit / projected_income * 100 if projected_income else 0
        remaining_days = max(0, days_in_month - elapsed_days)
        required_daily_income = max(0, total_target - actual_total_income) / remaining_days if remaining_days else 0

        branch_summary = []
        for b in selected_branches:
            bplans = [p for p in plan_rows if p["branch"] == b]
            bids = {p["id"] for p in bplans}
            bbudget = sum(float(i["budget_amount"] or 0) for i in item_rows if i["plan_id"] in bids)
            bexp = sum(float(r["actual"] or 0) for r in actual_expenses if r["branch"] == b)
            binc = sum(float(r["actual"] or 0) for r in actual_income if r["branch"] == b)
            btgt = sum(float(r["shop_sales_target"] or 0) + float(r["membership_target"] or 0) + float(r["other_income_target"] or 0) for r in target_rows if r["plan_id"] in bids)
            branch_summary.append({"branch": b, "income_target": round(btgt,3), "actual_income": round(binc,3), "expense_budget": round(bbudget,3), "actual_expense": round(bexp,3), "profit": round(binc-bexp,3)})

        plan_status = "Not Created"
        locked = False
        notes = ""
        if branch != "All" and plan_rows:
            plan_status = plan_rows[0]["status"]
            locked = bool(plan_rows[0]["locked"])
            notes = plan_rows[0]["notes"]
        elif branch == "All" and plan_rows:
            states = {p["status"] for p in plan_rows}
            plan_status = states.pop() if len(states) == 1 else "Mixed"
            locked = bool(plan_rows) and all(bool(p["locked"]) for p in plan_rows)

        self.send_json({
            "ok": True, "month": month, "branch": branch, "rows": rows, "categories": category_rows,
            "target": target, "actual_income": {"shop_sales": round(actual_shop,3), "membership": round(actual_membership,3), "other": round(actual_other,3), "total": round(actual_total_income,3)},
            "summary": {"total_budget": round(total_budget,3), "actual_expense": round(total_actual_expense,3), "remaining_budget": round(total_budget-total_actual_expense,3),
                        "over_budget_categories": sum(1 for r in rows if r["status"] in ("Over Budget","No Budget")),
                        "income_target": round(total_target,3), "actual_income": round(actual_total_income,3), "income_achievement": round(actual_total_income/total_target*100,1) if total_target else 0,
                        "actual_profit": round(actual_profit,3), "actual_margin": round(actual_margin,1), "projected_income": round(projected_income,3),
                        "projected_expense": round(projected_expense,3), "projected_profit": round(projected_profit,3), "projected_margin": round(projected_margin,1),
                        "required_daily_income": round(required_daily_income,3), "elapsed_days": elapsed_days, "days_in_month": days_in_month},
            "branch_summary": branch_summary, "revisions": revision_rows, "status": plan_status, "locked": locked, "plan_notes": notes,
            "statuses": list(BUDGET_STATUSES), "can_write": self.has_permission(user,"budget_write"), "can_approve": self.has_permission(user,"budget_approve")
        })

    def handle_budget_plan_save(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "budget_write"):
            return
        data = self.parse_json()
        month = str(data.get("month", ""))
        try:
            datetime.strptime(month, "%Y-%m")
        except ValueError as exc:
            raise ValueError("Invalid budget month") from exc
        branch = str(data.get("branch", ""))
        if branch == "All" or not branch:
            raise ValueError("Select one branch before saving a budget")
        if not self.validate_branch_write(user, branch):
            return
        items = data.get("items") or []
        targets = data.get("targets") or {}
        revision_reason = str(data.get("revision_reason", "")).strip()
        with db_connect() as conn:
            plan = self.get_or_create_budget_plan(conn, month, branch, user)
            if plan["locked"]:
                raise ValueError("This budget is locked. Unlock it before making changes")
            conn.execute("UPDATE budget_plans SET notes=?,updated_at=? WHERE id=?", (str(data.get("notes", "")), now_iso(), plan["id"]))
            for raw in items:
                category_id = int(raw.get("category_id") or 0)
                if not category_id:
                    continue
                amount = float(raw.get("budget_amount") or 0)
                warning = float(raw.get("warning_percent") or 80)
                notes = str(raw.get("notes") or "")
                if amount < 0:
                    raise ValueError("Budget amount cannot be negative")
                if warning < 1 or warning > 100:
                    raise ValueError("Warning limit must be between 1% and 100%")
                existing = conn.execute("SELECT * FROM budget_items WHERE plan_id=? AND category_id=?", (plan["id"], category_id)).fetchone()
                if existing:
                    changed = abs(float(existing["budget_amount"]) - amount) > 0.0001 or abs(float(existing["warning_percent"]) - warning) > 0.0001
                    conn.execute("UPDATE budget_items SET budget_amount=?,warning_percent=?,notes=?,updated_by=?,updated_at=? WHERE id=?",
                                 (amount,warning,notes,user["full_name"],now_iso(),existing["id"]))
                    if changed:
                        conn.execute("INSERT INTO budget_revisions(budget_item_id,old_amount,new_amount,old_warning_percent,new_warning_percent,reason,changed_by,changed_at) VALUES (?,?,?,?,?,?,?,?)",
                                     (existing["id"],existing["budget_amount"],amount,existing["warning_percent"],warning,revision_reason,user["full_name"],now_iso()))
                else:
                    cur = conn.execute("INSERT INTO budget_items(plan_id,category_id,budget_amount,warning_percent,notes,updated_by,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                                       (plan["id"],category_id,amount,warning,notes,user["full_name"],now_iso(),now_iso()))
                    if amount or notes:
                        conn.execute("INSERT INTO budget_revisions(budget_item_id,old_amount,new_amount,old_warning_percent,new_warning_percent,reason,changed_by,changed_at) VALUES (?,0,?,80,?,?,?,?)",
                                     (cur.lastrowid,amount,warning,revision_reason or "Initial budget",user["full_name"],now_iso()))
            shop = float(targets.get("shop_sales_target") or 0)
            membership = float(targets.get("membership_target") or 0)
            other = float(targets.get("other_income_target") or 0)
            margin = float(targets.get("min_profit_margin") or 20)
            if min(shop,membership,other) < 0 or margin < 0 or margin > 100:
                raise ValueError("Income targets and margin must be valid positive values")
            conn.execute("""INSERT INTO income_targets(plan_id,shop_sales_target,membership_target,other_income_target,min_profit_margin,notes,updated_by,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(plan_id) DO UPDATE SET shop_sales_target=excluded.shop_sales_target,membership_target=excluded.membership_target,
                other_income_target=excluded.other_income_target,min_profit_margin=excluded.min_profit_margin,notes=excluded.notes,updated_by=excluded.updated_by,updated_at=excluded.updated_at""",
                (plan["id"],shop,membership,other,margin,str(targets.get("notes") or ""),user["full_name"],now_iso(),now_iso()))
            log_audit(conn,user,"UPDATE","Budget",plan["id"],f"Saved {month} budget for {branch}")
        self.send_json({"ok": True})

    def handle_budget_status(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "budget_approve"):
            return
        data = self.parse_json(); month = str(data.get("month", "")); branch = str(data.get("branch", "")); status = str(data.get("status", ""))
        try:
            datetime.strptime(month, "%Y-%m")
        except ValueError as exc:
            raise ValueError("Invalid budget month") from exc
        if status not in BUDGET_STATUSES:
            raise ValueError("Invalid budget status")
        if branch == "All" or not branch:
            raise ValueError("Select one branch before changing budget status")
        if not self.validate_branch_write(user, branch): return
        with db_connect() as conn:
            plan = self.get_or_create_budget_plan(conn, month, branch, user)
            locked = 1 if status in ("Locked", "Closed") else 0
            approved_by = user["full_name"] if status in ("Approved","Locked","Closed") else None
            conn.execute("UPDATE budget_plans SET status=?,locked=?,approved_by=?,updated_at=? WHERE id=?", (status,locked,approved_by,now_iso(),plan["id"]))
            log_audit(conn,user,"STATUS","Budget",plan["id"],f"{month} {branch} budget changed to {status}")
        self.send_json({"ok": True, "status": status, "locked": bool(locked), "approved_by": approved_by})

    def handle_budget_copy(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "budget_write"):
            return
        data = self.parse_json(); source = str(data.get("source_month", "")); target = str(data.get("target_month", "")); branch = str(data.get("branch", ""))
        try:
            datetime.strptime(source,"%Y-%m"); datetime.strptime(target,"%Y-%m")
        except ValueError as exc:
            raise ValueError("Invalid source or target month") from exc
        branches = [branch]
        if branch == "All":
            if user["branch"] != "All": branches = [user["branch"]]
            else:
                with db_connect() as conn: branches = [r["name"] for r in conn.execute("SELECT name FROM branches WHERE active=1")]
        with db_connect() as conn:
            copied = 0
            for b in branches:
                if not self.validate_branch_write(user,b): return
                src = conn.execute("SELECT * FROM budget_plans WHERE month_key=? AND branch=?",(source,b)).fetchone()
                if not src: continue
                tgt = self.get_or_create_budget_plan(conn,target,b,user)
                if tgt["locked"]: raise ValueError(f"{b} target budget is locked")
                conn.execute("UPDATE budget_plans SET notes=?,status='Draft',locked=0,approved_by=NULL,updated_at=? WHERE id=?",(src["notes"],now_iso(),tgt["id"]))
                for item in conn.execute("SELECT * FROM budget_items WHERE plan_id=?",(src["id"],)):
                    conn.execute("""INSERT INTO budget_items(plan_id,category_id,budget_amount,warning_percent,notes,updated_by,created_at,updated_at)
                        VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(plan_id,category_id) DO UPDATE SET budget_amount=excluded.budget_amount,warning_percent=excluded.warning_percent,
                        notes=excluded.notes,updated_by=excluded.updated_by,updated_at=excluded.updated_at""",
                        (tgt["id"],item["category_id"],item["budget_amount"],item["warning_percent"],item["notes"],user["full_name"],now_iso(),now_iso()))
                src_target=conn.execute("SELECT * FROM income_targets WHERE plan_id=?",(src["id"],)).fetchone()
                if src_target:
                    conn.execute("""INSERT INTO income_targets(plan_id,shop_sales_target,membership_target,other_income_target,min_profit_margin,notes,updated_by,created_at,updated_at)
                        VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(plan_id) DO UPDATE SET shop_sales_target=excluded.shop_sales_target,membership_target=excluded.membership_target,
                        other_income_target=excluded.other_income_target,min_profit_margin=excluded.min_profit_margin,notes=excluded.notes,updated_by=excluded.updated_by,updated_at=excluded.updated_at""",
                        (tgt["id"],src_target["shop_sales_target"],src_target["membership_target"],src_target["other_income_target"],src_target["min_profit_margin"],src_target["notes"],user["full_name"],now_iso(),now_iso()))
                copied += 1
                log_audit(conn,user,"COPY","Budget",tgt["id"],f"Copied {source} to {target} for {b}")
        self.send_json({"ok": True, "copied": copied})

    def handle_export_budget(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "budget_read"):
            return
        branch,month=self.budget_context(user)
        start,end,_,_=self.budget_month_bounds(month)
        params: list[Any]=[month]
        branch_filter=""
        if branch!="All": branch_filter=" AND bp.branch=?";params.append(branch)
        with db_connect() as conn:
            rows=list(conn.execute(f"""SELECT bp.month_key,bp.branch,bp.status,ec.name category,bi.budget_amount,bi.warning_percent,bi.notes,
                COALESCE((SELECT SUM(fe.amount) FROM finance_entries fe WHERE fe.type='Expense' AND fe.branch=bp.branch AND lower(fe.category)=lower(ec.name) AND fe.date BETWEEN ? AND ?),0) actual
                FROM budget_plans bp JOIN budget_items bi ON bi.plan_id=bp.id JOIN expense_categories ec ON ec.id=bi.category_id
                WHERE bp.month_key=? {branch_filter} ORDER BY bp.branch,ec.name""",[start,end,*params]))
        currency = self.report_currency()
        headers=["Month","Branch","Status","Category",f"Budget ({currency})",f"Actual ({currency})",f"Remaining ({currency})","Used %","Warning %","Notes"]
        out=[]
        for r in rows:
            used=float(r["actual"] or 0)/float(r["budget_amount"] or 1)*100 if r["budget_amount"] else (100 if r["actual"] else 0)
            out.append([r["month_key"],r["branch"],r["status"],r["category"],r["budget_amount"],r["actual"],float(r["budget_amount"])-float(r["actual"]),round(used,1),r["warning_percent"],r["notes"]])
        self.send_csv(self.export_filename(f"budget_vs_actual_{month}", "csv"),headers,out)

    def handle_payroll_list(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "payroll_read"):
            return
        branch, month = self.payroll_context(user)
        start, end = month_date_range(month)
        params: list[Any] = [month, start, end, start, end, start, end]
        branch_sql = ""
        if branch != "All":
            branch_sql = " AND e.branch=?"
            params.append(branch)
        sql = f"""
            SELECT e.id employee_id,e.name,e.role,e.branch,e.active,e.base_salary,
                   pr.id payroll_id,pr.basic_salary payroll_basic_salary,pr.commission,
                   pr.bonus,pr.overtime_hours,pr.overtime_amount,pr.other_allowance,
                   pr.advance_deduction,pr.other_deductions,pr.net_salary,pr.status,
                   pr.notes,pr.paid_at,
                   COALESCE(att.present_days,0) present_days,
                   COALESCE(att.absent_days,0) absent_days,
                   COALESCE(att.leave_days,0) leave_days,
                   COALESCE(att.half_days,0) half_days,
                   COALESCE(att.weekly_off_days,0) weekly_off_days,
                   COALESCE(prod.prod_ot_hours,0) production_ot_hours,
                   COALESCE(cards.card_commission,0) card_commission_auto
            FROM employees e
            LEFT JOIN payroll_records pr ON pr.employee_id=e.id AND pr.month_key=?
            LEFT JOIN (
                SELECT employee_id,
                  SUM(CASE WHEN status='Present' THEN 1 ELSE 0 END) present_days,
                  SUM(CASE WHEN status='Absent' THEN 1 ELSE 0 END) absent_days,
                  SUM(CASE WHEN status='Leave' THEN 1 ELSE 0 END) leave_days,
                  SUM(CASE WHEN status='Half Day' THEN 1 ELSE 0 END) half_days,
                  SUM(CASE WHEN status IN ('Weekly Off','Holiday') THEN 1 ELSE 0 END) weekly_off_days
                FROM attendance_records WHERE date BETWEEN ? AND ? GROUP BY employee_id
            ) att ON att.employee_id=e.id
            LEFT JOIN (
                SELECT employee_id,SUM(ot_hours) prod_ot_hours FROM production_entries
                WHERE date BETWEEN ? AND ? GROUP BY employee_id
            ) prod ON prod.employee_id=e.id
            LEFT JOIN (
                SELECT sales_agent_id employee_id,SUM(commission_amount) card_commission
                FROM membership_cards WHERE issue_date BETWEEN ? AND ? AND sales_agent_id IS NOT NULL
                GROUP BY sales_agent_id
            ) cards ON cards.employee_id=e.id
            WHERE (e.active=1 OR pr.id IS NOT NULL){branch_sql}
            ORDER BY e.branch,e.name
        """
        with db_connect() as conn:
            rows = [dict(r) for r in conn.execute(sql, params)]
        total_basic = total_commission = total_bonus = total_net = 0.0
        paid = pending = 0
        for row in rows:
            row["basic_salary"] = row["payroll_basic_salary"] if row["payroll_id"] else row["base_salary"]
            if not row["payroll_id"]:
                row["commission"] = 0
                row["bonus"] = 0
                row["overtime_hours"] = row["production_ot_hours"]
                row["overtime_amount"] = 0
                row["other_allowance"] = 0
                row["advance_deduction"] = 0
                row["other_deductions"] = 0
                row["status"] = "Draft"
                row["notes"] = ""
                row["net_salary"] = row["basic_salary"] + row["commission"]
            total_basic += float(row["basic_salary"] or 0)
            total_commission += float(row["commission"] or 0)
            total_bonus += float(row["bonus"] or 0)
            total_net += float(row["net_salary"] or 0)
            if row["status"] == "Paid": paid += 1
            else: pending += 1
        self.send_json({"ok": True, "month": month, "branch": branch, "rows": rows,
            "summary": {"employees": len(rows), "total_basic": total_basic,
                "total_commission": total_commission, "total_bonus": total_bonus,
                "total_net": total_net, "paid": paid, "pending": pending},
            "statuses": list(PAYROLL_STATUSES), "can_write": self.has_permission(user, "payroll_write")})

    def handle_payroll_save(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "payroll_write"):
            return
        data = self.parse_json()
        employee_id = int(data.get("employee_id") or 0)
        month = str(data.get("month_key", "")).strip()
        try: datetime.strptime(month, "%Y-%m")
        except ValueError as exc: raise ValueError("Invalid payroll month") from exc
        with db_connect() as conn:
            emp = conn.execute("SELECT * FROM employees WHERE id=?", (employee_id,)).fetchone()
            if not emp: raise ValueError("Employee not found")
            if not self.validate_branch_write(user, emp["branch"]): return
            basic = float(data.get("basic_salary", emp["base_salary"]) or 0)
            commission = float(data.get("commission", 0) or 0)
            bonus = float(data.get("bonus", 0) or 0)
            ot_hours = float(data.get("overtime_hours", 0) or 0)
            ot_amount = float(data.get("overtime_amount", 0) or 0)
            allowance = float(data.get("other_allowance", 0) or 0)
            advance = float(data.get("advance_deduction", 0) or 0)
            deductions = float(data.get("other_deductions", 0) or 0)
            values = [basic,commission,bonus,ot_hours,ot_amount,allowance,advance,deductions]
            if any(v < 0 for v in values): raise ValueError("Payroll amounts cannot be negative")
            status = str(data.get("status", "Draft"))
            if status not in PAYROLL_STATUSES: raise ValueError("Invalid payroll status")
            notes = str(data.get("notes", "")).strip()
            net = round(basic + commission + bonus + ot_amount + allowance - advance - deductions, 3)
            paid_at = now_iso() if status == "Paid" else None
            conn.execute("UPDATE employees SET base_salary=? WHERE id=?", (basic, employee_id))
            conn.execute("""INSERT INTO payroll_records(month_key,employee_id,branch,basic_salary,commission,bonus,overtime_hours,overtime_amount,other_allowance,advance_deduction,other_deductions,net_salary,status,notes,entered_by,created_at,updated_at,paid_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(month_key,employee_id) DO UPDATE SET branch=excluded.branch,basic_salary=excluded.basic_salary,
                commission=excluded.commission,bonus=excluded.bonus,overtime_hours=excluded.overtime_hours,
                overtime_amount=excluded.overtime_amount,other_allowance=excluded.other_allowance,
                advance_deduction=excluded.advance_deduction,other_deductions=excluded.other_deductions,
                net_salary=excluded.net_salary,status=excluded.status,notes=excluded.notes,
                entered_by=excluded.entered_by,updated_at=excluded.updated_at,paid_at=excluded.paid_at""",
                (month,employee_id,emp["branch"],basic,commission,bonus,ot_hours,ot_amount,allowance,advance,deductions,net,status,notes,user["full_name"],now_iso(),now_iso(),paid_at))
            log_audit(conn,user,"UPSERT","Payroll",employee_id,f"{month} | {emp['name']} | Net OMR {net:.3f} | {status}")
        self.send_json({"ok": True, "net_salary": net})

    def handle_attendance_list(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "attendance_read"):
            return
        q=self.query(); branch=self.allowed_branch(user,q.get("branch",["All"])[0]); month=q.get("month",[current_month_key()])[0]
        try: datetime.strptime(month,"%Y-%m")
        except ValueError as exc: raise ValueError("Invalid attendance month") from exc
        start,end=month_date_range(month)
        clauses=["a.date BETWEEN ? AND ?"]; params=[start,end]
        if branch!="All": clauses.append("a.branch=?"); params.append(branch)
        employee=q.get("employee_id",[""])[0]
        if employee: clauses.append("a.employee_id=?"); params.append(int(employee))
        with db_connect() as conn:
            rows=[dict(r) for r in conn.execute(f"""SELECT a.*,e.name employee_name,e.role FROM attendance_records a
                JOIN employees e ON e.id=a.employee_id WHERE {' AND '.join(clauses)} ORDER BY a.date DESC,e.name""",params)]
        self.send_json({"ok":True,"rows":rows,"statuses":list(ATTENDANCE_STATUSES),"can_write":self.has_permission(user,"attendance_write")})

    def handle_attendance_save(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user,"attendance_write"): return
        data=self.parse_json(); employee_id=int(data.get("employee_id") or 0); date=str(data.get("date","")).strip(); status=str(data.get("status","")).strip(); notes=str(data.get("notes","")).strip()
        try: datetime.strptime(date,"%Y-%m-%d")
        except ValueError as exc: raise ValueError("Invalid attendance date") from exc
        if status not in ATTENDANCE_STATUSES: raise ValueError("Invalid attendance status")
        with db_connect() as conn:
            emp=conn.execute("SELECT * FROM employees WHERE id=?",(employee_id,)).fetchone()
            if not emp: raise ValueError("Employee not found")
            if not self.validate_branch_write(user,emp["branch"]): return
            conn.execute("""INSERT INTO attendance_records(date,employee_id,branch,status,notes,entered_by,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(date,employee_id) DO UPDATE SET branch=excluded.branch,status=excluded.status,
                notes=excluded.notes,entered_by=excluded.entered_by,updated_at=excluded.updated_at""",
                (date,employee_id,emp["branch"],status,notes,user["full_name"],now_iso(),now_iso()))
            row=conn.execute("SELECT id FROM attendance_records WHERE date=? AND employee_id=?",(date,employee_id)).fetchone()
            log_audit(conn,user,"UPSERT","Attendance",row["id"],f"{date} | {emp['name']} | {status}")
        self.send_json({"ok":True})

    def handle_attendance_delete(self, user: dict[str, Any], record_id: int) -> None:
        if not self.require_permission(user,"attendance_write"): return
        with db_connect() as conn:
            row=conn.execute("SELECT a.*,e.name FROM attendance_records a JOIN employees e ON e.id=a.employee_id WHERE a.id=?",(record_id,)).fetchone()
            if not row: self.send_error_json("Attendance record not found",404); return
            if not self.validate_branch_write(user,row["branch"]): return
            conn.execute("DELETE FROM attendance_records WHERE id=?",(record_id,))
            log_audit(conn,user,"DELETE","Attendance",record_id,f"{row['date']} | {row['name']} | {row['status']}")
        self.send_json({"ok":True})

    def handle_export_payroll(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user,"payroll_read"): return
        branch,month=self.payroll_context(user); params=[month]; where="pr.month_key=?"
        if branch!="All": where+=" AND pr.branch=?"; params.append(branch)
        with db_connect() as conn:
            rows=list(conn.execute(f"""SELECT pr.*,e.name,e.role FROM payroll_records pr JOIN employees e ON e.id=pr.employee_id
                WHERE {where} ORDER BY pr.branch,e.name""",params))
        currency = self.report_currency()
        headers=["Month","Branch","Employee","Designation",f"Basic Salary ({currency})",f"Commission ({currency})",f"Bonus ({currency})","OT Hours",f"OT Amount ({currency})",f"Other Allowance ({currency})",f"Advance Deduction ({currency})",f"Other Deductions ({currency})",f"Net Salary ({currency})","Status","Notes"]
        out=[[r["month_key"],r["branch"],r["name"],r["role"],r["basic_salary"],r["commission"],r["bonus"],r["overtime_hours"],r["overtime_amount"],r["other_allowance"],r["advance_deduction"],r["other_deductions"],r["net_salary"],r["status"],r["notes"]] for r in rows]
        self.send_csv(self.export_filename(f"payroll_{month}", "csv"),headers,out)

    def handle_export_attendance(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user,"attendance_read"): return
        q=self.query(); branch=self.allowed_branch(user,q.get("branch",["All"])[0]); month=q.get("month",[current_month_key()])[0]
        start,end=month_date_range(month)
        params=[start,end]; where="a.date BETWEEN ? AND ?"
        if branch!="All": where+=" AND a.branch=?"; params.append(branch)
        with db_connect() as conn:
            rows=list(conn.execute(f"""SELECT a.*,e.name,e.role FROM attendance_records a JOIN employees e ON e.id=a.employee_id
                WHERE {where} ORDER BY a.date,e.name""",params))
        headers=["Date","Branch","Employee","Designation","Status","Notes","Entered By"]
        out=[[r["date"],r["branch"],r["name"],r["role"],r["status"],r["notes"],r["entered_by"]] for r in rows]
        self.send_csv(self.export_filename(f"attendance_{month}", "csv"),headers,out)

    def order_filters(self, user: dict[str, Any]) -> tuple[str, list[Any]]:
        q = self.query()
        branch = self.allowed_branch(user, q.get("branch", ["All"])[0])
        status = q.get("status", ["All"])[0]
        default_start, default_end = current_month_range()
        start = q.get("start", [default_start])[0] or default_start
        end = q.get("end", [default_end])[0] or default_end
        search = q.get("search", [""])[0].strip()
        clauses = ["o.booking_date BETWEEN ? AND ?"]
        params: list[Any] = [start, end]
        if branch != "All":
            clauses.append("o.branch=?"); params.append(branch)
        if status != "All":
            clauses.append("o.status=?"); params.append(status)
        if search:
            clauses.append("(o.order_no LIKE ? OR o.customer_name LIKE ? OR o.phone LIKE ?)")
            term = f"%{search}%"; params.extend([term, term, term])
        return " WHERE " + " AND ".join(clauses), params

    def handle_orders_list(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "orders_read"):
            return
        where, params = self.order_filters(user)
        with db_connect() as conn:
            rows = [dict(r) for r in conn.execute(
                f"""SELECT o.*,e.name assigned_employee,
                CASE WHEN o.due_date < date('now') AND o.status NOT IN ('Delivered','Cancelled') THEN 1 ELSE 0 END overdue
                FROM customer_orders o LEFT JOIN employees e ON e.id=o.assigned_employee_id
                {where} ORDER BY o.due_date,o.id""", params
            )]
        can_see_finance = self.has_permission(user, "finance_read")
        if not can_see_finance:
            for row in rows:
                row["total_amount"] = None
                row["advance_amount"] = None
                row["balance_amount"] = None
        else:
            for row in rows:
                row["balance_amount"] = float(row["total_amount"]) - float(row["advance_amount"])
        summary = {
            "total": len(rows),
            "pending": sum(1 for r in rows if r["status"] not in ("Delivered", "Cancelled")),
            "ready": sum(1 for r in rows if r["status"] == "Ready"),
            "overdue": sum(1 for r in rows if r["overdue"]),
            "delivered": sum(1 for r in rows if r["status"] == "Delivered"),
        }
        self.send_json({
            "ok": True, "orders": rows, "summary": summary,
            "statuses": list(ORDER_STATUSES), "item_types": list(ORDER_ITEM_TYPES),
            "can_write": self.has_permission(user, "orders_write"),
            "can_delete": user.get("role") in ("Owner", "Administrator"),
            "can_see_finance": can_see_finance,
        })

    def validate_order_data(self, data: dict[str, Any], existing: sqlite3.Row | None = None) -> tuple:
        def val(key: str, default: Any = "") -> Any:
            return data.get(key, existing[key] if existing else default)
        order_no = str(val("order_no")).strip()
        booking_date = str(val("booking_date")).strip()
        due_date = str(val("due_date")).strip()
        branch = str(val("branch")).strip()
        customer_name = str(val("customer_name")).strip()
        phone = str(val("phone")).strip()
        item_type = str(val("item_type")).strip()
        quantity = int(float(val("quantity", 1) or 1))
        employee_raw = val("assigned_employee_id", None)
        assigned_employee_id = int(employee_raw) if employee_raw not in (None, "", 0, "0") else None
        status = str(val("status", "New Booking")).strip()
        total_amount = float(val("total_amount", 0) or 0)
        advance_amount = float(val("advance_amount", 0) or 0)
        notes = str(val("notes", "")).strip()
        if not all((booking_date, due_date, branch, customer_name, item_type)):
            raise ValueError("Booking date, due date, branch, customer and item are required")
        try:
            if datetime.strptime(due_date, "%Y-%m-%d") < datetime.strptime(booking_date, "%Y-%m-%d"):
                raise ValueError("Due date cannot be before booking date")
        except ValueError as exc:
            if "before" in str(exc): raise
            raise ValueError("Use valid booking and due dates") from exc
        if status not in ORDER_STATUSES:
            raise ValueError("Invalid order status")
        if item_type not in ORDER_ITEM_TYPES:
            raise ValueError("Invalid item type")
        if quantity <= 0:
            raise ValueError("Quantity must be greater than zero")
        if total_amount < 0 or advance_amount < 0:
            raise ValueError("Amounts cannot be negative")
        if advance_amount > total_amount and total_amount > 0:
            raise ValueError("Advance amount cannot exceed total amount")
        return (order_no, booking_date, due_date, branch, customer_name, phone, item_type,
                quantity, assigned_employee_id, status, total_amount, advance_amount, notes)

    def next_order_number(self, conn: sqlite3.Connection, booking_date: str) -> str:
        year = booking_date[:4] if len(booking_date) >= 4 else str(datetime.now().year)
        row = conn.execute(
            "SELECT order_no FROM customer_orders WHERE order_no LIKE ? ORDER BY id DESC LIMIT 1",
            (f"DAS-{year}-%",),
        ).fetchone()
        last = 0
        if row:
            try: last = int(str(row["order_no"]).rsplit("-", 1)[1])
            except (ValueError, IndexError): last = 0
        return f"DAS-{year}-{last + 1:04d}"

    def validate_order_employee(self, conn: sqlite3.Connection, employee_id: int | None, branch: str) -> None:
        if employee_id is None:
            return
        emp = conn.execute("SELECT branch,active FROM employees WHERE id=?", (employee_id,)).fetchone()
        if not emp or not emp["active"]:
            raise ValueError("Assigned employee was not found or is inactive")
        # Nizwa orders may be assigned to Al Khoud workshop employees.
        if branch != "Nizwa" and emp["branch"] != branch:
            raise ValueError("Assigned employee must belong to the selected branch")

    def handle_order_create(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "orders_write"):
            return
        values = list(self.validate_order_data(self.parse_json()))
        if not self.validate_branch_write(user, values[3]):
            return
        with db_connect() as conn:
            self.validate_order_employee(conn, values[8], values[3])
            if not values[0]: values[0] = self.next_order_number(conn, values[1])
            delivered_at = now_iso() if values[9] == "Delivered" else None
            cur = conn.execute(
                """INSERT INTO customer_orders(order_no,booking_date,due_date,branch,customer_name,phone,item_type,quantity,assigned_employee_id,status,total_amount,advance_amount,notes,entered_by,created_at,updated_at,delivered_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (*values, user["full_name"], now_iso(), now_iso(), delivered_at),
            )
            log_audit(conn, user, "CREATE", "Orders", cur.lastrowid,
                      f"{values[0]} | {values[4]} | {values[3]} | {values[9]}")
        self.send_json({"ok": True, "id": cur.lastrowid, "order_no": values[0]}, 201)

    def handle_order_update(self, user: dict[str, Any], order_id: int) -> None:
        if not self.require_permission(user, "orders_write"):
            return
        data = self.parse_json()
        with db_connect() as conn:
            existing = conn.execute("SELECT * FROM customer_orders WHERE id=?", (order_id,)).fetchone()
            if not existing:
                self.send_error_json("Order not found", 404); return
            values = list(self.validate_order_data(data, existing))
            if not self.validate_branch_write(user, values[3]):
                return
            self.validate_order_employee(conn, values[8], values[3])
            delivered_at = existing["delivered_at"]
            if values[9] == "Delivered" and not delivered_at: delivered_at = now_iso()
            if values[9] != "Delivered": delivered_at = None
            conn.execute(
                """UPDATE customer_orders SET order_no=?,booking_date=?,due_date=?,branch=?,customer_name=?,phone=?,item_type=?,quantity=?,assigned_employee_id=?,status=?,total_amount=?,advance_amount=?,notes=?,updated_at=?,delivered_at=? WHERE id=?""",
                (*values, now_iso(), delivered_at, order_id),
            )
            log_audit(conn, user, "UPDATE", "Orders", order_id,
                      f"{values[0]} | status={values[9]} | due={values[2]}")
        self.send_json({"ok": True})

    def handle_order_delete(self, user: dict[str, Any], order_id: int) -> None:
        if not self.require_permission(user, "orders_write"):
            return
        if user.get("role") not in ("Owner", "Administrator"):
            self.send_error_json("Only Owner or Administrator can delete an order", 403); return
        with db_connect() as conn:
            row = conn.execute("SELECT * FROM customer_orders WHERE id=?", (order_id,)).fetchone()
            if not row:
                self.send_error_json("Order not found", 404); return
            if not self.validate_branch_write(user, row["branch"]):
                return
            conn.execute("DELETE FROM customer_orders WHERE id=?", (order_id,))
            log_audit(conn, user, "DELETE", "Orders", order_id,
                      f"{row['order_no']} | {row['customer_name']} | {row['branch']}")
        self.send_json({"ok": True})

    def internal_customer_key(self) -> str:
        # Kept only for backward-compatible database storage; never shown to users.
        return f"INTERNAL-{secrets.token_hex(8).upper()}"

    def customer_filters(self, user: dict[str, Any]) -> tuple[str, list[Any]]:
        q = self.query()
        branch = self.allowed_branch(user, q.get("branch", ["All"])[0])
        search = q.get("search", [""])[0].strip()
        include_inactive = q.get("include_inactive", ["0"])[0] == "1"
        where = " WHERE 1=1"
        params: list[Any] = []
        if branch != "All":
            where += " AND c.branch=?"; params.append(branch)
        if not include_inactive:
            where += " AND c.active=1"
        if search:
            where += " AND (c.name LIKE ? OR c.phone LIKE ? OR c.email LIKE ?)"
            token = f"%{search}%"; params += [token, token, token]
        return where, params

    def handle_customers(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "membership_read"):
            return
        where, params = self.customer_filters(user)
        with db_connect() as conn:
            rows = [dict(r) for r in conn.execute(
                f"""SELECT c.id,c.name,c.phone,c.email,c.branch,c.address,c.notes,c.active,c.created_by,c.created_at,c.updated_at,
                COUNT(mc.id) card_count,
                COALESCE(SUM(CASE WHEN mc.status='Active' THEN mc.current_balance ELSE 0 END),0) active_balance
                FROM customers c LEFT JOIN membership_cards mc ON mc.customer_id=c.id
                {where} GROUP BY c.id ORDER BY c.name""", params
            )]
        self.send_json({"ok": True, "customers": rows, "can_write": self.has_permission(user, "membership_write")})

    def validate_customer_data(self, data: dict[str, Any], existing: sqlite3.Row | None = None) -> tuple:
        def val(key: str, default: Any = "") -> Any:
            return data.get(key, existing[key] if existing else default)
        name = str(val("name")).strip()
        phone = str(val("phone")).strip()
        email = str(val("email")).strip()
        branch = str(val("branch")).strip()
        address = str(val("address")).strip()
        notes = str(val("notes")).strip()
        active = int(bool(val("active", 1)))
        if not name or not branch:
            raise ValueError("Customer name and branch are required")
        return name, phone, email, branch, address, notes, active

    def handle_customer_create(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "membership_write"):
            return
        values = self.validate_customer_data(self.parse_json())
        if not self.validate_branch_write(user, values[3]):
            return
        with db_connect() as conn:
            internal_key = self.internal_customer_key()
            cur = conn.execute(
                """INSERT INTO customers(customer_code,name,phone,email,branch,address,notes,active,created_by,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (internal_key, *values, user["full_name"], now_iso(), now_iso()),
            )
            log_audit(conn, user, "CREATE", "Customers", cur.lastrowid, f"{values[0]} | {values[3]}")
        self.send_json({"ok": True, "id": cur.lastrowid}, 201)

    def handle_customer_update(self, user: dict[str, Any], customer_id: int) -> None:
        if not self.require_permission(user, "membership_write"):
            return
        with db_connect() as conn:
            existing = conn.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
            if not existing:
                self.send_error_json("Customer not found", 404); return
            values = self.validate_customer_data(self.parse_json(), existing)
            if not self.validate_branch_write(user, values[3]):
                return
            if values[3] != existing["branch"] and conn.execute("SELECT COUNT(*) FROM membership_cards WHERE customer_id=?", (customer_id,)).fetchone()[0]:
                raise ValueError("Customer branch cannot be changed after a membership card is issued")
            conn.execute(
                "UPDATE customers SET name=?,phone=?,email=?,branch=?,address=?,notes=?,active=?,updated_at=? WHERE id=?",
                (*values, now_iso(), customer_id),
            )
            log_audit(conn, user, "UPDATE", "Customers", customer_id, f"{values[0]} | active={values[6]}")
        self.send_json({"ok": True})

    def handle_membership_plans(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "membership_read"):
            return
        with db_connect() as conn:
            rows = [dict(r) for r in conn.execute("SELECT * FROM membership_plans ORDER BY sale_price DESC,name")]
        self.send_json({"ok": True, "plans": rows, "can_write": self.has_permission(user, "membership_write")})

    def validate_membership_plan(self, data: dict[str, Any], existing: sqlite3.Row | None = None) -> tuple:
        def val(key: str, default: Any = 0) -> Any:
            return data.get(key, existing[key] if existing else default)
        name = str(val("name", "")).strip()
        sale_price = float(val("sale_price", 0) or 0)
        wallet_balance = float(val("wallet_balance", 0) or 0)
        benefit_amount = float(val("benefit_amount", 0) or 0)
        validity_months = int(float(val("validity_months", 12) or 12))
        free_deliveries = int(float(val("free_deliveries", 0) or 0))
        active = int(bool(val("active", 1)))
        if not name:
            raise ValueError("Plan name is required")
        if min(sale_price, wallet_balance, benefit_amount) < 0 or validity_months <= 0 or free_deliveries < -1:
            raise ValueError("Plan values are invalid")
        return name, sale_price, wallet_balance, benefit_amount, validity_months, free_deliveries, active

    def handle_membership_plan_create(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "membership_write"):
            return
        values = self.validate_membership_plan(self.parse_json())
        with db_connect() as conn:
            cur = conn.execute(
                """INSERT INTO membership_plans(name,sale_price,wallet_balance,benefit_amount,validity_months,free_deliveries,active,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)""", (*values, now_iso(), now_iso())
            )
            log_audit(conn, user, "CREATE", "Membership Plans", cur.lastrowid, f"{values[0]} | OMR {values[1]:.3f}")
        self.send_json({"ok": True, "id": cur.lastrowid}, 201)

    def handle_membership_plan_update(self, user: dict[str, Any], plan_id: int) -> None:
        if not self.require_permission(user, "membership_write"):
            return
        with db_connect() as conn:
            existing = conn.execute("SELECT * FROM membership_plans WHERE id=?", (plan_id,)).fetchone()
            if not existing:
                self.send_error_json("Membership plan not found", 404); return
            values = self.validate_membership_plan(self.parse_json(), existing)
            conn.execute(
                """UPDATE membership_plans SET name=?,sale_price=?,wallet_balance=?,benefit_amount=?,validity_months=?,free_deliveries=?,active=?,updated_at=? WHERE id=?""",
                (*values, now_iso(), plan_id),
            )
            log_audit(conn, user, "UPDATE", "Membership Plans", plan_id, f"{values[0]} | active={values[6]}")
        self.send_json({"ok": True})

    def membership_filters(self, user: dict[str, Any]) -> tuple[str, list[Any]]:
        q = self.query()
        branch = self.allowed_branch(user, q.get("branch", ["All"])[0])
        status = q.get("status", ["All"])[0]
        search = q.get("search", [""])[0].strip()
        where = " WHERE 1=1"
        params: list[Any] = []
        if branch != "All":
            where += " AND mc.branch=?"; params.append(branch)
        if status != "All":
            where += " AND mc.status=?"; params.append(status)
        if search:
            where += " AND (mc.card_no LIKE ? OR c.name LIKE ? OR c.phone LIKE ? OR e.name LIKE ? OR mc.sales_agent_name LIKE ?)"
            token = f"%{search}%"; params += [token, token, token, token, token]
        return where, params

    def handle_membership_list(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "membership_read"):
            return
        where, params = self.membership_filters(user)
        with db_connect() as conn:
            conn.execute("UPDATE membership_cards SET status='Expired',updated_at=? WHERE expiry_date < date('now') AND status='Active'", (now_iso(),))
            rows = [dict(r) for r in conn.execute(
                f"""SELECT mc.*,c.name customer_name,c.phone,c.email,
                mp.name plan_name,mp.benefit_amount,mp.validity_months,mp.free_deliveries,
                COALESCE(e.name,NULLIF(mc.sales_agent_name,'')) sales_agent_display,
                COALESCE(e.role,CASE WHEN TRIM(COALESCE(mc.sales_agent_name,''))<>'' THEN 'Manual Sales Agent' ELSE '' END) sales_agent_role
                FROM membership_cards mc
                JOIN customers c ON c.id=mc.customer_id
                JOIN membership_plans mp ON mp.id=mc.plan_id
                LEFT JOIN employees e ON e.id=mc.sales_agent_id
                {where} ORDER BY mc.issue_date DESC,mc.id DESC""", params
            )]
            summary_row = conn.execute(
                f"""SELECT
                COUNT(*) total_cards,
                COUNT(CASE WHEN mc.status='Active' THEN 1 END) active_cards,
                COUNT(CASE WHEN mc.status='Expired' THEN 1 END) expired_cards,
                COUNT(CASE WHEN mc.status='Active' AND mc.expiry_date BETWEEN date('now') AND date('now','+30 day') THEN 1 END) expiring_cards,
                COALESCE(SUM(CASE WHEN mc.status='Active' THEN mc.current_balance ELSE 0 END),0) wallet_outstanding,
                COALESCE(SUM(mc.sale_price),0) total_sales,
                COALESCE(SUM(mc.commission_amount),0) total_commission
                FROM membership_cards mc JOIN customers c ON c.id=mc.customer_id
                LEFT JOIN employees e ON e.id=mc.sales_agent_id {where}""", params
            ).fetchone()
            plans = [dict(r) for r in conn.execute("SELECT * FROM membership_plans ORDER BY sale_price DESC,name")]
        self.send_json({
            "ok": True,
            "cards": rows,
            "summary": dict(summary_row),
            "plans": plans,
            "statuses": list(MEMBERSHIP_STATUSES),
            "transaction_types": list(MEMBERSHIP_TRANSACTION_TYPES),
            "can_write": self.has_permission(user, "membership_write"),
            "can_delete": user.get("role") in ("Owner", "Administrator"),
            "can_see_finance": self.has_permission(user, "finance_read"),
        })

    def validate_membership_card(self, data: dict[str, Any], existing: sqlite3.Row | None = None) -> dict[str, Any]:
        def val(key: str, default: Any = "") -> Any:
            return data.get(key, existing[key] if existing else default)
        result = {
            "card_no": str(val("card_no")).strip(),
            "customer_id": int(val("customer_id", 0) or 0),
            "plan_id": int(val("plan_id", 0) or 0),
            "branch": str(val("branch")).strip(),
            "issue_date": str(val("issue_date")).strip(),
            "expiry_date": str(val("expiry_date")).strip(),
            "sale_price": float(val("sale_price", 0) or 0),
            "opening_balance": float(val("opening_balance", 0) or 0),
            "status": str(val("status", "Active")).strip(),
            "payment_method": str(val("payment_method", "Other")).strip(),
            "sales_agent_id": int(val("sales_agent_id", 0) or 0) or None,
            "sales_agent_name": str(val("sales_agent_name", "")).strip(),
            "commission_rate": float(val("commission_rate", 10) or 0),
            "notes": str(val("notes")).strip(),
            "record_finance": bool(data.get("record_finance", False)),
        }
        if not result["card_no"]:
            raise ValueError("Card number is required. Enter the number from your existing card series")
        if not result["customer_id"] or not result["plan_id"] or not result["branch"] or not result["issue_date"]:
            raise ValueError("Customer, plan, branch and issue date are required")
        if result["status"] not in MEMBERSHIP_STATUSES:
            raise ValueError("Invalid membership status")
        if result["sale_price"] < 0 or result["opening_balance"] < 0 or result["commission_rate"] < 0:
            raise ValueError("Card values and commission rate cannot be negative")
        if result["commission_rate"] > 100:
            raise ValueError("Commission rate cannot exceed 100%")
        try:
            datetime.strptime(result["issue_date"], "%Y-%m-%d")
            if result["expiry_date"]:
                datetime.strptime(result["expiry_date"], "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("Use valid issue and expiry dates") from exc
        return result

    def validate_membership_relations(self, conn: sqlite3.Connection, values: dict[str, Any]) -> tuple[sqlite3.Row, sqlite3.Row]:
        customer = conn.execute("SELECT * FROM customers WHERE id=? AND active=1", (values["customer_id"],)).fetchone()
        plan = conn.execute("SELECT * FROM membership_plans WHERE id=? AND active=1", (values["plan_id"],)).fetchone()
        if not customer:
            raise ValueError("Customer not found or inactive")
        if not plan:
            raise ValueError("Membership plan not found or inactive")
        if customer["branch"] != values["branch"]:
            raise ValueError("Customer must belong to the selected branch")
        return customer, plan

    def resolve_sales_agent(self, conn: sqlite3.Connection, sales_agent_id: int | None, sales_agent_name: str, branch: str) -> tuple[int | None, str, sqlite3.Row | None]:
        name = str(sales_agent_name or "").strip()
        if sales_agent_id:
            agent = conn.execute("SELECT * FROM employees WHERE id=?", (sales_agent_id,)).fetchone()
            if not agent or not agent["active"]:
                raise ValueError("Sales agent not found or inactive")
            if agent["branch"] != branch:
                raise ValueError("Sales agent must belong to the selected branch")
            return agent["id"], agent["name"], agent
        if name:
            agent = conn.execute("SELECT * FROM employees WHERE branch=? AND active=1 AND lower(name)=lower(?)", (branch, name)).fetchone()
            if agent:
                return agent["id"], agent["name"], agent
            return None, name, None
        return None, "", None

    def ensure_unique_card_number(self, conn: sqlite3.Connection, card_no: str, exclude_id: int | None = None) -> None:
        sql = "SELECT id FROM membership_cards WHERE lower(card_no)=lower(?)"
        params: list[Any] = [card_no]
        if exclude_id is not None:
            sql += " AND id<>?"; params.append(exclude_id)
        if conn.execute(sql, params).fetchone():
            raise ValueError(f"Card number '{card_no}' already exists. Enter a different number")

    def handle_membership_card_create(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "membership_write"):
            return
        values = self.validate_membership_card(self.parse_json())
        if not self.validate_branch_write(user, values["branch"]):
            return
        with db_connect() as conn:
            customer, plan = self.validate_membership_relations(conn, values)
            agent_id, agent_name, agent = self.resolve_sales_agent(conn, values["sales_agent_id"], values["sales_agent_name"], values["branch"])
            self.ensure_unique_card_number(conn, values["card_no"])
            if not values["expiry_date"]:
                values["expiry_date"] = add_months(values["issue_date"], plan["validity_months"])
            if values["sale_price"] == 0:
                values["sale_price"] = float(plan["sale_price"])
            if values["opening_balance"] == 0:
                values["opening_balance"] = float(plan["wallet_balance"])
            commission_amount = round(values["sale_price"] * values["commission_rate"] / 100, 3) if agent_name else 0
            cur = conn.execute(
                """INSERT INTO membership_cards(card_no,customer_id,plan_id,branch,issue_date,expiry_date,sale_price,opening_balance,current_balance,status,payment_method,sales_agent_id,sales_agent_name,commission_rate,commission_amount,notes,created_by,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (values["card_no"], values["customer_id"], values["plan_id"], values["branch"], values["issue_date"], values["expiry_date"], values["sale_price"], values["opening_balance"], values["opening_balance"], values["status"], values["payment_method"], agent_id, agent_name, values["commission_rate"], commission_amount, values["notes"], user["full_name"], now_iso(), now_iso()),
            )
            if values["record_finance"] and self.has_permission(user, "finance_write") and values["sale_price"] > 0:
                conn.execute(
                    """INSERT INTO finance_entries(date,branch,type,category,description,amount,payment_method,reference,entered_by,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (values["issue_date"], values["branch"], "Income", "Membership Cards", f"{plan['name']} card sale — {customer['name']}", values["sale_price"], values["payment_method"], values["card_no"], user["full_name"], now_iso(), now_iso()),
                )
            agent_text = agent_name or "Direct sale / no agent"
            log_audit(conn, user, "CREATE", "Membership Cards", cur.lastrowid, f"{values['card_no']} | {customer['name']} | {plan['name']} | Agent: {agent_text} | Commission: OMR {commission_amount:.3f}")
        self.send_json({"ok": True, "id": cur.lastrowid, "card_no": values["card_no"]}, 201)

    def handle_membership_card_update(self, user: dict[str, Any], card_id: int) -> None:
        if not self.require_permission(user, "membership_write"):
            return
        with db_connect() as conn:
            existing = conn.execute("SELECT * FROM membership_cards WHERE id=?", (card_id,)).fetchone()
            if not existing:
                self.send_error_json("Membership card not found", 404); return
            values = self.validate_membership_card(self.parse_json(), existing)
            if not self.validate_branch_write(user, values["branch"]):
                return
            customer, plan = self.validate_membership_relations(conn, values)
            agent_id, agent_name, agent = self.resolve_sales_agent(conn, values["sales_agent_id"], values["sales_agent_name"], values["branch"])
            self.ensure_unique_card_number(conn, values["card_no"], card_id)
            if not values["expiry_date"]:
                values["expiry_date"] = add_months(values["issue_date"], plan["validity_months"])
            adjusted_balance = max(0, float(existing["current_balance"]) + values["opening_balance"] - float(existing["opening_balance"]))
            commission_amount = round(values["sale_price"] * values["commission_rate"] / 100, 3) if agent_name else 0
            conn.execute(
                """UPDATE membership_cards SET card_no=?,customer_id=?,plan_id=?,branch=?,issue_date=?,expiry_date=?,sale_price=?,opening_balance=?,current_balance=?,status=?,payment_method=?,sales_agent_id=?,sales_agent_name=?,commission_rate=?,commission_amount=?,notes=?,updated_at=? WHERE id=?""",
                (values["card_no"], values["customer_id"], values["plan_id"], values["branch"], values["issue_date"], values["expiry_date"], values["sale_price"], values["opening_balance"], adjusted_balance, values["status"], values["payment_method"], agent_id, agent_name, values["commission_rate"], commission_amount, values["notes"], now_iso(), card_id),
            )
            log_audit(conn, user, "UPDATE", "Membership Cards", card_id, f"{values['card_no']} | {customer['name']} | status={values['status']}")
        self.send_json({"ok": True})

    def handle_membership_card_delete(self, user: dict[str, Any], card_id: int) -> None:
        if not self.require_permission(user, "membership_write"):
            return
        if user.get("role") not in ("Owner", "Administrator"):
            self.send_error_json("Only Owner or Administrator can delete a membership card", 403); return
        with db_connect() as conn:
            row = conn.execute("SELECT * FROM membership_cards WHERE id=?", (card_id,)).fetchone()
            if not row:
                self.send_error_json("Membership card not found", 404); return
            if not self.validate_branch_write(user, row["branch"]):
                return
            conn.execute("DELETE FROM membership_cards WHERE id=?", (card_id,))
            log_audit(conn, user, "DELETE", "Membership Cards", card_id, f"{row['card_no']} | {row['branch']}")
        self.send_json({"ok": True})

    def handle_membership_transactions(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "membership_read"):
            return
        q = self.query()
        card_id = int(q.get("card_id", ["0"])[0] or 0)
        if not card_id:
            raise ValueError("Card ID is required")
        with db_connect() as conn:
            card = conn.execute(
                """SELECT mc.*,c.name customer_name,mp.name plan_name FROM membership_cards mc
                JOIN customers c ON c.id=mc.customer_id JOIN membership_plans mp ON mp.id=mc.plan_id WHERE mc.id=?""",
                (card_id,),
            ).fetchone()
            if not card:
                self.send_error_json("Membership card not found", 404); return
            allowed = self.allowed_branch(user, card["branch"])
            if user.get("branch") != "All" and allowed != card["branch"]:
                self.send_error_json("Branch access denied", 403); return
            rows = [dict(r) for r in conn.execute("SELECT * FROM membership_transactions WHERE card_id=? ORDER BY date DESC,id DESC", (card_id,))]
        self.send_json({"ok": True, "card": dict(card), "transactions": rows, "can_write": self.has_permission(user, "membership_write")})

    def handle_membership_transaction_create(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "membership_write"):
            return
        data = self.parse_json()
        card_id = int(data.get("card_id", 0) or 0)
        date = str(data.get("date", "")).strip()
        tx_type = str(data.get("type", "Purchase")).strip()
        amount = float(data.get("amount", 0) or 0)
        reference = str(data.get("reference", "")).strip()
        notes = str(data.get("notes", "")).strip()
        if not card_id or not date or amount <= 0:
            raise ValueError("Card, date and amount greater than zero are required")
        if tx_type not in MEMBERSHIP_TRANSACTION_TYPES:
            raise ValueError("Invalid transaction type")
        with db_connect() as conn:
            card = conn.execute("SELECT * FROM membership_cards WHERE id=?", (card_id,)).fetchone()
            if not card:
                self.send_error_json("Membership card not found", 404); return
            if not self.validate_branch_write(user, card["branch"]):
                return
            if card["status"] != "Active":
                raise ValueError("Only an active membership card can be used")
            current = float(card["current_balance"])
            debit = tx_type in ("Purchase", "Adjustment Debit")
            new_balance = current - amount if debit else current + amount
            if new_balance < -0.0001:
                raise ValueError("Transaction amount exceeds the available card balance")
            cur = conn.execute(
                """INSERT INTO membership_transactions(card_id,date,type,amount,reference,notes,entered_by,created_at)
                VALUES (?,?,?,?,?,?,?,?)""",
                (card_id, date, tx_type, amount, reference, notes, user["full_name"], now_iso()),
            )
            conn.execute("UPDATE membership_cards SET current_balance=?,updated_at=? WHERE id=?", (new_balance, now_iso(), card_id))
            log_audit(conn, user, "CREATE", "Membership Transactions", cur.lastrowid, f"{card['card_no']} | {tx_type} | OMR {amount:.3f}")
        self.send_json({"ok": True, "id": cur.lastrowid, "new_balance": new_balance}, 201)

    def handle_export_membership(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "membership_read"):
            return
        where, params = self.membership_filters(user)
        with db_connect() as conn:
            rows = list(conn.execute(
                f"""SELECT mc.*,c.name customer_name,c.phone,mp.name plan_name,COALESCE(e.name,NULLIF(mc.sales_agent_name,'')) sales_agent_display
                FROM membership_cards mc JOIN customers c ON c.id=mc.customer_id
                JOIN membership_plans mp ON mp.id=mc.plan_id
                LEFT JOIN employees e ON e.id=mc.sales_agent_id {where}
                ORDER BY mc.issue_date,mc.id""", params
            ))
        currency = self.report_currency()
        headers = ["Card No","Customer","Phone","Plan","Branch","Issue Date","Expiry Date","Status",f"Opening Balance ({currency})",f"Current Balance ({currency})",f"Sale Price ({currency})","Payment Method","Sales Agent","Commission Rate %",f"Commission Amount ({currency})","Notes"]
        out = [[r["card_no"],r["customer_name"],r["phone"],r["plan_name"],r["branch"],r["issue_date"],r["expiry_date"],r["status"],r["opening_balance"],r["current_balance"],r["sale_price"],r["payment_method"],r["sales_agent_display"] or "Direct sale / no agent",r["commission_rate"],r["commission_amount"],r["notes"]] for r in rows]
        self.send_csv(self.export_filename("membership_cards", "csv"), headers, out)

    def membership_commission_filters(self, user: dict[str, Any]) -> tuple[str, list[Any], str, str]:
        q = self.query()
        branch = self.allowed_branch(user, q.get("branch", ["All"])[0])
        month = q.get("month", [current_month_key()])[0]
        try:
            datetime.strptime(month, "%Y-%m")
        except ValueError as exc:
            raise ValueError("Commission month must use YYYY-MM format") from exc
        start, end = month_date_range(month)
        where = " WHERE mc.issue_date BETWEEN ? AND ?"
        params: list[Any] = [start, end]
        if branch != "All":
            where += " AND mc.branch=?"; params.append(branch)
        return where, params, branch, month

    def handle_membership_commissions(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "membership_read"):
            return
        where, params, branch, month = self.membership_commission_filters(user)
        with db_connect() as conn:
            rows = [dict(r) for r in conn.execute(
                f"""SELECT mc.sales_agent_id,COALESCE(e.name,NULLIF(mc.sales_agent_name,'')) sales_agent,
                COALESCE(e.role,'Manual Sales Agent') designation,mc.branch,
                COUNT(mc.id) cards_sold,COALESCE(SUM(mc.sale_price),0) total_sales,
                COALESCE(SUM(mc.commission_amount),0) total_commission
                FROM membership_cards mc LEFT JOIN employees e ON e.id=mc.sales_agent_id
                {where} AND TRIM(COALESCE(e.name,mc.sales_agent_name,''))<>''
                GROUP BY COALESCE(CAST(mc.sales_agent_id AS TEXT),'manual:'||lower(mc.sales_agent_name)),COALESCE(e.name,mc.sales_agent_name),COALESCE(e.role,'Manual Sales Agent'),mc.branch
                ORDER BY total_commission DESC,sales_agent""", params
            )]
            summary = conn.execute(
                f"""SELECT COUNT(mc.id) cards_sold,COUNT(DISTINCT COALESCE(CAST(mc.sales_agent_id AS TEXT),'manual:'||lower(mc.sales_agent_name))) agents,
                COALESCE(SUM(mc.sale_price),0) total_sales,COALESCE(SUM(mc.commission_amount),0) total_commission
                FROM membership_cards mc {where} AND TRIM(COALESCE(mc.sales_agent_name,''))<>''""", params
            ).fetchone()
        self.send_json({"ok": True, "month": month, "branch": branch, "rows": rows, "summary": dict(summary), "can_see_finance": self.has_permission(user, "finance_read")})

    def handle_export_membership_commissions(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "membership_read"):
            return
        where, params, branch, month = self.membership_commission_filters(user)
        with db_connect() as conn:
            rows = list(conn.execute(
                f"""SELECT COALESCE(e.name,NULLIF(mc.sales_agent_name,'')) sales_agent,
                COALESCE(e.role,'Manual Sales Agent') designation,mc.branch,COUNT(mc.id) cards_sold,
                COALESCE(SUM(mc.sale_price),0) total_sales,COALESCE(SUM(mc.commission_amount),0) total_commission
                FROM membership_cards mc LEFT JOIN employees e ON e.id=mc.sales_agent_id
                {where} AND TRIM(COALESCE(e.name,mc.sales_agent_name,''))<>''
                GROUP BY COALESCE(CAST(mc.sales_agent_id AS TEXT),'manual:'||lower(mc.sales_agent_name)),COALESCE(e.name,mc.sales_agent_name),COALESCE(e.role,'Manual Sales Agent'),mc.branch
                ORDER BY total_commission DESC,sales_agent""", params
            ))
        currency = self.report_currency()
        headers = ["Month","Branch","Sales Agent","Designation","Cards Sold",f"Card Sales ({currency})",f"Commission ({currency})"]
        out = [[month,r["branch"],r["sales_agent"],r["designation"],r["cards_sold"],r["total_sales"],r["total_commission"]] for r in rows]
        self.send_csv(self.export_filename(f"card_commission_{month}", "csv"), headers, out)

    def production_filters(self, user: dict[str, Any]) -> tuple[str, list[Any]]:
        q = self.query()
        branch = self.allowed_branch(user, q.get("branch", ["All"])[0])
        default_start, default_end = current_month_range()
        start = q.get("start", [default_start])[0] or default_start
        end = q.get("end", [default_end])[0] or default_end
        employee_id = q.get("employee_id", [""])[0]
        where = " WHERE p.date BETWEEN ? AND ?"
        params: list[Any] = [start, end]
        if branch != "All":
            where += " AND p.branch=?"; params.append(branch)
        if employee_id:
            where += " AND p.employee_id=?"; params.append(int(employee_id))
        return where, params

    def handle_production_list(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "production_read"):
            return
        where, params = self.production_filters(user)
        q = self.query()
        ready_branch = self.allowed_branch(user, q.get("branch", ["All"])[0])
        default_start, default_end = current_month_range()
        ready_start = q.get("start", [default_start])[0] or default_start
        ready_end = q.get("end", [default_end])[0] or default_end
        ready_where = "WHERE date BETWEEN ? AND ?"
        ready_params: list[Any] = [ready_start, ready_end]
        if ready_branch != "All":
            ready_where += " AND branch=?"
            ready_params.append(ready_branch)
        with db_connect() as conn:
            entries = [dict(r) for r in conn.execute(
                f"""SELECT p.*,e.name employee,e.role employee_role FROM production_entries p
                JOIN employees e ON e.id=p.employee_id {where} ORDER BY p.date DESC,p.id DESC""", params
            )]
            summary = [dict(r) for r in conn.execute(
                f"""WITH totals AS (
                    SELECT p.employee_id,e.name employee,p.branch,
                    SUM(CASE WHEN p.activity='Body' THEN p.quantity ELSE 0 END) body,
                    SUM(CASE WHEN p.activity='Joint/Side' THEN p.quantity ELSE 0 END) joint_side,
                    SUM(CASE WHEN p.activity='Daraz' THEN p.quantity ELSE 0 END) daraz,
                    SUM(CASE WHEN p.activity='VIP Design' THEN p.quantity ELSE 0 END) vip_design,
                    SUM(CASE WHEN p.activity='Button' THEN p.quantity ELSE 0 END) button,
                    SUM(CASE WHEN p.activity='Alteration' THEN p.quantity ELSE 0 END) alteration,
                    SUM(CASE WHEN p.activity='Cutting' THEN p.quantity ELSE 0 END) cutting,
                    SUM(CASE WHEN p.activity='Iron' THEN p.quantity ELSE 0 END) iron,
                    SUM(CASE WHEN p.activity='Sample' THEN p.quantity ELSE 0 END) sample,
                    SUM(p.quantity) total_quantity,SUM(p.ot_hours) ot_hours
                    FROM production_entries p JOIN employees e ON e.id=p.employee_id {where}
                    GROUP BY p.employee_id,e.name,p.branch
                )
                SELECT *,MIN(body,joint_side) full_body_produced,
                    MIN(body,joint_side)+daraz+vip_design+button+alteration+cutting+iron+sample total_pcs_produced,
                    MIN(body,joint_side)+daraz+vip_design+button+alteration+cutting+iron+sample ready_pcs
                FROM totals ORDER BY employee""", params
            )]
            daily_ready = [dict(r) for r in conn.execute(
                f"""SELECT * FROM production_daily_ready {ready_where}
                ORDER BY date DESC,branch""", ready_params
            )]
            ready_total = sum(int(r["total_ready_completed"] or 0) for r in daily_ready)
        self.send_json({
            "ok": True, "entries": entries, "summary": summary,
            "daily_ready": daily_ready, "ready_total": ready_total,
            "can_write": self.has_permission(user,"production_write")
        })

    def handle_production_ready_list(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "production_read"):
            return
        q = self.query()
        branch = self.allowed_branch(user, q.get("branch", ["All"])[0])
        default_start, default_end = current_month_range()
        start = q.get("start", [default_start])[0] or default_start
        end = q.get("end", [default_end])[0] or default_end
        where = "WHERE date BETWEEN ? AND ?"
        params: list[Any] = [start, end]
        if branch != "All":
            where += " AND branch=?"; params.append(branch)
        with db_connect() as conn:
            rows = [dict(r) for r in conn.execute(
                f"SELECT * FROM production_daily_ready {where} ORDER BY date DESC,branch", params
            )]
        self.send_json({"ok": True, "rows": rows, "total": sum(int(r["total_ready_completed"] or 0) for r in rows)})

    def handle_production_ready_save(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "production_write"):
            return
        data = self.parse_json()
        date = str(data.get("date", "")).strip()
        branch = str(data.get("branch", "")).strip()
        raw_total = data.get("total_ready_completed", 0)
        if not date or not branch:
            raise ValueError("Date and branch are required")
        if not self.validate_branch_write(user, branch):
            return
        try:
            value = float(raw_total or 0)
        except (TypeError, ValueError):
            raise ValueError("Total Ready Completed must be a number")
        if value < 0 or not value.is_integer():
            raise ValueError("Total Ready Completed must be a whole number of pieces")
        total = int(value)
        notes = str(data.get("notes", "")).strip()
        with db_connect() as conn:
            existing = conn.execute(
                "SELECT * FROM production_daily_ready WHERE date=? AND branch=?", (date, branch)
            ).fetchone()
            if existing:
                conn.execute(
                    """UPDATE production_daily_ready SET total_ready_completed=?,notes=?,entered_by=?,updated_at=?
                    WHERE id=?""",
                    (total, notes, user["full_name"], now_iso(), existing["id"]),
                )
                record_id = existing["id"]
                action = "UPDATE"
                detail = f"{branch} {date} | Total Ready Completed {existing['total_ready_completed']} → {total}"
            else:
                cur = conn.execute(
                    """INSERT INTO production_daily_ready(date,branch,total_ready_completed,notes,entered_by,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?)""",
                    (date, branch, total, notes, user["full_name"], now_iso(), now_iso()),
                )
                record_id = cur.lastrowid
                action = "CREATE"
                detail = f"{branch} {date} | Total Ready Completed {total}"
            log_audit(conn, user, action, "Daily Ready Completed", record_id, detail)
            row = dict(conn.execute("SELECT * FROM production_daily_ready WHERE id=?", (record_id,)).fetchone())
        self.send_json({"ok": True, "record": row}, 201 if action == "CREATE" else 200)

    def handle_production_ready_delete(self, user: dict[str, Any], record_id: int) -> None:
        if not self.require_permission(user, "production_write"):
            return
        with db_connect() as conn:
            row = conn.execute("SELECT * FROM production_daily_ready WHERE id=?", (record_id,)).fetchone()
            if not row:
                self.send_error_json("Daily Ready Completed record not found", 404); return
            if not self.validate_branch_write(user, row["branch"]):
                return
            conn.execute("DELETE FROM production_daily_ready WHERE id=?", (record_id,))
            log_audit(conn, user, "DELETE", "Daily Ready Completed", record_id,
                      f"{row['branch']} {row['date']} | Deleted total {row['total_ready_completed']}")
        self.send_json({"ok": True})

    def handle_production_history(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "production_read"):
            return
        q = self.query(); emp_id = int(q.get("employee_id", ["0"])[0] or 0)
        if not emp_id:
            raise ValueError("employee_id is required")
        with db_connect() as conn:
            emp = conn.execute("SELECT * FROM employees WHERE id=?", (emp_id,)).fetchone()
            if not emp:
                self.send_error_json("Employee not found",404); return
            allowed = self.allowed_branch(user, emp["branch"])
            if user.get("branch") != "All" and emp["branch"] != allowed:
                self.send_error_json("Branch access denied",403); return
            history = [dict(r) for r in conn.execute(
                """SELECT month_key,activity,quantity,ready_pcs,ot_hours FROM production_monthly_history
                WHERE employee_id=? ORDER BY month_key,activity""", (emp_id,)
            )]
        grouped: dict[str, dict[str, Any]] = {}
        for r in history:
            m = grouped.setdefault(r["month_key"], {"month_key":r["month_key"],"month":month_name(r["month_key"]),"activities":{},"total_quantity":0,"ready_pcs":0,"ot_hours":0})
            m["activities"][r["activity"]] = r["quantity"]
            m["total_quantity"] += r["quantity"]
            m["ot_hours"] += r["ot_hours"]
        for m in grouped.values():
            body=float(m["activities"].get("Body",0) or 0); joint=float(m["activities"].get("Joint/Side",0) or 0)
            other=sum(float(v or 0) for k,v in m["activities"].items() if k not in ("Body","Joint/Side"))
            m["full_body_produced"]=round(min(body,joint),3)
            m["ready_pcs"]=round(min(body,joint)+other,3)
            m["total_pcs_produced"]=m["ready_pcs"]
        self.send_json({"ok":True,"employee":dict(emp),"history":list(grouped.values())})

    def validate_branch_write(self, user: dict[str, Any], branch: str) -> bool:
        assigned = user.get("branch", "All")
        if assigned != "All" and branch != assigned:
            self.send_error_json("You can only enter data for your assigned branch", 403)
            return False
        return True

    def handle_production_create(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "production_write"):
            return
        data = self.parse_json()
        required = ["date","branch","employee_id"]
        if any(not data.get(k) for k in required):
            raise ValueError("Date, branch and employee are required")
        if not self.validate_branch_write(user, str(data["branch"])):
            return
        ot = float(data.get("ot_hours",0) or 0)
        if ot < 0:
            raise ValueError("Overtime hours cannot be negative")
        with db_connect() as conn:
            emp = conn.execute("SELECT * FROM employees WHERE id=? AND active=1", (int(data["employee_id"]),)).fetchone()
            if not emp or emp["branch"] != data["branch"]:
                raise ValueError("Employee does not belong to selected branch")
            allowed_activities = self.employee_skills(conn, emp["id"])
            activity_quantities = data.get("activity_quantities")
            entries_to_save: list[tuple[str,float]] = []
            if isinstance(activity_quantities, dict):
                for activity, raw_qty in activity_quantities.items():
                    qty = float(raw_qty or 0)
                    if qty < 0:
                        raise ValueError("Production quantities cannot be negative")
                    if qty > 0:
                        if activity not in allowed_activities:
                            raise ValueError(f"{activity} is not assigned to this employee")
                        entries_to_save.append((activity, qty))
            else:
                activity = str(data.get("activity", ""))
                qty = float(data.get("quantity",0) or 0)
                if not activity:
                    raise ValueError("Activity is required")
                if qty < 0:
                    raise ValueError("Production quantity cannot be negative")
                if activity not in allowed_activities:
                    raise ValueError("Selected activity is not assigned to this employee")
                entries_to_save.append((activity, qty))
            if not entries_to_save:
                raise ValueError("Enter at least one production quantity")
            ids=[]
            for idx,(activity,qty) in enumerate(entries_to_save):
                produced = 0 if activity in ("Body","Joint/Side") else qty
                entry_ot = ot if idx == 0 else 0
                cur = conn.execute(
                    """INSERT INTO production_entries(date,branch,employee_id,activity,quantity,ready_pcs,ot_hours,notes,entered_by,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (data["date"],data["branch"],int(data["employee_id"]),activity,qty,produced,entry_ot,str(data.get("notes","")),user["full_name"],now_iso(),now_iso()),
                )
                ids.append(cur.lastrowid)
            detail = ", ".join(f"{activity} {qty:g}" for activity,qty in entries_to_save)
            log_audit(conn,user,"CREATE","Production",",".join(map(str,ids)),f"{emp['name']} | {detail}")
        self.send_json({"ok":True,"ids":ids,"id":ids[0]},201)

    def handle_production_update(self, user: dict[str, Any], entry_id: int) -> None:
        if not self.require_permission(user, "production_write"):
            return
        data=self.parse_json()
        with db_connect() as conn:
            existing=conn.execute("SELECT * FROM production_entries WHERE id=?",(entry_id,)).fetchone()
            if not existing:
                self.send_error_json("Production entry not found",404);return
            branch=str(data.get("branch",existing["branch"]))
            if not self.validate_branch_write(user,branch):return
            emp_id=int(data.get("employee_id",existing["employee_id"]))
            emp=conn.execute("SELECT * FROM employees WHERE id=?",(emp_id,)).fetchone()
            if not emp or emp["branch"]!=branch:raise ValueError("Employee does not belong to selected branch")
            activity=str(data.get("activity",existing["activity"]))
            if activity not in self.employee_skills(conn, emp_id):raise ValueError("Selected activity is not assigned to this employee")
            quantity=float(data.get("quantity",existing["quantity"]))
            produced=0 if activity in ("Body","Joint/Side") else quantity
            values=(str(data.get("date",existing["date"])),branch,emp_id,activity,quantity,produced,float(data.get("ot_hours",existing["ot_hours"])),str(data.get("notes",existing["notes"])),now_iso(),entry_id)
            if min(values[4],values[5],values[6])<0:raise ValueError("Quantity values cannot be negative")
            conn.execute("UPDATE production_entries SET date=?,branch=?,employee_id=?,activity=?,quantity=?,ready_pcs=?,ot_hours=?,notes=?,updated_at=? WHERE id=?",values)
            log_audit(conn,user,"UPDATE","Production",entry_id,f"Updated {emp['name']} production entry")
        self.send_json({"ok":True})

    def handle_production_delete(self, user: dict[str, Any], entry_id: int) -> None:
        if not self.require_permission(user,"production_write"):return
        with db_connect() as conn:
            row=conn.execute("SELECT p.*,e.name employee FROM production_entries p JOIN employees e ON e.id=p.employee_id WHERE p.id=?",(entry_id,)).fetchone()
            if not row:self.send_error_json("Production entry not found",404);return
            if not self.validate_branch_write(user,row["branch"]):return
            conn.execute("DELETE FROM production_entries WHERE id=?",(entry_id,))
            log_audit(conn,user,"DELETE","Production",entry_id,f"Deleted {row['employee']} | {row['activity']} | Qty {row['quantity']}")
        self.send_json({"ok":True})

    POS_REQUIRED_HEADERS = (
        "Date", "Invoice No.", "Customer name", "Contact Number", "Location",
        "Payment Status", "Payment Method", "Total amount", "Total paid", "Sell Due",
        "Sell Return Due", "Shipping Status", "Total Items", "Added By", "Sell note",
        "Staff note", "Shipping Details"
    )
    POS_TEMPLATE_HEADERS = ("Action", *POS_REQUIRED_HEADERS)

    def send_attachment(self, filename: str, content_type: str, body: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def build_pos_template_csv(self) -> bytes:
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(self.POS_TEMPLATE_HEADERS)
        return output.getvalue().encode("utf-8-sig")

    @staticmethod
    def xlsx_col_name(index: int) -> str:
        name = ""
        index += 1
        while index:
            index, rem = divmod(index - 1, 26)
            name = chr(65 + rem) + name
        return name

    @staticmethod
    def xml_escape(value: Any) -> str:
        return (
            str(value)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    def xlsx_sheet_xml(self, rows: list[list[Any]]) -> str:
        row_xml = []
        for row_idx, row in enumerate(rows, start=1):
            cells = []
            for col_idx, value in enumerate(row):
                ref = f"{self.xlsx_col_name(col_idx)}{row_idx}"
                text = self.xml_escape(value)
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>')
            row_xml.append(f'<row r="{row_idx}">{"".join(cells)}</row>')
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetData>{"".join(row_xml)}</sheetData>'
            '</worksheet>'
        )

    def build_pos_template_xlsx(self) -> bytes:
        import_rows = [list(self.POS_TEMPLATE_HEADERS)]
        instruction_rows = [
            ["Sales Import Template"],
            ["Fill the Sales Import sheet, then upload the workbook or save it as CSV."],
            ["Date formats", "Use YYYY-MM-DD, such as 2026-06-26. MM/DD/YYYY, such as 06/26/2026, is also accepted."],
            ["Excel date cells", "Date-only Excel cells are accepted."],
            ["Branch detection", "Location and invoice prefix are used unless a Branch Detection override is selected during import."],
            ["Duplicate protection", "Invoice No. is the unique key. Re-importing an invoice updates the existing sales record."],
        ]
        content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>"""
        rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""
        workbook = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Sales Import" sheetId="1" r:id="rId1"/>
    <sheet name="Instructions" sheetId="2" r:id="rId2"/>
  </sheets>
</workbook>"""
        workbook_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>
</Relationships>"""
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", content_types)
            archive.writestr("_rels/.rels", rels)
            archive.writestr("xl/workbook.xml", workbook)
            archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
            archive.writestr("xl/worksheets/sheet1.xml", self.xlsx_sheet_xml(import_rows))
            archive.writestr("xl/worksheets/sheet2.xml", self.xlsx_sheet_xml(instruction_rows))
        return output.getvalue()

    def handle_sales_import_template_csv(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "finance_write"):
            return
        self.send_attachment("sales_import_template.csv", "text/csv; charset=utf-8", self.build_pos_template_csv())

    def handle_sales_import_template_xlsx(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "finance_write"):
            return
        self.send_attachment(
            "sales_import_template.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            self.build_pos_template_xlsx(),
        )

    def parse_pos_money(self, value: Any) -> float:
        text = str(value or "").strip().replace(",", "")
        if not text:
            return 0.0
        cleaned = re.sub(r"[^0-9.\-]", "", text)
        if cleaned in ("", "-", ".", "-."):
            return 0.0
        try:
            return round(float(cleaned), 3)
        except ValueError as exc:
            raise ValueError(f"Invalid amount: {value}") from exc

    def parse_pos_datetime(self, value: Any) -> tuple[str, str]:
        raw = str(value or "").strip()
        if re.fullmatch(r"\d+(\.\d+)?", raw):
            try:
                serial = float(raw)
                if 20000 <= serial <= 80000:
                    dt = datetime(1899, 12, 30) + timedelta(days=serial)
                    return dt.strftime("%Y-%m-%d %H:%M:%S"), dt.strftime("%Y-%m-%d")
            except ValueError:
                pass
        formats = (
            "%d-%m-%Y %H:%M", "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
            "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%Y",
        )
        for fmt in formats:
            try:
                dt = datetime.strptime(raw, fmt)
                return dt.strftime("%Y-%m-%d %H:%M:%S"), dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
        raise ValueError(f"Invalid POS date: {raw}")

    def normalize_pos_branch(self, location: Any, invoice_no: Any, override: str = "Auto Detect") -> str:
        if override and override != "Auto Detect":
            return override
        loc = re.sub(r"[^a-z]", "", str(location or "").lower())
        invoice = str(invoice_no or "").strip().upper()
        # Invoice prefix is more reliable than the customer/location text.
        if invoice.startswith(("AK", "ALK")):
            return "Al Khoud"
        if invoice.startswith(("AZ", "AZB")):
            return "Azaiba"
        if invoice.startswith(("NZ", "NIZ")):
            return "Nizwa"
        if "khoud" in loc:
            return "Al Khoud"
        if "azaiba" in loc or "azeba" in loc:
            return "Azaiba"
        if "nizwa" in loc:
            return "Nizwa"
        return "Al Khoud"

    def decode_pos_file_payload(self, data: dict[str, Any]) -> tuple[str, bytes]:
        file_name = str(data.get("file_name", "POS sales.csv") or "POS sales.csv")[:250]
        encoded = str(data.get("file_content_b64", "") or "").strip()
        if encoded:
            try:
                raw = base64.b64decode(encoded, validate=True)
            except Exception as exc:
                raise ValueError("The selected POS file could not be read") from exc
            if len(raw) > 15_000_000:
                raise ValueError("POS file is larger than 15 MB")
            return file_name, raw
        # Backward compatibility with the earlier CSV-only build.
        csv_text = str(data.get("csv_text", "") or "")
        if csv_text:
            return file_name, csv_text.encode("utf-8")
        raise ValueError("Select a POS CSV or Excel file")

    def decode_csv_bytes(self, raw: bytes) -> str:
        for encoding in ("utf-8-sig", "utf-16", "cp1252"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise ValueError("CSV encoding is not supported. Export the file as UTF-8 CSV or XLSX")

    def xlsx_cell_value(self, cell: ET.Element, shared_strings: list[str], main_ns: str) -> str:
        cell_type = cell.attrib.get("t", "")
        if cell_type == "inlineStr":
            inline = cell.find(f"{{{main_ns}}}is")
            return "" if inline is None else "".join(inline.itertext())
        value_node = cell.find(f"{{{main_ns}}}v")
        value = "" if value_node is None or value_node.text is None else value_node.text
        if cell_type == "s":
            try:
                return shared_strings[int(value)]
            except (ValueError, IndexError):
                return ""
        if cell_type == "b":
            return "TRUE" if value == "1" else "FALSE"
        if cell_type in ("str", "e"):
            return value
        # POS contact numbers and quantities are often stored as numeric cells.
        try:
            number = float(value)
            if number.is_integer():
                return str(int(number))
            return format(number, ".15g")
        except (TypeError, ValueError):
            return value

    def parse_xlsx_rows(self, raw: bytes) -> list[list[str]]:
        try:
            archive = zipfile.ZipFile(io.BytesIO(raw))
        except zipfile.BadZipFile as exc:
            raise ValueError("The Excel file is invalid or damaged") from exc
        with archive:
            names = set(archive.namelist())
            if "xl/workbook.xml" not in names:
                raise ValueError("The Excel workbook structure is not supported")
            main_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
            rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
            office_rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

            shared_strings: list[str] = []
            if "xl/sharedStrings.xml" in names:
                root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                for si in root.findall(f"{{{main_ns}}}si"):
                    shared_strings.append("".join(si.itertext()))

            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            sheet = workbook.find(f".//{{{main_ns}}}sheet")
            if sheet is None:
                raise ValueError("The Excel workbook has no worksheet")
            rel_id = sheet.attrib.get(f"{{{office_rel_ns}}}id", "")
            rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            target = ""
            for rel in rels.findall(f"{{{rel_ns}}}Relationship"):
                if rel.attrib.get("Id") == rel_id:
                    target = rel.attrib.get("Target", "")
                    break
            if not target:
                raise ValueError("The first Excel worksheet could not be opened")
            target = target.replace("\\", "/")
            if target.startswith("/"):
                sheet_path = target.lstrip("/")
            elif target.startswith("xl/"):
                sheet_path = target
            else:
                sheet_path = "xl/" + target.lstrip("./")
            if sheet_path not in names:
                raise ValueError("The first Excel worksheet file is missing")

            sheet_root = ET.fromstring(archive.read(sheet_path))
            output: list[list[str]] = []
            for row_node in sheet_root.findall(f".//{{{main_ns}}}sheetData/{{{main_ns}}}row"):
                row_values: dict[int, str] = {}
                max_col = -1
                for cell in row_node.findall(f"{{{main_ns}}}c"):
                    ref = cell.attrib.get("r", "")
                    letters = "".join(ch for ch in ref if ch.isalpha()).upper()
                    col = 0
                    for ch in letters:
                        col = col * 26 + (ord(ch) - 64)
                    col = max(0, col - 1)
                    row_values[col] = self.xlsx_cell_value(cell, shared_strings, main_ns)
                    max_col = max(max_col, col)
                output.append([row_values.get(i, "") for i in range(max_col + 1)] if max_col >= 0 else [])
            return output

    def find_pos_header(self, rows: list[list[Any]]) -> tuple[int, list[str]]:
        required = set(self.POS_REQUIRED_HEADERS)
        for idx, row in enumerate(rows[:15]):
            headers = [str(value or "").strip() for value in row]
            if required.issubset(set(headers)):
                return idx, headers
        raise ValueError("POS columns were not found. Use the original ‘All sales’ CSV or XLSX export")

    def parse_pos_rows(self, source_rows: list[list[Any]], branch_override: str, assigned_branch: str = "All") -> dict[str, Any]:
        header_index, headers = self.find_pos_header(source_rows)
        missing = [h for h in self.POS_REQUIRED_HEADERS if h not in headers]
        if missing:
            raise ValueError("POS columns are missing: " + ", ".join(missing))
        parsed: list[dict[str, Any]] = []
        invalid: list[dict[str, Any]] = []
        seen: dict[str, int] = {}
        duplicate_in_file = 0
        source_count = 0
        for row_index, values in enumerate(source_rows[header_index + 1:], start=header_index + 2):
            source_count += 1
            padded = list(values) + [""] * max(0, len(headers) - len(values))
            raw = {headers[i]: padded[i] if i < len(padded) else "" for i in range(len(headers))}
            invoice = str(raw.get("Invoice No.", "") or "").strip()
            date_raw = str(raw.get("Date", "") or "").strip()
            action = str(raw.get("Action", "") or "").strip()
            if invoice.lower().startswith("total") or date_raw.lower().startswith("total") or action.lower().startswith("total"):
                continue
            if not any(str(value or "").strip() for value in values):
                continue
            try:
                if not invoice:
                    raise ValueError("Invoice number is missing")
                sale_datetime, sale_date = self.parse_pos_datetime(date_raw)
                branch = self.normalize_pos_branch(raw.get("Location"), invoice, branch_override)
                if assigned_branch != "All" and branch != assigned_branch:
                    raise ValueError(f"Invoice belongs to {branch}; your login is restricted to {assigned_branch}")
                row = {
                    "invoice_no": invoice,
                    "sale_datetime": sale_datetime,
                    "sale_date": sale_date,
                    "branch": branch,
                    "customer_name": str(raw.get("Customer name", "") or "").strip(),
                    "contact_number": str(raw.get("Contact Number", "") or "").strip(),
                    "location": str(raw.get("Location", "") or "").strip(),
                    "payment_status": str(raw.get("Payment Status", "") or "").strip() or "Unknown",
                    "payment_method": str(raw.get("Payment Method", "") or "").strip() or "Other",
                    "total_amount": self.parse_pos_money(raw.get("Total amount")),
                    "total_paid": self.parse_pos_money(raw.get("Total paid")),
                    "sell_due": self.parse_pos_money(raw.get("Sell Due")),
                    "sell_return_due": self.parse_pos_money(raw.get("Sell Return Due")),
                    "shipping_status": str(raw.get("Shipping Status", "") or "").strip(),
                    "total_items": self.parse_pos_money(raw.get("Total Items")),
                    "added_by": str(raw.get("Added By", "") or "").strip(),
                    "sell_note": str(raw.get("Sell note", "") or "").strip(),
                    "staff_note": str(raw.get("Staff note", "") or "").strip(),
                    "shipping_details": str(raw.get("Shipping Details", "") or "").strip(),
                    "raw_json": json.dumps(raw, ensure_ascii=False),
                    "line_no": row_index,
                }
                if invoice in seen:
                    duplicate_in_file += 1
                    parsed[seen[invoice]] = row
                else:
                    seen[invoice] = len(parsed)
                    parsed.append(row)
            except ValueError as exc:
                invalid.append({"line": row_index, "invoice_no": invoice, "error": str(exc)})
        return {"rows": parsed, "invalid": invalid, "source_rows": source_count, "duplicate_in_file": duplicate_in_file}

    def parse_pos_file(self, data: dict[str, Any], branch_override: str, assigned_branch: str = "All") -> dict[str, Any]:
        file_name, raw = self.decode_pos_file_payload(data)
        extension = Path(file_name).suffix.lower()
        if extension == ".xlsx":
            rows = self.parse_xlsx_rows(raw)
            parsed = self.parse_pos_rows(rows, branch_override, assigned_branch)
            parsed["source_format"] = "Excel XLSX"
        elif extension == ".csv" or not extension:
            text = self.decode_csv_bytes(raw)
            rows = list(csv.reader(io.StringIO(text.lstrip("\ufeff"))))
            parsed = self.parse_pos_rows(rows, branch_override, assigned_branch)
            parsed["source_format"] = "CSV"
        elif extension == ".xls":
            raise ValueError("Old .xls files are not supported. Export as .xlsx or .csv")
        else:
            raise ValueError("Unsupported file type. Select a .csv or .xlsx POS export")
        parsed["file_name"] = file_name
        parsed["file_bytes"] = raw
        return parsed

    def pos_sales_summary(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "invoice_count": len(rows),
            "total_amount": round(sum(float(r.get("total_amount", 0) or 0) for r in rows), 3),
            "total_paid": round(sum(float(r.get("total_paid", 0) or 0) for r in rows), 3),
            "sell_due": round(sum(float(r.get("sell_due", 0) or 0) for r in rows), 3),
            "return_due": round(sum(float(r.get("sell_return_due", 0) or 0) for r in rows), 3),
            "total_items": round(sum(float(r.get("total_items", 0) or 0) for r in rows), 3),
            "customer_count": len({(str(r.get("contact_number", "")).strip() or str(r.get("customer_name", "")).strip().lower()) for r in rows if str(r.get("contact_number", "")).strip() or str(r.get("customer_name", "")).strip()}),
        }

    def handle_pos_sales_preview(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "finance_write"):
            return
        data = self.parse_json()
        branch_override = str(data.get("branch_override", "Auto Detect") or "Auto Detect")
        if branch_override not in ("Auto Detect", "Al Khoud", "Azaiba", "Nizwa"):
            raise ValueError("Invalid branch override")
        parsed = self.parse_pos_file(data, branch_override, user.get("branch", "All"))
        rows = parsed["rows"]
        invoices = [r["invoice_no"] for r in rows]
        existing: set[str] = set()
        if invoices:
            with db_connect() as conn:
                for i in range(0, len(invoices), 800):
                    chunk = invoices[i:i+800]
                    marks = ",".join("?" for _ in chunk)
                    existing.update(r["invoice_no"] for r in conn.execute(f"SELECT invoice_no FROM pos_sales WHERE invoice_no IN ({marks})", chunk))
        branches: dict[str, int] = {}
        statuses: dict[str, int] = {}
        for r in rows:
            branches[r["branch"]] = branches.get(r["branch"], 0) + 1
            statuses[r["payment_status"]] = statuses.get(r["payment_status"], 0) + 1
        self.send_json({
            "ok": True,
            "summary": self.pos_sales_summary(rows),
            "valid_rows": len(rows),
            "invalid_rows": len(parsed["invalid"]),
            "duplicate_in_file": parsed["duplicate_in_file"],
            "new_invoices": len(rows) - len(existing),
            "existing_invoices": len(existing),
            "branches": branches,
            "payment_statuses": statuses,
            "sample": rows[:12],
            "errors": parsed["invalid"][:20],
            "source_format": parsed.get("source_format", "POS File"),
            "file_name": parsed.get("file_name", ""),
        })

    def upsert_pos_customer(self, conn: sqlite3.Connection, row: dict[str, Any], user: dict[str, Any]) -> tuple[int | None, bool]:
        name = row["customer_name"] or "Walk-in Customer"
        phone = re.sub(r"\s+", "", row["contact_number"])
        branch = row["branch"]
        existing = None
        if phone:
            existing = conn.execute("SELECT * FROM customers WHERE phone=? AND branch=? ORDER BY id LIMIT 1", (phone, branch)).fetchone()
        if not existing and name:
            existing = conn.execute("SELECT * FROM customers WHERE lower(name)=lower(?) AND branch=? ORDER BY id LIMIT 1", (name, branch)).fetchone()
        if existing:
            changes = []
            new_name = name if name and name != "Walk-in Customer" else existing["name"]
            new_phone = phone or existing["phone"]
            new_address = row["location"] or existing["address"]
            if new_name != existing["name"] or new_phone != existing["phone"] or new_address != existing["address"]:
                conn.execute("UPDATE customers SET name=?,phone=?,address=?,updated_at=? WHERE id=?", (new_name,new_phone,new_address,now_iso(),existing["id"]))
                changes.append("updated")
            return int(existing["id"]), False
        cur = conn.execute(
            """INSERT INTO customers(customer_code,name,phone,email,branch,address,notes,active,created_by,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (self.internal_customer_key(), name, phone, "", branch, row["location"], "Imported from POS sales", 1, user["full_name"], now_iso(), now_iso()),
        )
        return int(cur.lastrowid), True

    def upsert_pos_finance(self, conn: sqlite3.Connection, row: dict[str, Any], user: dict[str, Any], basis: str, existing_finance_id: int | None = None) -> int | None:
        amount = row["total_amount"] if basis == "Total Amount" else row["total_paid"]
        if amount <= 0:
            return existing_finance_id
        description = f"POS Sale — {row['customer_name'] or 'Walk-in Customer'}"
        payment = row["payment_method"] or "Other"
        finance = None
        if existing_finance_id:
            finance = conn.execute("SELECT * FROM finance_entries WHERE id=?", (existing_finance_id,)).fetchone()
        if not finance:
            finance = conn.execute("SELECT * FROM finance_entries WHERE type='Income' AND reference=? ORDER BY id LIMIT 1", (row["invoice_no"],)).fetchone()
        if finance:
            conn.execute(
                """UPDATE finance_entries SET date=?,branch=?,category='Shop Sales',description=?,amount=?,payment_method=?,updated_at=? WHERE id=?""",
                (row["sale_date"],row["branch"],description,amount,payment,now_iso(),finance["id"]),
            )
            return int(finance["id"])
        cur = conn.execute(
            """INSERT INTO finance_entries(date,branch,type,category,description,amount,payment_method,reference,entered_by,created_at,updated_at)
            VALUES (?,?, 'Income','Shop Sales',?,?,?,?,?,?,?)""",
            (row["sale_date"],row["branch"],description,amount,payment,row["invoice_no"],user["full_name"],now_iso(),now_iso()),
        )
        return int(cur.lastrowid)

    def handle_pos_sales_import(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "finance_write"):
            return
        data = self.parse_json()
        file_name = str(data.get("file_name", "POS sales.csv"))[:250]
        branch_override = str(data.get("branch_override", "Auto Detect") or "Auto Detect")
        post_to_finance = bool(data.get("post_to_finance", True))
        basis = str(data.get("revenue_basis", "Total Amount") or "Total Amount")
        update_existing = bool(data.get("update_existing", True))
        if basis not in ("Total Amount", "Total Paid"):
            raise ValueError("Revenue basis must be Total Amount or Total Paid")
        if branch_override not in ("Auto Detect", "Al Khoud", "Azaiba", "Nizwa"):
            raise ValueError("Invalid branch override")
        parsed = self.parse_pos_file(data, branch_override, user.get("branch", "All"))
        file_name = parsed.get("file_name", file_name)
        rows = parsed["rows"]
        if not rows:
            raise ValueError("No valid POS sales rows were found")
        inserted = updated = unchanged = customer_created = 0
        with db_connect() as conn:
            file_hash = hashlib.sha256(parsed.get("file_bytes", b"")).hexdigest()
            cur = conn.execute(
                """INSERT INTO pos_import_batches(file_name,file_hash,branch_override,post_to_finance,revenue_basis,rows_total,invalid_count,imported_by,imported_at)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (file_name,file_hash,branch_override,int(post_to_finance),basis,len(rows),len(parsed["invalid"]),user["full_name"],now_iso()),
            )
            batch_id = int(cur.lastrowid)
            for row in rows:
                customer_id, was_created = self.upsert_pos_customer(conn,row,user)
                customer_created += int(was_created)
                existing = conn.execute("SELECT * FROM pos_sales WHERE invoice_no=?", (row["invoice_no"],)).fetchone()
                if existing and not update_existing:
                    unchanged += 1
                    continue
                finance_id = existing["finance_entry_id"] if existing else None
                if post_to_finance:
                    finance_id = self.upsert_pos_finance(conn,row,user,basis,finance_id)
                values = (
                    row["sale_datetime"],row["sale_date"],row["branch"],row["customer_name"],row["contact_number"],row["location"],
                    row["payment_status"],row["payment_method"],row["total_amount"],row["total_paid"],row["sell_due"],row["sell_return_due"],
                    row["shipping_status"],row["total_items"],row["added_by"],row["sell_note"],row["staff_note"],row["shipping_details"],
                    customer_id,finance_id,batch_id,file_name,row["raw_json"],now_iso()
                )
                if existing:
                    comparable = (
                        existing["sale_datetime"],existing["branch"],existing["customer_name"],existing["contact_number"],
                        existing["payment_status"],existing["payment_method"],round(float(existing["total_amount"]),3),round(float(existing["total_paid"]),3),
                        round(float(existing["sell_due"]),3),round(float(existing["total_items"]),3)
                    )
                    current = (
                        row["sale_datetime"],row["branch"],row["customer_name"],row["contact_number"],row["payment_status"],row["payment_method"],
                        row["total_amount"],row["total_paid"],row["sell_due"],row["total_items"]
                    )
                    if comparable == current and (not post_to_finance or finance_id == existing["finance_entry_id"]):
                        unchanged += 1
                        conn.execute("UPDATE pos_sales SET import_batch_id=?,source_file=?,updated_at=? WHERE id=?", (batch_id,file_name,now_iso(),existing["id"]))
                    else:
                        conn.execute(
                            """UPDATE pos_sales SET sale_datetime=?,sale_date=?,branch=?,customer_name=?,contact_number=?,location=?,payment_status=?,payment_method=?,
                            total_amount=?,total_paid=?,sell_due=?,sell_return_due=?,shipping_status=?,total_items=?,added_by=?,sell_note=?,staff_note=?,shipping_details=?,
                            customer_id=?,finance_entry_id=?,import_batch_id=?,source_file=?,raw_json=?,updated_at=? WHERE id=?""",
                            (*values,existing["id"]),
                        )
                        updated += 1
                else:
                    conn.execute(
                        """INSERT INTO pos_sales(invoice_no,sale_datetime,sale_date,branch,customer_name,contact_number,location,payment_status,payment_method,
                        total_amount,total_paid,sell_due,sell_return_due,shipping_status,total_items,added_by,sell_note,staff_note,shipping_details,
                        customer_id,finance_entry_id,import_batch_id,source_file,raw_json,created_at,updated_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (row["invoice_no"],*values,now_iso()),
                    )
                    inserted += 1
            conn.execute(
                """UPDATE pos_import_batches SET inserted_count=?,updated_count=?,unchanged_count=?,customer_count=? WHERE id=?""",
                (inserted,updated,unchanged,customer_created,batch_id),
            )
            log_audit(conn,user,"IMPORT","Sales Record",batch_id,f"{file_name} | inserted={inserted}, updated={updated}, unchanged={unchanged}, invalid={len(parsed['invalid'])}")
        self.send_json({
            "ok": True,"batch_id":batch_id,"inserted":inserted,"updated":updated,"unchanged":unchanged,
            "invalid":len(parsed["invalid"]),"customers_created":customer_created,"summary":self.pos_sales_summary(rows)
        },201)

    def pos_sales_filters(self, user: dict[str, Any]) -> tuple[str, list[Any], dict[str, str]]:
        q = self.query()
        branch = self.allowed_branch(user, q.get("branch", ["All"])[0])
        default_start, default_end = current_month_range()
        start = q.get("start", [default_start])[0] or default_start
        end = q.get("end", [default_end])[0] or default_end
        status = q.get("status", ["All"])[0]
        search = q.get("search", [""])[0].strip()
        where = " WHERE ps.sale_date BETWEEN ? AND ?"
        params: list[Any] = [start,end]
        if branch != "All":
            where += " AND ps.branch=?";params.append(branch)
        if status != "All":
            where += " AND ps.payment_status=?";params.append(status)
        if search:
            token=f"%{search}%"
            where += " AND (ps.invoice_no LIKE ? OR ps.customer_name LIKE ? OR ps.contact_number LIKE ? OR ps.added_by LIKE ?)"
            params += [token,token,token,token]
        return where,params,{"branch":branch,"start":start,"end":end,"status":status,"search":search}

    def handle_pos_sales_list(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user,"finance_read"):
            return
        where,params,filters=self.pos_sales_filters(user)
        with db_connect() as conn:
            rows=[dict(r) for r in conn.execute(f"""SELECT ps.* FROM pos_sales ps {where} ORDER BY ps.sale_datetime DESC,ps.id DESC LIMIT 5000""",params)]
            summary=dict(conn.execute(f"""SELECT COUNT(*) invoice_count,COALESCE(SUM(total_amount),0) total_amount,COALESCE(SUM(total_paid),0) total_paid,
                COALESCE(SUM(sell_due),0) sell_due,COALESCE(SUM(sell_return_due),0) return_due,COALESCE(SUM(total_items),0) total_items,
                COUNT(DISTINCT CASE WHEN contact_number<>'' THEN contact_number ELSE lower(customer_name) END) customer_count FROM pos_sales ps {where}""",params).fetchone())
        self.send_json({"ok":True,"sales":rows,"summary":summary,"filters":filters,"can_import":self.has_permission(user,"finance_write")})

    def handle_pos_sale_delete(self, user: dict[str, Any], sale_id: int) -> None:
        if not self.require_permission(user, "finance_write"):
            return
        with db_connect() as conn:
            row = conn.execute("SELECT * FROM pos_sales WHERE id=?", (sale_id,)).fetchone()
            if not row:
                self.send_error_json("Sales record not found", 404)
                return
            if not self.validate_branch_write(user, row["branch"]):
                return
            finance_deleted = False
            finance_id = row["finance_entry_id"]
            conn.execute("DELETE FROM pos_sales WHERE id=?", (sale_id,))
            if finance_id:
                finance = conn.execute("SELECT * FROM finance_entries WHERE id=?", (finance_id,)).fetchone()
                if finance and finance["reference"] == row["invoice_no"]:
                    conn.execute("DELETE FROM finance_entries WHERE id=?", (finance_id,))
                    finance_deleted = True
            log_audit(
                conn, user, "DELETE", "Sales Record", sale_id,
                f"Invoice {row['invoice_no']} | {row['branch']} | OMR {float(row['total_amount']):.3f} | linked finance deleted={finance_deleted}",
            )
        self.send_json({"ok": True, "finance_deleted": finance_deleted})

    def handle_pos_import_batches(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user,"finance_read"):
            return
        with db_connect() as conn:
            if user.get("branch") == "All":
                rows=[dict(r) for r in conn.execute("SELECT * FROM pos_import_batches ORDER BY id DESC LIMIT 50")]
            else:
                rows=[dict(r) for r in conn.execute("""SELECT DISTINCT b.* FROM pos_import_batches b
                    JOIN pos_sales ps ON ps.import_batch_id=b.id WHERE ps.branch=? ORDER BY b.id DESC LIMIT 50""",(user["branch"],))]
        self.send_json({"ok":True,"imports":rows})

    def handle_export_pos_sales(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user,"finance_read"):
            return
        where,params,_=self.pos_sales_filters(user)
        with db_connect() as conn:
            rows=conn.execute(f"SELECT * FROM pos_sales ps {where} ORDER BY sale_datetime DESC,id DESC",params).fetchall()
        out=[[r["sale_datetime"],r["invoice_no"],r["branch"],r["customer_name"],r["contact_number"],r["location"],r["payment_status"],r["payment_method"],r["total_amount"],r["total_paid"],r["sell_due"],r["sell_return_due"],r["total_items"],r["added_by"],r["sell_note"],r["staff_note"],r["shipping_status"],r["shipping_details"],r["source_file"]] for r in rows]
        currency = self.report_currency()
        headers=["Date & Time","Invoice No.","Branch","Customer","Contact Number","Location","Payment Status","Payment Method",f"Total Amount ({currency})",f"Total Paid ({currency})",f"Sell Due ({currency})",f"Return Due ({currency})","Total Items","Added By","Sell Note","Staff Note","Shipping Status","Shipping Details","Source File"]
        self.send_csv(self.export_filename("sales_record", "csv"),headers,out)

    def handle_finance_list(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user,"finance_read"):return
        q=self.query();branch=self.allowed_branch(user,q.get("branch",["All"])[0]);default_start,default_end=current_month_range();start=q.get("start",[default_start])[0] or default_start;end=q.get("end",[default_end])[0] or default_end
        sql="SELECT * FROM finance_entries WHERE date BETWEEN ? AND ?";params:[Any]=[start,end]
        if branch!="All":sql+=" AND branch=?";params.append(branch)
        sql+=" ORDER BY date DESC,id DESC"
        with db_connect() as conn:rows=[dict(r) for r in conn.execute(sql,params)]
        self.send_json({"ok":True,"entries":rows,"can_write":self.has_permission(user,"finance_write")})

    def validate_finance_data(self,data:dict[str,Any],existing:sqlite3.Row|None=None)->tuple:
        def val(k,default=""):return data.get(k,existing[k] if existing else default)
        date=str(val("date"));branch=str(val("branch"));typ=str(val("type"));category=str(val("category"));description=str(val("description"));amount=float(val("amount",0));payment=str(val("payment_method","Other"));reference=str(val("reference",""))
        if not all((date,branch,typ,category,description)):raise ValueError("All required financial fields must be completed")
        if typ not in ("Income","Expense"):raise ValueError("Type must be Income or Expense")
        if amount<=0:raise ValueError("Amount must be greater than zero")
        return date,branch,typ,category,description,amount,payment,reference

    def handle_finance_create(self,user:dict[str,Any])->None:
        if not self.require_permission(user,"finance_write"):return
        values=self.validate_finance_data(self.parse_json())
        if not self.validate_branch_write(user,values[1]):return
        with db_connect() as conn:
            cur=conn.execute("""INSERT INTO finance_entries(date,branch,type,category,description,amount,payment_method,reference,entered_by,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",(*values,user["full_name"],now_iso(),now_iso()))
            log_audit(conn,user,"CREATE","Finance",cur.lastrowid,f"{values[2]} | {values[1]} | OMR {values[5]:.3f}")
        self.send_json({"ok":True,"id":cur.lastrowid},201)

    def handle_finance_update(self,user:dict[str,Any],entry_id:int)->None:
        if not self.require_permission(user,"finance_write"):return
        data=self.parse_json()
        with db_connect() as conn:
            existing=conn.execute("SELECT * FROM finance_entries WHERE id=?",(entry_id,)).fetchone()
            if not existing:self.send_error_json("Financial entry not found",404);return
            values=self.validate_finance_data(data,existing)
            if not self.validate_branch_write(user,values[1]):return
            conn.execute("""UPDATE finance_entries SET date=?,branch=?,type=?,category=?,description=?,amount=?,payment_method=?,reference=?,updated_at=? WHERE id=?""",(*values,now_iso(),entry_id))
            log_audit(conn,user,"UPDATE","Finance",entry_id,f"{values[2]} | {values[1]} | OMR {values[5]:.3f}")
        self.send_json({"ok":True})

    def handle_finance_delete(self,user:dict[str,Any],entry_id:int)->None:
        if not self.require_permission(user,"finance_write"):return
        with db_connect() as conn:
            row=conn.execute("SELECT * FROM finance_entries WHERE id=?",(entry_id,)).fetchone()
            if not row:self.send_error_json("Financial entry not found",404);return
            if not self.validate_branch_write(user,row["branch"]):return
            conn.execute("DELETE FROM finance_entries WHERE id=?",(entry_id,))
            log_audit(conn,user,"DELETE","Finance",entry_id,f"{row['type']} | {row['branch']} | OMR {row['amount']:.3f}")
        self.send_json({"ok":True})


    def notification_branches(self, user: dict[str, Any], requested: str) -> tuple[str, list[str]]:
        branch = self.allowed_branch(user, requested or "All")
        with db_connect() as conn:
            available = [r["name"] for r in conn.execute("SELECT name FROM branches WHERE active=1 ORDER BY id")]
        if user.get("branch") != "All":
            branch = user["branch"]
        if branch != "All" and branch not in available:
            raise ValueError("Invalid branch")
        return branch, available if branch == "All" else [branch]

    def notification_setting(self, conn: sqlite3.Connection, branch: str) -> dict[str, Any]:
        row = conn.execute("SELECT * FROM notification_settings WHERE branch=?", (branch,)).fetchone()
        if not row:
            conn.execute(
                """INSERT INTO notification_settings(branch,membership_expiry_days,low_production_percent,
                attendance_reminder_hour,production_reminder_hour,payroll_reminder_day,
                income_lag_tolerance_percent,updated_by,updated_at) VALUES (?,?,?,?,?,?,?,?,?)""",
                (branch,30,80,18,18,25,5,"System",now_iso()),
            )
            row = conn.execute("SELECT * FROM notification_settings WHERE branch=?", (branch,)).fetchone()
        return dict(row)

    def build_notifications(self, user: dict[str, Any], requested_branch: str = "All") -> dict[str, Any]:
        branch, branches = self.notification_branches(user, requested_branch)
        today_dt = datetime.now()
        today = today_dt.strftime("%Y-%m-%d")
        month = today_dt.strftime("%Y-%m")
        start = f"{month}-01"
        days_in_month = calendar.monthrange(today_dt.year, today_dt.month)[1]
        elapsed_days = max(1, today_dt.day)
        end = today
        alerts: list[dict[str, Any]] = []
        severity_rank = {"critical": 0, "warning": 1, "info": 2, "success": 3}

        def add_alert(kind: str, severity: str, title: str, message: str, alert_branch: str,
                      target_page: str, suffix: str, metric: float | int | str = "") -> None:
            key = f"{kind}:{alert_branch}:{suffix}"
            alerts.append({
                "key": key, "type": kind, "severity": severity, "title": title,
                "message": message, "branch": alert_branch, "target_page": target_page,
                "metric": metric, "created_label": today,
            })

        with db_connect() as conn:
            settings_map = {b: self.notification_setting(conn, b) for b in branches}
            selected_setting = self.notification_setting(conn, branch)
            ph = ",".join("?" for _ in branches)

            # Daily management summary. Financial values are hidden from non-financial roles.
            daily = {
                "date": today, "branch": branch, "income": None, "expenses": None,
                "ready_pcs": 0, "new_orders": 0, "delivered_orders": 0,
                "present": 0, "absent": 0, "active_employees": 0,
            }
            if self.has_permission(user, "finance_read"):
                row = conn.execute(
                    f"""SELECT COALESCE(SUM(CASE WHEN type='Income' THEN amount ELSE 0 END),0) income,
                    COALESCE(SUM(CASE WHEN type='Expense' THEN amount ELSE 0 END),0) expenses
                    FROM finance_entries WHERE date=? AND branch IN ({ph})""", [today, *branches]
                ).fetchone()
                daily["income"], daily["expenses"] = round(row["income"],3), round(row["expenses"],3)
            if self.has_permission(user, "production_read"):
                prod_daily=list(conn.execute(
                    f"""SELECT employee_id,
                    SUM(CASE WHEN activity='Body' THEN quantity ELSE 0 END) body,
                    SUM(CASE WHEN activity='Joint/Side' THEN quantity ELSE 0 END) joint_side,
                    SUM(CASE WHEN activity NOT IN ('Body','Joint/Side') THEN quantity ELSE 0 END) other_qty
                    FROM production_entries WHERE date=? AND branch IN ({ph}) GROUP BY employee_id""",
                    [today, *branches]))
                daily["ready_pcs"] = round(sum(min(float(r["body"] or 0),float(r["joint_side"] or 0))+float(r["other_qty"] or 0) for r in prod_daily),3)
            if self.has_permission(user, "orders_read"):
                daily["new_orders"] = conn.execute(
                    f"SELECT COUNT(*) c FROM customer_orders WHERE booking_date=? AND branch IN ({ph})",
                    [today, *branches]).fetchone()["c"]
                daily["delivered_orders"] = conn.execute(
                    f"""SELECT COUNT(*) c FROM customer_orders WHERE branch IN ({ph}) AND
                    (substr(COALESCE(delivered_at,''),1,10)=? OR (status='Delivered' AND substr(updated_at,1,10)=?))""",
                    [*branches, today, today]).fetchone()["c"]
            if self.has_permission(user, "attendance_read"):
                att = conn.execute(
                    f"""SELECT COALESCE(SUM(CASE WHEN status='Present' THEN 1 ELSE 0 END),0) present,
                    COALESCE(SUM(CASE WHEN status='Absent' THEN 1 ELSE 0 END),0) absent
                    FROM attendance_records WHERE date=? AND branch IN ({ph})""", [today, *branches]
                ).fetchone()
                daily["present"], daily["absent"] = att["present"], att["absent"]
            daily["active_employees"] = conn.execute(
                f"SELECT COUNT(*) c FROM employees WHERE active=1 AND branch IN ({ph})", branches
            ).fetchone()["c"]

            for b in branches:
                cfg = settings_map[b]
                # Orders and delivery alerts.
                if self.has_permission(user, "orders_read") and cfg["order_alerts"]:
                    overdue = conn.execute("""SELECT COUNT(*) c FROM customer_orders
                        WHERE branch=? AND status NOT IN ('Delivered','Cancelled') AND due_date<?""", (b,today)).fetchone()["c"]
                    due_today = conn.execute("""SELECT COUNT(*) c FROM customer_orders
                        WHERE branch=? AND status NOT IN ('Delivered','Cancelled') AND due_date=?""", (b,today)).fetchone()["c"]
                    ready = conn.execute("SELECT COUNT(*) c FROM customer_orders WHERE branch=? AND status='Ready'", (b,)).fetchone()["c"]
                    if overdue:
                        add_alert("orders_overdue","critical",f"{overdue} overdue order{'s' if overdue!=1 else ''}",
                                  "Promised delivery date has passed. Immediate customer and workshop follow-up is required.",b,"orders",f"{today}:{overdue}",overdue)
                    if due_today:
                        add_alert("orders_due_today","warning",f"{due_today} order{'s' if due_today!=1 else ''} due today",
                                  "Review production status and confirm delivery readiness.",b,"orders",f"{today}:{due_today}",due_today)
                    if ready:
                        add_alert("orders_ready","info",f"{ready} ready order{'s' if ready!=1 else ''} awaiting delivery",
                                  "Contact customers and complete delivery to reduce pending inventory.",b,"orders",f"{today}:{ready}",ready)

                # Membership expiry alerts.
                if self.has_permission(user, "membership_read") and cfg["membership_alerts"]:
                    expiry_end = (today_dt + timedelta(days=int(cfg["membership_expiry_days"]))).strftime("%Y-%m-%d")
                    expiring = conn.execute("""SELECT COUNT(*) c FROM membership_cards
                        WHERE branch=? AND status='Active' AND expiry_date BETWEEN ? AND ?""", (b,today,expiry_end)).fetchone()["c"]
                    if expiring:
                        add_alert("membership_expiry","warning",f"{expiring} membership card{'s' if expiring!=1 else ''} expiring soon",
                                  f"Expiry is within {cfg['membership_expiry_days']} days. Contact customers for renewal.",b,"membership",f"{today}:{cfg['membership_expiry_days']}:{expiring}",expiring)

                # Attendance and production completeness alerts (Friday is weekly holiday).
                if today_dt.weekday() != 4 and self.has_permission(user, "attendance_read") and cfg["attendance_alerts"] and today_dt.hour >= int(cfg["attendance_reminder_hour"]):
                    missing = conn.execute("""SELECT COUNT(*) c FROM employees e WHERE e.active=1 AND e.branch=?
                        AND NOT EXISTS(SELECT 1 FROM attendance_records a WHERE a.employee_id=e.id AND a.date=?)""", (b,today)).fetchone()["c"]
                    if missing:
                        add_alert("attendance_missing","warning",f"Attendance missing for {missing} employee{'s' if missing!=1 else ''}",
                                  "Complete today's attendance register before closing the branch.",b,"payroll",f"{today}:{missing}",missing)

                if today_dt.weekday() != 4 and self.has_permission(user, "production_read") and cfg["production_alerts"] and today_dt.hour >= int(cfg["production_reminder_hour"]):
                    missing_prod = conn.execute("""SELECT COUNT(*) c FROM employees e WHERE e.active=1 AND e.branch=?
                        AND EXISTS(SELECT 1 FROM employee_skills s WHERE s.employee_id=e.id)
                        AND NOT EXISTS(SELECT 1 FROM production_entries p WHERE p.employee_id=e.id AND p.date=?)""", (b,today)).fetchone()["c"]
                    if missing_prod:
                        add_alert("production_missing","warning",f"Production entry missing for {missing_prod} employee{'s' if missing_prod!=1 else ''}",
                                  "Workshop production has not been recorded for all active production employees.",b,"production",f"{today}:{missing_prod}",missing_prod)

                    low_rows = list(conn.execute("""SELECT e.id,e.name,e.monthly_target,COALESCE(SUM(p.quantity),0) actual
                        FROM employees e JOIN employee_skills es ON es.employee_id=e.id
                        LEFT JOIN production_entries p ON p.employee_id=e.id AND p.date BETWEEN ? AND ?
                        WHERE e.active=1 AND e.branch=? AND e.monthly_target>0
                        GROUP BY e.id,e.name,e.monthly_target""", (start,today,b)))
                    low = []
                    for r in low_rows:
                        expected = float(r["monthly_target"]) * elapsed_days / days_in_month
                        performance = float(r["actual"] or 0) / expected * 100 if expected else 100
                        if performance < float(cfg["low_production_percent"]):
                            low.append((r["name"], performance))
                    if low and elapsed_days >= 3:
                        low.sort(key=lambda x:x[1])
                        names = ", ".join(f"{n} ({p:.0f}%)" for n,p in low[:3])
                        add_alert("production_low","warning",f"{len(low)} employee{'s' if len(low)!=1 else ''} below production pace",
                                  f"Below {cfg['low_production_percent']:.0f}% of prorated target: {names}.",b,"production",f"{month}:{len(low)}",len(low))

                # Payroll readiness alerts, shown from the configured day of month.
                if self.has_permission(user, "payroll_read") and cfg["payroll_alerts"] and today_dt.day >= int(cfg["payroll_reminder_day"]):
                    active = conn.execute("SELECT COUNT(*) c FROM employees WHERE active=1 AND branch=?", (b,)).fetchone()["c"]
                    saved = conn.execute("SELECT COUNT(*) c FROM payroll_records WHERE branch=? AND month_key=?", (b,month)).fetchone()["c"]
                    draft = conn.execute("SELECT COUNT(*) c FROM payroll_records WHERE branch=? AND month_key=? AND status='Draft'", (b,month)).fetchone()["c"]
                    approved = conn.execute("SELECT COUNT(*) c FROM payroll_records WHERE branch=? AND month_key=? AND status='Approved'", (b,month)).fetchone()["c"]
                    missing_payroll = max(0, active-saved)
                    if missing_payroll:
                        add_alert("payroll_missing","warning",f"Payroll not prepared for {missing_payroll} employee{'s' if missing_payroll!=1 else ''}",
                                  "Create or update monthly payroll records before salary processing.",b,"payroll",f"{month}:{missing_payroll}",missing_payroll)
                    if draft:
                        add_alert("payroll_draft","warning",f"{draft} payroll record{'s' if draft!=1 else ''} awaiting approval",
                                  "Review commission, bonus, overtime and deductions.",b,"payroll",f"{month}:draft:{draft}",draft)
                    if approved:
                        add_alert("payroll_payment","info",f"{approved} approved salary record{'s' if approved!=1 else ''} pending payment",
                                  "Mark payroll as Paid after salary transfer is completed.",b,"payroll",f"{month}:approved:{approved}",approved)

                # CFO budget, target and profitability alerts.
                if self.has_permission(user, "budget_read") and cfg["budget_alerts"]:
                    plan = conn.execute("SELECT * FROM budget_plans WHERE month_key=? AND branch=?", (month,b)).fetchone()
                    if plan:
                        budget_rows = list(conn.execute("""SELECT ec.name,bi.budget_amount,bi.warning_percent,
                            COALESCE((SELECT SUM(fe.amount) FROM finance_entries fe WHERE fe.branch=? AND fe.type='Expense'
                            AND lower(trim(fe.category))=lower(trim(ec.name)) AND fe.date BETWEEN ? AND ?),0) actual
                            FROM budget_items bi JOIN expense_categories ec ON ec.id=bi.category_id WHERE bi.plan_id=?""", (b,start,end,plan["id"])))
                        for r in budget_rows:
                            budget_amount=float(r["budget_amount"] or 0); actual=float(r["actual"] or 0)
                            used=actual/budget_amount*100 if budget_amount>0 else (100 if actual>0 else 0)
                            if actual>0 and budget_amount<=0:
                                add_alert("budget_no_limit","critical",f"{r['name']} has expenses without a budget",
                                          f"Actual expense is OMR {actual:.3f}. Set or revise the monthly category limit.",b,"budget",f"{month}:{r['name']}:no-budget",round(actual,3))
                            elif used>100:
                                add_alert("budget_over","critical",f"{r['name']} is over budget",
                                          f"OMR {actual:.3f} spent against OMR {budget_amount:.3f} budget ({used:.1f}%).",b,"budget",f"{month}:{r['name']}:{int(used)}",round(used,1))
                            elif used>=float(r["warning_percent"] or 80):
                                add_alert("budget_warning","warning",f"{r['name']} reached {used:.1f}% of budget",
                                          f"OMR {budget_amount-actual:.3f} remains in this category.",b,"budget",f"{month}:{r['name']}:{int(used)}",round(used,1))

                        tgt = conn.execute("SELECT * FROM income_targets WHERE plan_id=?", (plan["id"],)).fetchone()
                        if tgt and self.has_permission(user,"finance_read"):
                            total_target=float(tgt["shop_sales_target"] or 0)+float(tgt["membership_target"] or 0)+float(tgt["other_income_target"] or 0)
                            fin=conn.execute("""SELECT COALESCE(SUM(CASE WHEN type='Income' THEN amount ELSE 0 END),0) income,
                                COALESCE(SUM(CASE WHEN type='Expense' THEN amount ELSE 0 END),0) expense
                                FROM finance_entries WHERE branch=? AND date BETWEEN ? AND ?""", (b,start,today)).fetchone()
                            income=float(fin["income"] or 0); expense=float(fin["expense"] or 0)
                            expected_pct=elapsed_days/days_in_month*100
                            achieved=income/total_target*100 if total_target else 0
                            tolerance=float(cfg["income_lag_tolerance_percent"] or 5)
                            if total_target>0 and achieved+tolerance<expected_pct:
                                add_alert("income_behind","warning","Income target is behind schedule",
                                          f"Achievement is {achieved:.1f}% versus {expected_pct:.1f}% month elapsed.",b,"budget",f"{month}:{int(achieved)}:{int(expected_pct)}",round(achieved,1))
                            margin=(income-expense)/income*100 if income else 0
                            if income>0 and margin<float(tgt["min_profit_margin"] or 20):
                                add_alert("profit_margin","critical","Profit margin is below target",
                                          f"Current margin is {margin:.1f}% versus {float(tgt['min_profit_margin']):.1f}% target.",b,"budget",f"{month}:{int(margin)}",round(margin,1))

            read_keys = {r["alert_key"] for r in conn.execute("SELECT alert_key FROM notification_reads WHERE user_id=?", (user["id"],))}

        for alert in alerts:
            alert["read"] = alert["key"] in read_keys
        alerts.sort(key=lambda a:(a["read"], severity_rank.get(a["severity"],9), a["branch"], a["title"]))
        summary = {
            "total": len(alerts), "unread": sum(1 for a in alerts if not a["read"]),
            "critical": sum(1 for a in alerts if a["severity"]=="critical"),
            "warning": sum(1 for a in alerts if a["severity"]=="warning"),
            "info": sum(1 for a in alerts if a["severity"]=="info"),
        }
        return {"ok": True, "branch": branch, "date": today, "alerts": alerts, "summary": summary,
                "daily": daily, "settings": selected_setting, "can_manage": self.has_permission(user,"alert_manage")}

    def handle_notifications(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "alert_read"):
            return
        q=self.query(); branch=q.get("branch",["All"])[0]
        self.send_json(self.build_notifications(user, branch))

    def handle_notification_read(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "alert_read"):
            return
        data=self.parse_json(); keys=data.get("keys",[])
        if isinstance(keys,str): keys=[keys]
        if data.get("all"):
            branch=str(data.get("branch","All")); keys=[a["key"] for a in self.build_notifications(user,branch)["alerts"]]
        keys=[str(k)[:300] for k in keys if k]
        with db_connect() as conn:
            conn.executemany("INSERT OR REPLACE INTO notification_reads(user_id,alert_key,read_at) VALUES (?,?,?)",
                             [(user["id"],k,now_iso()) for k in keys])
        self.send_json({"ok":True,"marked":len(keys)})

    def handle_notification_settings_save(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "alert_manage"):
            return
        data=self.parse_json(); branch=str(data.get("branch","All"))
        allowed={"All","Al Khoud","Azaiba","Nizwa"}
        if branch not in allowed: raise ValueError("Invalid branch")
        values={
            "membership_expiry_days":max(1,min(365,int(data.get("membership_expiry_days",30)))),
            "low_production_percent":max(1,min(100,float(data.get("low_production_percent",80)))),
            "attendance_reminder_hour":max(0,min(23,int(data.get("attendance_reminder_hour",18)))),
            "production_reminder_hour":max(0,min(23,int(data.get("production_reminder_hour",18)))),
            "payroll_reminder_day":max(1,min(31,int(data.get("payroll_reminder_day",25)))),
            "income_lag_tolerance_percent":max(0,min(50,float(data.get("income_lag_tolerance_percent",5)))),
        }
        flags={k:int(bool(data.get(k,True))) for k in ("order_alerts","budget_alerts","membership_alerts","attendance_alerts","production_alerts","payroll_alerts")}
        with db_connect() as conn:
            targets = [branch]
            if branch == "All":
                targets = ["All"] + [r["name"] for r in conn.execute("SELECT name FROM branches WHERE active=1 ORDER BY id")]
            for target_branch in targets:
                self.notification_setting(conn,target_branch)
                conn.execute("""UPDATE notification_settings SET membership_expiry_days=?,low_production_percent=?,
                    attendance_reminder_hour=?,production_reminder_hour=?,payroll_reminder_day=?,income_lag_tolerance_percent=?,
                    order_alerts=?,budget_alerts=?,membership_alerts=?,attendance_alerts=?,production_alerts=?,payroll_alerts=?,
                    updated_by=?,updated_at=? WHERE branch=?""",
                    (values["membership_expiry_days"],values["low_production_percent"],values["attendance_reminder_hour"],
                     values["production_reminder_hour"],values["payroll_reminder_day"],values["income_lag_tolerance_percent"],
                     flags["order_alerts"],flags["budget_alerts"],flags["membership_alerts"],flags["attendance_alerts"],
                     flags["production_alerts"],flags["payroll_alerts"],user["full_name"],now_iso(),target_branch))
            log_audit(conn,user,"UPDATE","Alerts",branch,"Updated notification thresholds and module alert settings")
        self.send_json({"ok":True})

    def handle_export_notifications(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user,"alert_read"):
            return
        q=self.query(); branch=q.get("branch",["All"])[0]
        data=self.build_notifications(user,branch)
        self.send_csv(self.export_filename("management_alerts", "csv"),
                      ["Severity","Type","Branch","Title","Message","Metric","Read","Date"],
                      [[a["severity"],a["type"],a["branch"],a["title"],a["message"],a["metric"],"Yes" if a["read"] else "No",a["created_label"]] for a in data["alerts"]])

    def handle_audit(self,user:dict[str,Any])->None:
        if not self.require_permission(user,"audit"):return
        q=self.query();limit=min(500,max(1,int(q.get("limit",["200"])[0])))
        with db_connect() as conn:rows=[dict(r) for r in conn.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?",(limit,))]
        self.send_json({"ok":True,"logs":rows})

    def handle_users(self,user:dict[str,Any])->None:
        if not self.require_permission(user,"users"):return
        with db_connect() as conn:
            rows=[dict(r) for r in conn.execute("SELECT id,username,full_name,role,branch,active,language,created_at FROM users ORDER BY id")]
            roles=[dict(r) for r in conn.execute("SELECT id,name,description,active,created_at,updated_at FROM roles ORDER BY name")]
            for role in roles:
                role["permissions"]=[r["permission"] for r in conn.execute("SELECT permission FROM role_permissions WHERE role_id=? ORDER BY permission",(role["id"],))]
        catalog=[{"key":key,"group":value[0],"label":value[1],"description":value[2]} for key,value in PERMISSION_CATALOG.items()]
        self.send_json({"ok":True,"users":rows,"roles":[r["name"] for r in roles if r["active"]],"role_details":roles,"permission_catalog":catalog})

    def handle_roles(self,user:dict[str,Any])->None:
        if not self.require_permission(user,"users"):return
        with db_connect() as conn:
            roles=[dict(r) for r in conn.execute("SELECT id,name,description,active,created_at,updated_at FROM roles ORDER BY name")]
            for role in roles:
                role["permissions"]=[r["permission"] for r in conn.execute("SELECT permission FROM role_permissions WHERE role_id=? ORDER BY permission",(role["id"],))]
        catalog=[{"key":key,"group":value[0],"label":value[1],"description":value[2]} for key,value in PERMISSION_CATALOG.items()]
        self.send_json({"ok":True,"roles":roles,"permission_catalog":catalog})

    def validate_role_payload(self,data:dict[str,Any],existing:sqlite3.Row|None=None)->tuple[str,str,int,list[str]]:
        name=str(data.get("name",existing["name"] if existing else "")).strip()
        description=str(data.get("description",existing["description"] if existing else "")).strip()
        active=int(bool(data.get("active",existing["active"] if existing else True)))
        permissions=data.get("permissions") or []
        if not name: raise ValueError("Role name is required")
        if not isinstance(permissions,list): raise ValueError("Permissions must be a list")
        invalid=[x for x in permissions if x not in PERMISSION_CATALOG]
        if invalid: raise ValueError("Invalid permissions: "+", ".join(invalid))
        return name,description,active,sorted(set(permissions))

    def handle_role_create(self,user:dict[str,Any])->None:
        if not self.require_permission(user,"users"):return
        name,description,active,permissions=self.validate_role_payload(self.parse_json())
        with db_connect() as conn:
            cur=conn.execute("INSERT INTO roles(name,description,active,created_at,updated_at) VALUES (?,?,?,?,?)",(name,description,active,now_iso(),now_iso()))
            for permission in permissions:
                conn.execute("INSERT INTO role_permissions(role_id,permission) VALUES (?,?)",(cur.lastrowid,permission))
            log_audit(conn,user,"CREATE","Roles",cur.lastrowid,f"Created role {name} with {len(permissions)} permissions")
        self.send_json({"ok":True,"id":cur.lastrowid},201)

    def handle_role_update(self,user:dict[str,Any],role_id:int)->None:
        if not self.require_permission(user,"users"):return
        data=self.parse_json()
        with db_connect() as conn:
            existing=conn.execute("SELECT * FROM roles WHERE id=?",(role_id,)).fetchone()
            if not existing:self.send_error_json("Role not found",404);return
            name,description,active,permissions=self.validate_role_payload(data,existing)
            if existing["name"] in ("Owner","Administrator") and not active:
                raise ValueError("Owner and Administrator roles cannot be deactivated")
            if name!=existing["name"]:
                if existing["name"] in ("Owner","Administrator"):
                    raise ValueError("Core role names cannot be changed")
                conn.execute("UPDATE users SET role=? WHERE role=?",(name,existing["name"]))
            conn.execute("UPDATE roles SET name=?,description=?,active=?,updated_at=? WHERE id=?",(name,description,active,now_iso(),role_id))
            conn.execute("DELETE FROM role_permissions WHERE role_id=?",(role_id,))
            for permission in permissions:
                conn.execute("INSERT INTO role_permissions(role_id,permission) VALUES (?,?)",(role_id,permission))
            log_audit(conn,user,"UPDATE","Roles",role_id,f"Updated role {name} with {len(permissions)} permissions")
        self.send_json({"ok":True})

    def handle_user_create(self,user:dict[str,Any])->None:
        if not self.require_permission(user,"users"):return
        data=self.parse_json();username=str(data.get("username","")).strip().lower();full_name=str(data.get("full_name","")).strip();password=str(data.get("password",""));role=str(data.get("role","Viewer"));branch=str(data.get("branch","All"));language=normalize_language(data.get("language"))
        if not username or not full_name or len(password)<8:raise ValueError("Username, full name and password of at least 8 characters are required")
        with db_connect() as conn:
            role_row=conn.execute("SELECT * FROM roles WHERE name=? AND active=1",(role,)).fetchone()
            if not role_row:raise ValueError("Invalid or inactive role")
            salt,digest=hash_password(password)
            cur=conn.execute("INSERT INTO users(username,full_name,password_hash,salt,role,branch,language,created_at) VALUES (?,?,?,?,?,?,?,?)",(username,full_name,digest,salt,role,branch,language,now_iso()))
            log_audit(conn,user,"CREATE","Users",cur.lastrowid,f"Created {username} as {role}")
        self.send_json({"ok":True,"id":cur.lastrowid},201)

    def handle_user_update(self,user:dict[str,Any],user_id:int)->None:
        if not self.require_permission(user,"users"):return
        data=self.parse_json()
        with db_connect() as conn:
            existing=conn.execute("SELECT * FROM users WHERE id=?",(user_id,)).fetchone()
            if not existing:self.send_error_json("User not found",404);return
            full_name=str(data.get("full_name",existing["full_name"]));role=str(data.get("role",existing["role"]));branch=str(data.get("branch",existing["branch"]));active=int(bool(data.get("active",existing["active"])));language=normalize_language(data.get("language",existing["language"]))
            role_row=conn.execute("SELECT * FROM roles WHERE name=? AND active=1",(role,)).fetchone()
            if not role_row:raise ValueError("Invalid or inactive role")
            if user_id==user["id"] and not active:raise ValueError("You cannot deactivate your own account")
            conn.execute("UPDATE users SET full_name=?,role=?,branch=?,active=?,language=? WHERE id=?",(full_name,role,branch,active,language,user_id))
            if data.get("password"):
                password=str(data["password"])
                if len(password)<8:raise ValueError("Password must have at least 8 characters")
                salt,digest=hash_password(password);conn.execute("UPDATE users SET password_hash=?,salt=? WHERE id=?",(digest,salt,user_id))
            log_audit(conn,user,"UPDATE","Users",user_id,f"Updated {existing['username']} | {role} | active={active}")
        self.send_json({"ok":True})

    def report_currency(self) -> str:
        with db_connect() as conn:
            profile = get_company_profile(conn)
        return str(profile.get("currency_label") or DEFAULT_COMPANY_PROFILE["currency_label"]).strip() or DEFAULT_COMPANY_PROFILE["currency_label"]

    def export_filename(self, stem: str, ext: str, profile: dict[str, Any] | None = None) -> str:
        if profile is None:
            with db_connect() as conn:
                profile = get_company_profile(conn)
        return f"{profile_slug(profile)}_{stem}.{ext}"

    def report_logo(self, conn: sqlite3.Connection) -> dict[str, Any] | None:
        data_b64 = get_setting(conn, "company_logo_data", "")
        mime = get_setting(conn, "company_logo_mime", "")
        if not data_b64 or not mime:
            return None
        try:
            raw = base64.b64decode(data_b64)
        except Exception:
            return None
        return parse_report_image(raw, mime)

    def send_report_pdf(self, stem: str, title: str, branch: str, period: str, headers: list[str],
                        rows: list[list[Any]], widths: list[float] | None = None,
                        aligns: list[str] | None = None, totals: list[list[Any]] | None = None,
                        summary: list[tuple[str, str]] | None = None) -> None:
        with db_connect() as conn:
            profile = get_company_profile(conn)
            logo = self.report_logo(conn)
        pdf = PdfReportDocument(title, profile, branch, period, logo)
        pdf.add_summary(summary or [])
        pdf.add_table(headers, rows, widths=widths, aligns=aligns, totals=totals)
        self.send_attachment(self.export_filename(stem, "pdf", profile), "application/pdf", pdf.build())

    def handle_export_finance_pdf(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "finance_read"):
            return
        q = self.query()
        branch = self.allowed_branch(user, q.get("branch", ["All"])[0])
        default_start, default_end = current_month_range()
        start = q.get("start", [default_start])[0] or default_start
        end = q.get("end", [default_end])[0] or default_end
        sql = "SELECT * FROM finance_entries WHERE date BETWEEN ? AND ?"
        params: list[Any] = [start, end]
        if branch != "All":
            sql += " AND branch=?"; params.append(branch)
        sql += " ORDER BY date,id"
        with db_connect() as conn:
            rs = list(conn.execute(sql, params))
            currency = get_company_profile(conn)["currency_label"]
        rows = [[r["date"], r["branch"], r["type"], r["category"], r["description"], r["payment_method"], r["reference"], format_report_money(r["amount"], currency)] for r in rs]
        income = sum(float(r["amount"] or 0) for r in rs if r["type"] == "Income")
        expense = sum(float(r["amount"] or 0) for r in rs if r["type"] == "Expense")
        totals = [
            ["", "", "", "", "", "", "Income", format_report_money(income, currency)],
            ["", "", "", "", "", "", "Expenses", format_report_money(expense, currency)],
            ["", "", "", "", "", "", "Net Position", format_report_money(income - expense, currency)],
        ]
        self.send_report_pdf(
            f"financial_entries_{start}_to_{end}", "Financial Report", branch, date_range_label(start, end),
            ["Date", "Branch", "Type", "Category", "Description", "Payment", "Reference", f"Amount ({currency})"],
            rows, widths=[0.9, 1.0, 0.8, 1.0, 2.0, 1.0, 1.1, 1.1],
            aligns=["left", "left", "left", "left", "left", "left", "left", "right"], totals=totals,
            summary=[("Transactions", str(len(rows))), ("Income", format_report_money(income, currency)),
                     ("Expenses", format_report_money(expense, currency)), ("Net Position", format_report_money(income - expense, currency))],
        )

    def handle_export_production_pdf(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "production_read"):
            return
        q = self.query()
        branch = self.allowed_branch(user, q.get("branch", ["All"])[0])
        default_start, default_end = current_month_range()
        start = q.get("start", [default_start])[0] or default_start
        end = q.get("end", [default_end])[0] or default_end
        where, params = self.production_filters(user)
        with db_connect() as conn:
            rs = list(conn.execute(f"SELECT p.*,e.name employee FROM production_entries p JOIN employees e ON e.id=p.employee_id {where} ORDER BY p.date,p.id", params))
        rows = [[r["date"], r["branch"], r["employee"], r["activity"], format_report_number(r["quantity"]), format_report_number(r["ready_pcs"]), format_report_number(r["ot_hours"]), r["notes"], r["entered_by"]] for r in rs]
        quantity = sum(float(r["quantity"] or 0) for r in rs)
        ready = sum(float(r["ready_pcs"] or 0) for r in rs)
        ot_hours = sum(float(r["ot_hours"] or 0) for r in rs)
        totals = [["", "", "Totals", "", format_report_number(quantity), format_report_number(ready), format_report_number(ot_hours), "", ""]]
        self.send_report_pdf(
            f"production_entries_{start}_to_{end}", "Production Report", branch, date_range_label(start, end),
            ["Date", "Branch", "Employee", "Activity", "Quantity", "Ready Pcs", "OT Hours", "Notes", "Entered By"],
            rows, widths=[0.9, 1.0, 1.3, 1.0, 0.8, 0.8, 0.7, 1.7, 1.0],
            aligns=["left", "left", "left", "left", "right", "right", "right", "left", "left"], totals=totals,
            summary=[("Entries", str(len(rows))), ("Quantity", format_report_number(quantity)),
                     ("Ready Pcs", format_report_number(ready)), ("OT Hours", format_report_number(ot_hours))],
        )

    def handle_export_orders_pdf(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "orders_read"):
            return
        q = self.query()
        branch = self.allowed_branch(user, q.get("branch", ["All"])[0])
        default_start, default_end = current_month_range()
        start = q.get("start", [default_start])[0] or default_start
        end = q.get("end", [default_end])[0] or default_end
        where, params = self.order_filters(user)
        with db_connect() as conn:
            rs = list(conn.execute(
                f"""SELECT o.*,e.name assigned_employee FROM customer_orders o
                LEFT JOIN employees e ON e.id=o.assigned_employee_id {where}
                ORDER BY o.booking_date,o.id""", params
            ))
            currency = get_company_profile(conn)["currency_label"]
        can_finance = self.has_permission(user, "finance_read")
        headers = ["Order", "Booking", "Due", "Customer", "Phone", "Branch", "Item / Qty", "Assigned", "Status"]
        widths = [0.9, 0.8, 0.8, 1.3, 0.9, 0.9, 1.1, 1.1, 1.0]
        aligns = ["left"] * len(headers)
        if can_finance:
            headers += [f"Total ({currency})", f"Advance ({currency})", f"Balance ({currency})"]
            widths += [0.9, 0.9, 0.9]
            aligns += ["right", "right", "right"]
        rows = []
        for r in rs:
            line = [r["order_no"], r["booking_date"], r["due_date"], r["customer_name"], r["phone"], r["branch"], f"{r['item_type']} x {r['quantity']}", r["assigned_employee"] or "Unassigned", r["status"]]
            if can_finance:
                line += [format_report_money(r["total_amount"], currency), format_report_money(r["advance_amount"], currency), format_report_money(float(r["total_amount"] or 0) - float(r["advance_amount"] or 0), currency)]
            rows.append(line)
        totals = []
        if can_finance:
            total = sum(float(r["total_amount"] or 0) for r in rs)
            advance = sum(float(r["advance_amount"] or 0) for r in rs)
            totals = [["", "", "", "", "", "", "Totals", "", "", format_report_money(total, currency), format_report_money(advance, currency), format_report_money(total - advance, currency)]]
        summary = [("Orders", str(len(rows))), ("Delivered", str(sum(1 for r in rs if r["status"] == "Delivered"))),
                   ("Pending", str(sum(1 for r in rs if r["status"] not in ("Delivered", "Cancelled"))))]
        if can_finance:
            summary.append(("Balance", format_report_money(sum(float(r["total_amount"] or 0) - float(r["advance_amount"] or 0) for r in rs), currency)))
        self.send_report_pdf(
            f"orders_{start}_to_{end}", "Orders Report", branch, date_range_label(start, end),
            headers, rows, widths=widths, aligns=aligns, totals=totals, summary=summary,
        )

    def handle_export_membership_pdf(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "membership_read"):
            return
        q = self.query()
        branch = self.allowed_branch(user, q.get("branch", ["All"])[0])
        status = q.get("status", ["All"])[0]
        where, params = self.membership_filters(user)
        with db_connect() as conn:
            rs = list(conn.execute(
                f"""SELECT mc.*,c.name customer_name,c.phone,mp.name plan_name,COALESCE(e.name,NULLIF(mc.sales_agent_name,'')) sales_agent_display
                FROM membership_cards mc JOIN customers c ON c.id=mc.customer_id
                JOIN membership_plans mp ON mp.id=mc.plan_id
                LEFT JOIN employees e ON e.id=mc.sales_agent_id {where}
                ORDER BY mc.issue_date,mc.id""", params
            ))
            currency = get_company_profile(conn)["currency_label"]
        headers = ["Card No", "Customer", "Phone", "Plan", "Branch", "Issue", "Expiry", "Status", f"Opening ({currency})", f"Current ({currency})", f"Sale ({currency})", "Sales Agent", f"Commission ({currency})"]
        rows = [[r["card_no"], r["customer_name"], r["phone"], r["plan_name"], r["branch"], r["issue_date"], r["expiry_date"], r["status"],
                 format_report_money(r["opening_balance"], currency), format_report_money(r["current_balance"], currency), format_report_money(r["sale_price"], currency),
                 r["sales_agent_display"] or "Direct sale", format_report_money(r["commission_amount"], currency)] for r in rs]
        totals = [["", "", "", "", "", "", "", "Totals", format_report_money(sum(float(r["opening_balance"] or 0) for r in rs), currency),
                   format_report_money(sum(float(r["current_balance"] or 0) for r in rs), currency), format_report_money(sum(float(r["sale_price"] or 0) for r in rs), currency),
                   "", format_report_money(sum(float(r["commission_amount"] or 0) for r in rs), currency)]]
        self.send_report_pdf(
            "membership_cards", "Customer / Member Report", branch, f"Status: {status}",
            headers, rows, widths=[0.9, 1.2, 0.8, 1.0, 0.8, 0.8, 0.8, 0.8, 0.9, 0.9, 0.9, 1.1, 0.9],
            aligns=["left", "left", "left", "left", "left", "left", "left", "left", "right", "right", "right", "left", "right"],
            totals=totals,
            summary=[("Cards", str(len(rows))), ("Active", str(sum(1 for r in rs if r["status"] == "Active"))),
                     ("Wallet Balance", format_report_money(sum(float(r["current_balance"] or 0) for r in rs), currency)),
                     ("Card Sales", format_report_money(sum(float(r["sale_price"] or 0) for r in rs), currency))],
        )

    def handle_export_membership_commissions_pdf(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "membership_read"):
            return
        where, params, branch, month = self.membership_commission_filters(user)
        with db_connect() as conn:
            rs = list(conn.execute(
                f"""SELECT COALESCE(e.name,NULLIF(mc.sales_agent_name,'')) sales_agent,
                COALESCE(e.role,'Manual Sales Agent') designation,mc.branch,COUNT(mc.id) cards_sold,
                COALESCE(SUM(mc.sale_price),0) total_sales,COALESCE(SUM(mc.commission_amount),0) total_commission
                FROM membership_cards mc LEFT JOIN employees e ON e.id=mc.sales_agent_id
                {where} AND TRIM(COALESCE(e.name,mc.sales_agent_name,''))<>''
                GROUP BY COALESCE(CAST(mc.sales_agent_id AS TEXT),'manual:'||lower(mc.sales_agent_name)),COALESCE(e.name,mc.sales_agent_name),COALESCE(e.role,'Manual Sales Agent'),mc.branch
                ORDER BY total_commission DESC,sales_agent""", params
            ))
            currency = get_company_profile(conn)["currency_label"]
        rows = [[month, r["branch"], r["sales_agent"], r["designation"], format_report_number(r["cards_sold"]), format_report_money(r["total_sales"], currency), format_report_money(r["total_commission"], currency)] for r in rs]
        total_sales = sum(float(r["total_sales"] or 0) for r in rs)
        total_commission = sum(float(r["total_commission"] or 0) for r in rs)
        totals = [["", "", "Totals", "", format_report_number(sum(int(r["cards_sold"] or 0) for r in rs)), format_report_money(total_sales, currency), format_report_money(total_commission, currency)]]
        self.send_report_pdf(
            f"card_commission_{month}", "Sales Agent Commission Report", branch, month_name(month),
            ["Month", "Branch", "Sales Agent", "Designation", "Cards Sold", f"Card Sales ({currency})", f"Commission ({currency})"],
            rows, widths=[0.8, 0.9, 1.4, 1.3, 0.8, 1.0, 1.0],
            aligns=["left", "left", "left", "left", "right", "right", "right"], totals=totals,
            summary=[("Agents", str(len(rows))), ("Cards Sold", format_report_number(sum(int(r["cards_sold"] or 0) for r in rs))),
                     ("Card Sales", format_report_money(total_sales, currency)), ("Commission", format_report_money(total_commission, currency))],
        )

    def handle_export_budget_pdf(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "budget_read"):
            return
        branch, month = self.budget_context(user)
        start, end, _, _ = self.budget_month_bounds(month)
        params: list[Any] = [month]
        branch_filter = ""
        if branch != "All":
            branch_filter = " AND bp.branch=?"; params.append(branch)
        with db_connect() as conn:
            rs = list(conn.execute(f"""SELECT bp.month_key,bp.branch,bp.status,ec.name category,bi.budget_amount,bi.warning_percent,bi.notes,
                COALESCE((SELECT SUM(fe.amount) FROM finance_entries fe WHERE fe.type='Expense' AND fe.branch=bp.branch AND lower(fe.category)=lower(ec.name) AND fe.date BETWEEN ? AND ?),0) actual
                FROM budget_plans bp JOIN budget_items bi ON bi.plan_id=bp.id JOIN expense_categories ec ON ec.id=bi.category_id
                WHERE bp.month_key=? {branch_filter} ORDER BY bp.branch,ec.name""", [start, end, *params]))
            currency = get_company_profile(conn)["currency_label"]
        rows = []
        for r in rs:
            budget = float(r["budget_amount"] or 0)
            actual = float(r["actual"] or 0)
            used = actual / budget * 100 if budget else (100 if actual else 0)
            rows.append([r["month_key"], r["branch"], r["status"], r["category"], format_report_money(budget, currency), format_report_money(actual, currency),
                         format_report_money(budget - actual, currency), f"{used:.1f}%", f"{float(r['warning_percent'] or 0):.0f}%", r["notes"]])
        total_budget = sum(float(r["budget_amount"] or 0) for r in rs)
        total_actual = sum(float(r["actual"] or 0) for r in rs)
        totals = [["", "", "", "Totals", format_report_money(total_budget, currency), format_report_money(total_actual, currency), format_report_money(total_budget - total_actual, currency), "", "", ""]]
        self.send_report_pdf(
            f"budget_vs_actual_{month}", "Budget Report", branch, month_name(month),
            ["Month", "Branch", "Status", "Category", f"Budget ({currency})", f"Actual ({currency})", f"Remaining ({currency})", "Used", "Warning", "Notes"],
            rows, widths=[0.8, 0.9, 0.8, 1.3, 1.0, 1.0, 1.0, 0.6, 0.6, 1.5],
            aligns=["left", "left", "left", "left", "right", "right", "right", "right", "right", "left"], totals=totals,
            summary=[("Categories", str(len(rows))), ("Budget", format_report_money(total_budget, currency)),
                     ("Actual", format_report_money(total_actual, currency)), ("Remaining", format_report_money(total_budget - total_actual, currency))],
        )

    def payroll_report_rows(self, user: dict[str, Any]) -> tuple[str, str, list[dict[str, Any]], dict[str, Any]]:
        branch, month = self.payroll_context(user)
        start, end = month_date_range(month)
        params: list[Any] = [month, start, end, start, end, start, end]
        branch_sql = ""
        if branch != "All":
            branch_sql = " AND e.branch=?"
            params.append(branch)
        sql = f"""
            SELECT e.id employee_id,e.name,e.role,e.branch,e.active,e.base_salary,
                   pr.id payroll_id,pr.basic_salary payroll_basic_salary,pr.commission,
                   pr.bonus,pr.overtime_hours,pr.overtime_amount,pr.other_allowance,
                   pr.advance_deduction,pr.other_deductions,pr.net_salary,pr.status,
                   pr.notes,pr.paid_at,
                   COALESCE(att.present_days,0) present_days,
                   COALESCE(att.absent_days,0) absent_days,
                   COALESCE(att.leave_days,0) leave_days,
                   COALESCE(att.half_days,0) half_days,
                   COALESCE(att.weekly_off_days,0) weekly_off_days,
                   COALESCE(prod.prod_ot_hours,0) production_ot_hours,
                   COALESCE(cards.card_commission,0) card_commission_auto
            FROM employees e
            LEFT JOIN payroll_records pr ON pr.employee_id=e.id AND pr.month_key=?
            LEFT JOIN (
                SELECT employee_id,
                  SUM(CASE WHEN status='Present' THEN 1 ELSE 0 END) present_days,
                  SUM(CASE WHEN status='Absent' THEN 1 ELSE 0 END) absent_days,
                  SUM(CASE WHEN status='Leave' THEN 1 ELSE 0 END) leave_days,
                  SUM(CASE WHEN status='Half Day' THEN 1 ELSE 0 END) half_days,
                  SUM(CASE WHEN status IN ('Weekly Off','Holiday') THEN 1 ELSE 0 END) weekly_off_days
                FROM attendance_records WHERE date BETWEEN ? AND ? GROUP BY employee_id
            ) att ON att.employee_id=e.id
            LEFT JOIN (
                SELECT employee_id,SUM(ot_hours) prod_ot_hours FROM production_entries
                WHERE date BETWEEN ? AND ? GROUP BY employee_id
            ) prod ON prod.employee_id=e.id
            LEFT JOIN (
                SELECT sales_agent_id employee_id,SUM(commission_amount) card_commission
                FROM membership_cards WHERE issue_date BETWEEN ? AND ? AND sales_agent_id IS NOT NULL
                GROUP BY sales_agent_id
            ) cards ON cards.employee_id=e.id
            WHERE (e.active=1 OR pr.id IS NOT NULL){branch_sql}
            ORDER BY e.branch,e.name
        """
        with db_connect() as conn:
            rows = [dict(r) for r in conn.execute(sql, params)]
        summary = {"employees": len(rows), "total_basic": 0.0, "total_commission": 0.0, "total_bonus": 0.0, "total_net": 0.0, "paid": 0, "pending": 0}
        for row in rows:
            row["basic_salary"] = row["payroll_basic_salary"] if row["payroll_id"] else row["base_salary"]
            if not row["payroll_id"]:
                row["commission"] = 0
                row["bonus"] = 0
                row["overtime_hours"] = row["production_ot_hours"]
                row["overtime_amount"] = 0
                row["other_allowance"] = 0
                row["advance_deduction"] = 0
                row["other_deductions"] = 0
                row["status"] = "Draft"
                row["notes"] = ""
                row["net_salary"] = row["basic_salary"] + row["commission"]
            summary["total_basic"] += float(row["basic_salary"] or 0)
            summary["total_commission"] += float(row["commission"] or 0)
            summary["total_bonus"] += float(row["bonus"] or 0)
            summary["total_net"] += float(row["net_salary"] or 0)
            if row["status"] == "Paid":
                summary["paid"] += 1
            else:
                summary["pending"] += 1
        return branch, month, rows, summary

    def handle_export_payroll_pdf(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "payroll_read"):
            return
        branch, month, rs, summary = self.payroll_report_rows(user)
        with db_connect() as conn:
            currency = get_company_profile(conn)["currency_label"]
        rows = [[r["name"], r["role"], r["branch"], f"{r['present_days']} P / {r['absent_days']} A / {r['leave_days']} L / {r['half_days']} H",
                 format_report_money(r["basic_salary"], currency), format_report_money(r["commission"], currency), format_report_money(r["bonus"], currency),
                 format_report_money(r["overtime_amount"], currency), format_report_money(r["other_allowance"], currency),
                 format_report_money(r["advance_deduction"], currency), format_report_money(r["other_deductions"], currency),
                 format_report_money(r["net_salary"], currency), r["status"]] for r in rs]
        totals = [["Totals", "", "", "", format_report_money(summary["total_basic"], currency), format_report_money(summary["total_commission"], currency),
                   format_report_money(summary["total_bonus"], currency), "", "", "", "", format_report_money(summary["total_net"], currency), ""]]
        self.send_report_pdf(
            f"payroll_{month}", "Payroll Report", branch, month_name(month),
            ["Employee", "Designation", "Branch", "Attendance", f"Basic ({currency})", f"Commission ({currency})", f"Bonus ({currency})",
             f"OT ({currency})", f"Allowance ({currency})", f"Advance ({currency})", f"Deductions ({currency})", f"Net ({currency})", "Status"],
            rows, widths=[1.2, 1.0, 0.8, 1.0, 0.8, 0.8, 0.7, 0.7, 0.8, 0.8, 0.8, 0.9, 0.7],
            aligns=["left", "left", "left", "left", "right", "right", "right", "right", "right", "right", "right", "right", "left"],
            totals=totals,
            summary=[("Employees", str(summary["employees"])), ("Basic Salary", format_report_money(summary["total_basic"], currency)),
                     ("Commission + Bonus", format_report_money(summary["total_commission"] + summary["total_bonus"], currency)),
                     ("Net Payroll", format_report_money(summary["total_net"], currency))],
        )

    def handle_export_attendance_pdf(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "attendance_read"):
            return
        q = self.query()
        branch = self.allowed_branch(user, q.get("branch", ["All"])[0])
        month = q.get("month", [current_month_key()])[0]
        start, end = month_date_range(month)
        params: list[Any] = [start, end]
        where = "a.date BETWEEN ? AND ?"
        if branch != "All":
            where += " AND a.branch=?"; params.append(branch)
        with db_connect() as conn:
            rs = list(conn.execute(f"""SELECT a.*,e.name,e.role FROM attendance_records a JOIN employees e ON e.id=a.employee_id
                WHERE {where} ORDER BY a.date,e.name""", params))
        rows = [[r["date"], r["branch"], r["name"], r["role"], r["status"], r["notes"], r["entered_by"]] for r in rs]
        status_counts = {status: sum(1 for r in rs if r["status"] == status) for status in ATTENDANCE_STATUSES}
        self.send_report_pdf(
            f"attendance_{month}", "Attendance Report", branch, month_name(month),
            ["Date", "Branch", "Employee", "Designation", "Status", "Notes", "Entered By"],
            rows, widths=[0.9, 1.0, 1.3, 1.2, 0.9, 1.8, 1.0], aligns=["left"] * 7,
            summary=[("Entries", str(len(rows))), ("Present", str(status_counts.get("Present", 0))),
                     ("Absent", str(status_counts.get("Absent", 0))), ("Leave", str(status_counts.get("Leave", 0)))],
        )

    def handle_export_pos_sales_pdf(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "finance_read"):
            return
        where, params, filters = self.pos_sales_filters(user)
        with db_connect() as conn:
            rs = list(conn.execute(f"SELECT * FROM pos_sales ps {where} ORDER BY sale_datetime DESC,id DESC", params))
            currency = get_company_profile(conn)["currency_label"]
        rows = [[r["sale_datetime"], r["invoice_no"], r["branch"], r["customer_name"], r["payment_status"], r["payment_method"],
                 format_report_money(r["total_amount"], currency), format_report_money(r["total_paid"], currency),
                 format_report_money(r["sell_due"], currency), format_report_number(r["total_items"]), r["added_by"]] for r in rs]
        total_amount = sum(float(r["total_amount"] or 0) for r in rs)
        total_paid = sum(float(r["total_paid"] or 0) for r in rs)
        total_due = sum(float(r["sell_due"] or 0) for r in rs)
        totals = [["", "", "", "", "", "Totals", format_report_money(total_amount, currency), format_report_money(total_paid, currency), format_report_money(total_due, currency), format_report_number(sum(float(r["total_items"] or 0) for r in rs)), ""]]
        self.send_report_pdf(
            f"sales_record_{filters['start']}_to_{filters['end']}", "Sales Report", filters["branch"], date_range_label(filters["start"], filters["end"]),
            ["Date & Time", "Invoice", "Branch", "Customer", "Status", "Method", f"Total ({currency})", f"Paid ({currency})", f"Due ({currency})", "Items", "Added By"],
            rows, widths=[1.2, 1.0, 0.8, 1.3, 0.8, 0.9, 0.9, 0.9, 0.9, 0.6, 1.0],
            aligns=["left", "left", "left", "left", "left", "left", "right", "right", "right", "right", "left"], totals=totals,
            summary=[("Invoices", str(len(rows))), ("Total Sales", format_report_money(total_amount, currency)),
                     ("Paid", format_report_money(total_paid, currency)), ("Due", format_report_money(total_due, currency))],
        )

    def handle_export_notifications_pdf(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "alert_read"):
            return
        q = self.query()
        requested_branch = q.get("branch", ["All"])[0]
        data = self.build_notifications(user, requested_branch)
        rows = [[a["severity"].title(), a["type"], a["branch"], a["title"], a["message"], a["metric"], "Yes" if a["read"] else "No", a["created_label"]] for a in data["alerts"]]
        summary = data.get("summary", {})
        self.send_report_pdf(
            f"management_alerts_{data['date']}", "Management Alerts Report", data["branch"], data["date"],
            ["Severity", "Type", "Branch", "Title", "Message", "Metric", "Read", "Date"],
            rows, widths=[0.8, 1.0, 0.9, 1.4, 2.2, 0.7, 0.6, 0.8], aligns=["left"] * 8,
            summary=[("Alerts", str(summary.get("total", 0))), ("Unread", str(summary.get("unread", 0))),
                     ("Critical", str(summary.get("critical", 0))), ("Warning", str(summary.get("warning", 0)))],
        )

    def send_csv(self,filename:str,headers:list[str],rows:list[list[Any]])->None:
        output=io.StringIO(newline="");writer=csv.writer(output);writer.writerow(headers);writer.writerows(rows);body=output.getvalue().encode("utf-8-sig")
        self.send_response(200);self.send_header("Content-Type","text/csv; charset=utf-8");self.send_header("Content-Disposition",f'attachment; filename="{filename}"');self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)

    def handle_export_orders(self, user: dict[str, Any]) -> None:
        if not self.require_permission(user, "orders_read"):
            return
        where, params = self.order_filters(user)
        with db_connect() as conn:
            rows = list(conn.execute(
                f"""SELECT o.*,e.name assigned_employee FROM customer_orders o
                LEFT JOIN employees e ON e.id=o.assigned_employee_id {where}
                ORDER BY o.booking_date,o.id""", params
            ))
        can_finance = self.has_permission(user, "finance_read")
        headers = ["Order No","Booking Date","Due Date","Branch","Customer","Phone","Item","Quantity","Assigned Employee","Status"]
        currency = self.report_currency()
        if can_finance: headers += [f"Total ({currency})",f"Advance ({currency})",f"Balance ({currency})"]
        headers += ["Notes","Entered By"]
        out = []
        for r in rows:
            line = [r["order_no"],r["booking_date"],r["due_date"],r["branch"],r["customer_name"],r["phone"],r["item_type"],r["quantity"],r["assigned_employee"] or "",r["status"]]
            if can_finance: line += [r["total_amount"],r["advance_amount"],r["total_amount"]-r["advance_amount"]]
            line += [r["notes"],r["entered_by"]]
            out.append(line)
        self.send_csv(self.export_filename("orders", "csv"), headers, out)

    def handle_export_finance(self,user:dict[str,Any])->None:
        if not self.require_permission(user,"finance_read"):return
        q=self.query();branch=self.allowed_branch(user,q.get("branch",["All"])[0]);default_start,default_end=current_month_range();start=q.get("start",[default_start])[0] or default_start;end=q.get("end",[default_end])[0] or default_end
        sql="SELECT * FROM finance_entries WHERE date BETWEEN ? AND ?";params=[start,end]
        if branch!="All":sql+=" AND branch=?";params.append(branch)
        sql+=" ORDER BY date,id"
        with db_connect() as conn:rs=list(conn.execute(sql,params))
        currency = self.report_currency()
        self.send_csv(self.export_filename("financial_entries", "csv"),["ID","Date","Branch","Type","Category","Description",f"Amount ({currency})","Payment Method","Reference","Entered By"],[[r["id"],r["date"],r["branch"],r["type"],r["category"],r["description"],r["amount"],r["payment_method"],r["reference"],r["entered_by"]] for r in rs])

    def handle_export_production(self,user:dict[str,Any])->None:
        if not self.require_permission(user,"production_read"):return
        where,params=self.production_filters(user)
        with db_connect() as conn:rs=list(conn.execute(f"SELECT p.*,e.name employee FROM production_entries p JOIN employees e ON e.id=p.employee_id {where} ORDER BY p.date,p.id",params))
        self.send_csv(self.export_filename("production_entries", "csv"),["ID","Date","Branch","Employee","Activity","Quantity","Ready Pcs","OT Hours","Notes","Entered By"],[[r["id"],r["date"],r["branch"],r["employee"],r["activity"],r["quantity"],r["ready_pcs"],r["ot_hours"],r["notes"],r["entered_by"]] for r in rs])

    def handle_backup(self,user:dict[str,Any])->None:
        if not self.require_permission(user,"backup"):return
        stamp=datetime.now().strftime("%Y%m%d_%H%M%S");backup=BACKUP_DIR/self.export_filename(f"backup_{stamp}", "db")
        with db_connect() as conn:
            conn.execute("PRAGMA wal_checkpoint(FULL)")
            log_audit(conn,user,"BACKUP","Database",backup.name,"Manual database backup")
        shutil.copy2(DB_PATH,backup);body=backup.read_bytes()
        self.send_response(200);self.send_header("Content-Type","application/octet-stream");self.send_header("Content-Disposition",f'attachment; filename="{backup.name}"');self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)


def main() -> None:
    init_db()
    port = PORT
    if len(sys.argv) > 1:
        try: port = int(sys.argv[1])
        except ValueError: pass
    server = ThreadingHTTPServer((HOST, port), AppHandler)
    display_host = "127.0.0.1" if HOST == "0.0.0.0" else HOST
    url = f"http://{display_host}:{port}"
    print("=" * 72)
    print(" Dar al Sultan Management App — Phase 3.2 Mobile Cloud Demo")
    print(f" Mode: {'Cloud demo' if CLOUD_MODE else 'Local cloud-ready test'}")
    print(f" Database: {DB_PATH}")
    print(f" Open: {url}")
    print(" Press Ctrl+C to stop the application")
    print("=" * 72)
    if not CLOUD_MODE and os.environ.get("DAS_NO_BROWSER") != "1":
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nApplication stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
