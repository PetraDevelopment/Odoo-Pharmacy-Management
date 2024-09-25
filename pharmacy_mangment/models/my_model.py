import base64
import tempfile
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging
from odoo.tools import pdf
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from io import BytesIO
from reportlab.pdfgen import canvas
import base64
from datetime import datetime


_logger = logging.getLogger(__name__)

class MedcineShape(models.Model):
    _name = 'medcine.shape'
    _rec_name = 'medcine_shape_name'

    medcine_shape_name = fields.Char(string='Name')

class EffectiveMaterial(models.Model):
    _name = 'effective.material'
    _rec_name = 'EffectiveMaterial_name'

    EffectiveMaterial_name = fields.Char(string='Name')

class EXTproducttemplate(models.Model):
    _inherit='product.template'

    medcine_shape_id = fields.Many2one('medcine.shape', string='Medicine Shape')
    effective_material_ids = fields.Many2many('effective.material', string='Effective Material')

class QuotationRejectReason(models.Model):
    _name = 'quotation.reject.reason'
    _description = 'quotation_reject_reason'
    _inherit = "mail.thread"

    reason = fields.Char(string='Reject Reason', required=True)
    name = fields.Char(string='Number', required=True)

class PurchaseOrderEXT(models.Model):
    _inherit = 'purchase.order'
    _rec_name = 'ref'

    state = fields.Selection(
        selection_add=[
            ('waiting_for_verify', 'WAITING FOR VERIFY'),
            ('waiting_for_approval', 'APPROVAL')
        ], readonly=True, index=True, copy=False, track_visibility='onchange'
    )

    ref = fields.Char(compute="_set_record_name", store=False)
    
    @api.depends('name', 'state')
    def _set_record_name(self):
        for purchase_order in self:
            if purchase_order.state in ['draft', 'waiting_for_verify', 'waiting_for_approval', 'purchase', 'cancel']:
                name_without_state = purchase_order.name.split('(')[0].strip()
                if purchase_order.state == 'draft':
                    purchase_order.ref = name_without_state + '(draft)'
                elif purchase_order.state == 'waiting_for_verify':
                    purchase_order.ref = name_without_state + '(WAITING FOR VERIFY)'
                elif purchase_order.state == 'waiting_for_approval':
                    purchase_order.ref = name_without_state + '(APPROVAL)'
                elif purchase_order.state == 'purchase':
                    purchase_order.ref = name_without_state + '(purchase)'
                elif purchase_order.state == 'cancel':
                    purchase_order.ref = name_without_state + '(cancel)'

    def submit_for_verify(self):
        for rec in self:
            rec.state = 'waiting_for_verify'

    def submit_for_approval(self):
        for rec in self:
            rec.state = 'waiting_for_approval'
        return {}

    def action_reject_quotation_wizard(self):
        return {
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'reject.reason.wizard',
            'target': 'new',
            'context': {
                'default_reason_reject': ' ',
                'default_name': self.name
            },
        }

    def action_cancel(self):
        return super().action_cancel()

    def reject_approve(self):
        action = self.action_reject_quotation_wizard()
        for rec in self:
            rec.state = 'cancel'
        return action

    def button_confirm(self):
        super(PurchaseOrderEXT, self).button_confirm()
        for rec in self:
            rec.state = 'purchase'
            # Ensure related stock pickings are created and in the right state
            rec._create_picking()
        return {}

    def _create_picking(self):
        for order in self:
            if order.state not in ['purchase', 'done']:
                continue
            # Ensure location_id is set
            if not order.picking_type_id.default_location_src_id:
                default_location = self.env.ref('stock.stock_location_stock', raise_if_not_found=False)
                if not default_location:
                    raise UserError(_('Default source location is not set for the picking type and no global default location found.'))
                _logger.warning('Default source location is not set for the picking type. Using global default location.')
                order.picking_type_id.default_location_src_id = default_location
            order._create_picking_from_order_lines()

    
    def _create_picking_from_order_lines(self):
        if not self.order_line:
            _logger.warning("No order lines found for purchase order %s", self.name)
            return

        for line in self.order_line:
            if line.product_id.type in ['consu', 'product']:
                picking_vals = self._prepare_picking_vals()
                try:
                    picking = self.env['stock.picking'].create(picking_vals)
                    moves = line._prepare_stock_moves(picking)
                    moves = self.env['stock.move'].create(moves)
                    moves._action_confirm()
                    moves._action_assign()
                    picking.action_confirm()
                    picking.action_assign()
                except Exception as e:
                    _logger.error("Error creating picking for line %s in purchase order %s: %s", line.id, self.name, e)


    def _prepare_picking_vals(self):
        return {
            'picking_type_id': self.picking_type_id.id,
            'partner_id': self.partner_id.id,
            'date': self.date_order,
            'origin': self.name,
            'location_dest_id': self.partner_id.property_stock_customer.id,
            'location_id': self.picking_type_id.default_location_src_id.id,
            'company_id': self.company_id.id,
            'purchase_id': self.id,
        }

