import logging
logger = logging.getLogger(__name__)

from api.utils.currency_format import format_inr
# email_service.py
import sys
import threading
from collections import defaultdict

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils.html import strip_tags

from .models import Payment

# 🚀 Fetch the dynamic production URL (Defaults to localhost for local testing)
FRONTEND_URL = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000').rstrip('/')

def _send_html_email(to_email, subject, html_content):
    """Core function to send HTML emails using the Django Anymail (Brevo) Bridge"""
    try:
        text_content = strip_tags(html_content)
        
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[to_email]
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send()
        
        logger.info(f"[EMAIL LOG] ✅ Sent to {to_email} | Subject: {subject}")
        return True
    except Exception as e:
        logger.error(f"[EMAIL ERROR] ❌ Anymail API failed: {e!s}")
        return False

def get_base_template(header_color, header_title, icon, body_html):
    """The Premium Master Layout with dynamic theme colors and prominent branding."""
    BRAND_GREEN = "#16a34a" 
    
    return f"""
    <div style="background-color: #f4f5f7; padding: 40px 10px; font-family: 'Inter', 'Helvetica Neue', Helvetica, Arial, sans-serif; line-height: 1.6;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 15px 35px rgba(0,0,0,0.05); border: 1px solid #eaeaea;">
            
            <div style="padding: 30px 20px; text-align: center; border-bottom: 2px solid #f8fafc;">
                <h1 style="margin: 0; font-size: 32px; font-weight: 900; color: {BRAND_GREEN}; letter-spacing: -1.5px;">
                    EazyShop<span style="color: #0f172a;">.</span>
                </h1>
            </div>

            <div style="background-color: {header_color}; padding: 30px 20px; text-align: center;">
                <h2 style="color: #ffffff; margin: 0; font-size: 22px; font-weight: 800; letter-spacing: -0.5px;">
                    <span style="font-size: 26px; vertical-align: middle; margin-right: 8px;">{icon}</span> 
                    <span style="vertical-align: middle;">{header_title}</span>
                </h2>
            </div>
            
            <div style="padding: 40px 35px; color: #374151;">
                {body_html}
            </div>
            
            <div style="background-color: #f8fafc; padding: 30px; text-align: center; border-top: 1px solid #e2e8f0;">
                <p style="margin: 0; color: #64748b; font-size: 13px;">Premium Quality, Delivered Fast.</p>
                <p style="margin: 15px 0 0 0; color: #94a3b8; font-size: 12px;">© 2026 EazyShop Inc. All rights reserved.</p>
            </div>
        </div>
    </div>
    """

def send_welcome_email(to_email, username):
    theme_color = "#4F46E5" 
    subject = "Welcome to EazyShop! 🎉"
    
    body = f"""
    <h2 style="margin-top: 0; color: #0f172a; font-size: 22px; font-weight: 700;">Welcome aboard, {username}!</h2>
    <p style="font-size: 16px; color: #475569;">We are thrilled to have you join the EazyShop family. Get ready to discover amazing products, unbeatable prices, and lightning-fast delivery.</p>
    
    <div style="text-align: center; margin: 45px 0;">
        <a href="{FRONTEND_URL}/products" style="background-color: {theme_color}; color: #ffffff; text-decoration: none; padding: 16px 36px; border-radius: 50px; font-size: 16px; font-weight: 700; display: inline-block; box-shadow: 0 10px 20px rgba(79, 70, 229, 0.25); text-transform: uppercase; letter-spacing: 1px;">Start Shopping Now</a>
    </div>
    
    <p style="font-size: 15px; color: #64748b; border-top: 1px solid #e2e8f0; padding-top: 20px; text-align: center;">If you ever need help, just reply to this email. Our support team has your back.</p>
    """
    html = get_base_template(theme_color, "Account Created", "👋", body)
    return _send_html_email(to_email, subject, html)

def send_otp_email(to_email, username, otp):
    theme_color = "#0F172A" 
    subject = "Your EazyShop Security Code 🔐"
    
    body = f"""
    <h2 style="margin-top: 0; color: #0f172a; font-size: 20px;">Hello {username},</h2>
    <p style="font-size: 16px; color: #475569;">A request was made to verify your identity. Please use the secure authorization code below:</p>
    
    <div style="text-align: center; margin: 40px 0;">
        <div style="background-color: #f1f5f9; border: 2px dashed #94a3b8; border-radius: 12px; padding: 25px 40px; display: inline-block; box-shadow: inset 0 2px 4px rgba(0,0,0,0.02);">
            <span style="font-size: 42px; font-weight: 900; color: #0f172a; letter-spacing: 12px; margin-right: -12px;">{otp}</span>
        </div>
    </div>
    
    <div style="background-color: #fef2f2; border-left: 4px solid #ef4444; padding: 15px; border-radius: 0 8px 8px 0;">
        <p style="font-size: 14px; color: #b91c1c; margin: 0; font-weight: 600;">⚠️ Security Notice</p>
        <p style="font-size: 13px; color: #991b1b; margin: 5px 0 0 0;">This code expires in 5 minutes. If you didn't request this, you can safely ignore this message.</p>
    </div>
    """
    html = get_base_template(theme_color, "Security Verification", "🛡️", body)
    return _send_html_email(to_email, subject, html)

