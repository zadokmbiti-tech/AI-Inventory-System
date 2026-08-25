from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime
from app.models.models import MovementType, DocumentType, TaxCategory, LicenseStatus


# ─── Auth ────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    business_name: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    business_name: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


# ─── Category ─────────────────────────────────────────────────────────────────

class CategoryCreate(BaseModel):
    name: str


class CategoryOut(BaseModel):
    id: int
    name: str
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Product ─────────────────────────────────────────────────────────────────

class ProductCreate(BaseModel):
    name: str
    sku: Optional[str] = None
    description: Optional[str] = None
    unit: str = "pcs"
    cost_price: float
    selling_price: float
    current_stock: float = 0
    reorder_point: float = 0
    reorder_quantity: float = 0
    category_id: Optional[int] = None
    tax_category: TaxCategory = TaxCategory.STANDARD
    tax_rate: float = 16.0  # % — default is Kenya's standard VAT rate; override for REDUCED items etc.


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    cost_price: Optional[float] = None
    selling_price: Optional[float] = None
    reorder_point: Optional[float] = None
    reorder_quantity: Optional[float] = None
    category_id: Optional[int] = None
    is_active: Optional[bool] = None
    tax_category: Optional[TaxCategory] = None
    tax_rate: Optional[float] = None


class ProductOut(BaseModel):
    id: int
    name: str
    sku: Optional[str]
    unit: str
    cost_price: float
    selling_price: float
    current_stock: float
    reorder_point: float
    reorder_quantity: float
    is_active: bool
    category_id: Optional[int]
    tax_category: TaxCategory
    tax_rate: float
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Stock Movement ───────────────────────────────────────────────────────────

class StockMovementCreate(BaseModel):
    product_id: int
    movement_type: MovementType
    quantity: float
    notes: Optional[str] = None


class StockMovementOut(BaseModel):
    id: int
    product_id: int
    movement_type: MovementType
    quantity: float
    balance_after: float
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Sales ────────────────────────────────────────────────────────────────────

class SaleItemCreate(BaseModel):
    product_id: int
    quantity: float
    unit_price: float


class SaleCreate(BaseModel):
    items: List[SaleItemCreate]
    payment_method: str = "cash"
    notes: Optional[str] = None


class SaleItemOut(BaseModel):
    id: int
    product_id: int
    quantity: float
    unit_price: float
    subtotal: float
    tax_category: TaxCategory
    tax_rate: float
    tax_amount: float

    class Config:
        from_attributes = True


class SaleOut(BaseModel):
    id: int
    subtotal_amount: float
    tax_amount: float
    total_amount: float
    payment_method: str
    notes: Optional[str]
    items: List[SaleItemOut]
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Tax / VAT Reporting ──────────────────────────────────────────────────────

class VatSummary(BaseModel):
    period_days: int
    net_sales: float           # total sales excluding VAT
    output_vat_collected: float  # VAT charged to customers — what you owe KRA before input VAT credits
    gross_sales: float          # net_sales + output_vat_collected
    by_tax_category: List[dict]  # breakdown: category, net_sales, vat_amount, count
    disclaimer: str


# ─── Document Records (Receipts / Invoices / Delivery Notes) ─────────────────

class DocumentRecordOut(BaseModel):
    id: int
    doc_type: DocumentType
    reference_number: Optional[str]
    party_name: Optional[str]
    amount: Optional[float]
    doc_date: Optional[datetime]
    notes: Optional[str]
    original_filename: Optional[str]
    content_type: Optional[str]
    file_size: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


# ─── AI Insights ─────────────────────────────────────────────────────────────

class ForecastPoint(BaseModel):
    date: str
    predicted_demand: float
    lower_bound: float
    upper_bound: float


class ProductForecast(BaseModel):
    product_id: int
    product_name: str
    forecast: List[ForecastPoint]
    suggested_reorder_point: float
    suggested_reorder_quantity: float


class LowStockAlert(BaseModel):
    product_id: int
    product_name: str
    current_stock: float
    reorder_point: float
    days_until_stockout: Optional[float]
    urgency: str   # "critical", "warning", "ok"


class AnalyticsSummary(BaseModel):
    total_revenue: float
    total_vat_collected: float
    total_cost: float
    gross_profit: float
    profit_margin: float
    total_sales: int
    top_products: List[dict]
    revenue_by_day: List[dict]


# ─── Licensing ────────────────────────────────────────────────────────────────

class LicenseOut(BaseModel):
    license_key: str
    status: LicenseStatus
    plan: str
    issued_at: datetime
    expires_at: datetime
    days_remaining: int

    class Config:
        from_attributes = True


class LicenseRenewRequest(BaseModel):
    plan: str = "monthly"
    amount_paid: Optional[float] = None
    mpesa_receipt: Optional[str] = None
