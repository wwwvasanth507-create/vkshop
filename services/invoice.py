import io
import os
from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

def draw_pdf_watermark(canvas, doc):
    canvas.saveState()
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    logo_path = os.path.join(base_dir, "static", "logo.jpeg")
    watermark_path = os.path.join(base_dir, "static", "logo_watermark.png")
    
    if os.path.exists(logo_path):
        if not os.path.exists(watermark_path):
            try:
                img = Image.open(logo_path).convert("RGBA")
                alpha = img.split()[3]
                new_alpha = alpha.point(lambda i: int(i * 0.05))
                img.putalpha(new_alpha)
                img.save(watermark_path, "PNG")
            except Exception:
                pass
        
        if os.path.exists(watermark_path):
            w, h = 350, 350
            x = (612 - w) / 2
            y = (792 - h) / 2
            canvas.drawImage(watermark_path, x, y, width=w, height=h, mask='auto')
    canvas.restoreState()


class InvoiceService:
    @staticmethod
    def generate_invoice_pdf(order):
        """
        Generates a PDF invoice as an in-memory byte buffer for an order.
        """
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36
        )
        
        styles = getSampleStyleSheet()
        
        # Custom styles
        title_style = ParagraphStyle(
            'InvoiceTitle',
            parent=styles['Heading1'],
            fontName='Helvetica-Bold',
            fontSize=24,
            textColor=colors.HexColor('#111827'), # Dark gray
            spaceAfter=15
        )
        
        normal_style = ParagraphStyle(
            'InvoiceNormal',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=10,
            textColor=colors.HexColor('#374151'),
            spaceAfter=5
        )
        
        bold_style = ParagraphStyle(
            'InvoiceBold',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=10,
            textColor=colors.HexColor('#111827'),
            spaceAfter=5
        )

        elements = []
        
        # Fetch Marketplace Invoice Address and Support Email dynamically
        from routes.admin import get_setting
        m_address_invoice = get_setting('MARKETPLACE_ADDRESS_INVOICE', '123 Innovation Way, Tech Park\nBangalore, KA 560001')
        m_address_invoice_html = m_address_invoice.replace('\n', '<br/>')
        support_email = get_setting('SUPPORT_OFFICIAL_EMAIL', 'support@vkshop.com')
        
        store_address = f"<b>VKshop Marketplace</b><br/>{m_address_invoice_html}<br/>Support: {support_email}"
        invoice_details = (
            f"<b>Invoice Number:</b> {order.order_number}<br/>"
            f"<b>Date:</b> {order.created_at.strftime('%Y-%m-%d %H:%M')}<br/>"
            f"<b>Payment Method:</b> {order.payment.payment_method if order.payment else 'N/A'}<br/>"
            f"<b>Payment Status:</b> {order.payment.status if order.payment else 'Pending'}"
        )
        
        header_table_data = [
            [Paragraph(store_address, normal_style), Paragraph(invoice_details, normal_style)]
        ]
        
        header_table = Table(header_table_data, colWidths=[270, 270])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('ALIGN', (1,0), (1,0), 'RIGHT')
        ]))
        elements.append(header_table)
        elements.append(Spacer(1, 20))
        
        # Divider
        divider = Table([[""]], colWidths=[540])
        divider.setStyle(TableStyle([
            ('LINEBELOW', (0,0), (-1,-1), 1, colors.HexColor('#E5E7EB')),
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
            ('TOPPADDING', (0,0), (-1,-1), 0),
        ]))
        elements.append(divider)
        elements.append(Spacer(1, 15))
        
        # Billing Address Details
        shipping_title = Paragraph("<b>Ship To:</b>", bold_style)
        if order.address:
            addr = order.address
            address_info = f"{addr.fullName}<br/>{addr.addressLine1}<br/>"
            if addr.addressLine2:
                address_info += f"{addr.addressLine2}<br/>"
            address_info += f"{addr.city}, {addr.state} - {addr.postalCode}<br/>Phone: {addr.phone}"
        else:
            address_info = "Customer Address Details Unavailable"
            
        elements.append(shipping_title)
        elements.append(Paragraph(address_info, normal_style))
        elements.append(Spacer(1, 20))
        
        # Items Table Header & Content
        table_data = [
            [
                Paragraph("<b>Item Description</b>", bold_style),
                Paragraph("<b>Qty</b>", bold_style),
                Paragraph("<b>Unit Price</b>", bold_style),
                Paragraph("<b>Total</b>", bold_style)
            ]
        ]
        
        for item in order.items:
            variant_desc = f" ({item.variant_details})" if item.variant_details else ""
            item_desc = f"{item.product_name}{variant_desc}"
            table_data.append([
                Paragraph(item_desc, normal_style),
                Paragraph(str(item.quantity), normal_style),
                Paragraph(f"INR {item.unit_price:.2f}", normal_style),
                Paragraph(f"INR {item.total_price:.2f}", normal_style)
            ])
            
        items_table = Table(table_data, colWidths=[280, 50, 100, 110])
        items_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#F9FAFB')),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F3F4F6')]),
            ('BOTTOMPADDING', (0,0), (-1,-1), 8),
            ('TOPPADDING', (0,0), (-1,-1), 8),
            ('LINEBELOW', (0,0), (-1,-1), 0.5, colors.HexColor('#E5E7EB')),
        ]))
        elements.append(items_table)
        elements.append(Spacer(1, 20))
        
        # Summary Area Table
        summary_data = [
            ["Subtotal:", f"INR {order.total_amount:.2f}"],
            ["Discount:", f"- INR {order.discount_amount:.2f}"],
            ["Tax Amount:", f"INR {order.tax_amount:.2f}"],
            ["Shipping Charges:", f"INR {order.shipping_charges:.2f}"],
        ]
        
        if order.wallet_deduction > 0:
            summary_data.append(["Wallet Used:", f"- INR {order.wallet_deduction:.2f}"])
        if order.reward_points_deduction > 0:
            summary_data.append(["Reward points:", f"- INR {order.reward_points_deduction:.2f}"])
            
        summary_data.append(["Grand Total:", f"INR {order.grand_total:.2f}"])
        
        summary_table_data = []
        for label, val in summary_data:
            style = bold_style if label == "Grand Total:" else normal_style
            summary_table_data.append([
                Paragraph(f"<b>{label}</b>" if label == "Grand Total:" else label, style),
                Paragraph(f"<b>{val}</b>" if label == "Grand Total:" else val, style)
            ])
            
        summary_table = Table(summary_table_data, colWidths=[380, 160])
        summary_table.setStyle(TableStyle([
            ('ALIGN', (1,0), (1,-1), 'RIGHT'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('LINEBELOW', (0,-1), (-1,-1), 1.5, colors.HexColor('#111827')),
        ]))
        elements.append(summary_table)
        elements.append(Spacer(1, 20))
        
        # Add Store/Seller Details section
        elements.append(Paragraph("<b>Seller / Store Information:</b>", bold_style))
        elements.append(Spacer(1, 5))
        
        unique_stores = {}
        for item in order.items:
            if item.product and item.product.store:
                st = item.product.store
                unique_stores[st.id] = st
                
        store_elements_data = []
        for st in unique_stores.values():
            st_address = getattr(st, 'store_address', '') or "Not Available"
            st_contact = getattr(st, 'store_contact', '') or "Not Available"
            st_tax = st.tax_number or "Not Available"
            st_upi = st.upi_id or "Not Available"
            
            # Re-format newlines in store address to HTML breaks
            st_address_html = st_address.replace('\n', '<br/>')
            
            store_info_text = (
                f"<b>Store Name:</b> {st.name}<br/>"
                f"<b>Store Address:</b> {st_address_html}<br/>"
                f"<b>Contact Information:</b> {st_contact}<br/>"
                f"<b>GST/Tax Number:</b> {st_tax} | <b>UPI ID:</b> {st_upi} | <b>Rating:</b> {st.rating:.1f}/5.0"
            )
            store_elements_data.append([Paragraph(store_info_text, normal_style)])
            
        store_table = Table(store_elements_data, colWidths=[540])
        store_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F9FAFB')),
            ('BORDER', (0,0), (-1,-1), 1, colors.HexColor('#E5E7EB')),
            ('TOPPADDING', (0,0), (-1,-1), 8),
            ('BOTTOMPADDING', (0,0), (-1,-1), 8),
            ('LEFTPADDING', (0,0), (-1,-1), 10),
            ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ]))
        elements.append(store_table)
        elements.append(Spacer(1, 20))
        
        # Footer Note
        footer_note = "Thank you for shopping with VKshop! This is a computer-generated invoice and does not require a physical signature."
        elements.append(Paragraph(f"<font color='#9CA3AF' size='8'><i>{footer_note}</i></font>", normal_style))
        
        # Build Document
        doc.build(elements, onFirstPage=draw_pdf_watermark, onLaterPages=draw_pdf_watermark)
        buffer.seek(0)
        return buffer