def send_order_email(to_email, username, order_id, status, total, payment_method, txn_id, address):
    status = status.lower()
    
    if status == 'pending':
        theme_color = "#2563EB"
        icon = "🧾"
        header_title = "Order Confirmed"
        subject = f"Order Confirmation: #{order_id} has been placed!"
        intro = "Great news! We have received your payment and your order is currently being prepared for shipment."
    elif status == 'shipped':
        theme_color = "#EA580C"
        icon = "🚚"
        header_title = "Order Shipped"
        subject = f"Update: Order #{order_id} is on its way!"
        intro = "Pack your bags (or just wait by the door)—your order has left our facility and is en route to your address!"
    elif status == 'delivered':
        theme_color = "#10B981"
        icon = "📦"
        header_title = "Order Delivered"
        subject = f"Delivered: Order #{order_id} has arrived!"
        intro = "Success! Your package has been safely delivered. We hope you love your new items."
    elif status == 'cancelled':
        theme_color = "#E11D48"
        icon = "❌"
        header_title = "Order Cancelled"
        subject = f"Cancelled: Order #{order_id}"
        intro = "Your order has been cancelled. If a charge was made, it will be refunded to your original payment method within 3-5 business days."
    else:
        theme_color = "#475569"
        icon = "📋"
        header_title = f"Order {status.capitalize()}"
        subject = f"Update on Order #{order_id}"
        intro = f"There is an update on your order. The new status is: {status.upper()}"

    body = f"""
    <h2 style="margin-top: 0; color: #0f172a; font-size: 20px;">Hi {username},</h2>
    <p style="font-size: 16px; color: #475569;">{intro}</p>
    
    <div style="background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; margin: 35px 0; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.02);">
        <div style="background-color: {theme_color}15; padding: 15px 25px; border-bottom: 1px solid #e2e8f0;">
            <h3 style="margin: 0; color: {theme_color}; font-size: 13px; text-transform: uppercase; letter-spacing: 1.5px; font-weight: 800;">Receipt Details</h3>
        </div>
        <div style="padding: 25px;">
            <table style="width: 100%; font-size: 15px; color: #334155; border-collapse: collapse;">
                <tr>
                    <td style="padding: 12px 0; border-bottom: 1px dashed #cbd5e1; color: #64748b;">Order ID</td>
                    <td style="padding: 12px 0; text-align: right; border-bottom: 1px dashed #cbd5e1; font-weight: 600; color: #0f172a;">#{order_id}</td>
                </tr>
                <tr>
                    <td style="padding: 12px 0; border-bottom: 1px dashed #cbd5e1; color: #64748b;">Current Status</td>
                    <td style="padding: 12px 0; text-align: right; border-bottom: 1px dashed #cbd5e1; font-weight: 800; color: {theme_color};">{status.upper()}</td>
                </tr>
                <tr>
                    <td style="padding: 12px 0; border-bottom: 1px dashed #cbd5e1; color: #64748b;">Payment Method</td>
                    <td style="padding: 12px 0; text-align: right; border-bottom: 1px dashed #cbd5e1; font-weight: 500;">{payment_method}</td>
                </tr>
                <tr>
                    <td style="padding: 12px 0; border-bottom: 1px dashed #cbd5e1; color: #64748b;">Transaction ID</td>
                    <td style="padding: 12px 0; text-align: right; border-bottom: 1px dashed #cbd5e1; font-weight: 600; font-family: monospace; font-size: 13px; color: #475569;">{txn_id}</td>
                </tr>
                <tr>
                    <td style="padding: 12px 0; border-bottom: 2px solid #e2e8f0; color: #64748b;">Delivery To</td>
                    <td style="padding: 12px 0; text-align: right; border-bottom: 2px solid #e2e8f0; font-size: 14px; line-height: 1.4;">{address}</td>
                </tr>
                <tr>
                    <td style="padding: 18px 0 0 0; color: #0f172a; font-weight: 700; font-size: 16px;">Total Amount</td>
                    <td style="padding: 18px 0 0 0; text-align: right; font-weight: 900; font-size: 22px; color: #0f172a;">{format_inr(total)}</td>
                </tr>
            </table>
        </div>
    </div>
    
    <p style="font-size: 14px; text-align: center; color: #64748b; margin-top: 30px;">
        Track your full order history anytime in your <a href="{FRONTEND_URL}/dashboard" style="color: {theme_color}; text-decoration: none; font-weight: 600;">EazyShop Dashboard</a>.
    </p>
    """
    html = get_base_template(theme_color, header_title, icon, body)
    return _send_html_email(to_email, subject, html)

