class EmailService:
    @staticmethod
    def send_mock_support_email(to_email, subject, body):
        from routes.admin import get_setting
        support_address = get_setting('MARKETPLACE_ADDRESS_SUPPORT', 'VKshop Support Center, 123 E-Commerce Way, Bangalore - 560001')
        email_content = (
            f"From: VKshop Support Team <support@vkshop.com>\n"
            f"To: {to_email}\n"
            f"Subject: {subject}\n"
            f"Body:\n{body}\n\n"
            f"---\n"
            f"Support Office Address:\n{support_address}\n"
            f"========================================"
        )
        print("====== SENDING MOCK SUPPORT EMAIL ======")
        print(email_content)
