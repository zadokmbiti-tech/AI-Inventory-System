from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app.models.models import Product, Category, User
from app.schemas.schemas import ProductCreate, ProductUpdate, ProductOut, CategoryCreate, CategoryOut
from app.services.auth import get_current_user

router = APIRouter(prefix="/api", tags=["Products"])


# ─── Categories ──────────────────────────────────────────────────────────────

@router.post("/categories", response_model=CategoryOut, status_code=201)
def create_category(payload: CategoryCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cat = Category(name=payload.name, user_id=user.id)
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


@router.get("/categories", response_model=List[CategoryOut])
def list_categories(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(Category).filter(Category.user_id == user.id).all()


# ─── Products ─────────────────────────────────────────────────────────────────

@router.post("/products", response_model=ProductOut, status_code=201)
def create_product(payload: ProductCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    product = Product(**payload.model_dump(), user_id=user.id)
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.get("/products", response_model=List[ProductOut])
def list_products(
    category_id: Optional[int] = None,
    low_stock_only: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    q = db.query(Product).filter(Product.user_id == user.id, Product.is_active == True)
    if category_id:
        q = q.filter(Product.category_id == category_id)
    if low_stock_only:
        q = q.filter(Product.current_stock <= Product.reorder_point)
    return q.order_by(Product.name).all()


@router.get("/products/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    product = db.query(Product).filter(Product.id == product_id, Product.user_id == user.id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.patch("/products/{product_id}", response_model=ProductOut)
def update_product(product_id: int, payload: ProductUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    product = db.query(Product).filter(Product.id == product_id, Product.user_id == user.id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    db.commit()
    db.refresh(product)
    return product


@router.delete("/products/{product_id}", status_code=204)
def delete_product(product_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    product = db.query(Product).filter(Product.id == product_id, Product.user_id == user.id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    product.is_active = False   # soft delete
    db.commit()
