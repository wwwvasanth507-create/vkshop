import io
import os
from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from config import Config

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

class SellerPdfService:
    @staticmethod
    def generate_seller_profile_pdf(store):
        buffer = io.BytesIO()
        # Create PDF document template with 0.5 inch margins
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36
        )
        
        styles = getSampleStyleSheet()
        
        title_style = ParagraphStyle(
            'PdfTitle',
            parent=styles['Heading1'],
            fontName='Helvetica-Bold',
            fontSize=22,
            textColor=colors.HexColor('#1E3A8A'),
            spaceAfter=15
        )
        
        section_style = ParagraphStyle(
            'PdfSection',
            parent=styles['Heading2'],
            fontName='Helvetica-Bold',
            fontSize=13,
            textColor=colors.HexColor('#1E3A8A'),
            spaceBefore=10,
            spaceAfter=5
        )
        
        normal_style = ParagraphStyle(
            'PdfNormal',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=10,
            textColor=colors.HexColor('#374151'),
            spaceAfter=4,
            leading=14
        )
        
        bold_style = ParagraphStyle(
            'PdfBold',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=10,
            textColor=colors.HexColor('#111827'),
            spaceAfter=4
        )
        
        elements = []
        
        # Document Title
        elements.append(Paragraph("Merchant Onboarding & Verification Report", title_style))
        elements.append(Spacer(1, 10))
        
        # Section 1: Store details
        elements.append(Paragraph("Store Information", section_style))
        store_details = [
            [Paragraph("<b>Store Name:</b>", normal_style), Paragraph(store.name, normal_style)],
            [Paragraph("<b>Description:</b>", normal_style), Paragraph(store.description or "N/A", normal_style)],
            [Paragraph("<b>Status:</b>", normal_style), Paragraph(store.status, normal_style)],
            [Paragraph("<b>Store Rating:</b>", normal_style), Paragraph(f"{store.rating:.1f} / 5.0", normal_style)],
            [Paragraph("<b>GST / Tax Registration:</b>", normal_style), Paragraph(store.tax_number or "Not Available", normal_style)],
            [Paragraph("<b>UPI ID:</b>", normal_style), Paragraph(store.upi_id or "Not Available", normal_style)],
            [Paragraph("<b>Store Address:</b>", normal_style), Paragraph((store.store_address or "Not Available").replace('\n', '<br/>'), normal_style)],
            [Paragraph("<b>Store Contact:</b>", normal_style), Paragraph(store.store_contact or "Not Available", normal_style)],
        ]
        t1 = Table(store_details, colWidths=[150, 390])
        t1.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('LINEBELOW', (0,0), (-1,-1), 0.5, colors.HexColor('#E5E7EB')),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('TOPPADDING', (0,0), (-1,-1), 4),
        ]))
        elements.append(t1)
        elements.append(Spacer(1, 12))
        
        # Section 2: Owner details
        elements.append(Paragraph("Owner & Contact Details", section_style))
        owner_details = [
            [Paragraph("<b>Owner Username:</b>", normal_style), Paragraph(store.user.username, normal_style)],
            [Paragraph("<b>Owner Email:</b>", normal_style), Paragraph(store.user.email, normal_style)],
            [Paragraph("<b>Bank Details:</b>", normal_style), Paragraph("Not Available", normal_style)],
        ]
        t2 = Table(owner_details, colWidths=[150, 390])
        t2.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('LINEBELOW', (0,0), (-1,-1), 0.5, colors.HexColor('#E5E7EB')),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('TOPPADDING', (0,0), (-1,-1), 4),
        ]))
        elements.append(t2)
        elements.append(Spacer(1, 12))
        
        # Section 3: Identity Verification (Aadhaar details & images)
        elements.append(Paragraph("Identity Proof Details", section_style))
        elements.append(Paragraph(f"<b>Aadhaar Number:</b> {store.aadhaar_number or 'N/A'}", normal_style))
        elements.append(Spacer(1, 6))
        
        img_row = []
        if store.aadhaar_front:
            front_path = os.path.join(Config.USER_UPLOADS, store.aadhaar_front)
            if os.path.exists(front_path):
                try:
                    img_row.append(RLImage(front_path, width=250, height=150))
                except Exception:
                    img_row.append(Paragraph("[Aadhaar Front Image Error]", normal_style))
            else:
                img_row.append(Paragraph("[Aadhaar Front File Missing]", normal_style))
        else:
            img_row.append(Paragraph("Aadhaar Front: Not Uploaded", normal_style))
            
        if store.aadhaar_back:
            back_path = os.path.join(Config.USER_UPLOADS, store.aadhaar_back)
            if os.path.exists(back_path):
                try:
                    img_row.append(RLImage(back_path, width=250, height=150))
                except Exception:
                    img_row.append(Paragraph("[Aadhaar Back Image Error]", normal_style))
            else:
                img_row.append(Paragraph("[Aadhaar Back File Missing]", normal_style))
        else:
            img_row.append(Paragraph("Aadhaar Back: Not Uploaded", normal_style))
            
        t_imgs = Table([img_row], colWidths=[270, 270])
        t_imgs.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ]))
        elements.append(t_imgs)
        elements.append(Spacer(1, 12))
        
        # Section 4: Owner Photo & Signature
        elements.append(Paragraph("Verification Documents & Onboarding Signature", section_style))
        
        photo_sig_row = []
        if store.photo:
            photo_path = os.path.join(Config.USER_UPLOADS, store.photo)
            if os.path.exists(photo_path):
                try:
                    photo_sig_row.append(RLImage(photo_path, width=120, height=120))
                except Exception:
                    photo_sig_row.append(Paragraph("[Owner Photo Image Error]", normal_style))
            else:
                photo_sig_row.append(Paragraph("[Owner Photo File Missing]", normal_style))
        else:
            photo_sig_row.append(Paragraph("Photo: Not Uploaded", normal_style))
            
        if store.signature:
            sig_path = os.path.join(Config.USER_UPLOADS, store.signature)
            if os.path.exists(sig_path):
                try:
                    photo_sig_row.append(RLImage(sig_path, width=160, height=50))
                except Exception:
                    photo_sig_row.append(Paragraph("[Signature Image Error]", normal_style))
            else:
                photo_sig_row.append(Paragraph("[Signature File Missing]", normal_style))
        else:
            photo_sig_row.append(Paragraph("Signature: Not Uploaded", normal_style))
            
        t_photo_sig = Table([photo_sig_row], colWidths=[270, 270])
        t_photo_sig.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ]))
        elements.append(t_photo_sig)
        elements.append(Spacer(1, 10))
        
        # Legal Signature Disclaimer
        elements.append(Paragraph("Legal Agreement & Signed Declaration", section_style))
        declaration_text = (
            "<b>Legal Declaration Statement:</b><br/>"
            "<i>\"I hereby acknowledge and agree that if I engage in any fraudulent activity or commit any "
            "misconduct on this platform, the website administrators have the full right to initiate legal "
            "proceedings against me, including filing a First Information Report (FIR) with the police.\"</i>"
        )
        elements.append(Paragraph(declaration_text, normal_style))
        
        signed_text = "<b>Status:</b> Digitally Agreed & Checked during seller registration." if store.agreed_to_terms else "<b>Status:</b> Not Agreed"
        elements.append(Paragraph(signed_text, normal_style))
        
        # Build Document
        doc.build(elements, onFirstPage=draw_pdf_watermark, onLaterPages=draw_pdf_watermark)
        buffer.seek(0)
        return buffer
