from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime,
    ForeignKey, Text, Enum as SAEnum
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.database import Base


class UserRole(str, enum.Enum):
    OWNER = "owner"                # a business using the product
    SUPER_ADMIN = "super_admin"    # platform operator — you


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(150), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    business_name = Column(String(150))
    role = Column(SAEnum(UserRole), nullable=False, default=UserRole.OWNER)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    products = relationship("Product", back_populates="owner")
    sales = relationship("Sale", back_populates="owner")
    documents = relationship("DocumentRecord", back_populates="owner")
    reset_tokens = relationship("PasswordResetToken", back_populates="user")
    licenses = relationship("License", back_populates="user")
    login_events = relationship("LoginEvent", back_populates="user")


class LoginEvent(Base):
    """
    One row per successful login. This is what account-sharing detection
    is built on: if the same account logs in from an unusual number of
    distinct IPs/devices in a short window, that's a signal the login
    (not the product) is being shared between businesses.
    """
    __tablename__ = "login_events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    ip_address = Column(String(64))
    user_agent = Column(String(500))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    user = relationship("User", back_populates="login_events")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token_hash = Column(String(255), nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="reset_tokens")


class LicenseStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class License(Base):
    __tablename__ = "licenses"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    license_key = Column(String(40), unique=True, index=True, nullable=False)
    status = Column(SAEnum(LicenseStatus), nullable=False, default=LicenseStatus.ACTIVE)
    plan = Column(String(50), default="monthly")     # "trial", "monthly", etc.
    amount_paid = Column(Float, nullable=True)
    mpesa_receipt = Column(String(100), nullable=True)  # M-Pesa transaction code, once payments are wired in
    issued_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)

    user = relationship("User", back_populates="licenses")


class TaxCategory(str, enum.Enum):
    STANDARD = "STANDARD"       # 16% general VAT rate (KRA VAT Act 2013, current as of 2026)
    REDUCED = "REDUCED"         # e.g. certain petroleum products — rate set per product via tax_rate
    ZERO_RATED = "ZERO_RATED"   # 0% — exports & Second Schedule items (basic foodstuffs, medical, ag inputs)
    EXEMPT = "EXEMPT"           # no VAT charged, no input VAT recovery


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    products = relationship("Product", back_populates="category")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    sku = Column(String(100), index=True)
    description = Column(Text)
    unit = Column(String(50), default="pcs")           # pcs, kg, litres, etc
    cost_price = Column(Float, nullable=False)
    selling_price = Column(Float, nullable=False)          # tax-EXCLUSIVE price
    tax_category = Column(SAEnum(TaxCategory), nullable=False, default=TaxCategory.STANDARD)
    tax_rate = Column(Float, nullable=False, default=16.0)  # percent; only applied when category is STANDARD/REDUCED
    current_stock = Column(Float, default=0)
    reorder_point = Column(Float, default=0)           # AI will suggest this
    reorder_quantity = Column(Float, default=0)        # how much to reorder
    is_active = Column(Boolean, default=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    owner = relationship("User", back_populates="products")
    category = relationship("Category", back_populates="products")
    sale_items = relationship("SaleItem", back_populates="product")
    stock_movements = relationship("StockMovement", back_populates="product")


class MovementType(str, enum.Enum):
    IN = "IN"           # stock received/purchased
    OUT = "OUT"         # sold or removed
    ADJUSTMENT = "ADJUSTMENT"   # manual correction
    LOSS = "LOSS"       # spoilage, damage


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    movement_type = Column(SAEnum(MovementType), nullable=False)
    quantity = Column(Float, nullable=False)
    balance_after = Column(Float, nullable=False)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    product = relationship("Product", back_populates="stock_movements")


class Sale(Base):
    __tablename__ = "sales"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    subtotal_amount = Column(Float, nullable=False, default=0)  # sum of item subtotals, tax-EXCLUSIVE (net sales)
    tax_amount = Column(Float, nullable=False, default=0)       # total VAT/output-tax collected on this sale
    total_amount = Column(Float, nullable=False)                # subtotal_amount + tax_amount (what the customer pays)
    payment_method = Column(String(50), default="cash")  # cash, mpesa, credit
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    owner = relationship("User", back_populates="sales")
    items = relationship("SaleItem", back_populates="sale")


class SaleItem(Base):
    __tablename__ = "sale_items"

    id = Column(Integer, primary_key=True, index=True)
    sale_id = Column(Integer, ForeignKey("sales.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Float, nullable=False)
    unit_price = Column(Float, nullable=False)          # tax-EXCLUSIVE unit price at time of sale
    subtotal = Column(Float, nullable=False)            # quantity * unit_price, tax-EXCLUSIVE
    tax_category = Column(SAEnum(TaxCategory), nullable=False, default=TaxCategory.STANDARD)
    tax_rate = Column(Float, nullable=False, default=0)  # % rate actually applied, frozen at sale time for audit
    tax_amount = Column(Float, nullable=False, default=0)  # subtotal * tax_rate / 100

    sale = relationship("Sale", back_populates="items")
    product = relationship("Product", back_populates="sale_items")


class DocumentType(str, enum.Enum):
    RECEIPT = "RECEIPT"
    INVOICE = "INVOICE"
    DELIVERY_NOTE = "DELIVERY_NOTE"


class DocumentRecord(Base):
    __tablename__ = "document_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    doc_type = Column(SAEnum(DocumentType), nullable=False)
    reference_number = Column(String(100))
    party_name = Column(String(200))            # supplier / customer name
    amount = Column(Float)
    doc_date = Column(DateTime(timezone=True))
    notes = Column(Text)
    file_path = Column(String(1000))            # Vercel Blob URL in production, local path in dev
    original_filename = Column(String(255))
    content_type = Column(String(100))
    file_size = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    owner = relationship("User", back_populates="documents")
