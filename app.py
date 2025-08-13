from flask import Flask, render_template, request, send_file
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from io import BytesIO
import datetime

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        # ข้อมูลบริษัท
        company_name = request.form["company_name"]
        company_address = request.form["company_address"]
        company_phone = request.form["company_phone"]

        # ข้อมูลลูกค้า
        customer_name = request.form["customer_name"]
        customer_address = request.form["customer_address"]
        customer_phone = request.form["customer_phone"]

        # รายการสินค้า
        items = request.form.getlist("item[]")
        prices = request.form.getlist("price[]")
        qtys = request.form.getlist("qty[]")

        total = 0
        for p, q in zip(prices, qtys):
            total += float(p) * int(q)

        # สร้าง PDF
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4

        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, height - 50, f"ใบเสนอราคา - {datetime.date.today()}")

        c.setFont("Helvetica", 12)
        c.drawString(50, height - 80, f"บริษัท: {company_name}")
        c.drawString(50, height - 100, f"ที่อยู่: {company_address}")
        c.drawString(50, height - 120, f"โทร: {company_phone}")

        c.drawString(50, height - 160, f"ลูกค้า: {customer_name}")
        c.drawString(50, height - 180, f"ที่อยู่: {customer_address}")
        c.drawString(50, height - 200, f"โทร: {customer_phone}")

        y = height - 240
        c.drawString(50, y, "รายการ")
        c.drawString(250, y, "จำนวน")
        c.drawString(350, y, "ราคา")
        c.drawString(450, y, "รวม")

        y -= 20
        for item, qty, price in zip(items, qtys, prices):
            c.drawString(50, y, item)
            c.drawString(250, y, qty)
            c.drawString(350, y, price)
            c.drawString(450, y, f"{float(price) * int(qty):,.2f}")
            y -= 20

        c.setFont("Helvetica-Bold", 12)
        c.drawString(350, y - 20, "ยอดรวม:")
        c.drawString(450, y - 20, f"{total:,.2f} บาท")

        c.showPage()
        c.save()
        buffer.seek(0)

        return send_file(buffer, as_attachment=True, download_name="quotation.pdf", mimetype="application/pdf")

    return render_template("form.html")

if __name__ == "__main__":
    app.run(debug=True)