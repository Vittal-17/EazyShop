# api/utils/pdf_generator.py
import logging
logger = logging.getLogger(__name__)

import os
import hashlib
import requests
import concurrent.futures
from io import BytesIO
from django.conf import settings
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from api.models import OrderItem, Payment  # 🚀 Added Payment import

# 1. Persistent cache directory for lightning-fast subsequent PDF generations
CACHE_DIR = os.path.join(settings.BASE_DIR, 'media', 'pdf_cache')
os.makedirs(CACHE_DIR, exist_ok=True)

# 2. Blazing-fast connection session pool with a real browser User-Agent
# to prevent external e-commerce sites from blocking or throttling requests
session = requests.Session()
adapter = requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=20)
session.mount('https://', adapter)
session.mount('http://', adapter)
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
})

def format_pdf_inr(amount):
    """Safe INR formatter for ReportLab standard fonts to prevent black square glyph errors."""
    try:
        numeric_amount = float(amount or 0)
    except (ValueError, TypeError):
        numeric_amount = 0.00
    return f"Rs. {numeric_amount:,.2f}"

def get_product_image(item):
    """Fetch product image with local disk caching and session pooling."""
    try:
        img_source = None
        if hasattr(item, 'image_url') and item.image_url:
            img_source = item.image_url
        elif hasattr(item, 'image') and item.image:
            img_source = item.image

        if not img_source and hasattr(item, 'product') and item.product:
            prod = item.product
            for field_name in ['image', 'image_url', 'thumbnail', 'photo', 'cloudinary_image']:
                val = getattr(prod, field_name, None)
                if val:
                    if hasattr(val, 'url'):
                        img_source = val.url
                    elif isinstance(val, str):
                        img_source = val
                    break

        if not img_source:
            return None

        # Check local cache first (Instant load on repeat downloads)
        url_hash = hashlib.md5(str(img_source).encode('utf-8')).hexdigest()
        cached_file_path = os.path.join(CACHE_DIR, f"{url_hash}.jpg")

        if os.path.exists(cached_file_path):
            return RLImage(cached_file_path, width=32, height=32)

        # Handle local media files
        if isinstance(img_source, str):
            if img_source.startswith('/media/') or not img_source.startswith('http'):
                clean_path = img_source.replace('/media/', '').lstrip('/')
                full_path = os.path.join(settings.MEDIA_ROOT, clean_path)
                if os.path.exists(full_path):
                    return RLImage(full_path, width=32, height=32)
            else:
                # Download via session pool and save to local disk cache
                response = session.get(img_source, timeout=2)
                if response.status_code == 200:
                    with open(cached_file_path, 'wb') as f:
                        f.write(response.content)
                    return RLImage(cached_file_path, width=32, height=32)
    except Exception as e:
        logger.error(f"[PDF IMAGE ERROR] {e}")

    return None

def get_shop_logo():
    """Locates the EazyShop logo directly from the utils folder."""
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        local_path = os.path.join(current_dir, 'logo.png')

        if os.path.exists(local_path):
            return RLImage(local_path, width=36, height=36)

        fallback_path = os.path.join(settings.BASE_DIR, 'static', 'images', 'logo.png')
        if os.path.exists(fallback_path):
            return RLImage(fallback_path, width=36, height=36)
    except Exception as e:
        logger.error(f"[PDF LOGO ERROR] {e}")

    return None

def draw_ambient_glass_background(canvas, doc):
    """Paints an edge-to-edge ambient background and a floating glass card on every page."""
    canvas.saveState()

    # 1. Edge-to-Edge Ambient Base Color
    canvas.setFillColor(colors.HexColor("#F0FDF4"))
    canvas.rect(0, 0, 612, 792, fill=1, stroke=0)

    # 2. Ambient Glow Orbs
    canvas.setFillColor(colors.HexColor("#0B8457"))
    canvas.setFillAlpha(0.06)
    canvas.circle(600, 750, 250, fill=1, stroke=0)
    canvas.setFillAlpha(0.04)
    canvas.circle(50, 50, 300, fill=1, stroke=0)

    # 3. Drop Shadow & Floating Glass Card
    canvas.setFillAlpha(0.12)
    canvas.setFillColor(colors.HexColor("#000000"))
    canvas.roundRect(28, 24, 556, 740, 24, fill=1, stroke=0)

    canvas.setFillAlpha(1.0)
    canvas.setFillColor(colors.HexColor("#FFFFFF"))
    canvas.setStrokeColor(colors.HexColor("#A7F3D0"))
    canvas.setLineWidth(1)
    canvas.roundRect(26, 26, 560, 740, 24, fill=1, stroke=1)

    canvas.restoreState()

