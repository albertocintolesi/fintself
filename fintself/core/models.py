import re
from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional, List

from pydantic import BaseModel, Field, field_validator

AccountType = Literal["corriente", "credito", "debito", "prepago"]


class MovementModel(BaseModel):
    """
    Pydantic model to represent a bank movement.
    """

    date: datetime = Field(..., description="Date of the movement.")
    description: str = Field(..., description="Description of the movement.")
    amount: Decimal = Field(
        ...,
        description="Amount of the movement (positive for income, negative for expenses).",
    )
    currency: str = Field(...,
                          description="Currency of the movement (e.g., CLP, USD).")
    transaction_type: Optional[str] = Field(
        None, description="Type of transaction (e.g., 'Debit', 'Credit', 'Transfer')."
    )
    account_id: Optional[str] = Field(
        None,
        description="Identifier of the source/destination account (last 4 digits).",
    )
    account_type: Optional[AccountType] = Field(
        None,
        description="Type of account. Must be one of: corriente, credito, debito, prepago.",
    )
    raw_data: Optional[dict] = Field(
        {}, description="Additional raw data from the scraper."
    )

    @field_validator("account_id", mode="before")
    @classmethod
    def _format_account_id(cls, v: Optional[str]) -> Optional[str]:
        """Ensures the account_id is only the last 4 digits."""
        if v is None:
            return None
        # Remove all non-digit characters
        digits = re.sub(r"\D", "", str(v))
        if len(digits) >= 4:
            return digits[-4:]
        # Return whatever is left if less than 4 digits, or the original if no digits found
        return digits if digits else v

    class Config:
        json_schema_extra = {
            "example": {
                "date": "2023-10-26T10:00:00",
                "description": "Compra en Supermercado",
                "amount": "-15000.00",
                "currency": "CLP",
                "transaction_type": "Cargo",
                "account_id": "5678",
                "account_type": "credito",
                "raw_data": {
                    "original_desc": "COMPRA SUPERMERCADO LIDER",
                    "full_account_id": "1234-5678",
                },
            }
        }


class StockModel(BaseModel):
    """
    Pydantic model to represent a single stock position.
    """
    symbol: str = Field(...,
                        description="Ticker symbol of the asset (e.g., AAPL, VO, TSLA).")
    quantity: Decimal = Field(...,
                              description="Number of shares held (can be fractional).")
    average_cost: Decimal = Field(...,
                                  description="Average acquisition cost per share.")
    currency: str = Field(...,
                          description="Currency of the asset (e.g., USD).")

    raw_data: Optional[dict] = Field(
        {}, description="Additional raw data from the scraper."
    )

    class Config:
        json_schema_extra = {
            "example": {
                "symbol": "AAPL",
                "quantity": "5.4321",
                "average_cost": "150.50",
                "currency": "USD",

                "raw_data": {
                    "original_name": "APPLE INC",
                    "sector": "Technology"
                }
            }
        }


class PortfolioModel(BaseModel):
    """
    Pydantic model to represent the entire investment portfolio snapshot.
    """
    wallet_balance_usd: Decimal = Field(...,
                                        description="Available buying power (cash) in USD.")

    stocks: List[StockModel] = Field(
        default=[], description="List of stocks/assets currently held.")

    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="Time when this snapshot was taken."
    )

    class Config:
        json_schema_extra = {
            "example": {
                "wallet_balance_usd": "105.20",
                "timestamp": "2023-10-26T10:00:00",
                "stocks": [
                    {
                        "symbol": "AAPL",
                        "quantity": "10",
                        "average_cost": "150.00",
                        "currency": "USD"
                    }
                ]
            }
        }
