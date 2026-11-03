"""Create the joint-session angular reference. Requires reportlab, no hardware."""
import math
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
output = ROOT/"output/pdf/servo-protractor.pdf"
if output.exists(): raise SystemExit("Existing output rejected")
c = canvas.Canvas(str(output), pagesize=A4)
c.setTitle("SparkBench - servo angular reference")
w, h = A4
c.setFont("Helvetica-Bold", 19); c.drawString(42, h-48, "SparkBench angular reference")
c.setFont("Helvetica", 10)
c.drawString(42, h-68, "Print at 100% / Actual Size. Disable Fit to Page. Keep the paper flat.")
c.drawString(42, h-84, "Preparation only. Keep servo power off until the joint test is explicitly authorized.")
cx, cy, radius = w/2, 425, 72*mm
c.setLineWidth(.7); c.arc(cx-radius, cy-radius, cx+radius, cy+radius, 0, 180)
c.line(cx-radius, cy, cx+radius, cy)
for degree in range(181):
    a = math.radians(degree)
    length = 11 if degree % 10 == 0 else 7 if degree % 5 == 0 else 3.5
    c.setLineWidth(.65 if degree % 10 == 0 else .3)
    c.line(cx+(radius-length)*math.cos(a), cy+(radius-length)*math.sin(a),
           cx+radius*math.cos(a), cy+radius*math.sin(a))
    if degree % 10 == 0:
        r = radius-26
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(cx+r*math.cos(a), cy+r*math.sin(a)+(8 if degree in (0,180) else -3), str(degree))
c.setLineWidth(.5); c.circle(cx, cy, 3.5); c.line(cx-10,cy,cx+10,cy); c.line(cx,cy-10,cx,cy+10)
c.setFont("Helvetica-Bold", 10); c.drawCentredString(cx, cy-28, "CENTRE - align with shaft axis")
c.setFont("Helvetica", 9); c.drawCentredString(cx, cy-44, "Right-hand baseline = 0 degrees; left-hand baseline = 180 degrees")
c.setFont("Helvetica-Bold", 12); c.drawString(42, 341, "Placement for the joint session")
c.setFont("Helvetica", 10)
for i, line in enumerate([
    "1. We will choose a fixed zero direction relative to the servo case.",
    "2. The scale must be flat and parallel to the horn's rotation plane.",
    "3. Align its centre with the shaft axis; avoid an oblique reading/parallax.",
    "4. Keep the horn's full travel clear. Do not turn the horn by hand.",
    "5. Read the scale independently; a pulse command is never an angle reading.",
    "Do not reposition the phone, servo or existing grid just to place this sheet now.",
]): c.drawString(42, 320-i*17, line)
c.setFont("Helvetica-Bold", 10); c.drawString(42, 195, "Reference record (completed together)")
columns = [(42, "Role / image"), (180, "Pulse (us)"), (280, "Scale reading (deg)"), (430, "Reading uncertainty")]
for x, label in columns:
    c.setFont("Helvetica", 9); c.drawString(x, 175, label)
c.setStrokeColorRGB(.65,.65,.65); c.setLineWidth(.3)
for i, role in enumerate(["Fit 1", "Fit 2", "Fit 3", "Validation 1", "Validation 2", "Validation 3"]):
    y=155-i*18; c.line(42,y-5,w-42,y-5); c.drawString(42,y,role)
c.setFillColorRGB(.25,.25,.25); c.setFont("Helvetica", 8)
c.drawString(42, 36, "Angular reference only. Printing and placement do not by themselves validate camera accuracy.")
c.showPage(); c.save()
print(output)