def generate_invoice_pdf(order):
    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=56,
        leftMargin=56,
        topMargin=56,
        bottomMargin=56
    )

    elements = []
    styles = getSampleStyleSheet()

    PRIMARY_GREEN = colors.HexColor("#0B8457")
    LIGHT_GREEN_BG = colors.HexColor("#ECFDF5")
    DARK_TEXT = colors.HexColor("#0F172A")
    MUTED_TEXT = colors.HexColor("#64748B")
    BORDER_COLOR = colors.HexColor("#E2E8F0")
    WHITE = colors.HexColor("#FFFFFF")

    body_style = ParagraphStyle('InvoiceBody', parent=styles['Normal'], fontName='Helvetica', fontSize=9, leading=13, textColor=DARK_TEXT)
    right_body_style = ParagraphStyle('InvoiceBodyRight', parent=body_style, alignment=2)
    bold_body = ParagraphStyle('InvoiceBoldBody', parent=body_style, fontName='Helvetica-Bold')
    white_bold_body = ParagraphStyle('InvoiceWhiteBold', parent=body_style, fontName='Helvetica-Bold', textColor=WHITE)

    # 1. HEADER (Logo + Spaced Brand Text matching your email)
    logo_element = get_shop_logo()
    brand_text = Paragraph(
        f"<font size=16 color='#0B8457'><b>EazyShop<font color='#0F172A'>.</font></b></font><br/><font color='#64748B' size=8>Secure Order Receipt</font>",
        body_style
    )

    if logo_element:
        brand_table = Table([[logo_element, '', brand_text]], colWidths=[0.45 * inch, 0.18 * inch, 2.84 * inch])
        brand_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('ALIGN', (0,0), (0,0), 'LEFT')]))
        header_left = brand_table
    else:
        header_left = brand_text

    header_right = Paragraph(f"<font size=12 color='#0F172A'><b>INVOICE RECEIPT</b></font><br/><font color='#64748B' size=8><b>Invoice #:</b> INV-{order.id:05d}<br/><b>Date:</b> {order.created_at.strftime('%b %d, %Y')}</font>", right_body_style)

    header_table = Table([[header_left, header_right]], colWidths=[3.47 * inch, 3.47 * inch])
    header_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE')]))
    elements.append(header_table)
    elements.append(Spacer(1, 15))

    elements.append(Table([['']], colWidths=[6.94 * inch], rowHeights=[1], style=[('BACKGROUND', (0,0), (-1,-1), BORDER_COLOR)]))
    elements.append(Spacer(1, 15))

    # 2. METADATA BLOCK & TRANSACTION DETAILS 🚀
    customer_name = getattr(order.user, 'username', 'Valued Customer')
    customer_email = getattr(order.user, 'email', 'N/A')

    # Safely fetch the transaction details
    payment = Payment.objects.filter(order=order).first()
    payment_method = payment.payment_method.capitalize() if payment and payment.payment_method else "Razorpay Gateway"
    transaction_id = payment.transaction_id if payment and payment.transaction_id else "N/A"

    # 🚀 DYNAMIC PAYMENT STATUS LOGIC
    if order.status.lower() == 'cancelled':
        payment_status_html = "<font color='#E11D48'><b>Cancelled & Refunded</b></font>"
    else:
        payment_status_html = "<font color='#0B8457'><b>Paid & Verified</b></font>"

    billing_content = f"""
            <b>Billed To:</b><br/>
            <font size=10 color='#0F172A'><b>{customer_name}</b></font><br/>
            <font color='#64748B'>{customer_email}</font><br/><br/>
            <b>Payment Method:</b><br/>
            <font color='#0F172A'>{payment_method}</font>
        """

    status_content = f"""
            Payment: {payment_status_html}<br/>
            Fulfillment: <b>{order.status.capitalize()}</b><br/><br/>
            <b>Transaction ID:</b><br/>
            <font color='#64748B' size=9>{transaction_id}</font>
        """

    meta_table = Table([[Paragraph(billing_content, body_style), Paragraph(status_content, body_style)]], colWidths=[3.47 * inch, 3.47 * inch])
    meta_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BACKGROUND', (0,0), (-1,-1), LIGHT_GREEN_BG),
        ('PADDING', (0,0), (-1,-1), 12),
        ('ROUNDEDCORNERS', [8, 8, 8, 8]),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 20))

    # 3. LINE ITEMS TABLE (Lightning-fast parallel image fetching with thread pool)
    table_headers = [
        Paragraph("Photo", white_bold_body),
        Paragraph("Product Description", white_bold_body),
        Paragraph("Qty", white_bold_body),
        Paragraph("Price", white_bold_body),
        Paragraph("Total", white_bold_body),
    ]

    table_rows = [table_headers]
    order_items = list(OrderItem.objects.filter(order=order))

    # Fetch product images concurrently in the background
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        future_to_item = {executor.submit(get_product_image, item): item for item in order_items}
        item_images = {}
        for future in concurrent.futures.as_completed(future_to_item):
            item = future_to_item[future]
            try:
                item_images[item] = future.result()
            except Exception:
                item_images[item] = None

    for item in order_items:
        product_name = getattr(item, 'name', None) or getattr(item.product, 'name', 'Product')
        qty = int(item.quantity)
        price_val = float(item.price)
        total_val = qty * price_val

        img_cell = item_images.get(item)
        if not img_cell:
            img_cell = Paragraph("<font color='#94A3B8' size=8>No Image</font>", body_style)

        table_rows.append([
            img_cell,
            Paragraph(product_name, body_style),
            Paragraph(str(qty), body_style),
            Paragraph(format_pdf_inr(price_val), body_style),
            Paragraph(format_pdf_inr(total_val), bold_body)
        ])

    item_table = Table(table_rows, colWidths=[0.8 * inch, 2.74 * inch, 0.6 * inch, 1.2 * inch, 1.6 * inch])
    item_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), PRIMARY_GREEN),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,0), 8),
        ('TOPPADDING', (0,0), (-1,0), 8),
        ('BOTTOMPADDING', (0,1), (-1,-1), 10),
        ('TOPPADDING', (0,1), (-1,-1), 10),
        ('GRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('ROUNDEDCORNERS', [6, 6, 6, 6]),
    ]))
    elements.append(item_table)
    elements.append(Spacer(1, 15))

    # 4. ALIGNED TOTALS
    subtotal = sum(float(item.quantity) * float(item.price) for item in order_items)
    shipping_fee = float(getattr(order, 'shipping_fee', 0.00) or 0.00)
    grand_total = subtotal + shipping_fee

    totals_data = [
        ["Subtotal:", format_pdf_inr(subtotal)],
        ["Shipping & Handling:", format_pdf_inr(shipping_fee)],
        ["Grand Total:", format_pdf_inr(grand_total)]
    ]

    totals_table_rows = []
    for label, val in totals_data:
        is_grand = "Grand" in label
        lbl_style = ParagraphStyle('TotalLbl', parent=body_style, fontName='Helvetica-Bold' if is_grand else 'Helvetica', textColor=PRIMARY_GREEN if is_grand else DARK_TEXT)
        val_style = ParagraphStyle('TotalVal', parent=right_body_style, fontName='Helvetica-Bold' if is_grand else 'Helvetica', textColor=PRIMARY_GREEN if is_grand else DARK_TEXT)
        totals_table_rows.append([Paragraph(label, lbl_style), Paragraph(val, val_style)])

    totals_table = Table(totals_table_rows, colWidths=[2.0 * inch, 1.4 * inch])
    totals_table.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'RIGHT'),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('BACKGROUND', (0,2), (-1,2), LIGHT_GREEN_BG),
        ('BOX', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('ROUNDEDCORNERS', [4, 4, 4, 4]),
    ]))

    totals_wrapper = Table([['', totals_table]], colWidths=[3.54 * inch, 3.4 * inch])
    totals_wrapper.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ALIGN', (1,0), (1,0), 'RIGHT'),
    ]))

    elements.append(totals_wrapper)
    elements.append(Spacer(1, 25))

    # 5. FOOTER
    footer_style = ParagraphStyle('Footer', parent=styles['Normal'], fontName='Helvetica', fontSize=8, textColor=MUTED_TEXT, alignment=1)
    elements.append(Paragraph("Thank you for your business with EazyShop Enterprise. For support or queries, contact support@eazyshop.com", footer_style))

    # Build document with multi-page background rendering support
    doc.build(elements, onFirstPage=draw_ambient_glass_background, onLaterPages=draw_ambient_glass_background)
    buffer.seek(0)
    return buffer