class RejectReasonWizard(models.TransientModel):
    _name = 'reject.reason.wizard'
    _description = 'Reject Reason Wizard'

    reason_reject = fields.Text(string='Reject Reason', required=True)
    name = fields.Char(string='Purchase Order Reference')

    def action_reject(self):
        purchase_order = self.env['purchase.order'].search([('name', '=', self.name)])
        purchase_order.write({'state': 'cancel'})
        purchase_order.message_post(body='Purchase order rejected for reason: %s' % self.reason_reject)
        


   
    
            
class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'   

    cash_control = fields.Boolean(string="Control Cash Box at openning and closing",store=True)
  
    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        res.update(
            cash_control=self.env['ir.config_parameter'].sudo().get_param('pharmacy_mangment.cash_control', default=False)
        )
        return res

    @api.model
    def set_values(self):
        super(ResConfigSettings, self).set_values()
        try:
            self.env['ir.config_parameter'].sudo().set_param('pharmacy_mangment.cash_control', self.cash_control)
            _logger.info("cash_control value saved successfully")
        except Exception as e:
            _logger.error("Error saving cash_control value: %s", e)

 

    

class CashTransaction(models.Model):
    _name = 'cash.transaction'
    _description = 'Cash Transaction'

    amount = fields.Float(string='Amount')
    reason = fields.Char(string='Reason')
    session_id = fields.Many2one('pos.session', string='POS Session')

