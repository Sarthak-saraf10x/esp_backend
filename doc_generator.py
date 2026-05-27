import os
from docx import Document
from fpdf import FPDF
import re

def markdown_to_text(md_string):
    """A simple markdown stripper for clean documents."""
    # Remove bold/italic asterisks
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', md_string)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    # Remove # headers
    text = re.sub(r'#+\s(.*)', r'\1', text)
    return text

def generate_docx(title, content, output_dir="documents"):
    os.makedirs(output_dir, exist_ok=True)
    filename = f"{title.replace(' ', '_')}.docx"
    filepath = os.path.join(output_dir, filename)
    
    doc = Document()
    doc.add_heading(title, 0)
    
    # Simple split by double newlines for paragraphs
    paragraphs = content.split('\n\n')
    for p in paragraphs:
        clean_p = p.strip()
        if not clean_p:
            continue
        if clean_p.startswith('- ') or clean_p.startswith('* '):
            # It's a list item
            doc.add_paragraph(markdown_to_text(clean_p[2:]).strip(), style='List Bullet')
        else:
            doc.add_paragraph(markdown_to_text(clean_p))
            
    doc.save(filepath)
    return filepath

def generate_pdf(title, content, output_dir="documents"):
    os.makedirs(output_dir, exist_ok=True)
    filename = f"{title.replace(' ', '_')}.pdf"
    filepath = os.path.join(output_dir, filename)
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", size=16, style='B')
    pdf.cell(0, 10, text=title, new_x="LMARGIN", new_y="NEXT", align='C')
    pdf.ln(10)
    
    pdf.set_font("helvetica", size=12)
    paragraphs = content.split('\n\n')
    for p in paragraphs:
        clean_p = markdown_to_text(p.strip())
        if not clean_p:
            continue
        # FPDF2 supports unicode better natively
        pdf.multi_cell(0, 7, text=clean_p)
        pdf.ln(3)
        
    pdf.output(filepath)
    return filepath
