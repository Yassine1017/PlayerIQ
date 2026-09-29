"""Synthetic report layout; no private athlete data is committed."""

from io import BytesIO

import pytest
from PIL import Image, ImageDraw
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


@pytest.fixture
def synthetic_pdf() -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(612, 792))
    header = "ACTIVITY REPORT THURSDAY, MARCH 13, 2025 - 12:00:00 PM"
    for page_number in range(1, 6):
        pdf.setFont("Helvetica", 10)
        pdf.drawString(40, 760, f"{header} PAGE {page_number}/5")
        if page_number == 1:
            pdf.drawString(40, 740, "Activity 20250313120000")
            pdf.drawString(40, 720, "TOTAL TIME 1:30:00 TEAM DEMO CLUB VENUE DEFAULT")
        if page_number == 2:
            chart = Image.new("RGB", (700, 180), "white")
            draw = ImageDraw.Draw(chart)
            draw.text((20, 15), "Player Load & Maximum Velocity", fill="black")
            draw.text((20, 60), "ATHLETE1  Player Load 420  Maximum Velocity 29.75", fill="black")
            draw.text((20, 100), "ATHLETE2  Player Load 0  Maximum Velocity 0.00", fill="black")
            pdf.drawImage(ImageReader(chart), 40, 470, width=530, height=140)
        if page_number == 4:
            pdf.drawString(40, 740, "Athlete Breakdown")
            pdf.drawString(40, 720, "Distance (m) Overall (%)")
            for ordinal in range(12):
                top = 700 - ordinal * 40
                pdf.rect(40, top - 37, 530, 37)
                values = "0 0 0 0 0 0.00 0 0 0" if ordinal in (1, 5) else "3000 40 10 30 80 1.00 700 50 2"
                if ordinal == 8:
                    values = "15000 63 1550 5000 453 1.81 1179 449 75"
                pdf.drawString(45, top - 20, f"ATHLETE{ordinal + 1} FW {values}")
        if page_number == 5:
            pdf.drawString(40, 740, "Athlete Breakdown")
            pdf.drawString(40, 720, "Averages 3500.0 40.0 140.0 300.0 100.0 1.0 700.0 60.0 4.0")
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()