class PosSession(models.Model):
    _inherit = 'pos.session'

    ext_session_id = fields.Integer()
      
    
    @api.model
    def print_cash_transaction_in(self, session_ids):
        if not session_ids:
            return

        session = self.browse(session_ids[0])
        ext_session_id = session.id

        # Execute the SQL query to fetch move_line_name and debit
        self.env.cr.execute("""
            SELECT
                aml.name AS move_line_name,
                aml.debit
            FROM
                account_move_line aml
            LEFT JOIN
                account_account aa ON aml.account_id = aa.id
            WHERE
                (aml.name LIKE '%-in-%')
                AND aml.debit != 0
        """)

        query_results = self.env.cr.fetchall()

        # Get company details
        company = self.env.user.company_id
        logo = company.logo
        name = company.name
        phone = company.phone
        email = company.email
        website = company.website

        # Prepare the PDF
        buffer = BytesIO()
        page_height = 600  # Height of the page
        width = 280    # Receipt width in points (80mm)
        margin_top = 20  # Margin at the top of each page
        content_start_y = page_height - margin_top  # Starting Y position for content
        p = canvas.Canvas(buffer, pagesize=(width, page_height))

        # Helper function to center text
        def draw_centered_text(text, y_position, font_size=10, font_name="Helvetica"):
            p.setFont(font_name, font_size)
            text_width = p.stringWidth(text, font_name, font_size)
            p.drawString((width - text_width) / 2, y_position, text)
            return y_position

        # Helper function to center a block of text with spacing
        def draw_centered_text_block(lines, y_position, font_size=10, font_name="Helvetica", before_space=15, after_space=15):
            p.setFont(font_name, font_size)
            y_position -= before_space
            for line in lines:
                p.drawString((width - p.stringWidth(line, font_name, font_size)) / 2, y_position, line)
                y_position -= 15  # Line spacing for each line
            y_position -= after_space
            return y_position

        # Helper function to wrap text to fit within the receipt width
        def wrap_text(text, max_characters):
            lines = []
            while len(text) > max_characters:
                space_index = text.rfind(' ', 0, max_characters)
                if space_index == -1:
                    space_index = max_characters
                lines.append(text[:space_index])
                text = text[space_index:].strip()
            lines.append(text)
            return lines

        # Helper function to draw a line
        def draw_line(start_x, y_position, line_length):
            p.setLineWidth(1.0)
            p.setStrokeColorRGB(0, 0, 0)
            p.line(start_x, y_position, start_x + line_length, y_position)

        def add_new_page():
            nonlocal height
            p.showPage()
            height = content_start_y  # Reset height to start below the margin at the top of the page
            height -= 20  # Add space at the beginning of each new page

        # Add company logo
        if logo:
            logo_data = base64.b64decode(logo)
            with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmpfile:
                tmpfile.write(logo_data)
                tmpfile.flush()
                logo_path = tmpfile.name
            logo_width = 80
            logo_height = 30
            p.drawImage(logo_path, (width - logo_width) / 2, content_start_y - logo_height, width=logo_width, height=logo_height)
            height = content_start_y - (logo_height + 20)
        else:
            height = draw_centered_text(name, content_start_y, font_size=14, font_name="Helvetica-Bold")
            height -= 10

        details = [line for line in [name, f"Tel: {phone}", f"Email: {email}", f"Website: {website}"] if line]
        height = draw_centered_text_block(details, height, font_size=10, font_name="Helvetica", before_space=10, after_space=10)

        # Add current date on the left and session ID on the right
        current_date = datetime.now().strftime("%Y-%m-%d")
        p.setFont("Helvetica", 10)
        p.drawString(20, height, f"Date: {current_date}")  # Date on the left
        p.drawString(width - 20 - p.stringWidth(f"Session ID {ext_session_id}"), height, f"Session ID {ext_session_id}")  # Session ID on the right
        height -= 20  # Space after date and session ID

        # Add title - Centered
        title = "Cash In Statement"
        height = draw_centered_text(title, height, font_size=12, font_name="Helvetica-Bold")
        height -= 15  # Space after title

        p.setFont("Helvetica", 9)

        for result in query_results:
            move_line_name, debit = result

            # Split move_line_name into parts using '-' as delimiter
            parts = move_line_name.split('-')
            if len(parts) >= 3:
                real_session_id = parts[0].split('/')[-1].lstrip('0')  
                state = parts[1]  
                reason = '-'.join(parts[2:])  
            else:
                real_session_id = ""
                state = ""
                reason = ""

            # Check if ext_session_id matches real_session_id
            if ext_session_id == int(real_session_id) and state == 'in':
                wrapped_reason_lines = wrap_text(reason, 30)  # Wrap reason at 30 characters
                y_position = height

                required_space = 50 + 15 * len(wrapped_reason_lines)  # Calculate required space for the current entry

                if y_position - required_space < 30:  # Check if there’s enough space for the content
                    add_new_page()

                p.setFont("Helvetica-Bold", 10)
                p.drawString(20, height, "Reason:")
                p.setFont("Helvetica", 10)
                for line in wrapped_reason_lines:
                    p.drawString(80, height, line)
                    height -= 15  # Line spacing for each wrapped line

                height -= 15  # Move down for the amount text
                p.setFont("Helvetica-Bold", 10)
                p.drawString(20, height, "Amount:")
                p.setFont("Helvetica", 10)
                p.drawString(80, height, str(debit))

                height -= 15  # Add some space before the line
                draw_line(20, height, width - 40)  # Draw a line after the amount

                height -= 15  # Add some space before the next entry

        p.save()
        pdf_output = buffer.getvalue()
        buffer.close()

        # Create the attachment
        attachment_id = self.env['ir.attachment'].create({
            'name': f'Cash_In_Transactions_{ext_session_id}.pdf',
            'type': 'binary',
            'datas': base64.b64encode(pdf_output),
            'res_model': 'pos.session',
            'res_id': ext_session_id,
            'mimetype': 'application/pdf',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment_id.id,
            'target': 'new',
        }



    @api.model
    def print_cash_transaction_out(self, session_ids):
        if not session_ids:
            return

        session = self.browse(session_ids[0])
        ext_session_id = session.id

        # Execute the SQL query to fetch move_line_name and credit
        self.env.cr.execute("""
            SELECT
                aml.name AS move_line_name,
                aml.credit
            FROM
                account_move_line aml
            LEFT JOIN
                account_account aa ON aml.account_id = aa.id
            WHERE
                (aml.name LIKE '%-out-%')
                AND aml.credit != 0
        """)

        query_results = self.env.cr.fetchall()

        # Get company details
        company = self.env.user.company_id
        logo = company.logo
        name = company.name
        phone = company.phone
        email = company.email
        website = company.website

        # Prepare the PDF
        buffer = BytesIO()
        page_height = 600  # Height of the page
        width = 280    # Receipt width in points (80mm)
        margin_top = 20  # Margin at the top of each page
        content_start_y = page_height - margin_top  # Starting Y position for content
        p = canvas.Canvas(buffer, pagesize=(width, page_height))

        # Helper function to center text
        def draw_centered_text(text, y_position, font_size=10, font_name="Helvetica"):
            p.setFont(font_name, font_size)
            text_width = p.stringWidth(text, font_name, font_size)
            p.drawString((width - text_width) / 2, y_position, text)
            return y_position

        # Helper function to center a block of text with spacing
        def draw_centered_text_block(lines, y_position, font_size=10, font_name="Helvetica", before_space=15, after_space=15):
            p.setFont(font_name, font_size)
            y_position -= before_space
            for line in lines:
                p.drawString((width - p.stringWidth(line, font_name, font_size)) / 2, y_position, line)
                y_position -= 15  # Line spacing for each line
            y_position -= after_space
            return y_position

        # Helper function to wrap text to fit within the receipt width
        def wrap_text(text, max_characters):
            lines = []
            while len(text) > max_characters:
                space_index = text.rfind(' ', 0, max_characters)
                if space_index == -1:
                    space_index = max_characters
                lines.append(text[:space_index])
                text = text[space_index:].strip()
            lines.append(text)
            return lines

        # Helper function to draw a line
        def draw_line(start_x, y_position, line_length):
            p.setLineWidth(1.0)
            p.setStrokeColorRGB(0, 0, 0)
            p.line(start_x, y_position, start_x + line_length, y_position)

        def add_new_page():
            nonlocal height
            p.showPage()
            height = content_start_y  # Reset height to start below the margin at the top of the page
            height -= 20  # Add space at the beginning of each new page

        # Add company logo
        if logo:
            logo_data = base64.b64decode(logo)
            with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmpfile:
                tmpfile.write(logo_data)
                tmpfile.flush()
                logo_path = tmpfile.name
            logo_width = 80
            logo_height = 30
            p.drawImage(logo_path, (width - logo_width) / 2, content_start_y - logo_height, width=logo_width, height=logo_height)
            height = content_start_y - (logo_height + 20)
        else:
            height = draw_centered_text(name, content_start_y, font_size=14, font_name="Helvetica-Bold")
            height -= 10

        details = [line for line in [name, f"Tel: {phone}", f"Email: {email}", f"Website: {website}"] if line]
        height = draw_centered_text_block(details, height, font_size=10, font_name="Helvetica", before_space=10, after_space=10)

        # Add current date on the left and session ID on the right
        current_date = datetime.now().strftime("%Y-%m-%d")
        p.setFont("Helvetica", 10)
        p.drawString(20, height, f"Date: {current_date}")  # Date on the left
        p.drawString(width - 20 - p.stringWidth(f"Session ID {ext_session_id}"), height, f"Session ID {ext_session_id}")  # Session ID on the right
        height -= 20  # Space after date and session ID

        # Add title - Centered
        title = "Cash Out Statement"
        height = draw_centered_text(title, height, font_size=12, font_name="Helvetica-Bold")
        height -= 15  # Space after title

        p.setFont("Helvetica", 9)

        for result in query_results:
            move_line_name, credit = result

            # Split move_line_name into parts using '-' as delimiter
            parts = move_line_name.split('-')
            if len(parts) >= 3:
                real_session_id = parts[0].split('/')[-1].lstrip('0')  # Extract '20' from 'POS/000020-out-noooo'
                state = parts[1]  # Extract 'out' from 'POS/000020-out-noooo'
                reason = '-'.join(parts[2:])  # Extract 'noooo' from 'POS/000020-out-noooo'
            else:
                real_session_id = ""
                state = ""
                reason = ""

            # Check if ext_session_id matches real_session_id
            if ext_session_id == int(real_session_id) and state == 'out':
                wrapped_reason_lines = wrap_text(reason, 30)  # Wrap reason at 30 characters
                y_position = height

                required_space = 50 + 15 * len(wrapped_reason_lines)  # Calculate required space for the current entry

                if y_position - required_space < 30:  # Check if there’s enough space for the content
                    add_new_page()

                p.setFont("Helvetica-Bold", 10)
                p.drawString(20, height, "Reason:")
                p.setFont("Helvetica", 10)
                for line in wrapped_reason_lines:
                    p.drawString(80, height, line)
                    height -= 15  # Line spacing for each wrapped line

                height -= 15  # Move down for the amount text
                p.setFont("Helvetica-Bold", 10)
                p.drawString(20, height, "Amount:")
                p.setFont("Helvetica", 10)
                p.drawString(80, height, str(credit))

                height -= 15  # Add some space before the line
                draw_line(20, height, width - 40)  # Draw a line after the amount

                height -= 15  # Add some space before the next entry

        p.save()
        pdf_output = buffer.getvalue()
        buffer.close()

        # Create the attachment
        attachment_id = self.env['ir.attachment'].create({
            'name': f'Cash_Out_Transactions_{ext_session_id}.pdf',
            'type': 'binary',
            'datas': base64.b64encode(pdf_output),
            'res_model': 'pos.session',
            'res_id': ext_session_id,
            'mimetype': 'application/pdf',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment_id.id,
            'target': 'new',
        }


    
    @api.model
    def print_cash_transaction_in_outs(self, session_ids):
        if not session_ids:
            return

        session = self.browse(session_ids[0])
        ext_session_id = session.id
        session_date = session.start_at.strftime('%Y-%m-%d')  # Use start_at to get the session start date
        session_id_str = str(ext_session_id)

        # Execute the SQL query to fetch move_line_name, debit, credit, and balance
        self.env.cr.execute("""
            SELECT
                aml.name AS move_line_name,
                aml.debit,
                aml.credit,
                aml.debit - aml.credit AS balance
            FROM
                account_move_line aml
            LEFT JOIN
                account_account aa ON aml.account_id = aa.id
            WHERE
                (aml.debit != 0 AND aml.name LIKE '%-in-%') OR
                (aml.credit != 0 AND aml.name LIKE '%-out-%')
            ORDER BY
                aml.name ASC;
        """)
        query_results = self.env.cr.fetchall()
        _logger.info('Query Results: %s', query_results)

        # Get company details
        company = self.env.user.company_id
        logo = company.logo
        name = company.name
        phone = company.phone
        email = company.email
        website = company.website
        _logger.info('Company Details: name=%s, phone=%s, email=%s, website=%s', name, phone, email, website)

        # Prepare the PDF
        buffer = BytesIO()
        height = 510  # Increased height of the page (15 cm + 20%)
        width = 280    # Receipt width in points (80mm)
        p = canvas.Canvas(buffer, pagesize=(width, height))

        # Helper functions
        def draw_centered_text(text, y_position, font_size=10, font_name="Helvetica"):
            p.setFont(font_name, font_size)
            text_width = p.stringWidth(text, font_name, font_size)
            p.drawString((width - text_width) / 2, y_position, text)
            return y_position

        def draw_centered_text_block(lines, y_position, font_size=10, font_name="Helvetica", before_space=15, after_space=15):
            p.setFont(font_name, font_size)
            y_position -= before_space
            for line in lines:
                p.drawString((width - p.stringWidth(line, font_name, font_size)) / 2, y_position, line)
                y_position -= 15
            y_position -= after_space
            return y_position

        def wrap_text(text, max_characters):
            lines = []
            while len(text) > max_characters:
                space_index = text.rfind(' ', 0, max_characters)
                if space_index == -1:
                    space_index = max_characters
                lines.append(text[:space_index])
                text = text[space_index:].strip()
            lines.append(text)
            return lines

        def draw_black_line(start_x, y_position, line_length):
            p.setLineWidth(1.0)
            p.setStrokeColorRGB(0, 0, 0)
            p.line(start_x, y_position, start_x + line_length, y_position)

        def add_page(is_first_page=False):
            nonlocal height
            p.showPage()
            height = 510  # Reset height to full page height
            if is_first_page:
                # Adding a small space at the beginning of the new page
                height -= 30  # Adjust this value to set the space you want (30 points = 1.5/4 inch)
                draw_table_headers()
            else:
                height -= 10  # Add a small white space for subsequent pages
            return height

        def draw_table_headers():
            p.setFont("Helvetica-Bold", 10)
            p.drawString(20, height - 20, "Reason")
            p.drawString(140, height - 20, "Debit")
            p.drawString(180, height - 20, "Credit")
            p.drawString(220, height - 20, "Balance")
            draw_black_line(0, height - 30, width)  # Draw black line under the headers
            return height - 45  # Adjusted this value to leave extra space for the content below the line

        # Draw initial header with company info
        if logo:
            logo_data = base64.b64decode(logo)
            with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmpfile:
                tmpfile.write(logo_data)
                tmpfile.flush()
                logo_path = tmpfile.name
            logo_width = 80
            logo_height = 30
            p.drawImage(logo_path, (width - logo_width) / 2, height - logo_height - 20, width=logo_width, height=logo_height)
            height -= (logo_height + 20)
        else:
            height = draw_centered_text(name, height, font_size=14, font_name="Helvetica-Bold")
            height -= 10

        details = [line for line in [name, f"Tel: {phone}", f"Email: {email}", f"Website: {website}"] if line]
        height = draw_centered_text_block(details, height, font_size=10, font_name="Helvetica", before_space=10, after_space=10)

        # Draw Date and Session ID with bold labels before the title
        p.setFont("Helvetica-Bold", 10)
        p.drawString(20, height, f"Date: {session_date}")
        p.drawString(160, height, f"Session ID: {session_id_str}")  # Position Session ID at the right side of the page
        height -= 20  # Adjust height for the labels

        title = "Cash IN/OUT Statement"
        height = draw_centered_text(title, height, font_size=12, font_name="Helvetica-Bold")
        height -= 15

        # Draw table headers only on the first page
        height = draw_table_headers()

        p.setFont("Helvetica", 9)
        total_debit = 0
        total_credit = 0
        total_balance = 0  # Initialize total balance

        reason_column_width = 12  # Adjusted to fit text and keep the balance column
        debit_column_x = 140
        credit_column_x = 180
        balance_column_x = 220

        for result in query_results:
            move_line_name, debit, credit, balance = result

            parts = move_line_name.split('-')
            if len(parts) >= 3:
                real_session_id = parts[0].split('/')[-1].lstrip('0')
                state = parts[1]
                reason = '-'.join(parts[2:])
            else:
                real_session_id = ""
                state = ""
                reason = ""

            _logger.info('Processing move_line_name=%s, real_session_id=%s, state=%s, reason=%s', move_line_name, real_session_id, state, reason)

            if ext_session_id == int(real_session_id):
                wrapped_reason_lines = wrap_text(reason, reason_column_width)  # Wrap reason at 12 characters
                y_position = height

                if y_position - 10 * len(wrapped_reason_lines) < 30:  # Check if there’s enough space for the content
                    height = add_page(is_first_page=False)

                for line in wrapped_reason_lines:
                    p.drawString(20, height, line)  # Draw reason
                    height -= 10

                p.drawString(debit_column_x, height + (10 * len(wrapped_reason_lines)), str(debit))
                p.drawString(credit_column_x, height + (10 * len(wrapped_reason_lines)), str(credit))
                p.drawString(balance_column_x, height + (10 * len(wrapped_reason_lines)), str(balance))

                total_debit += debit
                total_credit += credit
                total_balance += balance  # Sum up the balances

                height -= 5

        draw_black_line(20, height, width - 40)

        p.setFont("Helvetica-Bold", 9)
        p.drawString(20, height - 10, "Total")
        p.drawString(debit_column_x, height - 10, str(total_debit))
        p.drawString(credit_column_x, height - 10, str(total_credit))
        p.drawString(balance_column_x, height - 10, str(total_balance))  # Total Balance

        p.save()
        pdf_output = buffer.getvalue()
        buffer.close()

        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
        temp_file.write(pdf_output)
        temp_file.close()

        attachment_id = self.env['ir.attachment'].create({
            'name': 'Cash_Transaction_In_Out_Statement.pdf',
            'type': 'binary',
            'datas': base64.b64encode(pdf_output),
            'res_model': 'pos.session',
            'res_id': ext_session_id,
            'mimetype': 'application/pdf',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment_id.id,
            'target': 'new',
        }
