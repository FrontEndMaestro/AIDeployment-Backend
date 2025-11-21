from fastapi import APIRouter, Depends
from ..controllers.auth_controller import (
    register_user_handler,
    login_user_handler,
    get_current_user_info_handler
)
from ..models.user import UserCreate, UserLogin, Token
from ..utils.auth import get_current_active_user

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/register", response_model=dict)
async def register_user(user_data: UserCreate):
    """
    Register a new user
    
    - **username**: Unique username (3-50 characters)
    - **email**: Valid email address
    - **password**: Password (minimum 6 characters)
    - **full_name**: Optional full name
    """
    return await register_user_handler(user_data)


@router.post("/login", response_model=Token)
async def login_user(credentials: UserLogin):
    """
    Login user and get JWT token
    
    - **username**: Username
    - **password**: Password
    
    Returns JWT access token valid for 24 hours
    """
    return await login_user_handler(credentials)


@router.get("/me")
async def get_current_user_info(current_user: dict = Depends(get_current_active_user)):
    """
    Get current user information
    
    Requires: Bearer token in Authorization header
    """
    return await get_current_user_info_handler(current_user)


@router.get("/verify")
async def verify_token(current_user: dict = Depends(get_current_active_user)):
    """
    Verify if JWT token is valid
    
    Returns user info if token is valid
    """
    return {
        "success": True,
        "message": "Token is valid",
        "user_id": str(current_user["_id"]),
        "username": current_user["username"]
    }