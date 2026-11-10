
import unittest

from ticket_fulfillment import validate_paypal_capture


class CaptureValidationTests(unittest.TestCase):

    def setUp(self):
        self.order = {
            "id": "TEST_ORDER_001",
            "status": "COMPLETED",
            "purchase_units": [
                {
                    "custom_id": "reservation_001",
                    "payments": {
                        "captures": [
                            {
                                "id": "TEST_CAPTURE_001",
                                "status": "COMPLETED",
                                "amount": {
                                    "currency_code": "USD",
                                    "value": "20.00"
                                }
                            }
                        ]
                    }
                }
            ]
        }

    def test_valid_capture(self):
        capture_id = validate_paypal_capture(
            self.order,
            "TEST_ORDER_001",
            "reservation_001",
            2000
        )

        self.assertEqual(
            capture_id,
            "TEST_CAPTURE_001"
        )

    def test_wrong_amount_rejected(self):
        with self.assertRaises(ValueError):
            validate_paypal_capture(
                self.order,
                "TEST_ORDER_001",
                "reservation_001",
                2500
            )

    def test_pending_capture_rejected(self):
        self.order["purchase_units"][0][
            "payments"
        ]["captures"][0]["status"] = "PENDING"

        with self.assertRaises(ValueError):
            validate_paypal_capture(
                self.order,
                "TEST_ORDER_001",
                "reservation_001",
                2000
            )


if __name__ == "__main__":
    unittest.main()
