import uuid
from datetime import datetime

class PaymentGateway:
    @staticmethod
    def process_payment(method, amount, details):
        """
        Simulate payment processing.
        Returns a tuple: (success: bool, transaction_id: str, message: str)
        """
        transaction_id = f"TXN-{uuid.uuid4().hex[:12].upper()}"
        
        # Simulated responses based on inputs
        if method == "COD":
            return True, transaction_id, "Cash on Delivery selected."
            
        elif method == "Wallet":
            return True, transaction_id, f"Wallet debited successfully for amount {amount}."
            
        elif method == "UPI":
            upi_id = details.get('upi_id', '')
            if not upi_id or '@' not in upi_id:
                return False, "", "Invalid UPI ID format."
            return True, transaction_id, "UPI payment authorized successfully."
            
        elif method == "Credit Card" or method == "Debit Card":
            card_num = details.get('card_number', '')
            cvv = details.get('cvv', '')
            if len(card_num.replace(' ', '')) < 15 or len(cvv) < 3:
                return False, "", "Invalid Card Number or CVV."
            return True, transaction_id, "Card payment completed."
            
        elif method == "Net Banking":
            bank = details.get('bank_name', '')
            if not bank:
                return False, "", "Please select a bank."
            return True, transaction_id, "Net Banking transaction authorized."
            
        elif method == "BNPL":
            # Buy Now Pay Later
            return True, transaction_id, "BNPL payment scheme registered."
            
        return False, "", f"Unsupported payment method: {method}"