def send_vendor_new_order_email(to_email, username, order_id, items_list, total_earnings, customer_name, address):
    theme_color = "#8B5CF6" 
    icon = "💰"
    header_title = "New Sale!"
    subject = f"Cha-ching! New Sale on EazyShop - Order #{order_id}"
    
    items_html = ""
    for item in items_list:
        items_html += f"""
            <tr>
                <td style="padding: 12px 0; border-bottom: 1px dashed #cbd5e1; color: #64748b;">Item Sold</td>
                <td style="padding: 12px 0; text-align: right; border-bottom: 1px dashed #cbd5e1; font-weight: 600;">{item['quantity']}x {item['product_name']}</td>
            </tr>
        """
    
    body = f"""
    <h2 style="margin-top: 0; color: #0f172a; font-size: 20px;">Cha-ching, {username}!</h2>
    <p style="font-size: 16px; color: #475569;">Great news! <strong>{customer_name}</strong> just purchased from you. It's time to pack and ship!</p>
    
    <div style="background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; margin: 35px 0; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.02);">
        <div style="background-color: {theme_color}15; padding: 15px 25px; border-bottom: 1px solid #e2e8f0;">
            <h3 style="margin: 0; color: {theme_color}; font-size: 13px; text-transform: uppercase; letter-spacing: 1.5px; font-weight: 800;">Sale Breakdown</h3>
        </div>
        <div style="padding: 25px;">
            <table style="width: 100%; font-size: 15px; color: #334155; border-collapse: collapse;">
                <tr>
                    <td style="padding: 12px 0; border-bottom: 1px dashed #cbd5e1; color: #64748b;">Order ID</td>
                    <td style="padding: 12px 0; text-align: right; border-bottom: 1px dashed #cbd5e1; font-weight: 600; color: #0f172a;">#{order_id}</td>
                </tr>
                {items_html}
                <tr>
                    <td style="padding: 12px 0; border-bottom: 2px solid #e2e8f0; color: #64748b;">Ship To</td>
                    <td style="padding: 12px 0; text-align: right; border-bottom: 2px solid #e2e8f0; font-size: 14px; line-height: 1.4;">{address}</td>
                </tr>
                <tr>
                    <td style="padding: 18px 0 0 0; color: #0f172a; font-weight: 700; font-size: 16px;">Your Earnings</td>
                    <td style="padding: 18px 0 0 0; text-align: right; font-weight: 900; font-size: 22px; color: #10B981;">{format_inr(total_earnings)}</td>
                </tr>
            </table>
        </div>
    </div>
    
    <p style="font-size: 14px; text-align: center; color: #64748b; margin-top: 30px;">
        Please log into your <a href="{FRONTEND_URL}/vendor" style="color: {theme_color}; text-decoration: none; font-weight: 600;">Vendor HQ</a> to update the shipping status.
    </p>
    """
    html = get_base_template(theme_color, header_title, icon, body)
    return _send_html_email(to_email, subject, html)

def send_vendor_product_status_email(to_email, username, product_name, status, admin_note=""):
    status = status.lower()
    
    if status == 'approved':
        theme_color = "#10B981"
        icon = "✅"
        header_title = "Product Approved"
        subject = f"Good News! '{product_name}' is now live on EazyShop"
        intro = f"Congratulations! Our moderation team has reviewed and approved your product <strong>'{product_name}'</strong>. It is now live on the marketplace and available for customers to purchase."
    else:
        theme_color = "#EF4444"
        icon = "⚠️"
        header_title = "Action Required"
        subject = f"Update regarding your product: '{product_name}'"
        intro = f"We have reviewed your product submission for <strong>'{product_name}'</strong>, but unfortunately, it requires some adjustments before it can go live."

    admin_note_html = ""
    if admin_note:
        admin_note_html = f"""
        <div style="background-color: #fffbeb; border-left: 4px solid #f59e0b; padding: 15px; margin-top: 20px; border-radius: 0 8px 8px 0;">
            <p style="margin: 0; color: #b45309; font-weight: 700; font-size: 14px;">Admin Feedback:</p>
            <p style="margin: 5px 0 0 0; color: #92400e; font-size: 14px;">"{admin_note}"</p>
        </div>
        """

    body = f"""
    <h2 style="margin-top: 0; color: #0f172a; font-size: 20px;">Hi {username},</h2>
    <p style="font-size: 16px; color: #475569;">{intro}</p>
    {admin_note_html}
    
    <div style="text-align: center; margin: 40px 0;">
        <a href="{FRONTEND_URL}/vendor" style="background-color: {theme_color}; color: #ffffff; text-decoration: none; padding: 14px 28px; border-radius: 8px; font-size: 15px; font-weight: 600; display: inline-block;">View Vendor Dashboard</a>
    </div>
    """
    html = get_base_template(theme_color, header_title, icon, body)
    return _send_html_email(to_email, subject, html)

