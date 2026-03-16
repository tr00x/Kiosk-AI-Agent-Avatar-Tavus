"""Exam sheet PDF generation and IPP printing.

Generates a PDF matching the Open Dental exam sheet layout and sends it
to a network printer via IPP (Internet Printing Protocol).
"""

import io
import logging
import struct
from datetime import datetime

import httpx
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.colors import Color
from reportlab.pdfgen import canvas

from config import settings

logger = logging.getLogger(__name__)

# Page dimensions
W, H = letter  # 8.5 x 11 inches

# Colors
BLUE = Color(0.2, 0.3, 0.6)
GRAY_BG = Color(0.85, 0.85, 0.85)
GREEN = Color(0.0, 0.4, 0.0)


def generate_exam_pdf(
    patient_name: str,
    pat_num: int,
    apt_time_str: str,
    checkin_time_str: str,
    sheet_date: str,
    treatment_note: str = "",
) -> bytes:
    """Generate exam sheet PDF matching Open Dental layout. Returns PDF bytes."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)

    # --- Border box ---
    margin = 0.6 * inch
    c.setStrokeColor(Color(0.7, 0.7, 0.7))
    c.setLineWidth(0.5)
    c.rect(margin, 0.5 * inch, W - 2 * margin, H - 1.0 * inch)

    x_left = margin + 0.3 * inch
    x_mid = 3.8 * inch
    x_right = 5.5 * inch

    # --- A: time (top right, large blue) ---
    c.setFont("Helvetica-Bold", 22)
    c.setFillColor(BLUE)
    c.drawString(x_right, H - 1.2 * inch, f"A: {apt_time_str}")

    # --- C: time (below A:, large blue) ---
    c.drawString(x_right, H - 1.7 * inch, f"C:{checkin_time_str}")

    # --- Exam for Name PatNum ---
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(Color(0, 0, 0))
    c.drawCentredString(W / 2 - 0.5 * inch, H - 1.5 * inch, f"Exam for {patient_name} {pat_num}")

    # --- Date ---
    c.setFont("Helvetica", 10)
    c.drawCentredString(W / 2 - 0.5 * inch, H - 1.7 * inch, sheet_date)

    # --- Left column: PAN, PA/Btw, Prophy, CT Scan, Pictures, Ceph ---
    y = H - 2.2 * inch
    left_items = [
        "PAN_________ [  ]",
        "PA/Btw:          [  ]",
        "Prophy_______ [  ]",
        "CT Scan______ [  ]",
        "Pictures______ [  ]",
        "Ceph            [  ]",
    ]
    c.setFont("Helvetica", 10)
    for item in left_items:
        c.drawString(x_left, y, item)
        y -= 0.28 * inch

    # --- Middle column: exam types ---
    y = H - 2.2 * inch
    mid_items = [
        ("Comprehensive exam", "[  ]"),
        ("Periodic exam", "[  ]"),
        ("Emergency exam", "[  ]"),
        ("Treatment", "[  ]"),
    ]
    c.setFont("Helvetica", 10)
    for label, box in mid_items:
        c.drawString(x_mid, y, label)
        c.drawString(x_mid + 1.5 * inch, y, box)
        y -= 0.28 * inch

    # --- Ref. TO ---
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x_right + 0.8 * inch, H - 2.5 * inch, "Ref. TO:")
    c.setFont("Helvetica", 10)
    c.drawString(x_right + 0.3 * inch, H - 2.8 * inch, "ENDO   OS/IMPLANTS")
    c.drawString(x_right + 0.6 * inch, H - 3.05 * inch, "ORTHO    PEDO")

    # --- Treatment note (green, large) ---
    if treatment_note:
        c.setFont("Helvetica-Bold", 16)
        c.setFillColor(GREEN)
        c.drawString(x_mid - 0.5 * inch, H - 3.5 * inch, treatment_note)
        c.setFillColor(Color(0, 0, 0))

    # --- Tooth charts: EXISTING and NEEDS ---
    _draw_tooth_chart(c, x_left - 0.1 * inch, H - 4.1 * inch, "EXISTING")
    _draw_tooth_chart(c, x_left - 0.1 * inch, H - 5.8 * inch, "NEEDS")

    # --- PT NEEDS ---
    y_pt = H - 7.5 * inch
    c.setFont("Helvetica-Bold", 13)
    c.drawString(x_left, y_pt, "PT NEEDS:")

    c.setFont("Helvetica", 10)
    row1 = ["RCT", "CROWNS/BRIDGES", "DENTURES", "SRP", "NG", "IMPLANTS", "LASER", "EXO"]
    row2 = ["FLUORIDE", "CHLOREXIDINE", "WATERPICK", "PERIDEX", "WHITENING", "FILLINGS", "RECALL"]

    x = x_left + 1.2 * inch
    for item in row1:
        c.drawString(x, y_pt - 0.3 * inch, item)
        x += len(item) * 5.5 + 12

    x = x_left + 0.5 * inch
    for item in row2:
        c.drawString(x, y_pt - 0.6 * inch, item)
        x += len(item) * 5.5 + 12

    # --- RX ---
    y_rx = y_pt - 1.2 * inch
    c.setFont("Helvetica-Bold", 13)
    c.drawString(x_left, y_rx, "RX ________________________")

    # --- DR / DA / DH ---
    y_dr = y_rx - 0.6 * inch
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x_left - 0.2 * inch, y_dr, "DR _________________________")
    c.drawString(x_left + 2.5 * inch, y_dr, "DA _________________________")
    c.drawString(x_left + 5.0 * inch, y_dr, "DH ___________________")

    c.save()
    return buf.getvalue()


def _draw_tooth_chart(c, x, y, label):
    """Draw a tooth number grid (upper + lower row)."""
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x, y, label)

    # Line under label
    c.setStrokeColor(Color(0, 0, 0))
    c.line(x + 1.0 * inch, y + 0.05 * inch, x + 4.5 * inch, y + 0.05 * inch)

    # Upper teeth: 1/1 through 16/3
    upper = ["1/1", "2/2", "3/3", "4/A", "5/B", "6/C", "7/D", "8/E", "9/F",
             "10/G", "11/H", "12/I", "13/J", "14/1", "15/2", "16/3"]
    lower = ["32/1", "31/2", "30/3", "29/T", "28/S", "27/R", "26/Q", "25/P", "24/O",
             "23/N", "22/M", "21/L", "20/K", "19/1", "18/2", "17/3"]

    cell_w = 0.4 * inch
    cell_h = 0.22 * inch
    start_x = x
    rows_y = y - 0.25 * inch

    c.setFont("Helvetica", 6.5)

    for row_idx, teeth in enumerate([upper]):
        for i, tooth in enumerate(teeth):
            cx = start_x + i * cell_w
            cy = rows_y
            # Header cell (gray bg)
            c.setFillColor(GRAY_BG)
            c.rect(cx, cy, cell_w, cell_h, fill=1, stroke=1)
            c.setFillColor(Color(0, 0, 0))
            c.drawCentredString(cx + cell_w / 2, cy + 0.06 * inch, tooth)

    # Empty rows for notes (3 rows)
    for row in range(3):
        for i in range(16):
            cx = start_x + i * cell_w
            cy = rows_y - (row + 1) * cell_h
            c.rect(cx, cy, cell_w, cell_h, stroke=1)

    # Lower teeth header
    lower_y = rows_y - 4 * cell_h
    for i, tooth in enumerate(lower):
        cx = start_x + i * cell_w
        c.setFillColor(GRAY_BG)
        c.rect(cx, lower_y, cell_w, cell_h, fill=1, stroke=1)
        c.setFillColor(Color(0, 0, 0))
        c.drawCentredString(cx + cell_w / 2, lower_y + 0.06 * inch, tooth)


# ---------------------------------------------------------------------------
# IPP printing
# ---------------------------------------------------------------------------

def _build_ipp_request(job_name: str = "ExamSheet") -> bytes:
    """Build a minimal IPP Print-Job request header."""
    # IPP version 1.1, operation Print-Job (0x0002)
    buf = io.BytesIO()
    buf.write(struct.pack(">bb", 1, 1))  # version 1.1
    buf.write(struct.pack(">h", 0x0002))  # Print-Job
    buf.write(struct.pack(">i", 1))  # request-id

    # Operation attributes
    buf.write(bytes([0x01]))  # operation-attributes-tag
    # charset
    buf.write(bytes([0x47]))  # charset type
    buf.write(struct.pack(">h", len("attributes-charset")))
    buf.write(b"attributes-charset")
    buf.write(struct.pack(">h", len("utf-8")))
    buf.write(b"utf-8")
    # natural-language
    buf.write(bytes([0x48]))  # naturalLanguage type
    buf.write(struct.pack(">h", len("attributes-natural-language")))
    buf.write(b"attributes-natural-language")
    buf.write(struct.pack(">h", len("en")))
    buf.write(b"en")
    # printer-uri
    printer_uri = f"ipp://{settings.printer_ip}/ipp/print"
    buf.write(bytes([0x45]))  # uri type
    buf.write(struct.pack(">h", len("printer-uri")))
    buf.write(b"printer-uri")
    buf.write(struct.pack(">h", len(printer_uri)))
    buf.write(printer_uri.encode())
    # job-name
    buf.write(bytes([0x42]))  # nameWithoutLanguage type
    buf.write(struct.pack(">h", len("job-name")))
    buf.write(b"job-name")
    buf.write(struct.pack(">h", len(job_name)))
    buf.write(job_name.encode())
    # document-format
    doc_format = "application/pdf"
    buf.write(bytes([0x49]))  # mimeMediaType type
    buf.write(struct.pack(">h", len("document-format")))
    buf.write(b"document-format")
    buf.write(struct.pack(">h", len(doc_format)))
    buf.write(doc_format.encode())

    # End of attributes
    buf.write(bytes([0x03]))

    return buf.getvalue()


async def print_pdf(pdf_bytes: bytes, job_name: str = "ExamSheet") -> bool:
    """Send PDF to printer via IPP. Returns True on success."""
    if not settings.printer_ip:
        return False

    printer_url = f"http://{settings.printer_ip}:631/ipp/print"
    ipp_header = _build_ipp_request(job_name)
    payload = ipp_header + pdf_bytes

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                printer_url,
                content=payload,
                headers={"Content-Type": "application/ipp"},
            )
        # IPP success status is 0x0000 in bytes 2-3 of response
        if len(resp.content) >= 4:
            status = struct.unpack(">h", resp.content[2:4])[0]
            if status <= 0x00FF:
                logger.info("print_pdf: sent to %s (status=0x%04x)", settings.printer_ip, status)
                return True
            else:
                logger.warning("print_pdf: printer returned status 0x%04x", status)
                return False
        logger.warning("print_pdf: unexpected response from printer")
        return False
    except Exception:
        logger.exception("print_pdf: failed to send to %s", settings.printer_ip)
        return False