# ==========================================
# ASYNC WRAPPERS
# ==========================================

def _safe_async_dispatch(target_func, *args, **kwargs):
    def wrapper():
        try:
            target_func(*args, **kwargs)
        except Exception as e:
            logger.error(f"[EMAIL ERROR] ❌ Threaded email failed: {e!s}")

    if 'test' in sys.argv:
        try:
            target_func(*args, **kwargs)
        except Exception as e:
            logger.error(f"[EMAIL ERROR] ❌ Threaded email failed: {e!s}")
    else:
        threading.Thread(target=wrapper).start()

def async_notify_vendors(order):
    vendor_groups = defaultdict(lambda: {'username': '', 'items': [], 'total_earnings': 0.0})
    
    for item in order.order_items.all():
        if item.vendor:
            email = item.vendor.email
            vendor_groups[email]['username'] = item.vendor.username
            vendor_groups[email]['items'].append({
                'product_name': item.product.name if item.product else 'Product',
                'quantity': item.quantity
            })
            vendor_groups[email]['total_earnings'] += float(item.seller_earnings or 0)

    customer_username = order.user.username
    order_id = order.id
    shipping_address = order.shipping_address or 'Saved Address'

    def send_emails():
        for vendor_email, data in vendor_groups.items():
            try:
                send_vendor_new_order_email(
                    to_email=vendor_email,
                    username=data['username'],
                    order_id=order_id,
                    items_list=data['items'],
                    total_earnings=data['total_earnings'],
                    customer_name=customer_username,
                    address=shipping_address
                )
            except Exception as e:
                logger.error(f"[EMAIL ERROR] ❌ Failed to notify vendor {vendor_email}: {e}")

    _safe_async_dispatch(send_emails)

def async_notify_customer_status(item):
    order = item.order
    payment = Payment.objects.filter(order=order).first()
    
    to_email = order.user.email
    username = order.user.username
    order_id = order.id
    item_status = item.status
    total_price = str(order.total_price)
    address = order.shipping_address or 'Saved Address'
    
    # 🚀 Dynamically extract the method since we removed choices
    payment_method_display = payment.payment_method.capitalize() if payment else "Completed"
    transaction_id_display = payment.transaction_id if (payment and payment.transaction_id) else "System Confirmed"

    def send_email():
        try:
            send_order_email(
                to_email=to_email,
                username=username,
                order_id=order_id,
                status=item_status,
                total=total_price,
                payment_method=payment_method_display,
                txn_id=transaction_id_display,
                address=address
            )
        except Exception as e:
            logger.error(f"[EMAIL ERROR] ❌ Failed to notify customer: {e!s}")

    _safe_async_dispatch(send_email)

def async_notify_cancellation(order):
    vendor_groups = defaultdict(lambda: {'username': '', 'products': []})
    
    for item in order.order_items.all():
        if item.vendor:
            email = item.vendor.email
            vendor_groups[email]['username'] = item.vendor.username
            vendor_groups[email]['products'].append(item.product.name if item.product else 'Product')

    order_id = order.id

    def send_cancellation_emails():
        for vendor_email, data in vendor_groups.items():
            subject = f"Notice: Order #{order_id} has been Cancelled"
            
            products_list = "".join([f"<li style='margin-bottom: 8px;'>{p}</li>" for p in data['products']])
            
            body = f"""
            <h2 style="margin-top: 0; color: #0f172a; font-size: 20px;">Hello {data['username']},</h2>
            <p style="font-size: 16px; color: #475569;">Order <strong>#{order_id}</strong> has been cancelled by the customer. Please <strong>do not fulfill</strong> the following items:</p>
            
            <div style="background-color: #fff1f2; border-left: 4px solid #e11d48; padding: 15px; margin: 20px 0; border-radius: 0 8px 8px 0;">
                <ul style="color: #9f1239; font-weight: 600; margin: 0; padding-left: 20px;">
                    {products_list}
                </ul>
            </div>
            
            <p style="font-size: 14px; color: #64748b; margin-top: 20px;">If any of these items have already shipped, please contact support immediately.</p>
            """
            
            try:
                html = get_base_template("#E11D48", "Order Cancelled", "❌", body)
                _send_html_email(vendor_email, subject, html)
            except Exception as e:
                logger.error(f"[EMAIL ERROR] ❌ Threaded email failed for order #{order_id}: {e!s}")

    _safe_async_dispatch(send_cancellation_emails)